from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from .models import Credential, CredentialHistory, CredentialUpdateRequest, CredentialCategory
from accounts.permissions import has_dynamic_permission
from .serializers import (
    CredentialSerializer, CredentialDetailSerializer, 
    CredentialHistorySerializer, CredentialUpdateRequestSerializer,
    CredentialCategorySerializer
)

class CredentialCategoryPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if view.action in ['list', 'retrieve']:
            return True
        return has_dynamic_permission(request.user, 'credentials:manage')

class CredentialCategoryViewSet(viewsets.ModelViewSet):
    queryset = CredentialCategory.objects.all().order_by('name')
    serializer_class = CredentialCategorySerializer
    permission_classes = [permissions.IsAuthenticated, CredentialCategoryPermission]

class CredentialPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        # All authenticated users can list/retrieve; get_queryset filters what they see
        if view.action in ['list', 'retrieve', 'history', 'requests', 'propose_update']:
            return True
        if view.action in ['create', 'update', 'partial_update', 'destroy', 'approve_request', 'reject_request']:
            return has_dynamic_permission(request.user, 'credentials:manage')
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        # Admins or users with credentials:manage can do anything
        if has_dynamic_permission(request.user, 'credentials:manage'):
            return True
            
        # Object-level checks
        is_creator = obj.created_by == request.user
        is_shared_user = obj.shared_users.filter(id=request.user.id).exists()
        is_shared_role = obj.shared_roles.filter(id__in=request.user.db_roles.all()).exists()
        
        has_read_access = is_creator or is_shared_user or is_shared_role

        if view.action in ['retrieve', 'history']:
            return has_read_access
            
        if view.action == 'propose_update':
            return has_read_access and not is_creator # Creators should just update directly
            
        if view.action in ['update', 'partial_update', 'destroy']:
            return is_creator
            
        return False

class CredentialViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, CredentialPermission]

    def get_queryset(self):
        user = self.request.user
        
        if has_dynamic_permission(user, 'credentials:manage') or user.is_superuser:
            return Credential.objects.all().order_by('-created_at')
            
        # Filter for only credentials user has access to
        q = Q(created_by=user) | Q(shared_users=user)
        if user.db_roles.exists():
            q |= Q(shared_roles__in=user.db_roles.all())
            
        return Credential.objects.filter(q).distinct().order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ['retrieve', 'create', 'update', 'partial_update']:
            return CredentialDetailSerializer
        return CredentialSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        # If password changes, save history
        instance = self.get_object()
        old_password = instance.encrypted_password
        
        updated_instance = serializer.save()
        
        if old_password != updated_instance.encrypted_password:
            CredentialHistory.objects.create(
                credential=updated_instance,
                encrypted_password=old_password,
                changed_by=self.request.user
            )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        credential = self.get_object()
        history = credential.history.all().order_by('-changed_at')
        serializer = CredentialHistorySerializer(history, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def propose_update(self, request, pk=None):
        credential = self.get_object()
        proposed_password = request.data.get('proposed_password')
        if not proposed_password:
            return Response({"error": "proposed_password is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if user already has a pending request
        if CredentialUpdateRequest.objects.filter(credential=credential, requested_by=request.user, status='PENDING').exists():
            return Response({"error": "You already have a pending request for this credential"}, status=status.HTTP_400_BAD_REQUEST)

        req = CredentialUpdateRequest.objects.create(
            credential=credential,
            requested_by=request.user
        )
        req.set_proposed_password(proposed_password)
        req.save()
        
        serializer = CredentialUpdateRequestSerializer(req)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class CredentialUpdateRequestViewSet(viewsets.ModelViewSet):
    serializer_class = CredentialUpdateRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if has_dynamic_permission(user, 'credentials:manage') or user.is_superuser:
            return CredentialUpdateRequest.objects.all().order_by('-created_at')
            
        return CredentialUpdateRequest.objects.filter(Q(requested_by=user) | Q(credential__created_by=user)).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != 'PENDING':
            return Response({"error": "Request is not pending"}, status=status.HTTP_400_BAD_REQUEST)
            
        credential = req.credential
        if credential.created_by != request.user and not has_dynamic_permission(request.user, 'credentials:manage') and not request.user.is_superuser:
            return Response({"error": "Not authorized to approve this request"}, status=status.HTTP_403_FORBIDDEN)

        # 1. Save old password to history
        CredentialHistory.objects.create(
            credential=credential,
            encrypted_password=credential.encrypted_password,
            changed_by=request.user
        )
        
        # 2. Update credential password
        credential.encrypted_password = req.proposed_encrypted_password
        credential.save()
        
        # 3. Update request status
        req.status = 'APPROVED'
        req.reviewed_by = request.user
        req.reviewed_at = timezone.now()
        req.save()
        
        return Response({"status": "approved"})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != 'PENDING':
            return Response({"error": "Request is not pending"}, status=status.HTTP_400_BAD_REQUEST)
            
        credential = req.credential
        if credential.created_by != request.user and not has_dynamic_permission(request.user, 'credentials:manage') and not request.user.is_superuser:
            return Response({"error": "Not authorized to reject this request"}, status=status.HTTP_403_FORBIDDEN)

        req.status = 'REJECTED'
        req.reviewed_by = request.user
        req.reviewed_at = timezone.now()
        req.save()
        
        return Response({"status": "rejected"})
