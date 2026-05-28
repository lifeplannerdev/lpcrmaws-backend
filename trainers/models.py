from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator

User = get_user_model()


class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.name


class Trainer(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='trainer_profile'
    )

    drive_link = models.URLField(
        blank=True,
        help_text="Link to trainer's Google Drive folder"
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainers'
    )

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('ON_LEAVE', 'On Leave'),
        ('INACTIVE', 'Inactive'),
    ]

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='ACTIVE'
    )

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class AcademicBatch(models.Model):
    name = models.CharField(max_length=100)
    academic_year = models.CharField(max_length=20, help_text="e.g. 2023-2024")
    grade = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. Grade 10")
    admission_date = models.DateField(blank=True, null=True)
    model_exam_date = models.DateField(blank=True, null=True)
    final_exam_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ['-academic_year', 'name']

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class Student(models.Model):
    BATCH_CHOICES = [
        ('A1', 'A1 (Beginner)'),
        ('A2', 'A2 (Elementary)'),
        ('B1', 'B1 (Intermediate)'),
        ('B2', 'B2 (Upper Intermediate)'),
        ('A1 ONLINE', 'A1 (Online)'),
        ('A2 ONLINE', 'A2 (Online)'),
        ('B1 ONLINE', 'B1 (Online)'),
        ('B2 ONLINE', 'B2 (Online)'),
        ('ONLINE', 'Online'),
        ('A1 EXAM PREPERATION', 'A1 (Exam Preparation)'),
        ('A2 EXAM PREPERATION', 'A2 (Exam Preparation)'),
        ('B1 EXAM PREPERATION', 'B1 (Exam Preparation)'),
        ('B2 EXAM PREPERATION', 'B2 (Exam Preparation)'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
        ('DROPPED', 'Dropped'),
    ]

    name = models.CharField(
        max_length=100,
        validators=[MinLengthValidator(3)]
    )

    batch = models.CharField(
        max_length=200,
        choices=BATCH_CHOICES,
        blank=True,
        null=True
    )
    
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students'
    )
    
    academic_batch = models.ForeignKey(
        AcademicBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students'
    )

    trainer = models.ForeignKey(
        Trainer,
        on_delete=models.PROTECT,
        related_name='students'
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='ACTIVE'
    )

    admission_date = models.DateField(
        help_text="Admission date"
    )

    start_date = models.DateField(
        blank=True,
        null=True,
        help_text="Course start date"
    )

    end_date = models.DateField(
        blank=True,
        null=True,
        help_text="Course end date"
    )

    notes = models.TextField(
        blank=True,
        help_text="General notes about the student"
    )

    email = models.EmailField(
        blank=True,
        null=True,
        help_text="Student's email address"
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Student's phone number"
    )

    drive_link = models.URLField(
        blank=True,
        null=True,
        help_text="Google Drive folder link for student materials"
    )

    # Manual entry (no choices)
    student_class = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Class type for the student (manual entry)"
    )

    class Meta:
        ordering = ['batch', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_batch_display()})"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('NO_SESSION', 'No Session'),
    ]

    date = models.DateField()

    trainer = models.ForeignKey(
        Trainer,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='PRESENT'
    )

    marked_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        unique_together = ['date', 'student']
        ordering = ['-date', 'student__name']
        indexes = [
            models.Index(fields=['date', 'trainer']),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.status}"


class ExamResult(models.Model):
    EXAM_TYPE_CHOICES = [
        ('MODEL', 'Model Exam'),
        ('FINAL', 'Final Exam'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exam_results'
    )
    academic_batch = models.ForeignKey(
        AcademicBatch,
        on_delete=models.CASCADE,
        related_name='exam_results'
    )
    exam_type = models.CharField(max_length=10, choices=EXAM_TYPE_CHOICES)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'academic_batch', 'exam_type']

    def __str__(self):
        return f"{self.student.name} - {self.get_exam_type_display()} - {self.score}"
