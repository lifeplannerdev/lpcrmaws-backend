# accounts/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import generics, filters, status
from rest_framework.pagination import PageNumberPagination
from .permissions import IsManagement, IsSuperAdmin
from leads.models import Lead
from trainers.models import Student
from .models import User, ActivityLog
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from .serializers import (
    StaffListSerializer,
    StaffDetailSerializer,
    StaffCreateSerializer,
    StaffUpdateSerializer,
    LoginSerializer,
    ActivityLogSerializer
)
from .filters import CompanyFilterBackend

# Pagination 
class StaffPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


# Dashboard Stats View
class DashboardStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "ADMIN":
            raise PermissionDenied("You are not allowed to view dashboard stats")

        data = {
            "total_leads": Lead.objects.count(),
            "active_staff": User.objects.filter(is_active=True).count(),
            "total_students": Student.objects.count(),
        }
        return Response(data)


# Recent Activities View
class ActivityLogListView(generics.ListAPIView):
    serializer_class   = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['action', 'entity_type', 'user']
    search_fields      = ['entity_name', 'description']
    ordering_fields    = ['created_at']
    ordering           = ['-created_at']
 
    def get_queryset(self):
        qs = ActivityLog.objects.select_related('user').all()

        user = self.request.user
        if user.role not in ('ADMIN', 'BUSINESS_HEAD', 'CEO'):
            qs = qs.filter(
                Q(user=user) |
                Q(user__isnull=True, entity_type='Staff', entity_id=user.pk)
            )
        else:
            qs = qs.exclude(
                user__role__in=['ADMIN', 'CEO']
            ).exclude(
                action__in=['USER_LOGIN', 'USER_LOGOUT'] 
            )

        # Date range filters
        date_from = self.request.query_params.get('date_from')
        date_to   = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
 
        return qs


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "company": user.company,
            "permissions": user.permissions,
            "phone": user.phone if hasattr(user, 'phone') else None,
            "location": user.location if hasattr(user, 'location') else None,
        })


#Login View 
class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        
        # Return refresh token in response body instead of cookie
        return Response({
            "message": "Login successful",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "company": user.company,
                "permissions": user.permissions
            }
        }, status=status.HTTP_200_OK)


# Token Refresh View - Updated
class RefreshTokenAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token not found"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            return Response({
                "access": access_token,
                "refresh": str(refresh) 
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED
            )


#Logout View
class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        response = Response(
            {"message": "Logged out successfully"},
            status=status.HTTP_200_OK
        )
        response.delete_cookie(
            key="refresh_token",
            path="/",
            samesite="None"
        )
        
        return response


# Staff List View

class StaffListView(generics.ListAPIView):
    serializer_class = StaffListSerializer
    permission_classes = [IsManagement]
    pagination_class = StaffPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, CompanyFilterBackend]
    search_fields = [
        'username', 'first_name', 'last_name',
        'email', 'role', 'phone', 'location', 'team'
    ]
    ordering_fields = ['date_joined', 'username']
    ordering = ['-date_joined']

    def get_queryset(self):
        queryset = User.objects.all()

        status_param = self.request.query_params.get('status')
        if status_param == 'inactive':
            queryset = queryset.filter(is_active=False)
        elif status_param == 'active':
            queryset = queryset.filter(is_active=True)
        # default or 'all' might not filter by is_active at all, but for now we default to active if not specified
        elif not status_param:
            queryset = queryset.filter(is_active=True)

        team = self.request.query_params.get('team')
        if team and team != "all":
            queryset = queryset.filter(team__iexact=team)

        return queryset

# Staff Detail View 
class StaffDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = StaffDetailSerializer
    permission_classes = [IsManagement]


# Staff Create View 
class StaffCreateView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = StaffCreateSerializer
    permission_classes = [IsManagement]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        
        # If user is a trainer and a branch_id was provided, update the trainer profile
        branch_id = request.data.get('branch_id')
        role = request.data.get('role')
        if role == 'TRAINER' and branch_id:
            try:
                # The user was created in super().create(), let's fetch it by email or username
                # But we don't have the instance easily from response. So let's get it by username
                username = request.data.get('username')
                user = User.objects.get(username=username)
                
                # Signal has already created trainer_profile
                if hasattr(user, 'trainer_profile'):
                    user.trainer_profile.branch_id = branch_id
                    user.trainer_profile.save()
            except Exception as e:
                print(f"Error setting branch for trainer: {e}")

        response.data = {"message": "Staff created successfully"}
        return response


# Staff Update View
class StaffUpdateView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = StaffUpdateSerializer
    permission_classes = [IsManagement]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # Handle branch update for trainers
        branch_id = request.data.get('branch_id')
        if instance.role == 'TRAINER' and branch_id:
            try:
                if hasattr(instance, 'trainer_profile'):
                    instance.trainer_profile.branch_id = branch_id
                    instance.trainer_profile.save()
            except Exception as e:
                print(f"Error setting branch for trainer: {e}")

        return Response(
            {"message": "Staff updated successfully"},
            status=status.HTTP_200_OK
        )





# Staff Asset Timeline View
class StaffAssetTimelineView(generics.ListAPIView):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsManagement]
    pagination_class = StaffPagination

    def get_queryset(self):
        staff_id = self.kwargs.get('pk')
        # We find activity logs related to assets where metadata contains staff_id=staff_id
        # In Django, JSONField can be queried directly: metadata__staff_id=staff_id
        return ActivityLog.objects.filter(
            entity_type='Asset',
            metadata__staff_id=int(staff_id)
        ).order_by('-created_at')


class EmployeeListAPI(APIView):
    def get(self, request):
        employees = User.objects.filter(
            role__in=[
                "ADM_MANAGER",
                "ADM_COUNSELLOR",  
                "ADM_EXEC",
                "FOE",
                "CM"
            ],
            is_active=True
        )

        data = []
        for emp in employees:
            data.append({
                "id": emp.id,
                "name": emp.get_full_name() or emp.username,  
                "role": emp.get_role_display()
            })

        return Response(data)