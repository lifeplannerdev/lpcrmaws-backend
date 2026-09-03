from django.db import models
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

class AttendancePolicy(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    grace_absences = models.PositiveSmallIntegerField(default=0)
    fee_block_on_pending = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        verbose_name_plural = 'Attendance Policies'
    def __str__(self): return self.name

class AcademicBatch(models.Model):
    MODE_CHOICES = [('offline', 'Offline'), ('online', 'Online')]
    STATUS_CHOICES = [('active', 'Active'), ('proposed', 'Proposed'), ('closed', 'Closed'), ('promoted', 'Promoted')]
    name = models.CharField(max_length=100, unique=True)
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name='batches')
    package = models.ForeignKey(AcademicPackage, on_delete=models.PROTECT, related_name='batches')
    starting_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='batches_starting')
    current_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='batches_current')
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_batches')
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='offline')
    schedule = models.CharField(max_length=100, blank=True)
    start_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    attendance_policy = models.ForeignKey(AttendancePolicy, on_delete=models.SET_NULL, null=True, blank=True, related_name='batches')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['campus', 'name']
    def __str__(self): return self.name
    @property
    def student_count(self): return self.students.filter(status='active').count()
    @property
    def grade_progress(self): return f"{self.starting_grade.code} -> {self.current_grade.code}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Always propagate batch's trainer to all enrolled students
        self.students.all().update(trainer=self.trainer)

class Student(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('demoted', 'Demoted - Awaiting Reassignment'), ('exited', 'Exited'), ('on_hold', 'On Hold')]
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    parent_name = models.CharField(max_length=200, blank=True)
    parent_phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=10, default='FLAG', editable=False)
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name='students')
    academic_package = models.ForeignKey(AcademicPackage, on_delete=models.PROTECT, related_name='students')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_students')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    mode_of_study = models.CharField(max_length=10, choices=[('offline', 'Offline'), ('online', 'Online')], default='offline')
    joined_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
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
        return self.batch.current_grade if self.batch else None
    @property
    def has_pending_fees(self):
        if hasattr(self, 'fee_account'): return self.fee_account.overdue_amount > 0
        return False
        
    @property
    def fee_status(self):
        if not hasattr(self, 'fee_account'):
            return 'NO_ACCOUNT'
        return self.fee_account.status
        
    @property
    def fee_account_id(self):
        if hasattr(self, 'fee_account'):
            return self.fee_account.id
        return None
    @property
    def pending_fee_amount(self):
        if hasattr(self, 'fee_account'): return self.fee_account.overdue_amount
        return 0

class StudentBatchHistory(models.Model):
    ACTION_CHOICES = [('enrolled', 'Enrolled'), ('promoted', 'Promoted'), ('demoted', 'Demoted'), ('exited', 'Exited'), ('transferred', 'Transferred')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='batch_history')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='history_records')
    grade_at_time = models.ForeignKey(Grade, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_date = models.DateField(default=timezone.now)
    to_date = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-from_date']
    def __str__(self): return f"{self.student.name} - {self.action} - {self.batch.name}"

class GradeExamRecord(models.Model):
    RESULT_CHOICES = [('pass', 'Pass'), ('fail', 'Fail'), ('pending', 'Result Pending')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_records')
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='exam_records')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='exam_records')
    attempt_number = models.PositiveSmallIntegerField(default=1)
    model_exam_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    grade_exam_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    model_exam_max = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    grade_exam_max = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    passing_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=60)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default='pending')
    exam_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-attempt_number', '-created_at']
    def __str__(self): return f"{self.student.name} | {self.grade.code} | Attempt {self.attempt_number}"
    @property
    def model_exam_percentage(self):
        if self.model_exam_marks is not None and self.model_exam_max > 0: return round((self.model_exam_marks / self.model_exam_max) * 100, 1)
        return None
    @property
    def grade_exam_percentage(self):
        if self.grade_exam_marks is not None and self.grade_exam_max > 0: return round((self.grade_exam_marks / self.grade_exam_max) * 100, 1)
        return None
    @property
    def average_percentage(self):
        percs = [p for p in [self.model_exam_percentage, self.grade_exam_percentage] if p is not None]
        if percs: return round(sum(percs) / len(percs), 1)
        return None
    @property
    def is_eligible_for_promotion(self):
        if self.model_exam_marks is None or self.grade_exam_marks is None: return False
        avg = self.average_percentage
        return avg is not None and avg >= float(self.passing_percentage)
    def auto_set_result(self):
        if self.model_exam_marks is not None and self.grade_exam_marks is not None:
            self.result = 'pass' if self.is_eligible_for_promotion else 'fail'
        else: self.result = 'pending'
    def save(self, *args, **kwargs):
        self.auto_set_result()
        super().save(*args, **kwargs)

class AttendanceSession(models.Model):
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='sessions')
    date = models.DateField(default=timezone.now)
    topic = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_finalized = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-date']
        unique_together = ['batch', 'date']
    def __str__(self): return f"{self.batch.name} - {self.date}"
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
    is_regularized = models.BooleanField(default=False)
    regularized_date = models.DateField(null=True, blank=True)
    regularized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='regularized_records')
    notes = models.CharField(max_length=200, blank=True)
    class Meta:
        unique_together = ['session', 'student']
    def __str__(self): return f"{self.student.name} - {self.session.date} - {self.status}"
    def regularize(self, user=None):
        if self.status == 'pending':
            self.status = 'present'
            self.is_regularized = True
            self.regularized_date = timezone.now().date()
            self.regularized_by = user
            self.save()

class PromotionEvent(models.Model):
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='promotion_events')
    from_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='promotions_from')
    to_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='promotions_to', null=True, blank=True)
    promoted_students = models.ManyToManyField(Student, related_name='promotions', blank=True)
    exited_students = models.ManyToManyField(Student, related_name='exits', blank=True)
    new_batch = models.ForeignKey(AcademicBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_from_promotions')
    notes = models.TextField(blank=True)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Promotion: {self.batch.name} | {self.from_grade} -> {self.to_grade} | {self.created_at.date()}"

class DemotionEvent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='demotion_events')
    from_batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='demotions_from')
    from_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='demotions_from')
    to_batch = models.ForeignKey(AcademicBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='demotions_to')
    to_grade = models.ForeignKey(Grade, on_delete=models.PROTECT, null=True, blank=True, related_name='demotions_to')
    reason = models.TextField(blank=True)
    reassigned = models.BooleanField(default=False)
    reassigned_date = models.DateField(null=True, blank=True)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Demotion: {self.student.name} from {self.from_batch.name}"
