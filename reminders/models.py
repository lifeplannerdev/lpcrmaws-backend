from django.db import models
from django.conf import settings
from django.utils import timezone


class Reminder(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
        ('FDS', 'FILMAATIC'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    
    # Ownership
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reminders',
        help_text="The employee whose reminder/checklist this is."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_reminders',
        help_text="The user who created this reminder."
    )

    # Optional Processing Student Link
    student = models.ForeignKey(
        'trainers.ProcessingStudent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reminders',
        help_text="Optional linked student from processing registry."
    )

    company = models.CharField(
        max_length=10,
        choices=COMPANY_CHOICES,
        default='LP',
        db_index=True
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        default='General',
        db_index=True
    )

    # Dates
    reminder_date = models.DateField(
        db_index=True,
        help_text="Primary reminder date. Can be past (backdated), present, or future."
    )
    deadline = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional target deadline date."
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='MEDIUM',
        db_index=True
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )

    # Main Task / Briefing completion
    briefing_completed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the main briefing/task itself is marked completed."
    )
    briefing_completed_at = models.DateTimeField(null=True, blank=True)
    briefing_remarks = models.TextField(
        blank=True,
        default='',
        help_text="Optional remarks for what was done for the main briefing task."
    )
    briefing_completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_briefing_reminders',
        help_text="User who marked the briefing task as done."
    )

    # Checklist storage: list of dicts [{ "id": 1, "text": "Task A", "completed": False, "completed_at": None }]
    checklist = models.JSONField(
        default=list,
        blank=True,
        help_text="Interactive checklist items."
    )

    # Completion & Approval workflow
    completion_remarks = models.TextField(
        blank=True,
        default='',
        help_text="Mandatory remarks entered by user or admin when marking completed."
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_reminders',
        help_text="User who submitted or completed this reminder."
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_reminders',
        help_text="Admin who approved completion."
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-reminder_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['reminder_date', 'status']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['status', 'priority']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()}) - {self.user.get_full_name() or self.user.username}"

    @property
    def is_backdated(self):
        """Returns True if the reminder date is in the past relative to creation date."""
        if not self.reminder_date:
            return False
        d = self.reminder_date
        if isinstance(d, str):
            from datetime import date
            d = date.fromisoformat(d)
        if self.created_at:
            return d < self.created_at.date()
        return d < timezone.now().date()

    @property
    def is_overdue(self):
        """Returns True if a deadline is set, date has passed, and reminder is not yet completed."""
        if self.status in ['COMPLETED', 'CANCELLED', 'PENDING_APPROVAL']:
            return False
        target_date = self.deadline or self.reminder_date
        if not target_date:
            return False
        if isinstance(target_date, str):
            from datetime import date
            target_date = date.fromisoformat(target_date)
        return timezone.now().date() > target_date


class ReminderUpdate(models.Model):
    reminder = models.ForeignKey(
        Reminder,
        on_delete=models.CASCADE,
        related_name='updates'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reminder_updates'
    )
    notes = models.TextField(help_text="Update remarks, feedback, or query notes.")
    previous_status = models.CharField(
        max_length=30,
        blank=True,
        default=''
    )
    new_status = models.CharField(
        max_length=30,
        blank=True,
        default=''
    )
    is_system_event = models.BooleanField(
        default=False,
        help_text="True if recorded automatically during approval/status change."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Update on '{self.reminder.title}' by {self.author.username} at {self.created_at}"
