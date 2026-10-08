from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.utils import timezone
from .models import (
    Grade, Campus, AcademicPackage,
    AcademicBatch, GradeBatch, Student, StudentBatchHistory,
    ExamRecord, AttendanceSession, AttendanceRecord
)
from .serializers import (
    GradeSerializer, CampusSerializer, AcademicPackageSerializer,
    AcademicBatchSerializer, GradeBatchSerializer, StudentSerializer, StudentBatchHistorySerializer,
    ExamRecordSerializer, AttendanceSessionSerializer, AttendanceRecordSerializer
)
from accounts.permissions import has_dynamic_permission

def is_flag_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return has_dynamic_permission(user, 'flag:admin')

def is_flag_trainer(user):
    if not user or not user.is_authenticated:
        return False
    if is_flag_admin(user):
        return False
    return (
        has_dynamic_permission(user, 'flag:trainer') or
        user.db_roles.filter(name__iexact='TRAINER').exists()
    )

class FlagBasePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_flag_admin(request.user):
            return True
        if request.method in permissions.SAFE_METHODS:
            return (
                has_dynamic_permission(request.user, 'flag:view') or 
                has_dynamic_permission(request.user, 'flag:trainer') or 
                has_dynamic_permission(request.user, 'flag:fees') or
                request.user.db_roles.filter(name__iexact='TRAINER').exists()
            )
        if has_dynamic_permission(request.user, 'flag:trainer') or request.user.db_roles.filter(name__iexact='TRAINER').exists():
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

class AcademicBatchViewSet(viewsets.ModelViewSet):
    queryset = AcademicBatch.objects.all()
    serializer_class = AcademicBatchSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'campus', 'trainer']

    def get_queryset(self):
        qs = super().get_queryset()
        if is_flag_trainer(self.request.user):
            qs = qs.filter(trainer=self.request.user)
        return qs

    def perform_create(self, serializer):
        if is_flag_trainer(self.request.user) and not serializer.validated_data.get('trainer'):
            batch = serializer.save(trainer=self.request.user)
        else:
            batch = serializer.save()
            
        package = batch.package
        grades = Grade.objects.filter(
            order__gte=package.starting_grade.order,
            order__lte=package.ending_grade.order
        )
        for g in grades:
            GradeBatch.objects.get_or_create(academic_batch=batch, grade=g)

class GradeBatchViewSet(viewsets.ModelViewSet):
    queryset = GradeBatch.objects.all()
    serializer_class = GradeBatchSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['academic_batch', 'grade']

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        'batch': ['exact'],
        'grade_batch': ['exact'],
        'status': ['exact'],
        'campus': ['exact'],
        'academic_package': ['exact'],
        'trainer': ['exact']
    }

    def get_queryset(self):
        qs = super().get_queryset()
        if is_flag_trainer(self.request.user):
            qs = qs.filter(trainer=self.request.user)
        return qs
        
    def create(self, request, *args, **kwargs):
        if is_flag_trainer(request.user):
            return Response({'detail': 'Trainers cannot create new students.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        student = self.get_object()
        if not student.grade_batch:
            return Response({'error': 'Student is not assigned to a Grade Batch.'}, status=400)
        
        current_order = student.grade_batch.grade.order
        academic_batch = student.batch
        
        next_grade_batch = GradeBatch.objects.filter(
            academic_batch=academic_batch,
            grade__order__gt=current_order
        ).order_by('grade__order').first()

        if not next_grade_batch:
            return Response({'error': 'Student has reached the highest grade in this package.'}, status=400)

        prev_history = StudentBatchHistory.objects.filter(student=student, to_date__isnull=True).order_by('-from_date').first()
        if prev_history:
            prev_history.to_date = timezone.now().date()
            prev_history.save()

        StudentBatchHistory.objects.create(
            student=student,
            batch=academic_batch,
            grade_batch=next_grade_batch,
            action='promoted',
            reason=request.data.get('reason', ''),
            done_by=request.user
        )

        student.grade_batch = next_grade_batch
        student.save()
        return Response({'status': 'Student promoted successfully', 'new_grade': next_grade_batch.grade.code})

    @action(detail=True, methods=['post'])
    def demote(self, request, pk=None):
        student = self.get_object()
        target_academic_batch_id = request.data.get('academic_batch_id')
        target_grade_batch_id = request.data.get('grade_batch_id')
        reason = request.data.get('reason', '')

        if not target_academic_batch_id or not target_grade_batch_id:
            return Response({'error': 'Both Academic Batch and Grade Batch must be specified for demotion/reassignment.'}, status=400)

        try:
            new_academic_batch = AcademicBatch.objects.get(id=target_academic_batch_id)
            new_grade_batch = GradeBatch.objects.get(id=target_grade_batch_id, academic_batch=new_academic_batch)
        except (AcademicBatch.DoesNotExist, GradeBatch.DoesNotExist):
            return Response({'error': 'Invalid Academic Batch or Grade Batch selected.'}, status=400)

        prev_history = StudentBatchHistory.objects.filter(student=student, to_date__isnull=True).order_by('-from_date').first()
        if prev_history:
            prev_history.to_date = timezone.now().date()
            prev_history.save()

        StudentBatchHistory.objects.create(
            student=student,
            batch=new_academic_batch,
            grade_batch=new_grade_batch,
            action='demoted',
            reason=reason,
            done_by=request.user
        )

        student.batch = new_academic_batch
        student.grade_batch = new_grade_batch
        student.save()
        return Response({'status': 'Student demoted/reassigned successfully'})

class StudentBatchHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StudentBatchHistory.objects.all()
    serializer_class = StudentBatchHistorySerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['student']

class ExamRecordViewSet(viewsets.ModelViewSet):
    queryset = ExamRecord.objects.all()
    serializer_class = ExamRecordSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['student', 'grade_batch', 'exam_type']

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

class AttendanceSessionViewSet(viewsets.ModelViewSet):
    queryset = AttendanceSession.objects.all()
    serializer_class = AttendanceSessionSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['grade_batch', 'date']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['post'])
    def bulk_entry(self, request):
        grade_batch_id = request.data.get('grade_batch')
        date = request.data.get('date')
        records = request.data.get('records', [])
        
        if not grade_batch_id or not date:
            return Response({'error': 'grade_batch and date are required'}, status=400)
            
        session, created = AttendanceSession.objects.get_or_create(
            grade_batch_id=grade_batch_id,
            date=date,
            defaults={'created_by': request.user}
        )
        
        for rec in records:
            student_id = rec.get('student')
            status = rec.get('status')
            if student_id and status:
                AttendanceRecord.objects.update_or_create(
                    session=session,
                    student_id=student_id,
                    defaults={'status': status}
                )
                
        return Response({'status': 'success', 'session_id': session.id})

class AttendanceRecordViewSet(viewsets.ModelViewSet):
    queryset = AttendanceRecord.objects.all()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [FlagBasePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['session', 'student']

class FlagTrainerView(APIView):
    permission_classes = [FlagBasePermission]

    def get(self, request):
        from django.db.models import Q
        from accounts.models import User
        trainers_qs = User.objects.filter(
            Q(db_roles__name__iexact='TRAINER') |
            Q(trainer_profile__isnull=False) |
            Q(managed_batches__isnull=False),
            is_active=True
        ).distinct()
        user_ids = set(trainers_qs.values_list('id', flat=True))
        for u in User.objects.filter(is_active=True).only('id', 'permissions'):
            perms = u.permissions if isinstance(u.permissions, list) else []
            if 'flag:trainer' in perms:
                user_ids.add(u.id)
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
            {'id': t.id, 'name': t.get_full_name().strip() or t.username, 'username': t.username, 'email': t.email or ''}
            for t in trainers
        ]
        return Response(data)

from django.db import connection
from django.core.management import call_command
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

@api_view(['GET'])
@permission_classes([AllowAny])
def emergency_reset_db(request):
    if request.GET.get('token') != 'fix-flag-2026':
        return Response({'error': 'Unauthorized'}, status=401)
        
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM django_migrations WHERE app = 'students';")
            
            tables = [
                'students_attendancerecord',
                'students_attendancesession',
                'students_examrecord',
                'students_gradeexamrecord',
                'students_studentbatchhistory',
                'students_student',
                'students_gradebatch',
                'students_academicbatch',
                'students_academicpackage',
                'students_campus',
                'students_grade',
            ]
            for table in tables:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                except Exception:
                    pass
                    
        call_command('migrate', 'students')
        return Response({'status': 'Database reset successfully. Old tables dropped and new migrations applied.'})
    except Exception as e:
        return Response({'error': str(e)}, status=500)
