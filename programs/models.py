from django.conf import settings
from django.db import models

class ProgramCountry(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class ProgramUniversity(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class ProgramIntake(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class Program(models.Model):
    title = models.CharField(max_length=255)
    country = models.ForeignKey(ProgramCountry, on_delete=models.SET_NULL, null=True, blank=True, related_name='programs')
    qualification = models.TextField(blank=True, null=True)
    course_duration = models.CharField(max_length=255, blank=True, null=True)
    university = models.ForeignKey(ProgramUniversity, on_delete=models.SET_NULL, null=True, blank=True, related_name='programs')
    intake = models.ForeignKey(ProgramIntake, on_delete=models.SET_NULL, null=True, blank=True, related_name='programs')
    
    # JSON field to store arbitrary fees structure (e.g. [{"name": "Application Fee", "amount": "25000 + GST"}, ...])
    fees_structure = models.JSONField(default=list, blank=True)
    
    # JSON field to store list of services (e.g. ["Enrollment", "Visa Assistance"])
    services = models.JSONField(default=list, blank=True)
    
    is_hidden = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.country}"


class AssignedProgram(models.Model):
    """Tracks Assigned Programs sheet rows (PROJECT, COUNTRY, ASSIGNMENT, COMPLETED, PRESENTATION, TRAINING TO TEAM)."""
    sl_no = models.PositiveIntegerField(null=True, blank=True)
    project = models.CharField(max_length=255)
    country = models.CharField(max_length=120, blank=True, default='')
    assignment = models.CharField(max_length=120, blank=True, default='')
    completed = models.CharField(max_length=120, blank=True, default='')
    presentation = models.CharField(max_length=120, blank=True, default='')
    training_to_team = models.CharField(max_length=255, blank=True, default='')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_program_rows',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_program_rows',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sl_no', 'id']
        indexes = [
            models.Index(fields=['assigned_to', 'id']),
        ]

    def __str__(self):
        return f"{self.project} ({self.country})"


class AssignedProgramChangeLog(models.Model):
    """Per-field audit timeline for AssignedProgram edits and assignments."""
    ACTION_CHOICES = [
        ('CREATED', 'Created'),
        ('UPDATED', 'Updated'),
        ('ASSIGNED', 'Assigned'),
    ]
    program = models.ForeignKey(
        AssignedProgram,
        on_delete=models.CASCADE,
        related_name='change_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='UPDATED')
    field_name = models.CharField(max_length=80, blank=True, default='')
    field_label = models.CharField(max_length=120, blank=True, default='')
    old_value = models.TextField(blank=True, default='')
    new_value = models.TextField(blank=True, default='')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_program_changes',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']


class AssignedStudentRecord(models.Model):
    """Tracks Assigned Students Database sheet rows with exact G-Sheet columns."""
    SOURCE_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('insta', 'Insta'),
        ('facebook', 'Facebook'),
        ('chatgpt', 'ChatGPT'),
        ('voxbay', 'Voxbay'),
        ('walkin', 'Walk-in'),
    ]

    sl_no = models.PositiveIntegerField(null=True, blank=True)
    name = models.CharField(max_length=255)
    age = models.CharField(max_length=30, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    email_address = models.CharField(max_length=255, blank=True, default='')
    place = models.CharField(max_length=200, blank=True, default='')
    qualification = models.CharField(max_length=255, blank=True, default='')
    preferred_country = models.CharField(max_length=150, blank=True, default='')
    preferred_program = models.CharField(max_length=255, blank=True, default='')
    intake = models.CharField(max_length=120, blank=True, default='')
    aps_status = models.CharField(max_length=120, blank=True, default='')
    ielts_status = models.CharField(max_length=120, blank=True, default='')
    german_status = models.CharField(max_length=120, blank=True, default='')
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, blank=True, default='')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_student_db_rows',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_student_db_rows',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sl_no', 'id']
        indexes = [
            models.Index(fields=['assigned_to', 'id']),
        ]

    def __str__(self):
        return f"{self.name} ({self.preferred_country})"


class AssignedStudentChangeLog(models.Model):
    """Per-field audit timeline for AssignedStudentRecord edits and assignments."""
    ACTION_CHOICES = [
        ('CREATED', 'Created'),
        ('UPDATED', 'Updated'),
        ('ASSIGNED', 'Assigned'),
    ]
    student_record = models.ForeignKey(
        AssignedStudentRecord,
        on_delete=models.CASCADE,
        related_name='change_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='UPDATED')
    field_name = models.CharField(max_length=80, blank=True, default='')
    field_label = models.CharField(max_length=120, blank=True, default='')
    old_value = models.TextField(blank=True, default='')
    new_value = models.TextField(blank=True, default='')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_student_db_changes',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']

