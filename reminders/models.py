from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    # Dates & Times
    reminder_date = models.DateField(
        db_index=True,
        help_text="Primary reminder date. Can be past (backdated), present, or future."
    )
    reminder_time = models.TimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional time for the reminder (HH:MM)."
    )
    deadline = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional target deadline date."
    )
    deadline_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Optional target deadline time (HH:MM)."
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
        """Returns True if the reminder date/time is in the past relative to creation date/time."""
        if not self.reminder_date:
            return False
        d = self.reminder_date
        if isinstance(d, str):
            from datetime import date
            d = date.fromisoformat(d)
        now = timezone.localtime()
        if self.created_at:
            created_local = timezone.localtime(self.created_at)
            if d < created_local.date():
                return True
            if d == created_local.date() and self.reminder_time:
                return self.reminder_time < created_local.time()
            return False
        if d < now.date():
            return True
        if d == now.date() and self.reminder_time:
            return self.reminder_time < now.time()
        return False

    @property
    def is_overdue(self):
        """Returns True if a deadline or reminder date/time has passed, and reminder is not yet completed."""
        if self.status in ['COMPLETED', 'CANCELLED', 'PENDING_APPROVAL']:
            return False
        target_date = self.deadline or self.reminder_date
        target_time = self.deadline_time if self.deadline else self.reminder_time
        if not target_date:
            return False
        if isinstance(target_date, str):
            from datetime import date
            target_date = date.fromisoformat(target_date)
        now = timezone.localtime()
        today = now.date()
        if today > target_date:
            return True
        if today == target_date:
            if target_time:
                return now.time().replace(second=0, microsecond=0) > target_time.replace(second=0, microsecond=0)
            return False
        return False


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


class ReminderNotificationSetting(models.Model):
    """
    Per-reminder notification configuration.
    Controls start date, intervals, delivery channels, and tracks dispatch timestamps.
    """
    INTERVAL_CHOICES = [
        (15, 'Every 15 minutes'),
        (30, 'Every 30 minutes'),
        (60, 'Every 1 hour'),
        (120, 'Every 2 hours'),
        (240, 'Every 4 hours'),
        (720, 'Every 12 hours'),
        (1440, 'Once daily (24 hours)'),
    ]

    reminder = models.OneToOneField(
        Reminder,
        on_delete=models.CASCADE,
        related_name='notification_setting'
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Master toggle: whether notifications are enabled for this reminder."
    )
    notify_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Specific date from which notifications should start arriving. If null, starts based on lead_days or immediately."
    )
    notify_start_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Optional specific time to start alerting on notify_start_date."
    )
    lead_days = models.PositiveIntegerField(
        default=0,
        help_text="Start alerting N days before deadline or reminder date (e.g. 1, 2, 3, 7 days before)."
    )
    interval_minutes = models.PositiveIntegerField(
        default=30,
        choices=INTERVAL_CHOICES,
        help_text="Interval between alert notifications in minutes."
    )
    last_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when notification was last sent for this reminder."
    )
    enable_in_app = models.BooleanField(
        default=True,
        help_text="Show floating alert card inside the CRM."
    )
    enable_desktop = models.BooleanField(
        default=True,
        help_text="Trigger native Windows / desktop notification."
    )
    enable_sound = models.BooleanField(
        default=True,
        help_text="Play synthesized harmonic audio chime."
    )
    notify_overdue_repeatedly = models.BooleanField(
        default=True,
        help_text="Continue alerting repeatedly if overdue until marked completed."
    )
    notes = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Optional custom note or instruction displayed with the alert."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status_str = "Enabled" if self.is_enabled else "Disabled"
        return f"Notification Setting for '{self.reminder.title}' ({status_str}, Every {self.interval_minutes}m)"

    def should_notify(self, now=None):
        """
        Determines whether an alert should be dispatched right now based on date, time, and interval.
        Returns (bool, str reason).
        """
        if not self.is_enabled:
            return False, "Notifications are disabled for this reminder."

        if self.reminder.status in ['COMPLETED', 'CANCELLED']:
            return False, f"Reminder status is {self.reminder.status}."

        now = now or timezone.localtime()
        today = now.date()
        current_time = now.time().replace(second=0, microsecond=0)

        eff_date = self.reminder.deadline or self.reminder.reminder_date
        eff_time = self.reminder.deadline_time if self.reminder.deadline else self.reminder.reminder_time
        if not eff_date:
            return False, "No reminder date or deadline configured."

        # Check start date condition
        start_date = self.notify_start_date
        start_time = self.notify_start_time or eff_time

        if start_date:
            if today < start_date:
                return False, f"Start date ({start_date}) has not yet arrived."
            if today == start_date and start_time:
                if current_time < start_time.replace(second=0, microsecond=0):
                    return False, f"Start time ({start_time.strftime('%H:%M')}) has not yet arrived."
        elif self.lead_days > 0:
            start_window = eff_date - timedelta(days=self.lead_days)
            if today < start_window:
                return False, f"Lead window ({self.lead_days} days before {eff_date}) starts on {start_window}."
            if today == eff_date and start_time:
                if current_time < start_time.replace(second=0, microsecond=0):
                    return False, f"Reminder time ({start_time.strftime('%H:%M')}) has not yet arrived."
        else:
            if today < eff_date:
                return False, f"Reminder date ({eff_date}) has not yet arrived."
            if today == eff_date and eff_time:
                if current_time < eff_time.replace(second=0, microsecond=0):
                    return False, f"Reminder time ({eff_time.strftime('%H:%M')}) has not yet arrived."

        # Check elapsed interval condition
        if self.last_notified_at:
            elapsed_minutes = (now - self.last_notified_at).total_seconds() / 60
            if elapsed_minutes < self.interval_minutes:
                return False, f"Interval not yet met: {int(elapsed_minutes)}m of {self.interval_minutes}m elapsed."

        return True, "Eligible for notification."


@receiver(post_save, sender=Reminder)
def create_default_reminder_notification_setting(sender, instance, created, **kwargs):
    if created:
        ReminderNotificationSetting.objects.get_or_create(
            reminder=instance,
            defaults={
                'is_enabled': True,
                'interval_minutes': 30,
                'notify_start_date': instance.reminder_date,
                'notify_start_time': instance.reminder_time,
            }
        )
