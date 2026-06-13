from django.db import models

from django.conf import settings


class AttendanceDocument(models.Model):
    name = models.CharField(max_length=255, verbose_name="Document Name")
    date = models.DateField(verbose_name="Date")
    month = models.CharField(max_length=100, verbose_name="Month")
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
    document = models.FileField(
        upload_to='attendance_documents/',
        verbose_name="Attendance Document",
        help_text="Upload attendance document (PDF, Excel, Image, etc.)",
        blank=True,
        null=True
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

    resume = models.FileField(
        upload_to="hr/candidate_resumes/",
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


class Branch(models.Model):
    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
    ]
    name = models.CharField(max_length=255)
    company = models.CharField(max_length=10, choices=COMPANY_CHOICES, default='LP', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return f"{self.name} - {self.company}"


class Location(models.Model):
    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
    ]
    name = models.CharField(max_length=255)
    company = models.CharField(max_length=10, choices=COMPANY_CHOICES, default='LP', db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='locations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.company}"


class AssetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Asset Categories'

    def __str__(self):
        return self.name


class Asset(models.Model):
    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
    ]

    name = models.CharField(max_length=255)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    company = models.CharField(max_length=10, choices=COMPANY_CHOICES, default='LP', db_index=True)
    
    category = models.ForeignKey(AssetCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets')
    assigned_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets', help_text="Physical location where this asset is placed")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets', help_text="Branch this asset belongs to")
    
    primary_sim = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='primary_for',
        help_text="Primary SIM assigned to this device"
    )
    secondary_sim = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='secondary_for',
        help_text="Secondary SIM assigned to this device"
    )
    provider = models.CharField(max_length=100, blank=True, null=True, help_text="Telecom Provider (for SIM Cards)")
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_assets',
        help_text="Staff member currently holding this asset"
    )
    
    attachment = models.FileField(
        upload_to='hr/assets/',
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
        category_name = self.category.name if self.category else "Uncategorized"
        return f"{self.name} ({category_name}) - {self.company}"
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Sync assigned_to with primary_sim and secondary_sim
        if self.primary_sim and self.primary_sim.assigned_to != self.assigned_to:
            self.primary_sim.assigned_to = self.assigned_to
            self.primary_sim.save()
            
        if self.secondary_sim and self.secondary_sim.assigned_to != self.assigned_to:
            self.secondary_sim.assigned_to = self.assigned_to
            self.secondary_sim.save()