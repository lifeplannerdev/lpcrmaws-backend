from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# ────────────────────────────────────────────────────────────────
# Choice constants
# ────────────────────────────────────────────────────────────────
FDS_BRANCH_CHOICES = [
    ('KOTTAYAM', 'Kottayam'),
    ('KOCHI', 'Kochi'),
]

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
    ('CASH', 'Cash'),
    ('UPI', 'UPI'),
    ('ONLINE', 'Online'),
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
# 1. Fee Structure (pricing catalog)
# ────────────────────────────────────────────────────────────────
class FdsFeeStructure(models.Model):
    FEE_CATEGORY_CHOICES = [
        ('DANCE', 'Dance'),
        ('ZUMBA', 'Zumba'),
        ('YOGA', 'Yoga'),
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

    name = models.CharField(max_length=150, blank=True, default='')
    category = models.CharField(max_length=50, default='DANCE')
    batch_type = models.CharField(max_length=50, default='WEEKEND', blank=True)
    admission_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_months = models.PositiveIntegerField(default=1)
    sessions_per_week = models.PositiveIntegerField(default=2)
    details = models.TextField(blank=True)
    notes = models.TextField(blank=True, null=True, help_text="Offers, discounts, notes")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'FDS Fee Structure'

    def get_category_display(self):
        if self.name:
            return self.name
        choices = dict(self.FEE_CATEGORY_CHOICES)
        return choices.get(self.category, self.category.title() if self.category else '')

    def __str__(self):
        title = self.name or dict(self.FEE_CATEGORY_CHOICES).get(self.category, self.category)
        return f"{title} — ₹{self.amount}"


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
    branch = models.CharField(max_length=20, choices=FDS_BRANCH_CHOICES, default='KOTTAYAM')
    coordinator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fds_batches_coordinated'
    )
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
# 3. Enquiry
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
        ('NEW', 'New'),
        ('CONTACTED', 'Contacted'),
        ('TRIAL_SCHEDULED', 'Trial Scheduled'),
        ('CONVERTED', 'Converted'),
        ('LOST', 'Lost / Not Interested'),
    ]
    CLASS_INTEREST_CHOICES = CLASS_CATEGORY_CHOICES + [('MULTIPLE', 'Multiple / Unsure')]

    enquiry_id = models.CharField(max_length=20, unique=True, blank=True)
    date = models.DateField(default=timezone.now)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True, null=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    class_interest = models.CharField(max_length=10, choices=CLASS_INTEREST_CHOICES, default='DANCE')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='WALK_IN')
    phone = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_no = models.CharField(max_length=20, blank=True, null=True)
    preferred_timing = models.CharField(max_length=100, blank=True, null=True)
    branch = models.CharField(max_length=20, choices=FDS_BRANCH_CHOICES, default='KOTTAYAM')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    follow_up_1 = models.DateField(null=True, blank=True)
    follow_up_2 = models.DateField(null=True, blank=True)
    joined = models.BooleanField(default=False)
    remarks = models.TextField(blank=True, null=True)
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
            self.enquiry_id = f"FDS-ENQ-{next_num:04d}"
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# 4. Trial
# ────────────────────────────────────────────────────────────────
class FdsTrial(models.Model):
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('COMPLETED', 'Completed'),
        ('NO_SHOW', 'No Show'),
        ('CANCELLED', 'Cancelled'),
    ]

    trial_id = models.CharField(max_length=20, unique=True, blank=True)
    enquiry = models.ForeignKey(
        FdsEnquiry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trials'
    )
    date = models.DateField(default=timezone.now)
    time = models.TimeField(null=True, blank=True)
    name = models.CharField(max_length=200)
    age = models.PositiveIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    class_category = models.CharField(max_length=10, choices=CLASS_CATEGORY_CHOICES, default='DANCE')
    branch = models.CharField(max_length=20, choices=FDS_BRANCH_CHOICES, default='KOTTAYAM')
    fee_quoted = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    feedback = models.TextField(blank=True, null=True)
    trainer_rating = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Rating out of 5"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    converted = models.BooleanField(default=False)
    join_date = models.DateField(null=True, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
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
            self.trial_id = f"FDS-TRL-{next_num:04d}"
        super().save(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# 5. Student
# ────────────────────────────────────────────────────────────────
class FdsStudent(models.Model):
    STUDENT_TYPE_CHOICES = [
        ('REGULAR', 'Regular Student'),
        ('WEDDING_MEMBER', 'Wedding Group Member'),
    ]

    student_id = models.CharField(max_length=20, unique=True, blank=True)
    student_type = models.CharField(max_length=20, choices=STUDENT_TYPE_CHOICES, default='REGULAR')
    branch = models.CharField(max_length=20, choices=FDS_BRANCH_CHOICES, default='KOTTAYAM')
    name = models.CharField(max_length=200)
    joining_date = models.DateField(default=timezone.now)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    parent_name = models.CharField(max_length=200, blank=True, null=True)
    contact_no = models.CharField(max_length=20, blank=True, null=True)
    emergency_contact_no = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_no = models.CharField(max_length=20, blank=True, null=True)
    batch = models.ForeignKey(
        FdsBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_students'
    )
    medical_condition = models.TextField(blank=True, null=True)
    media_consent = models.BooleanField(
        default=False,
        help_text="Consent to use photos/videos for media"
    )
    pickup_person_1_no = models.CharField(max_length=20, blank=True, null=True)
    can_leave_alone = models.BooleanField(default=False)
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
        return None

    @property
    def class_category(self):
        return self.batch.class_category if self.batch else None

    def save(self, *args, **kwargs):
        if not self.student_id:
            last = FdsStudent.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.student_id = f"FDS-STU-{next_num:04d}"
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
    branch = models.CharField(max_length=20, choices=FDS_BRANCH_CHOICES, default='KOTTAYAM')
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
    coordinator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_wedding_groups_coordinated'
    )
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
    # Stored from batch at time of marking (for historical accuracy even if batch changes)
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
# 8. Fee Accounts & Payments
# ────────────────────────────────────────────────────────────────

class FdsStudentFeeAccount(models.Model):
    ACCOUNT_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PARTIAL', 'Partial'),
        ('OVERDUE', 'Overdue'),
        ('SETTLED', 'Settled'),
        ('RESTRUCTURED', 'Restructured'),
        ('WAIVED', 'Waived'),
    ]

    PLAN_TYPE_CHOICES = [
        ('ONE_TIME', 'One Time'),
        ('INSTALLMENT', 'Installment'),
        ('MONTHLY', 'Monthly'),
        ('CUSTOM', 'Custom'),
        ('PACKAGE', 'Package'),
    ]

    student = models.OneToOneField(
        'FdsStudent', on_delete=models.CASCADE, related_name='fee_account'
    )
    active_package = models.ForeignKey(
        'FdsFeeStructure', on_delete=models.SET_NULL, null=True, blank=True
    )
    plan_code = models.CharField(max_length=80, blank=True)
    plan_name = models.CharField(max_length=150, blank=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default='PACKAGE')
    status = models.CharField(max_length=20, choices=ACCOUNT_STATUS_CHOICES, default='ACTIVE', db_index=True)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    registration_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_day = models.PositiveIntegerField(default=10)
    start_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True, db_index=True)
    last_payment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'FDS Student Fee Account'

    def __str__(self):
        return f"{self.student.name} - Account"

    def recalculate(self, save=True):
        # 1. Total paid from collections
        if self.payments.exists():
            payments_qs = self.payments.all()
        elif self.student:
            payments_qs = self.student.fds_payments.all()
        else:
            payments_qs = FdsFeesCollection.objects.none()

        self.total_paid = payments_qs.aggregate(t=models.Sum('paid_amount')).get('t') or Decimal('0')
        latest_payment = payments_qs.order_by('-pay_date').first()
        self.last_payment_date = latest_payment.pay_date if latest_payment else None

        # 2. Check installments vs non-installment accounts
        inst_qs = self.installments.all()
        if inst_qs.exists():
            today = timezone.localdate()
            overdue_inst = Decimal('0')
            for inst in inst_qs:
                inst.recalculate(save=True)
                if inst.due_date < today and inst.balance_amount > 0:
                    inst.status = 'OVERDUE'
                    inst.save(update_fields=['status'])
                    overdue_inst += inst.balance_amount

            inst_total = inst_qs.aggregate(
                sched=models.Sum('scheduled_amount'),
                bal=models.Sum('balance_amount')
            )
            total_scheduled = inst_total['sched'] or Decimal('0')
            installment_balance = inst_total['bal'] or Decimal('0')
            self.total_due = max(self.total_paid, total_scheduled)
            self.balance_due = max(Decimal('0'), installment_balance)
            self.overdue_amount = overdue_inst

            next_inst = self.installments.filter(status__in=['PENDING', 'PARTIAL', 'OVERDUE']).order_by('due_date').first()
            if next_inst:
                self.next_due_date = next_inst.due_date
        else:
            # Non-installment account (PACKAGE, ONE_TIME, MONTHLY, CUSTOM)
            if self.active_package and self.active_package.amount:
                if self.status == 'RESTRUCTURED' and self.total_due:
                    base_due = self.total_due
                else:
                    if self.plan_type in ['PACKAGE', 'MONTHLY'] and self.start_date and getattr(self.active_package, 'duration_months', 0):
                        from dateutil.relativedelta import relativedelta
                        today = timezone.localdate()
                        if today < self.start_date:
                            cycles = 1
                            self.next_due_date = self.start_date
                        else:
                            cycles = 0
                            current_due = self.start_date
                            while current_due <= today:
                                cycles += 1
                                current_due = current_due + relativedelta(months=self.active_package.duration_months)
                            self.next_due_date = current_due
                        base_due = Decimal(str(cycles * self.active_package.amount))
                    else:
                        base_due = self.active_package.amount
            elif self.total_due:
                base_due = self.total_due
            else:
                base_due = self.total_paid

            self.total_due = max(base_due, self.total_paid)
            self.balance_due = max(Decimal('0'), self.total_due - self.total_paid)
            self.overdue_amount = Decimal('0')

        # 3. Apply adjustments if any
        adj_total = self.adjustments.aggregate(t=models.Sum('amount_delta')).get('t') or Decimal('0')
        if adj_total:
            self.total_due = max(self.total_paid, self.total_due + adj_total)
            self.balance_due = max(Decimal('0'), self.total_due - self.total_paid)

        # 4. Update status
        if self.balance_due <= 0 and self.total_due > 0:
            self.status = 'SETTLED'
        elif self.overdue_amount > 0:
            self.status = 'OVERDUE'
        elif self.balance_due > 0 and self.total_paid > 0:
            self.status = 'PARTIAL'
        elif self.balance_due > 0:
            self.status = 'ACTIVE'

        if save:
            self.save(update_fields=['total_paid', 'total_due', 'balance_due', 'overdue_amount', 'next_due_date', 'last_payment_date', 'status', 'updated_at'])


class FdsFeeInstallment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partial'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('WAIVED', 'Waived'),
    ]

    account = models.ForeignKey(FdsStudentFeeAccount, on_delete=models.CASCADE, related_name='installments')
    sequence_number = models.PositiveIntegerField()
    label = models.CharField(max_length=120, blank=True)
    due_date = models.DateField(db_index=True)
    scheduled_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence_number']
        unique_together = ['account', 'sequence_number']

    def __str__(self):
        return f"{self.account.student.name} #{self.sequence_number}"

    def recalculate(self, save=True):
        self.balance_amount = max(Decimal('0'), self.scheduled_amount - self.paid_amount)
        if self.balance_amount <= 0:
            self.status = 'PAID'
        elif self.paid_amount > 0:
            self.status = 'PARTIAL'
        elif self.due_date < timezone.localdate():
            self.status = 'OVERDUE'
        else:
            self.status = 'PENDING'
        if save:
            self.save(update_fields=['balance_amount', 'status', 'updated_at'])


class FdsFeeAdjustment(models.Model):
    ADJUSTMENT_TYPE_CHOICES = [
        ('DISCOUNT', 'Discount'),
        ('WAIVER', 'Waiver'),
        ('REFUND', 'Refund'),
        ('RESTRUCTURE', 'Restructure'),
        ('CONCESSION', 'Concession'),
        ('MANUAL', 'Manual'),
    ]

    account = models.ForeignKey(FdsStudentFeeAccount, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES)
    amount_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField()
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fds_fee_adjustments_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.account.student.name} - {self.adjustment_type}"


class FdsFeesCollection(models.Model):
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    payment_id = models.CharField(max_length=20, unique=True, blank=True)
    account = models.ForeignKey(
        FdsStudentFeeAccount, on_delete=models.CASCADE,
        related_name='payments', null=True, blank=True
    )
    installment = models.ForeignKey(
        FdsFeeInstallment, on_delete=models.SET_NULL,
        related_name='payments', null=True, blank=True
    )
    student = models.ForeignKey(
        FdsStudent, on_delete=models.CASCADE,
        related_name='fds_payments', null=True, blank=True
    )
    # For wedding group payments (no individual student)
    wedding_group = models.ForeignKey(
        FdsWeddingGroup, on_delete=models.CASCADE,
        related_name='fds_payments', null=True, blank=True
    )
    pay_date = models.DateField(default=timezone.now)
    fees_type = models.ForeignKey(
        FdsFeeStructure, on_delete=models.PROTECT,
        related_name='collections'
    )
    # For monthly tracking
    fee_month = models.PositiveIntegerField(choices=MONTH_CHOICES, null=True, blank=True)
    fee_year = models.PositiveIntegerField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_fees = models.DecimalField(max_digits=10, decimal_places=2)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mode_of_pay = models.CharField(max_length=20, choices=MODE_OF_PAY_CHOICES, default='CASH')
    pdf_link = models.URLField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='PAID')
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
        name = self.student.name if self.student else (self.wedding_group.event_name if self.wedding_group else "Unknown")
        return f"{self.payment_id} — {name} — ₹{self.paid_amount}"

    def save(self, *args, **kwargs):
        # Initial save to get ID and ensure basic fields are set
        is_new = self.pk is None
        if not self.payment_id:
            last = FdsFeesCollection.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            self.payment_id = f"FDS-PAY-{next_num:04d}"

        # Ensure total_fees is at least paid_amount if total_fees is 0 or less
        if (not self.total_fees or self.total_fees <= 0) and self.paid_amount > 0:
            self.total_fees = self.paid_amount
            
        super().save(*args, **kwargs)

        # Skip cumulative logic if it's not a regular monthly student fee (e.g., wedding groups)
        if not (self.student and self.fee_month and self.fee_year and self.fees_type):
            self.balance = max(0, self.total_fees - self.paid_amount)
            if self.paid_amount >= self.total_fees:
                self.status = 'PAID'
            elif self.paid_amount > 0 and self.paid_amount < self.total_fees:
                self.status = 'PARTIAL'
            else:
                self.status = 'PENDING'
            super().save(update_fields=['balance', 'status'])
            if self.student and hasattr(self.student, 'fee_account'):
                self.student.fee_account.recalculate()
            return

        # Calculate cumulative totals for this student/month/year/type
        related_records = FdsFeesCollection.objects.filter(
            student=self.student,
            fee_month=self.fee_month,
            fee_year=self.fee_year,
            fees_type=self.fees_type
        )
        
        cumulative_paid = sum(r.paid_amount for r in related_records)
        actual_total_fees = max(self.total_fees, cumulative_paid)
        
        month_balance = max(0, actual_total_fees - cumulative_paid)
        if cumulative_paid >= actual_total_fees:
            month_status = 'PAID'
        elif cumulative_paid > 0:
            month_status = 'PARTIAL'
        else:
            month_status = 'PENDING'
            
        # Update ALL related records to reflect the final month status and balance
        for r in related_records:
            if r.balance != month_balance or r.status != month_status:
                r.balance = month_balance
                r.status = month_status
                super(FdsFeesCollection, r).save(update_fields=['balance', 'status'])
                
        # Finally, trigger a recalculation on the student's main fee account
        if hasattr(self.student, 'fee_account'):
            self.student.fee_account.recalculate()

    def delete(self, *args, **kwargs):
        student = self.student
        fee_month = self.fee_month
        fee_year = self.fee_year
        fees_type = self.fees_type
        
        super().delete(*args, **kwargs)
        
        # Recalculate related month records if any remain
        if student and fee_month and fee_year and fees_type:
            related_records = FdsFeesCollection.objects.filter(
                student=student,
                fee_month=fee_month,
                fee_year=fee_year,
                fees_type=fees_type
            )
            if related_records.exists():
                # Let the first one save to trigger recalculation for the group
                first_record = related_records.first()
                first_record.save()
                
        # Trigger recalculation on the student's main fee account
        if student and hasattr(student, 'fee_account'):
            student.fee_account.recalculate()
