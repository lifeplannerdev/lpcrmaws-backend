from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField
import os


class User(AbstractUser):
    ROLE_CHOICES = [
        ('ADMIN', 'General Manager'),
        ('OPS', 'Operations Manager'),
        ('ADM_MANAGER', 'Admission Manager'),
        ('ADM_COUNSELLOR', 'Admission Counsellor'), 
        ('ADM_EXEC', 'Admission Executive'),
        ('PROCESSING', 'Processing Executive'),
        ('MEDIA', 'Media Team'),
        ('TRAINER', 'Trainer'),
        ('BUSINESS_HEAD', 'Business Head'),
        ('BDM', 'Business Development Manager'),
        ('CM', 'Center Manager'),
        ('HR', 'Human Resources'),
        ('FOE', 'FOE Cum TC'),
        ('ACCOUNTS', 'Accounts'),
        ('CEO','Chief executive'),
        ('DOCUMENTATION','Documentation executive')
    ]

    role = models.CharField(
        max_length=100,
        choices=ROLE_CHOICES,
        db_index=True
    )
    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
    ]
    company = models.CharField(
        max_length=10,
        choices=COMPANY_CHOICES,
        default='LP',
        db_index=True
    )

    team = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    personal_phone = models.CharField(max_length=20, blank=True, null=True)
    office_phone = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    join_date = models.DateField(blank=True, null=True)
    permissions = models.JSONField(default=list, blank=True)

    # Resolve auth clashes
    groups = models.ManyToManyField(
        Group,
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='custom_user_groups',
        related_query_name='user',
    )

    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='custom_user_permissions',
        related_query_name='user',
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_business_head(self):
        return self.role == 'BUSINESS_HEAD'

    @property
    def is_cm(self):
        return self.role == 'CM'

    @property
    def is_hr(self):
        return self.role == 'HR'

class ActivityLog(models.Model):
    ACTION_CHOICES = [
        # ── Lead ─────────────────────────────────────────────
        ('LEAD_CREATED',            'Lead Created'),
        ('LEAD_UPDATED',            'Lead Updated'),
        ('LEAD_STATUS_CHANGED',     'Lead Status Changed'),
        ('LEAD_ASSIGNED',           'Lead Assigned'),
        ('LEAD_SUB_ASSIGNED',       'Lead Sub-Assigned'),
        ('LEAD_UNASSIGNED',         'Lead Unassigned'),
        ('LEAD_PROCESSING_UPDATED', 'Lead Processing Updated'),
        ('LEAD_REMARK_UPDATED',     'Lead Remark Updated'),
        ('LEAD_DELETED',            'Lead Deleted'),
 
        # ── Follow-Up ─────────────────────────────────────────
        ('FOLLOWUP_CREATED',        'Follow-Up Created'),
        ('FOLLOWUP_STATUS_CHANGED', 'Follow-Up Status Changed'),
        ('FOLLOWUP_CONVERTED',      'Follow-Up Converted to Lead'),
        ('FOLLOWUP_DELETED',        'Follow-Up Deleted'),
 
        # ── Task ──────────────────────────────────────────────
        ('TASK_CREATED',            'Task Created'),
        ('TASK_UPDATED',            'Task Updated'),
        ('TASK_STATUS_CHANGED',     'Task Status Changed'),
        ('TASK_COMPLETED',          'Task Completed'),
        ('TASK_CANCELLED',          'Task Cancelled'),
        ('TASK_OVERDUE',            'Task Marked Overdue'),
        ('TASK_DELETED',            'Task Deleted'),
 
        # ── Staff / User ───────────────────────────────────────
        ('STAFF_CREATED',           'Staff Created'),
        ('STAFF_UPDATED',           'Staff Updated'),
        ('STAFF_ACTIVATED',         'Staff Activated'),
        ('STAFF_DEACTIVATED',       'Staff Deactivated'),
        ('STAFF_DELETED',           'Staff Deleted'),
        ('USER_LOGIN',              'User Logged In'),
        ('USER_LOGOUT',             'User Logged Out'),
 
        # ── MicroWork ─────────────────────────────────────────
        ('MICROWORK_CREATED',       'Micro Work Created'),
        ('MICROWORK_COMPLETED',     'Micro Work Completed'),
        ('MICROWORK_DELETED',       'Micro Work Deleted'),
 
        # ── Trainer ───────────────────────────────────────────
        ('TRAINER_CREATED',         'Trainer Profile Created'),
        ('TRAINER_UPDATED',         'Trainer Profile Updated'),
        ('TRAINER_STATUS_CHANGED',  'Trainer Status Changed'),
        ('TRAINER_DELETED',         'Trainer Profile Deleted'),
 
        # ── Student ───────────────────────────────────────────
        ('STUDENT_ENROLLED',        'Student Enrolled'),
        ('STUDENT_UPDATED',         'Student Updated'),
        ('STUDENT_COMPLETED',       'Student Completed Course'),
        ('STUDENT_DROPPED',         'Student Dropped'),
        ('STUDENT_PAUSED',          'Student Paused'),
        ('STUDENT_REACTIVATED',     'Student Reactivated'),
        ('STUDENT_TRAINER_CHANGED', 'Student Trainer Changed'),
        ('STUDENT_BATCH_CHANGED',   'Student Batch Changed'),
        ('STUDENT_DELETED',         'Student Deleted'),
 
        # ── Attendance (Trainer) ───────────────────────────────
        ('ATTENDANCE_MARKED',       'Attendance Marked'),
        ('ATTENDANCE_UPDATED',      'Attendance Updated'),
 
        # ── HR / Penalty ───────────────────────────────────────
        ('PENALTY_ISSUED',          'Penalty Issued'),
        ('PENALTY_UPDATED',         'Penalty Updated'),
        ('PENALTY_DELETED',         'Penalty Deleted'),
 
        # ── HR / Attendance Document ───────────────────────────
        ('ATTENDANCE_DOC_UPLOADED', 'Attendance Document Uploaded'),
        ('ATTENDANCE_DOC_DELETED',  'Attendance Document Deleted'),

        # ── HR / Asset ─────────────────────────────────────────
        ('ASSET_CREATED',           'Asset Created'),
        ('ASSET_UPDATED',           'Asset Updated'),
        ('ASSET_ASSIGNED',          'Asset Assigned'),
        ('ASSET_UNASSIGNED',        'Asset Unassigned'),
        ('ASSET_DELETED',           'Asset Deleted'),
    ]
 
    user        = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True, blank=True,related_name='activity_logs')
    company     = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    action      = models.CharField(max_length=60, choices=ACTION_CHOICES, db_index=True)
    entity_type = models.CharField(max_length=50, db_index=True)
    entity_id   = models.PositiveIntegerField(null=True, blank=True)
    entity_name = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    metadata    = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
 
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['entity_type']),
            models.Index(fields=['created_at']),
        ]
 
    def __str__(self):
        user_str = self.user.username if self.user else 'System'
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {user_str} — {self.get_action_display()}"




class MicroWork(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='micro_works'
    )
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    job_title = models.CharField(
        max_length=200,
        verbose_name='Job Title',
        help_text='Title of the micro work'
    )
    description = models.TextField(
        verbose_name='Description',
        help_text='Detailed description of the work'
    )
    time_required = models.CharField(
        max_length=100,
        verbose_name='Time Required',
        help_text='Estimated time required (e.g., 2 hours, 30 minutes)'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Micro Work'
        verbose_name_plural = 'Micro Works'

    def __str__(self):
        return f"{self.job_title} - {self.user.get_full_name()}"

    def mark_completed(self):
        self.status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save()

    @property
    def is_completed(self):
        return self.status == 'COMPLETED'

    @property
    def completion_time(self):
        if self.completed_at and self.created_at:
            return self.completed_at - self.created_at
        return None

    @property
    def created_date_display(self):
        return self.created_at.strftime('%b %d, %Y')

    @property
    def created_time_display(self):
        return self.created_at.strftime('%I:%M %p')

    @property
    def completed_date_display(self):
        if self.completed_at:
            return self.completed_at.strftime('%b %d, %Y')
        return None

    @property
    def completed_time_display(self):
        if self.completed_at:
            return self.completed_at.strftime('%I:%M %p')
        return None
