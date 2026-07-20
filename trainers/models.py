from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

User = get_user_model()


class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return self.name


class CourseLevel(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="e.g. A1, A2, B1, B2")
    order = models.IntegerField(default=0, help_text="Order for promotion (1 for A1, 2 for A2, etc.)")
    
    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name


class CourseModule(models.Model):
    level = models.ForeignKey(CourseLevel, on_delete=models.CASCADE, related_name='modules')
    name = models.CharField(max_length=100, help_text="e.g. A1.1, A1.2")
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['level__order', 'order']
        unique_together = ['level', 'name']

    def __str__(self):
        return f"{self.level.name} - {self.name}"


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
    default_fee_template = models.ForeignKey(
        'fees.FeePlanTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='academic_batches'
    )

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
    ]

    STATUS_CHOICES = [
        ('PENDING_ENROLLMENT', 'Pending Enrollment'),
        ('PENDING_BATCH_ASSIGNMENT', 'Pending Batch Assignment'),
        ('ACTIVE', 'Active'),
        ('EXAM_PREPARATION', 'Exam Preparation'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
        ('DROPPED', 'Dropped'),
    ]

    name = models.CharField(
        max_length=100,
        validators=[MinLengthValidator(3)]
    )
    
    parent_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Parent's name"
    )

    parent_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Parent's phone number"
    )

    MODE_OF_STUDY_CHOICES = [
        ('OFFLINE', 'Offline'),
        ('ONLINE', 'Online'),
        ('HYBRID', 'Hybrid'),
    ]
    mode_of_study = models.CharField(
        max_length=20,
        choices=MODE_OF_STUDY_CHOICES,
        default='OFFLINE'
    )

    qualification = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Student's highest qualification"
    )

    preferred_country = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Student's preferred country for studies"
    )

    PREFERRED_LEVEL_CHOICES = [
        ('A1', 'A1'),
        ('A2', 'A2'),
        ('B1', 'B1'),
        ('B2', 'B2'),
        ('A1-B2', 'A1 to B2'),
        ('OTHER', 'Other'),
    ]
    preferred_level = models.CharField(
        max_length=20,
        choices=PREFERRED_LEVEL_CHOICES,
        blank=True,
        null=True
    )

    batch = models.CharField(
        max_length=200,
        choices=BATCH_CHOICES,
        blank=True,
        null=True
    )
    
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)

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
    
    current_level = models.ForeignKey(
        CourseLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        help_text="Current academic level in the revamped system"
    )

    trainer = models.ForeignKey(
        Trainer,
        on_delete=models.PROTECT,
        related_name='students'
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='PENDING_ENROLLMENT'
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

    FEE_ATTENDANCE_POLICY_CHOICES = [
        ('STRICT', 'Strict (Requires Fee Approval if Overdue)'),
        ('FLEXIBLE', 'Flexible'),
    ]
    fee_attendance_policy = models.CharField(
        max_length=20,
        choices=FEE_ATTENDANCE_POLICY_CHOICES,
        default='FLEXIBLE',
        help_text="Attendance policy regarding unpaid fees"
    )

    class Meta:
        ordering = ['batch', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_batch_display()})"


class StudentTimeline(models.Model):
    EVENT_CHOICES = [
        ('BATCH_ASSIGNMENT', 'Batch Assignment'),
        ('PROMOTE', 'Promote'),
        ('FALLBACK', 'Fallback'),
        ('STATUS_CHANGE', 'Status Change'),
        ('NOTE', 'Note'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='timeline'
    )
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.name} - {self.get_event_type_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class StudentModuleProgress(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='module_progress'
    )
    module = models.ForeignKey(
        CourseModule,
        on_delete=models.CASCADE,
        related_name='student_progress'
    )
    academic_batch = models.ForeignKey(
        AcademicBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='module_progress'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    evaluated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'module', 'academic_batch']

    def __str__(self):
        return f"{self.student.name} - {self.module.name} - {self.status}"



class Attendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('NO_SESSION', 'No Session'),
    ]

    date = models.DateField()
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)

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

    academic_batch = models.ForeignKey(
        AcademicBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_records',
        help_text="The batch this student was in when attendance was marked"
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='PRESENT'
    )

    APPROVAL_STATUS_CHOICES = [
        ('APPROVED', 'Approved'),
        ('PENDING_FEE_APPROVAL', 'Pending Fee Approval'),
    ]

    approval_status = models.CharField(
        max_length=30,
        choices=APPROVAL_STATUS_CHOICES,
        default='APPROVED'
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_attendances'
    )

    approval_notes = models.TextField(
        blank=True,
        help_text="Notes regarding the attendance approval (e.g., fee promises)"
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


class ProcessingStudent(models.Model):
    # Fixed fields based on requirements
    name = models.CharField(max_length=200)
    mobile_number = models.CharField(max_length=20)
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    parent_contact = models.CharField(max_length=200, blank=True, null=True, help_text="Contact number of parents (1 & 2)")
    program_applied = models.CharField(max_length=200, blank=True, null=True)
    date_of_registration = models.DateField(blank=True, null=True)
    university = models.CharField(max_length=200, blank=True, null=True)
    intake = models.CharField(max_length=100, blank=True, null=True)

    REG_FEE_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Shared with student', 'Shared with student'),
        ('Without Tax amount', 'Without Tax amount'),
    ]
    registration_fee_status = models.CharField(max_length=50, choices=REG_FEE_STATUS_CHOICES, default='Pending')

    ENROLLMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Shared', 'Shared'),
        ('Completed', 'Completed'),
    ]
    enrollment_process_status = models.CharField(max_length=50, choices=ENROLLMENT_STATUS_CHOICES, default='Pending')

    APP_DOCS_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Collected', 'Collected'),
    ]
    application_documents_status = models.CharField(max_length=50, choices=APP_DOCS_STATUS_CHOICES, default='Pending')

    application_status = models.CharField(max_length=200, blank=True, null=True)
    offer_letter_status = models.CharField(max_length=200, blank=True, null=True)
    visa_documentation_info_status = models.CharField(max_length=200, blank=True, null=True)
    visa_appointment = models.CharField(max_length=200, blank=True, null=True)
    visa_documentation = models.CharField(max_length=200, blank=True, null=True)
    accommodation = models.CharField(max_length=200, blank=True, null=True)
    visa_results = models.CharField(max_length=200, blank=True, null=True)

    # Required relationships and categorizations
    category = models.CharField(max_length=50, default='All Students', help_text="e.g., GCC Students")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_processing_students')

    # Fee tracking fields
    processing_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    processing_fee_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    PROCESSING_FEE_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partial'),
        ('PAID', 'Paid'),
    ]
    processing_fee_status = models.CharField(max_length=20, choices=PROCESSING_FEE_STATUS_CHOICES, default='PENDING')

    
    # Dynamic Fields Data
    dynamic_data = models.JSONField(default=dict, blank=True, help_text="Stores data for dynamically added fields")

    class Meta:
        permissions = [
            ("processing_students:read_any", "Can view any processing student"),
            ("processing_students:read_own", "Can view own processing students"),
            ("processing_students:edit_any", "Can edit any processing student"),
            ("processing_students:edit_own", "Can edit own processing students"),
            ("processing_students:manage_fees", "Can manage processing student fees"),
        ]
        ordering = ['-id']

    def __str__(self):
        return f"{self.name} - {self.category}"


class ProcessingDynamicField(models.Model):
    FIELD_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Boolean'),
        ('choice', 'Choice (Dropdown)'),
    ]
    
    name = models.CharField(max_length=100, unique=True, help_text="Internal field name (e.g., 'medical_check_status')")
    label = models.CharField(max_length=200, help_text="Display label (e.g., 'Medical Check Status')")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES, default='text')
    choices = models.JSONField(blank=True, null=True, help_text="List of choices if type is 'choice' (e.g., [\"Pending\", \"Done\"])")
    order = models.IntegerField(default=0, help_text="Order in which this field appears in the UI")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.label


class ProcessingStudentDocument(models.Model):
    student = models.ForeignKey(ProcessingStudent, related_name='documents', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    file = models.FileField(storage=S3Boto3Storage(), upload_to='processing_students/documents/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} ({self.student.name})"
