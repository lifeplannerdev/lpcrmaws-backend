from django.db import models

from django.conf import settings


class AttendanceDocument(models.Model):
    name = models.CharField(max_length=255, verbose_name="Document Name")
    date = models.DateField(verbose_name="Date")
    month = models.CharField(max_length=100, verbose_name="Month")
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')], default='LP', db_index=True)
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
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')], default='LP', db_index=True)
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

    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')], default='LP', db_index=True)
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
        ('FDS', 'FILMAATIC'),
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
        ('FDS', 'FILMAATIC'),
    ]
    name = models.CharField(max_length=255)
    company = models.CharField(max_length=10, choices=COMPANY_CHOICES, default='LP', db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='locations')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_locations',
        help_text="Person responsible for this space"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.company}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class AssetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    classification = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Grouping classification (e.g., Communication Systems, System Classification)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Asset Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.classification:
            self.classification = self.get_classification()
        super().save(*args, **kwargs)

    def get_classification(self):
        if self.classification:
            return self.classification
        clean_name = (self.name or '').strip().lower()
        classification_map = {
            # Communication Systems
            'mobile': 'Communication Systems',
            'mobiles': 'Communication Systems',
            'mobile phone': 'Communication Systems',
            'mobile phones': 'Communication Systems',
            'sim': 'Communication Systems',
            'sims': 'Communication Systems',
            'sim card': 'Communication Systems',
            'sim cards': 'Communication Systems',
            'phone': 'Communication Systems',
            'phones': 'Communication Systems',
            'telephone': 'Communication Systems',
            'telephones': 'Communication Systems',
            'smartphone': 'Communication Systems',
            'smartphones': 'Communication Systems',
            'tablet': 'Communication Systems',
            'tablets': 'Communication Systems',
            'iphone': 'Communication Systems',
            'iphones': 'Communication Systems',
            'ipad': 'Communication Systems',
            'ipads': 'Communication Systems',
            'cellphone': 'Communication Systems',
            'cellphones': 'Communication Systems',
            'handset': 'Communication Systems',
            'handsets': 'Communication Systems',
            'intercom': 'Communication Systems',
            'voip': 'Communication Systems',

            # System Classification
            'cpu': 'System Classification',
            'cpus': 'System Classification',
            'keyboard': 'System Classification',
            'keyboards': 'System Classification',
            'mouse': 'System Classification',
            'mice': 'System Classification',
            'pc': 'System Classification',
            'pcs': 'System Classification',
            'laptop': 'System Classification',
            'laptops': 'System Classification',
            'macbook': 'System Classification',
            'macbooks': 'System Classification',
            'thinkpad': 'System Classification',
            'thinkpads': 'System Classification',
            'imac': 'System Classification',
            'imacs': 'System Classification',
            'chromebook': 'System Classification',
            'chromebooks': 'System Classification',
            'workstation': 'System Classification',
            'workstations': 'System Classification',
            'server': 'System Classification',
            'servers': 'System Classification',
            'lap charger': 'System Classification',
            'laptop charger': 'System Classification',
            'moniter': 'System Classification',
            'monitors': 'System Classification',
            'monitor': 'System Classification',
            'screen': 'System Classification',
            'screens': 'System Classification',
            'display': 'System Classification',
            'displays': 'System Classification',
            'wify adaptor': 'System Classification',
            'wifi adaptor': 'System Classification',
            'wifi adapter': 'System Classification',
            'wifi adapters': 'System Classification',
            'hard drive': 'System Classification',
            'hard drives': 'System Classification',
            'hard disk': 'System Classification',
            'hard disks': 'System Classification',
            'ram': 'System Classification',
            'desktop': 'System Classification',
            'desktops': 'System Classification',

            # Office Furniture
            'chair': 'Office Furniture',
            'chairs': 'Office Furniture',
            'office chair': 'Office Furniture',
            'office chairs': 'Office Furniture',
            'table': 'Office Furniture',
            'tables': 'Office Furniture',
            'teapoy': 'Office Furniture',
            'teapoys': 'Office Furniture',
            'sofa': 'Office Furniture',
            'sofas': 'Office Furniture',
            'shelf': 'Office Furniture',
            'shelves': 'Office Furniture',
            'stand': 'Office Furniture',
            'stands': 'Office Furniture',
            'desk': 'Office Furniture',
            'desks': 'Office Furniture',
            'cupboard': 'Office Furniture',
            'cupboards': 'Office Furniture',

            # Electronics & Appliances
            'ac': 'Electronics & Appliances',
            'air conditioner': 'Electronics & Appliances',
            'fan': 'Electronics & Appliances',
            'fans': 'Electronics & Appliances',
            'tv': 'Electronics & Appliances',
            'television': 'Electronics & Appliances',
            'tv & remote': 'Electronics & Appliances',
            'home theatre': 'Electronics & Appliances',
            'speaker': 'Electronics & Appliances',
            'speakers': 'Electronics & Appliances',
            'ups': 'Electronics & Appliances',
            'projector': 'Electronics & Appliances',
            'projectors': 'Electronics & Appliances',

            # Office Equipment & Utilities
            'printer': 'Office Equipment & Utilities',
            'printers': 'Office Equipment & Utilities',
            'camera': 'Office Equipment & Utilities',
            'cameras': 'Office Equipment & Utilities',
            'white board': 'Office Equipment & Utilities',
            'whiteboard': 'Office Equipment & Utilities',
            'whiteboards': 'Office Equipment & Utilities',
            'id card': 'Office Equipment & Utilities',
            'id cards': 'Office Equipment & Utilities',
            'key set box': 'Office Equipment & Utilities',
            'waste in': 'Office Equipment & Utilities',
            'waste bin': 'Office Equipment & Utilities',
            'waste bins': 'Office Equipment & Utilities',
            'wastebin': 'Office Equipment & Utilities',
            'wastebins': 'Office Equipment & Utilities',
            'scanner': 'Office Equipment & Utilities',
            'scanners': 'Office Equipment & Utilities',
        }
        if clean_name in classification_map:
            return classification_map[clean_name]

        # Keyword and token fallback for compound/custom category names (e.g. 'Conference Chairs', 'Laser Printer')
        import re
        tokens = set(re.findall(r'\b[a-z0-9]+\b', clean_name))

        if tokens & {'mobile', 'mobiles', 'sim', 'sims', 'phone', 'phones', 'telephone', 'telephones', 'smartphone', 'smartphones', 'tablet', 'tablets', 'iphone', 'iphones', 'ipad', 'ipads', 'cellphone', 'cellphones', 'handset', 'handsets', 'voip', 'intercom'} or 'sim card' in clean_name or 'mobile phone' in clean_name:
            return 'Communication Systems'

        if tokens & {'cpu', 'cpus', 'keyboard', 'keyboards', 'mouse', 'mice', 'pc', 'pcs', 'laptop', 'laptops', 'macbook', 'macbooks', 'thinkpad', 'thinkpads', 'imac', 'imacs', 'chromebook', 'chromebooks', 'workstation', 'workstations', 'server', 'servers', 'charger', 'chargers', 'monitor', 'monitors', 'moniter', 'screen', 'screens', 'display', 'displays', 'adapter', 'adaptor', 'ram', 'desktop', 'desktops', 'router', 'routers', 'switch', 'switches', 'hub', 'hubs', 'webcam', 'webcams', 'headphone', 'headphones', 'headset', 'headsets', 'earphone', 'earphones', 'mic', 'mics', 'microphone', 'microphones', 'dock', 'docks'} or 'hard disk' in clean_name or 'hard drive' in clean_name or 'lap charger' in clean_name or 'wifi router' in clean_name or 'network switch' in clean_name:
            return 'System Classification'

        if tokens & {'chair', 'chairs', 'table', 'tables', 'teapoy', 'teapoys', 'sofa', 'sofas', 'shelf', 'shelves', 'stand', 'stands', 'desk', 'desks', 'cupboard', 'cupboards'} or 'office chair' in clean_name:
            return 'Office Furniture'

        if tokens & {'ac', 'fan', 'fans', 'tv', 'television', 'speaker', 'speakers', 'ups', 'projector', 'projectors', 'cooler', 'coolers', 'refrigerator', 'refrigerators', 'fridge', 'fridges', 'dispenser', 'dispensers', 'microwave', 'microwaves'} or 'air condition' in clean_name or 'home theatre' in clean_name or 'air cooler' in clean_name or 'water dispenser' in clean_name:
            return 'Electronics & Appliances'

        if tokens & {'printer', 'printers', 'camera', 'cameras', 'whiteboard', 'scanner', 'scanners', 'bin', 'bins', 'shredder', 'shredders', 'extinguisher', 'extinguishers'} or 'white board' in clean_name or 'id card' in clean_name or 'key set' in clean_name or 'waste' in clean_name or 'paper shredder' in clean_name or 'fire extinguisher' in clean_name:
            return 'Office Equipment & Utilities'

        return 'General Assets'


class Asset(models.Model):
    COMPANY_CHOICES = [
        ('LP', 'LP'),
        ('FLAG', 'FLAG'),
        ('FDS', 'FILMAATIC'),
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

    @property
    def classification(self):
        cat_cls = self.category.get_classification() if self.category else None
        if cat_cls and cat_cls != 'General Assets':
            return cat_cls
        if self.provider:
            return 'Communication Systems'
        if self.name:
            inferred = AssetCategory(name=self.name).get_classification()
            if inferred != 'General Assets':
                return inferred
        return cat_cls or 'General Assets'
        
    def save(self, *args, **kwargs):
        if self.assigned_location and not self.branch:
            self.branch = self.assigned_location.branch
        super().save(*args, **kwargs)

class DocumentDetail(models.Model):
    COMPANY_CHOICES = [
        ('LP', 'LP (All Branches)'),
        ('LP_HQ', 'LP — HQ'),
        ('LP_KOCHI', 'LP — Kochi'),
        ('FLAG', 'FLAG'),
        ('FLAG_KOCHI', 'FLAG — Kochi'),
        ('FDS', 'FDS (All Branches)'),
        ('FDS_KOCHI', 'FDS — Kochi'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('expired', 'Expired'),
    ]

    title = models.CharField(max_length=255, verbose_name="Document Title")
    document_type = models.CharField(max_length=100, verbose_name="Document Type", help_text="e.g. License, Contract, Certification")
    description = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True, verbose_name="Internal Notes")
    
    issue_date = models.DateField(blank=True, null=True, verbose_name="Issue Date")
    expiry_date = models.DateField(verbose_name="Expiry Date")
    
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='active',
        db_index=True, verbose_name="Status"
    )
    renewal_interval_days = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name="Renewal Interval (Days)",
        help_text="e.g. 365 for annual. Used to compute next renewal date."
    )
    next_renewal_date = models.DateField(
        blank=True, null=True, verbose_name="Next Renewal Date"
    )

    company = models.CharField(max_length=20, choices=COMPANY_CHOICES, default='LP', db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Document Detail'
        verbose_name_plural = 'Document Details'
        ordering = ['expiry_date']

    def save(self, *args, **kwargs):
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now().date()

        # Auto-compute next renewal date when interval is set
        if self.renewal_interval_days and self.expiry_date:
            self.next_renewal_date = self.expiry_date + timedelta(days=self.renewal_interval_days)

        # Auto-update status unless manually set to 'paid'
        if self.status != 'paid':
            if today > self.expiry_date:
                self.status = 'expired'
            elif self.expiry_date <= today + timedelta(days=30):
                self.status = 'overdue'
            else:
                self.status = 'active'

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.company}) - Expires {self.expiry_date}"