from django.db import models
from cloudinary.models import CloudinaryField
from django.conf import settings


class AttendanceDocument(models.Model):
    name = models.CharField(max_length=255, verbose_name="Document Name")
    date = models.DateField(verbose_name="Date")
    month = models.CharField(max_length=100, verbose_name="Month")
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    document = CloudinaryField(
        resource_type='auto',
        folder='hr/attendance_documents/',
        null=True,
        blank=True,
        verbose_name="Attendance Document",
        help_text="Upload attendance document (PDF, Excel, Image, etc.)"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Attendance Document'
        verbose_name_plural = 'Attendance Documents'
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.name} - {self.date}"


class Penalty(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="penalties",
    )
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    act = models.CharField(max_length=1000)
    amount = models.IntegerField(default=0, blank=True, verbose_name='Amount')
    month = models.CharField(max_length=100, verbose_name="Month")
    date = models.DateField()

    class Meta:
        verbose_name = "Penalty"
        verbose_name_plural = "Penalties"
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.username if self.user else 'No User'} - {self.month} - ₹{self.amount}"



class Candidate(models.Model):
    STATUS_CHOICES = [
        ("applied", "Applied"),
        ("interviewed", "Interviewed"),
        ("selected", "Selected"),
        ("rejected", "Rejected"),
    ]

    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)

    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    position_applied = models.CharField(max_length=255)

    resume = CloudinaryField(
        resource_type="auto",
        folder="hr/candidate_resumes/",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="applied"
    )

    interview_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True, null=True)

    rating = models.IntegerField(
        null=True,
        blank=True,
        help_text="Rate candidate out of 10"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.position_applied} ({self.status})"


class Asset(models.Model):
    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('ASSIGNED', 'Assigned'),
        ('MAINTENANCE', 'In Maintenance'),
        ('RETIRED', 'Retired')
    ]

    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
    ]

    name = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    company = models.CharField(max_length=10, choices=COMPANY_CHOICES, default='LP', db_index=True)
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_assets',
        help_text="Staff member currently holding this asset"
    )
    
    attachment = CloudinaryField(
        resource_type='auto',
        folder='hr/assets/',
        null=True,
        blank=True,
        verbose_name="Asset Photo/Invoice"
    )
    
    purchase_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Asset'
        verbose_name_plural = 'Assets'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.asset_type}) - {self.company}"