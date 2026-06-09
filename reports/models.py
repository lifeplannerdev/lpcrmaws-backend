from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
import urllib.parse
from datetime import time

User = get_user_model()

class ReportTimingSettings(models.Model):
    AGENDA_POLICY_CHOICES = (
        ('EVENING_BEFORE', 'Evening Before'),
        ('MORNING_OF', 'Morning Of'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='report_settings')
    agenda_policy = models.CharField(max_length=20, choices=AGENDA_POLICY_CHOICES, default='MORNING_OF')
    agenda_deadline = models.TimeField(default=time(10, 0))
    report_deadline = models.TimeField(default=time(18, 0))

    def __str__(self):
        return f"Report Settings for {self.user.get_full_name()}"

class DailyReport(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='daily_reports',
        db_index=True
    )
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    REPORT_TYPE_CHOICES = (
        ('MORNING', 'Morning Agenda'),
        ('EVENING', 'Evening Report'),
    )
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPE_CHOICES,
        default='EVENING',
        db_index=True
    )
    report_submitted_at = models.DateTimeField(null=True, blank=True)
    agenda_submitted_at = models.DateTimeField(null=True, blank=True)
    next_day_agenda = models.TextField(blank=True, null=True)
    name = models.CharField(
        max_length=200,
        verbose_name='Report Name',
        help_text='Give a title to your daily report'
    )
    report_heading = models.CharField(
        max_length=300,
        verbose_name='Report Heading',
        help_text='Brief summary of your daily report',
        blank=True, null=True
    )
    agenda_heading = models.CharField(
        max_length=300,
        verbose_name='Agenda Heading',
        help_text='Brief summary of your agenda',
        blank=True, null=True
    )
    report_text = models.TextField(
        verbose_name='Daily Update',
        help_text='Share your daily progress and updates',
        blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    report_date = models.DateField(
        default=timezone.now,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_reports'
    )
    review_comment = models.TextField(blank=True)

    class Meta:
        ordering = ['-report_date', '-created_at']
        verbose_name = 'Daily Report'
        verbose_name_plural = 'Daily Reports'

    def __str__(self):
        return f"{self.name} - {self.user.get_full_name()} - {self.report_date}"

    @property
    def is_today_report(self):
        return self.report_date == timezone.now().date()

    @property
    def completion_percentage(self):
        score = 0
        if self.next_day_agenda:
            score += 50
        if self.report_text:
            score += 50
        return score

    @property
    def is_agenda_late(self):
        if not self.agenda_submitted_at:
            return False
        try:
            settings = self.user.report_settings
        except ReportTimingSettings.DoesNotExist:
            return False
            
        if settings.agenda_policy == 'MORNING_OF':
            deadline = timezone.datetime.combine(self.report_date, settings.agenda_deadline)
            deadline = timezone.make_aware(deadline) if timezone.is_naive(deadline) else deadline
            return self.agenda_submitted_at > deadline
        elif settings.agenda_policy == 'EVENING_BEFORE':
            from datetime import timedelta
            deadline_date = self.report_date - timedelta(days=1)
            deadline = timezone.datetime.combine(deadline_date, settings.agenda_deadline)
            deadline = timezone.make_aware(deadline) if timezone.is_naive(deadline) else deadline
            return self.agenda_submitted_at > deadline
        return False

    @property
    def is_report_late(self):
        if not self.report_submitted_at:
            return False
        try:
            settings = self.user.report_settings
        except ReportTimingSettings.DoesNotExist:
            return False
            
        deadline = timezone.datetime.combine(self.report_date, settings.report_deadline)
        deadline = timezone.make_aware(deadline) if timezone.is_naive(deadline) else deadline
        return self.report_submitted_at > deadline


class DailyReportAttachment(models.Model):
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    attached_file = models.FileField(
        upload_to='daily_reports/attachments/',
        null=True, blank=True
    )
    original_filename = models.CharField(max_length=255, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def get_download_url(self):
        if not self.attached_file:
            return None
        return self.attached_file.url

    def __str__(self):
        return f"Attachment for {self.report.name}"
