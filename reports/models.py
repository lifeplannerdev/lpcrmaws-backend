from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField
import urllib.parse

User = get_user_model()


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
    submission_time = models.DateTimeField(auto_now_add=True, null=True)
    next_day_agenda = models.TextField(blank=True, null=True)
    name = models.CharField(
        max_length=200,
        verbose_name='Report Name',
        help_text='Give a title to your daily report'
    )
    heading = models.CharField(
        max_length=300,
        verbose_name='Report Heading',
        help_text='Brief summary of your daily report'
    )
    report_text = models.TextField(
        verbose_name='Daily Update',
        help_text='Share your daily progress and updates'
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


class DailyReportAttachment(models.Model):
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    attached_file = CloudinaryField(
        resource_type='auto',
        folder='daily_reports/attachments',
    )
    original_filename = models.CharField(max_length=255, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def get_download_url(self):
        
        if not self.attached_file:
            return None

        url = self.attached_file.url
        if url.startswith('http://'):
            url = url.replace('http://', 'https://')

        filename = self.original_filename or "download"

        safe_filename = filename.replace(' ', '_')

        encoded_name = urllib.parse.quote(
            safe_filename,
            safe='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-'
        )

        if '/upload/' in url:
            url = url.replace('/upload/', f'/upload/fl_attachment:{encoded_name}/', 1)

        return url

    def __str__(self):
        return f"Attachment for {self.report.name}"
