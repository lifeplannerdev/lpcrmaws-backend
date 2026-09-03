from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.utils import timezone
from .models import (
    Grade, Campus, AcademicPackage, AttendancePolicy,
    AcademicBatch, Student, StudentBatchHistory,
    GradeExamRecord, AttendanceSession, AttendanceRecord,
    PromotionEvent, DemotionEvent
)
from .serializers import (
    GradeSerializer, CampusSerializer, AcademicPackageSerializer, AttendancePolicySerializer,
    AcademicBatchSerializer, StudentSerializer, StudentBatchHistorySerializer,
    GradeExamRecordSerializer, AttendanceSessionSerializer, AttendanceRecordSerializer,
    PromotionEventSerializer, DemotionEventSerializer
)
from accounts.permissions import has_dynamic_permission

class FlagBasePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
            
        # Admin has full access
        if has_dynamic_permission(request.user, 'flag:admin'):
            return True
            
        # Any of these can read
        if request.method in permissions.SAFE_METHODS:
            return (
                has_dynamic_permission(request.user, 'flag:view') or 
                has_dynamic_permission(request.user, 'flag:trainer') or 
                has_dynamic_permission(request.user, 'flag:fees')
            )
            
        # Trainer can write to most things, but Student creation is blocked in StudentViewSet
        if has_dynamic_permission(request.user, 'flag:trainer'):
            return True
            
        return False

class GradeViewSet(viewsets.ModelViewSet):
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer
    permission_classes = [FlagBasePermission]

class CampusViewSet(viewsets.ModelViewSet):
    queryset = Campus.objects.all()
    serializer_class = CampusSerializer
    permission_classes = [FlagBasePermission]

class AcademicPackageViewSet(viewsets.ModelViewSet):
    queryset = AcademicPackage.objects.all()
    serializer_class = AcademicPackageSerializer
    permission_classes = [FlagBasePermission]

class AttendancePolicyViewSet(viewsets.ModelViewSet):
    queryset = AttendancePolicy.objects.all()
    serializer_class = AttendancePolicySerializer
    permission_classes = [FlagBasePermission]

class AcademicBatchViewSet(viewsets.ModelViewSet):
    queryset = AcademicBatch.objects.all()
    serializer_class = AcademicBatchSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'campus', 'starting_grade', 'current_grade']

    def get_queryset(self):
        qs = super().get_queryset()
        # If trainer, they might only see their batches, or maybe all depending on requirements.
        # Requirements: "Trainer... can view all but view only their students fees".
        # So they can view all batches.
        return qs

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['batch', 'status', 'campus', 'academic_package']

    def get_permissions(self):
        return super().get_permissions()
        
    def create(self, request, *args, **kwargs):
        if not has_dynamic_permission(request.user, 'flag:admin') and has_dynamic_permission(request.user, 'flag:trainer'):
            return Response({'detail': 'Trainers cannot create new students.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        student = self.get_object()
        # logic for individual promotion (usually done batch-wise though)
        return Response({'status': 'Not implemented here, use batch promotion'}, status=400)

class StudentBatchHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StudentBatchHistory.objects.all()
    serializer_class = StudentBatchHistorySerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['student']

class GradeExamRecordViewSet(viewsets.ModelViewSet):
    queryset = GradeExamRecord.objects.all()
    serializer_class = GradeExamRecordSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['student', 'batch', 'grade']

class AttendanceSessionViewSet(viewsets.ModelViewSet):
    queryset = AttendanceSession.objects.all()
    serializer_class = AttendanceSessionSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['batch', 'date']

class AttendanceRecordViewSet(viewsets.ModelViewSet):
    queryset = AttendanceRecord.objects.all()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['session', 'student', 'session__batch']

class PromotionEventViewSet(viewsets.ModelViewSet):
    queryset = PromotionEvent.objects.all()
    serializer_class = PromotionEventSerializer
    permission_classes = [FlagBasePermission]

class DemotionEventViewSet(viewsets.ModelViewSet):
    queryset = DemotionEvent.objects.all()
    serializer_class = DemotionEventSerializer
    permission_classes = [FlagBasePermission]

class FlagTrainerView(APIView):
    permission_classes = [FlagBasePermission]

    def get(self, request):
        from django.db.models import Q
        from accounts.models import User

        # Find users marked as trainer via db_roles, trainer_profile, or assigned to batches/students
        trainers_qs = User.objects.filter(
            Q(db_roles__name__iexact='TRAINER') |
            Q(trainer_profile__isnull=False) |
            Q(managed_batches__isnull=False) |
            Q(assigned_students__isnull=False),
            is_active=True
        ).distinct()

        user_ids = set(trainers_qs.values_list('id', flat=True))

        # Also include any active users that have 'flag:trainer' in their permissions list
        for u in User.objects.filter(is_active=True).only('id', 'permissions'):
            perms = u.permissions if isinstance(u.permissions, list) else []
            if 'flag:trainer' in perms:
                user_ids.add(u.id)

        # Fallback to active users if no users have been assigned the trainer role yet
        if not user_ids:
            trainers = User.objects.filter(is_active=True).order_by('first_name', 'username')
        else:
            trainers = User.objects.filter(id__in=user_ids).order_by('first_name', 'username')

        search = request.GET.get('search')
        if search:
            trainers = trainers.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(username__icontains=search)
            )

        data = [
            {
                'id': t.id,
                'name': t.get_full_name().strip() or t.username,
                'username': t.username,
                'email': t.email or ''
            }
            for t in trainers
        ]
        return Response(data)
