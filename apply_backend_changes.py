import os

MODELS_CODE = """from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

User = settings.AUTH_USER_MODEL

class Grade(models.Model):
    GRADE_CHOICES = [('A1', 'A1 - Beginner'), ('A2', 'A2 - Elementary'), ('B1', 'B1 - Intermediate'), ('B2', 'B2 - Upper Intermediate')]
    code = models.CharField(max_length=5, unique=True, choices=GRADE_CHOICES)
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField(unique=True, help_text="1=A1, 2=A2, 3=B1, 4=B2")
    class Meta:
        ordering = ['order']
    def __str__(self): return self.code
    def next_grade(self): return Grade.objects.filter(order=self.order + 1).first()
    def prev_grade(self): return Grade.objects.filter(order=self.order - 1).first()

class Campus(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    class Meta:
        verbose_name_plural = 'Campuses'
    def __str__(self): return f"{self.name} ({self.code})"

class AcademicPackage(models.Model):
    name = models.CharField(max_length=200, unique=True)
    starting_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='packages_starting')
    ending_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='packages_ending')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name
    @property
    def grade_range(self):
        if self.starting_grade == self.ending_grade: return self.starting_grade.code
        return f"{self.starting_grade.code} -> {self.ending_grade.code}"

class AcademicBatch(models.Model):
    MODE_CHOICES = [('offline', 'Offline'), ('online', 'Online')]
    STATUS_CHOICES = [('active', 'Active'), ('proposed', 'Proposed'), ('closed', 'Closed')]
    name = models.CharField(max_length=100, unique=True)
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name='batches')
    package = models.ForeignKey(AcademicPackage, on_delete=models.PROTECT, related_name='batches')
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_batches')
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='offline')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['campus', 'name']
    def __str__(self): return self.name
    @property
    def student_count(self): return self.students.filter(status='active').count()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.students.all().update(trainer=self.trainer)

class GradeBatch(models.Model):
    academic_batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='grade_batches')
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='grade_batches')
    class Meta:
        ordering = ['academic_batch', 'grade__order']
        unique_together = ['academic_batch', 'grade']
    def __str__(self): return f"{self.academic_batch.name} - {self.grade.code}"

class Student(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('demoted', 'Demoted'), ('exited', 'Exited'), ('on_hold', 'On Hold')]
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name='students')
    academic_package = models.ForeignKey(AcademicPackage, on_delete=models.PROTECT, related_name='students')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    grade_batch = models.ForeignKey(GradeBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_students')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    joined_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    def __str__(self): return self.name

    def save(self, *args, **kwargs):
        if self.batch:
            self.trainer = self.batch.trainer
        else:
            self.trainer = None
        super().save(*args, **kwargs)

    @property
    def current_grade(self):
        return self.grade_batch.grade if self.grade_batch else None
        
    @property
    def fee_account(self):
        return self.fee_accounts.order_by('-created_at').first()
    @property
    def has_pending_fees(self):
        account = self.fee_account
        if account: return account.overdue_amount > 0
        return False
    @property
    def fee_status(self):
        account = self.fee_account
        if not account: return 'NO_ACCOUNT'
        return account.status
    @property
    def fee_account_id(self):
        account = self.fee_account
        if account: return account.id
        return None
    @property
    def pending_fee_amount(self):
        account = self.fee_account
        if account: return account.overdue_amount
        return 0

class StudentBatchHistory(models.Model):
    ACTION_CHOICES = [('enrolled', 'Enrolled'), ('promoted', 'Promoted'), ('demoted', 'Demoted'), ('exited', 'Exited'), ('transferred', 'Transferred')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='batch_history')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='history_records')
    grade_batch = models.ForeignKey(GradeBatch, on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_date = models.DateField(default=timezone.now)
    to_date = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-from_date']
    def __str__(self): return f"{self.student.name} - {self.action} - {self.batch.name}"

class ExamRecord(models.Model):
    EXAM_TYPES = [('model', 'Model Exam'), ('grade', 'Grade Exam')]
    RESULT_CHOICES = [('pass', 'Pass'), ('fail', 'Fail')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_records')
    grade_batch = models.ForeignKey(GradeBatch, on_delete=models.CASCADE, related_name='exam_records')
    exam_type = models.CharField(max_length=10, choices=EXAM_TYPES)
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    achieved_marks = models.DecimalField(max_digits=5, decimal_places=2)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, blank=True)
    exam_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self): return f"{self.student.name} | {self.grade_batch.grade.code} | {self.exam_type}"

class AttendanceSession(models.Model):
    grade_batch = models.ForeignKey(GradeBatch, on_delete=models.CASCADE, related_name='sessions')
    date = models.DateField(default=timezone.now)
    topic = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-date']
        unique_together = ['grade_batch', 'date']
    def __str__(self): return f"{self.grade_batch} - {self.date}"
    @property
    def present_count(self): return self.records.filter(status='present').count()
    @property
    def absent_count(self): return self.records.filter(status='absent').count()
    @property
    def pending_count(self): return self.records.filter(status='pending').count()
    @property
    def total_count(self): return self.records.count()

class AttendanceRecord(models.Model):
    STATUS_CHOICES = [('present', 'Present'), ('absent', 'Absent'), ('late', 'Late'), ('pending', 'Pending (Fee Due)'), ('leave', 'Approved Leave')]
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='absent')
    class Meta:
        unique_together = ['session', 'student']
    def __str__(self): return f"{self.student.name} - {self.session.date} - {self.status}"
"""

SERIALIZERS_CODE = """from rest_framework import serializers
from .models import (
    Grade, Campus, AcademicPackage,
    AcademicBatch, GradeBatch, Student, StudentBatchHistory,
    ExamRecord, AttendanceSession, AttendanceRecord
)
from django.contrib.auth import get_user_model

User = get_user_model()

class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = '__all__'

class CampusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campus
        fields = '__all__'

class AcademicPackageSerializer(serializers.ModelSerializer):
    grade_range = serializers.ReadOnlyField()
    class Meta:
        model = AcademicPackage
        fields = '__all__'

class GradeBatchSerializer(serializers.ModelSerializer):
    grade_code = serializers.CharField(source='grade.code', read_only=True)
    academic_batch_name = serializers.CharField(source='academic_batch.name', read_only=True)
    class Meta:
        model = GradeBatch
        fields = '__all__'

class AcademicBatchSerializer(serializers.ModelSerializer):
    student_count = serializers.ReadOnlyField()
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    grade_batches = GradeBatchSerializer(many=True, read_only=True)
    
    def get_trainer_name(self, obj):
        if obj.trainer:
            return obj.trainer.get_full_name().strip() or obj.trainer.username
        return None

    class Meta:
        model = AcademicBatch
        fields = '__all__'

class StudentSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    grade_batch_id = serializers.IntegerField(source='grade_batch.id', read_only=True)
    current_grade = serializers.CharField(source='grade_batch.grade.code', read_only=True)
    package_name = serializers.CharField(source='academic_package.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    has_pending_fees = serializers.ReadOnlyField()
    pending_fee_amount = serializers.ReadOnlyField()
    fee_status = serializers.ReadOnlyField()
    fee_account_id = serializers.ReadOnlyField()

    def get_trainer_name(self, obj):
        trainer = obj.trainer or (obj.batch.trainer if obj.batch else None)
        if trainer:
            return trainer.get_full_name().strip() or trainer.username
        return None

    class Meta:
        model = Student
        fields = '__all__'

class StudentBatchHistorySerializer(serializers.ModelSerializer):
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    grade_code = serializers.CharField(source='grade_batch.grade.code', read_only=True)
    class Meta:
        model = StudentBatchHistory
        fields = '__all__'

class ExamRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    grade_code = serializers.CharField(source='grade_batch.grade.code', read_only=True)
    batch_name = serializers.CharField(source='grade_batch.academic_batch.name', read_only=True)

    class Meta:
        model = ExamRecord
        fields = '__all__'

class AttendanceSessionSerializer(serializers.ModelSerializer):
    present_count = serializers.ReadOnlyField()
    absent_count = serializers.ReadOnlyField()
    pending_count = serializers.ReadOnlyField()
    total_count = serializers.ReadOnlyField()
    batch_name = serializers.CharField(source='grade_batch.academic_batch.name', read_only=True)
    grade_name = serializers.CharField(source='grade_batch.grade.name', read_only=True)
    
    class Meta:
        model = AttendanceSession
        fields = '__all__'

class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    session_date = serializers.DateField(source='session.date', read_only=True)
    grade_batch_name = serializers.CharField(source='session.grade_batch.academic_batch.name', read_only=True)
    class Meta:
        model = AttendanceRecord
        fields = '__all__'
"""

VIEWS_CODE = """from rest_framework import viewsets, permissions, status
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
    filterset_fields = ['batch', 'status', 'campus', 'academic_package', 'trainer', 'grade_batch']

    def get_queryset(self):
        qs = super().get_queryset()
        if is_flag_trainer(self.request.user):
            qs = qs.filter(batch__trainer=self.request.user)
        return qs
        
    def create(self, request, *args, **kwargs):
        if is_flag_trainer(request.user):
            return Response({'detail': 'Trainers cannot create new students.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        student = self.get_object()
        return Response({'status': 'Not implemented here, use batch promotion'}, status=400)

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
            Q(managed_batches__isnull=False) |
            Q(assigned_students__isnull=False),
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
"""

URLS_CODE = """from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GradeViewSet, CampusViewSet, AcademicPackageViewSet,
    AcademicBatchViewSet, GradeBatchViewSet, StudentViewSet, StudentBatchHistoryViewSet,
    ExamRecordViewSet, AttendanceSessionViewSet, AttendanceRecordViewSet,
    FlagTrainerView
)

router = DefaultRouter()
router.register(r'grades', GradeViewSet)
router.register(r'campuses', CampusViewSet)
router.register(r'packages', AcademicPackageViewSet)
router.register(r'batches', AcademicBatchViewSet)
router.register(r'grade-batches', GradeBatchViewSet)
router.register(r'students', StudentViewSet)
router.register(r'batch-history', StudentBatchHistoryViewSet)
router.register(r'exam-records', ExamRecordViewSet)
router.register(r'attendance-sessions', AttendanceSessionViewSet)
router.register(r'attendance-records', AttendanceRecordViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('trainers/', FlagTrainerView.as_view(), name='flag-trainers'),
]
"""

with open("b:\\LP WORKSPACE\\lp_crm\\lpcrmbackend-main\\students\\models.py", "w") as f:
    f.write(MODELS_CODE)
with open("b:\\LP WORKSPACE\\lp_crm\\lpcrmbackend-main\\students\\serializers.py", "w") as f:
    f.write(SERIALIZERS_CODE)
with open("b:\\LP WORKSPACE\\lp_crm\\lpcrmbackend-main\\students\\views.py", "w") as f:
    f.write(VIEWS_CODE)
with open("b:\\LP WORKSPACE\\lp_crm\\lpcrmbackend-main\\students\\urls.py", "w") as f:
    f.write(URLS_CODE)
