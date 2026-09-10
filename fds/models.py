from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# ────────────────────────────────────────────────────────────────
# Choice constants
# ────────────────────────────────────────────────────────────────
CLASS_CATEGORY_CHOICES = [
    ('DANCE', 'Dance'),
    ('ZUMBA', 'Zumba'),
    ('YOGA', 'Yoga'),
]

DAY_CHOICES = [
    ('MON', 'Monday'),
    ('TUE', 'Tuesday'),
    ('WED', 'Wednesday'),
    ('THU', 'Thursday'),
    ('FRI', 'Friday'),
    ('SAT', 'Saturday'),
    ('SUN', 'Sunday'),
]

GENDER_CHOICES = [
    ('MALE', 'Male'),
    ('FEMALE', 'Female'),
    ('OTHER', 'Other'),
]

MODE_OF_PAY_CHOICES = [
    ('ONLINE', 'Online'),
    ('CASH', 'Cash'),
    ('UPI', 'UPI'),
    ('BANK_TRANSFER', 'Bank Transfer'),
    ('CARD', 'Card'),
    ('OTHER', 'Other'),
]

PAYMENT_STATUS_CHOICES = [
    ('PAID', 'Paid'),
    ('PARTIAL', 'Partial'),
    ('PENDING', 'Pending'),
    ('OVERDUE', 'Overdue'),
]


# ────────────────────────────────────────────────────────────────
# 1. Fee Structure (pricing catalog - Sheet 5 Mirror)
# ────────────────────────────────────────────────────────────────
class FdsFeeStructure(models.Model):
    FEE_CATEGORY_CHOICES = [
        ('MONTHLY', 'Monthly Fee'),
        ('PACKAGE_3M', 'Package 3 Months'),
        ('PACKAGE_6M', 'Package 6 Months'),
        ('ADMISSION', 'Admission / Registration Fee'),
        ('TRIAL', 'Trial Fee'),
        ('WEDDING_BASIC', 'Wedding - Basic'),
        ('WEDDING_COUPLE', 'Wedding - Couple'),
        ('WEDDING_PREMIUM', 'Wedding - Premium'),
        ('WEDDING_GROUP', 'Wedding - Family/Group'),
    ]

    category = models.CharField(max_length=100)
    category_name = models.CharField(max_length=150, blank=True, null=True)
    details = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_text = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. 12,000 / 8,000 or 1600")
    notes = models.TextField(blank=True, null=True, help_text="Offers, discounts, notes")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'FDS Fee Structure'

    def __str__(self):
        return f"{self.category} — ₹{self.amount_text or self.amount}"


# ────────────────────────────────────────────────────────────────
# 2. Batch
# ────────────────────────────────────────────────────────────────
class FdsBatch(models.Model):
    BATCH_TYPE_CHOICES = [
        ('REGULAR', 'Regular'),
        ('WEDDING_BASIC', 'Wedding - Basic'),
        ('WEDDING_COUPLE', 'Wedding - Couple'),
        ('WEDDING_PREMIUM', 'Wedding - Premium'),
        ('WEDDING_GROUP', 'Wedding - Family/Group'),
    ]
    BATCH_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('PAUSED', 'Paused'),
    ]

    name = models.CharField(max_length=150)
    batch_type = models.CharField(max_length=20, choices=BATCH_TYPE_CHOICES, default='REGULAR')
    class_category = models.CharField(max_length=10, choices=CLASS_CATEGORY_CHOICES, default='DANCE')
    schedule_days = models.CharField(
        max_length=100,
        blank=True,
        help_text="Comma-separated: MON,WED,FRI"
    )
    time_slot_start = models.TimeField(null=True, blank=True)
    time_slot_end = models.TimeField(null=True, blank=True)
    trainer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fds_batches'
    )
    max_capacity = models.PositiveIntegerField(default=20)
    status = models.CharField(max_length=10, choices=BATCH_STATUS_CHOICES, default='ACTIVE')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['class_category', 'name']
        verbose_name = 'FDS Batch'

    def __str__(self):
        return f"{self.name} ({self.get_class_category_display()})"

    @property
    def enrolled_count(self):
        return self.fds_students.filter(is_active=True).count()

    @property
    def time_display(self):
        if self.time_slot_start and self.time_slot_end:
            return f"{self.time_slot_start.strftime('%I:%M %p')} – {self.time_slot_end.strftime('%I:%M %p')}"
        return "–"


# ────────────────────────────────────────────────────────────────
# 3. Enquiry (Sheet 1 Mirror - All 15 columns)
# ────────────────────────────────────────────────────────────────
class FdsEnquiry(models.Model):
    SOURCE_CHOICES = [
        ('WALK_IN', 'Walk-In'),
        ('INSTAGRAM', 'Instagram'),
        ('FACEBOOK', 'Facebook'),
        ('REFERRAL', 'Referral'),
        ('GOOGLE', 'Google'),
        ('WHATSAPP', 'WhatsApp'),
        ('OTHER', 'Other'),
    ]
    STATUS_CHOICES = [
        ('interested', 'Interested'),
        ('not interested', 'Not Interested'),
        ('will call back', 'Will Call Back'),
        ('NEED CALL BACK', 'Need Call Back'),
        ('trial interested', 'Trial Interested'),
        ('NEW', 'New'),
        ('CONTACTED', 'Contacted'),
        ('TRIAL_SCHEDULED', 'Trial Scheduled'),
        ('CONVERTED', 'Converted'),
        ('LOST', 'Lost / Not Interested'),
    ]
    CLASS_INTEREST_CHOICES = CLASS_CATEGORY_CHOICES + [('MULTIPLE', 'Multiple / Unsure')]

    enquiry_id = models.CharField(max_length=50, unique=True, blank=True)
    date = models.DateField(default=timezone.now)
    name = models.CharField(max_length=200, help_text="Student Name")
    parent_name = models.CharField(max_length=200, blank=True, null=True, help_text="Parent Name")
    location = models.CharField(max_length=200, blank=True, null=True)
    age = models.CharField(max_length=50, blank=True, null=True, help_text="Age (e.g. 5yrs, College student, 30yrs)")
    class_interest = models.CharField(max_length=50, blank=True, default='DANCE')
    source = models.CharField(max_length=150, blank=True, default='WALK_IN', help_text="Source (INSTAGRAM, Facebook ad, etc.)")
    phone = models.CharField(max_length=50, blank=True, null=True)
    whatsapp_no = models.CharField(max_length=50, blank=True, null=True)
    previous_exp = models.CharField(max_length=150, blank=True, null=True, help_text="Previous Exp. (1year, yes,4yrs, etc.)")
    preferred_timing = models.CharField(max_length=150, blank=True, null=True, help_text="Preferred Timing")
    status = models.CharField(max_length=100, blank=True, default='interested')
    follow_up_1 = models.DateField(null=True, blank=True)
    follow_up_2 = models.DateField(null=True, blank=True)
    joined = models.BooleanField(default=False)
    joined_status = models.CharField(max_length=50, blank=True, null=True, help_text="Joined Or Not (Joined, None)")
    remarks = models.TextField(blank=True, null=True, help_text="Remarks / Concerns")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_enquiries_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'FDS Enquiry'
        verbose_name_plural = 'FDS Enquiries'

    def __str__(self):
        return f"{self.enquiry_id} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.enquiry_id:
            last = FdsEnquiry.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.enquiry_id = f"ENQ{next_num:03d}"
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# 4. Trial (Sheet 2 Mirror - All 16 columns)
# ────────────────────────────────────────────────────────────────
class FdsTrial(models.Model):
    STATUS_CHOICES = [
        ('WILL INFORM', 'Will Inform'),
        ('YES', 'Yes'),
        ('SCHEDULED', 'Scheduled'),
        ('COMPLETED', 'Completed'),
        ('NO_SHOW', 'No Show'),
        ('CANCELLED', 'Cancelled'),
    ]

    trial_id = models.CharField(max_length=50, unique=True, blank=True)
    enquiry = models.ForeignKey(
        FdsEnquiry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trials'
    )
    date = models.DateField(default=timezone.now)
    time = models.TimeField(null=True, blank=True)
    time_text = models.CharField(max_length=50, blank=True, null=True, help_text="Time text e.g. 16:30, 18:00")
    name = models.CharField(max_length=200)
    age = models.CharField(max_length=50, blank=True, null=True, help_text="Age e.g. 5, 6, 5 3/4")
    phone = models.CharField(max_length=50, blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    class_category = models.CharField(max_length=50, blank=True, default='DANCE')
    fee_quoted = models.CharField(max_length=50, blank=True, default='', help_text="Fee quoted e.g. 1600/-")
    feedback = models.TextField(blank=True, null=True, help_text="Feedback e.g. SATISFYING,EXCELLENT")
    trainer_rating = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="Rating out of 5"
    )
    status = models.CharField(max_length=100, blank=True, default='WILL INFORM')
    follow_up_date = models.DateField(null=True, blank=True, help_text="Follow up date")
    converted = models.BooleanField(default=False)
    converted_text = models.CharField(max_length=50, blank=True, null=True, help_text="Converted text e.g. JOINED")
    join_date = models.DateField(null=True, blank=True)
    fee_status = models.CharField(max_length=50, blank=True, default='PENDING', help_text="Fee e.g. PENDING")
    remarks = models.TextField(blank=True, null=True, help_text="Remarks e.g. SAT,SUN ,11-12PM")
    conducted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_trials_conducted'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_trials_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'FDS Trial'

    def __str__(self):
        return f"{self.trial_id} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.trial_id:
            last = FdsTrial.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.trial_id = f"TRL{next_num:03d}"
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# 5. Student (Sheet 4 Mirror - REGISTRATION DETAILS)
# ────────────────────────────────────────────────────────────────
class FdsStudent(models.Model):
    STUDENT_TYPE_CHOICES = [
        ('REGULAR', 'Regular Student'),
        ('WEDDING_MEMBER', 'Wedding Group Member'),
    ]

    student_id = models.CharField(max_length=50, unique=True, blank=True)
    student_type = models.CharField(max_length=20, choices=STUDENT_TYPE_CHOICES, default='REGULAR')
    name = models.CharField(max_length=200)
    joining_date = models.DateField(default=timezone.now)
    age_gender = models.CharField(max_length=50, blank=True, null=True, help_text="Age & Gender e.g. 5/F, 27/F, 6,F")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    parent_name = models.CharField(max_length=200, blank=True, null=True)
    contact_no = models.CharField(max_length=50, blank=True, null=True)
    emergency_contact_no = models.CharField(max_length=50, blank=True, null=True)
    whatsapp_no = models.CharField(max_length=50, blank=True, null=True)
    batch = models.ForeignKey(
        FdsBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_students'
    )
    batch_time_text = models.CharField(max_length=150, blank=True, null=True, help_text="Batch/Time e.g. SUN,SAT ,11-12pm")
    medical_condition = models.CharField(max_length=255, default='NO', blank=True, null=True)
    media_consent = models.BooleanField(
        default=False,
        help_text="Consent to use photos/videos for media"
    )
    pickup_person_1_no = models.CharField(max_length=50, blank=True, null=True)
    can_leave_alone = models.CharField(max_length=20, default='NO', blank=True, null=True, help_text="Can Leave alone e.g. NO, YES")
    fee_paid_date = models.DateField(null=True, blank=True, help_text="Admission Fee /Monthly fee Paid Date")
    admission_fee_paid_date = models.DateField(null=True, blank=True)
    fee_structure = models.ForeignKey(
        FdsFeeStructure, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students'
    )
    is_active = models.BooleanField(default=True)
    # Lineage tracking (optional links)
    enquiry = models.OneToOneField(
        FdsEnquiry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='converted_student'
    )
    trial = models.OneToOneField(
        FdsTrial, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='converted_student'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_students_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'FDS Student'

    def __str__(self):
        return f"{self.student_id} — {self.name}"

    @property
    def age(self):
        if self.date_of_birth:
            today = timezone.now().date()
            dob = self.date_of_birth
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if self.age_gender:
            parts = self.age_gender.replace(',', '/').split('/')
            return parts[0].strip()
        return None

    @property
    def class_category(self):
        return self.batch.class_category if self.batch else None

    def save(self, *args, **kwargs):
        if not self.student_id:
            last = FdsStudent.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.student_id = f"FDSKTM{next_num:03d}"
        if not self.fee_paid_date and self.admission_fee_paid_date:
            self.fee_paid_date = self.admission_fee_paid_date
        elif not self.admission_fee_paid_date and self.fee_paid_date:
            self.admission_fee_paid_date = self.fee_paid_date
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# 6. Wedding Group (separate entity from regular students)
# ────────────────────────────────────────────────────────────────
class FdsWeddingGroup(models.Model):
    PACKAGE_TYPE_CHOICES = [
        ('BASIC', 'Wedding - Basic (2hr×5 classes, max 8 people)'),
        ('COUPLE', 'Wedding - Couple (1hr×6 classes)'),
        ('PREMIUM', 'Wedding - Premium (2hr×10 classes, upto 20 people)'),
        ('FAMILY_GROUP', 'Wedding - Family/Group (2hr×12 classes, upto 30 people)'),
    ]
    STATUS_CHOICES = [
        ('ENQUIRY', 'Enquiry'),
        ('CONFIRMED', 'Confirmed'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    group_id = models.CharField(max_length=20, unique=True, blank=True)
    event_name = models.CharField(max_length=200, help_text="e.g., Riya & Arun Wedding")
    event_date = models.DateField(null=True, blank=True)
    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES)
    batch = models.ForeignKey(
        FdsBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='wedding_groups'
    )
    lead_contact_name = models.CharField(max_length=200)
    lead_contact_phone = models.CharField(max_length=20)
    total_members = models.PositiveIntegerField(default=1)
    total_classes_booked = models.PositiveIntegerField(default=0)
    classes_completed = models.PositiveIntegerField(default=0)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ENQUIRY')
    trainer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_wedding_groups'
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_wedding_groups_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'FDS Wedding Group'

    def __str__(self):
        return f"{self.group_id} — {self.event_name}"

    @property
    def balance(self):
        return self.fee_amount - self.amount_paid

    @property
    def classes_remaining(self):
        return self.total_classes_booked - self.classes_completed

    def save(self, *args, **kwargs):
        if not self.group_id:
            last = FdsWeddingGroup.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.group_id = f"FDS-WED-{next_num:04d}"
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# 7. Attendance
# ────────────────────────────────────────────────────────────────
class FdsAttendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LEAVE', 'Leave'),
        ('MAKEUP', 'Makeup Class'),
        ('HOLIDAY', 'Holiday / Studio Closed'),
    ]

    student = models.ForeignKey(
        FdsStudent, on_delete=models.CASCADE,
        related_name='fds_attendances'
    )
    batch = models.ForeignKey(
        FdsBatch, on_delete=models.CASCADE,
        related_name='fds_attendances'
    )
    date = models.DateField()
    class_start_time = models.TimeField(null=True, blank=True)
    class_end_time = models.TimeField(null=True, blank=True)
    class_category = models.CharField(
        max_length=10, choices=CLASS_CATEGORY_CHOICES,
        help_text="Denormalized from batch for fast filtering"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PRESENT')
    late_arrival = models.BooleanField(default=False)
    marked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='fds_attendances_marked'
    )
    notes = models.CharField(max_length=300, blank=True, null=True)
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'date', 'batch']
        ordering = ['-date']
        verbose_name = 'FDS Attendance'
        verbose_name_plural = 'FDS Attendance'

    def __str__(self):
        return f"{self.student.name} — {self.date} — {self.status}"


# ────────────────────────────────────────────────────────────────
# 8. Fee Accounts & Payments (Sheet 6 Mirror - FEES COLLECTION 2026)
# ────────────────────────────────────────────────────────────────
class FdsStudentFeeAccount(models.Model):
    ACCOUNT_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PARTIAL', 'Partial'),
        ('OVERDUE', 'Overdue'),
        ('SETTLED', 'Settled'),
    ]

    student = models.OneToOneField(
        'FdsStudent', on_delete=models.CASCADE, related_name='fee_account'
    )
    active_package = models.ForeignKey(
        'FdsFeeStructure', on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=ACCOUNT_STATUS_CHOICES, default='ACTIVE')
    total_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'FDS Student Fee Account'

    def __str__(self):
        return f"{self.student.name} - Account"

    def recalculate(self, save=True):
        collections = self.student.fds_payments.all()
        self.total_paid = sum(c.paid_amount for c in collections)
        
        billed_dict = {}
        for c in collections:
            if c.fee_month and c.fee_year:
                key = (c.fee_month, c.fee_year, c.fees_type_id)
                current_max = billed_dict.get(key, 0)
                billed_dict[key] = max(current_max, c.total_fees)
            elif c.total_fees > 0:
                key = f"one_off_{c.id}"
                billed_dict[key] = c.total_fees
                
        self.total_due = sum(billed_dict.values())
        self.balance_due = max(0, self.total_due - self.total_paid)
        
        if self.balance_due == 0 and self.total_due > 0:
            self.status = 'SETTLED'
        elif self.balance_due > 0 and self.total_paid > 0:
            self.status = 'PARTIAL'
        elif self.balance_due > 0:
            self.status = 'ACTIVE'
            
        if save:
            self.save(update_fields=['total_paid', 'total_due', 'balance_due', 'status', 'updated_at'])


class FdsFeesCollection(models.Model):
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    payment_id = models.CharField(max_length=50, unique=True, blank=True)
    student = models.ForeignKey(
        FdsStudent, on_delete=models.CASCADE,
        related_name='fds_payments', null=True, blank=True
    )
    student_id_code = models.CharField(max_length=50, blank=True, null=True, help_text="Student ID e.g. FDSKTM001")
    student_name_text = models.CharField(max_length=200, blank=True, null=True, help_text="Student Name from sheet")
    # For wedding group payments (no individual student)
    wedding_group = models.ForeignKey(
        FdsWeddingGroup, on_delete=models.CASCADE,
        related_name='fds_payments', null=True, blank=True
    )
    pay_date = models.DateField(default=timezone.now, null=True, blank=True)
    batch_time_text = models.CharField(max_length=150, blank=True, null=True, help_text="Batch/Time from sheet")
    fees_type = models.ForeignKey(
        FdsFeeStructure, on_delete=models.SET_NULL,
        related_name='collections', null=True, blank=True
    )
    fees_type_text = models.CharField(max_length=100, blank=True, default='MONTHLY', help_text="Fees Type e.g. MONTHLY")
    # For monthly tracking
    fee_month = models.PositiveIntegerField(choices=MONTH_CHOICES, null=True, blank=True)
    fee_year = models.PositiveIntegerField(null=True, blank=True, default=2026)
    month_name = models.CharField(max_length=50, blank=True, null=True, help_text="Month from sheet e.g. SEPTEMBER")
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount_text = models.CharField(max_length=50, blank=True, null=True, help_text="Paid Amount text e.g. 1600/-")
    total_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mode_of_pay = models.CharField(max_length=50, blank=True, default='ONLINE', help_text="Mode Of Pay e.g. ONLINE, CASH")
    transaction_id = models.CharField(max_length=100, blank=True, null=True, help_text="TRANSACTION ID e.g. 110622717946")
    pdf_link = models.URLField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, default='PAID')
    status_remarks = models.CharField(max_length=255, blank=True, null=True, help_text="Status/Remarks e.g. OFFER PRICE")
    remarks = models.TextField(blank=True, null=True)
    collected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_payments_collected'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pay_date', '-created_at']
        verbose_name = 'FDS Fees Collection'

    def __str__(self):
        name = self.student.name if self.student else (self.student_name_text or (self.wedding_group.event_name if self.wedding_group else "Unknown"))
        return f"{self.payment_id} — {name} — ₹{self.paid_amount}"

    def save(self, *args, **kwargs):
        if not self.payment_id:
            last = FdsFeesCollection.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.payment_id = f"FDS-PAY-{next_num:04d}"
        if self.student:
            if not self.student_id_code:
                self.student_id_code = self.student.student_id
            if not self.student_name_text:
                self.student_name_text = self.student.name
            if not self.batch_time_text and self.student.batch_time_text:
                self.batch_time_text = self.student.batch_time_text
        super().save(*args, **kwargs)

        if self.student and hasattr(self.student, 'fee_account'):
            self.student.fee_account.recalculate()


# ────────────────────────────────────────────────────────────────
# 9. Lead Sourcing (Sheet 3 Mirror - All 6 Directory Categories)
# ────────────────────────────────────────────────────────────────
class FdsLeadSourcing(models.Model):
    CATEGORY_CHOICES = [
        ('COLLEGES', 'Prominent Colleges in & around Kottayam'),
        ('SCHOOLS', 'Prominent Schools in & around Kottayam'),
        ('CLUBS', 'Recreation & Social Clubs in Kottayam'),
        ('RESIDENTS', 'Resident Welfare Associations & Housing Hubs (Proper Kottayam)'),
        ('VILLAS', 'Prominent Villa Projects & Gated Communities in Kottayam'),
        ('BUILDERS', 'Residency / Builder'),
    ]

    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='COLLEGES')
    name = models.CharField(max_length=255, help_text="Institution / School / Club / Association / Villa / Builder Name")
    location = models.CharField(max_length=255, blank=True, null=True, help_text="Location / Area / Landmark")
    phone = models.CharField(max_length=200, blank=True, null=True, help_text="Phone Number / Contact Number")
    email_website = models.CharField(max_length=255, blank=True, null=True, help_text="Email / Website")
    extra_info = models.CharField(max_length=255, blank=True, null=True, help_text="Board/Type for schools, Contact/Remarks for associations")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'FDS Lead Sourcing'
        verbose_name_plural = 'FDS Lead Sourcing Entries'

    def __str__(self):
        return f"[{self.category}] {self.name}"
