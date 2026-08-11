from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class AcademicGrade(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="e.g., A1, A2, B1, B2")
    order = models.IntegerField(default=0, help_text="Order for promotion")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name

class AcademicPackage(models.Model):
    name = models.CharField(max_length=150, help_text="e.g., A1 to B2 Package")
    starting_grade = models.ForeignKey(AcademicGrade, on_delete=models.PROTECT, related_name='packages_starting')
    ending_grade = models.ForeignKey(AcademicGrade, on_delete=models.PROTECT, related_name='packages_ending')

    class Meta:
        ordering = ['starting_grade__order']

    def __str__(self):
        return self.name

class AcademicBatch(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
    ]
    name = models.CharField(max_length=100)
    starting_grade = models.ForeignKey(AcademicGrade, on_delete=models.PROTECT, related_name='batches_started', null=True, blank=True)
    current_grade = models.ForeignKey(AcademicGrade, on_delete=models.PROTECT, related_name='batches')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    schedule = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Morning, Evening, Weekend")
    start_date = models.DateField(null=True, blank=True)
    target_end_date = models.DateField(null=True, blank=True)
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_batches')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.current_grade.name})"

class Student(models.Model):
    FEE_ATTENDANCE_POLICY_CHOICES = [
        ('STRICT', 'Strict (Requires Fee Regularization if Overdue)'),
        ('LENIENT', 'Lenient'),
    ]
    name = models.CharField(max_length=200)
    mobile_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Flag for German Training Center
    company = models.CharField(max_length=10, default='FLAG', editable=False)
    
    package = models.ForeignKey(AcademicPackage, on_delete=models.SET_NULL, null=True, blank=True)
    batch = models.ForeignKey(AcademicBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    
    fee_attendance_policy = models.CharField(max_length=20, choices=FEE_ATTENDANCE_POLICY_CHOICES, default='STRICT')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class ExamResult(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_results')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='exam_results')
    grade = models.ForeignKey(AcademicGrade, on_delete=models.CASCADE)
    marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'batch', 'grade']

class BatchAttendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('OFFDAY', 'Offday'),
    ]
    APPROVAL_STATUS_CHOICES = [
        ('APPROVED', 'Approved'),
        ('PENDING', 'Pending Accounts Regularization'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    batch = models.ForeignKey(AcademicBatch, on_delete=models.CASCADE, related_name='attendances')
    grade = models.ForeignKey(AcademicGrade, on_delete=models.PROTECT, null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    # Strict policy + Due pending => PENDING. Else APPROVED.
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='APPROVED')
    
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='marked_student_attendances')
    regularized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='regularized_student_attendances')
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'date']

class DailyRemark(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='remarks')
    trainer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    remark = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class StudentTimeline(models.Model):
    EVENT_CHOICES = [
        ('PROMOTED', 'Promoted'),
        ('DEMOTED', 'Demoted'),
        ('ENROLLED', 'Enrolled'),
        ('ATTENDANCE_FLAG', 'Attendance Flagged'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='timeline')
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    description = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='students_timelines')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
