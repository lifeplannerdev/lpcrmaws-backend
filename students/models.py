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
            self.campus = self.batch.campus
            self.academic_package = self.batch.package
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
