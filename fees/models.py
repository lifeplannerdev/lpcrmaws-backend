from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from students.models import Student


User = settings.AUTH_USER_MODEL


class FeePlanTemplate(models.Model):
    PLAN_TYPE_CHOICES = [
        ('ONE_TIME', 'One Time'),
        ('INSTALLMENT', 'Installment'),
        ('MONTHLY', 'Monthly'),
        ('CUSTOM', 'Custom'),
        ('PACKAGE', 'Package'),
    ]

    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')], default='LP', db_index=True)
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=150)
    course_label = models.CharField(max_length=150, blank=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default='CUSTOM')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    registration_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    installment_count = models.PositiveIntegerField(null=True, blank=True)
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    monthly_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    duration_months = models.PositiveIntegerField(null=True, blank=True)
    due_day = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['company', 'name']
        indexes = [
            models.Index(fields=['company', 'plan_type']),
            models.Index(fields=['company', 'course_label']),
        ]

    def __str__(self):
        return f"{self.name} ({self.company})"


class StudentFeeAccount(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PARTIAL', 'Partial'),
        ('OVERDUE', 'Overdue'),
        ('SETTLED', 'Settled'),
        ('RESTRUCTURED', 'Restructured'),
        ('WAIVED', 'Waived'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fee_accounts')
    grade = models.ForeignKey('students.Grade', on_delete=models.SET_NULL, null=True, blank=True, related_name='fee_accounts')
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')], default='LP', db_index=True)
    template = models.ForeignKey(FeePlanTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_accounts')
    plan_code = models.CharField(max_length=80, blank=True)
    plan_name = models.CharField(max_length=150, blank=True)
    plan_type = models.CharField(max_length=20, default='CUSTOM')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', db_index=True)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    registration_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_day = models.PositiveIntegerField(default=10)
    start_date = models.DateField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True, db_index=True)
    last_payment_date = models.DateField(null=True, blank=True)
    last_restructure_date = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    source_label = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    plan_snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_fee_accounts')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_fee_accounts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'next_due_date']),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.plan_name or self.plan_code or self.plan_type}"

    @property
    def is_overdue(self):
        return self.status == 'OVERDUE' or self.overdue_amount > Decimal('0')

    def recalculate(self, save=True):
        payments_total = self.payments.aggregate(total=models.Sum('amount')).get('total') or Decimal('0')
        installment_paid = self.installments.aggregate(total=models.Sum('paid_amount')).get('total') or Decimal('0')
        installment_balance = self.installments.aggregate(total=models.Sum('balance_amount')).get('total') or Decimal('0')

        self.total_paid = payments_total
        
        if self.installments.exists():
            self.balance_due = installment_balance
            self.total_due = installment_paid + installment_balance
        elif self.total_due:
            self.balance_due = max(Decimal('0'), self.total_due - payments_total)
        else:
            self.balance_due = Decimal('0')
            self.total_due = payments_total

        overdue_total = self.installments.filter(status='OVERDUE').aggregate(total=models.Sum('balance_amount')).get('total') or Decimal('0')
        self.overdue_amount = overdue_total

        if self.balance_due <= 0:
            self.status = 'SETTLED'
            self.closed_at = self.closed_at or timezone.now()
        elif self.overdue_amount > 0:
            self.status = 'OVERDUE'
        elif installment_paid > 0:
            self.status = 'PARTIAL'
        else:
            self.status = 'ACTIVE'

        if save:
            self.save(update_fields=['total_paid', 'total_due', 'balance_due', 'overdue_amount', 'status', 'closed_at', 'updated_at'])


class FeeInstallment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partial'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('WAIVED', 'Waived'),
    ]

    account = models.ForeignKey(StudentFeeAccount, on_delete=models.CASCADE, related_name='installments')
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
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]

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
            self.save(update_fields=['paid_amount', 'balance_amount', 'status', 'updated_at'])


class FeePayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('UPI', 'UPI'),
        ('CHEQUE', 'Cheque'),
        ('CARD', 'Card'),
        ('OTHER', 'Other'),
    ]

    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')], default='LP', db_index=True)
    account = models.ForeignKey(StudentFeeAccount, on_delete=models.CASCADE, related_name='payments')
    installment = models.ForeignKey(FeeInstallment, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    receipt_number = models.CharField(max_length=80, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    payment_date = models.DateTimeField(default=timezone.now, db_index=True)
    reference = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='fee_payments_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'payment_date']),
            models.Index(fields=['account', 'payment_date']),
        ]

    def __str__(self):
        return f"{self.receipt_number} - {self.account.student.name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.account.recalculate()
            if self.account.status in ['ACTIVE', 'SETTLED', 'PARTIAL']:
                # Regularize pending attendance for FLAG students
                if self.company == 'FLAG':
                    from students.models import AttendanceRecord
                    pending_records = AttendanceRecord.objects.filter(
                        student=self.account.student, status='pending'
                    )
                    for record in pending_records:
                        record.regularize(user=self.created_by)


class FeeAdjustment(models.Model):
    ADJUSTMENT_TYPE_CHOICES = [
        ('DISCOUNT', 'Discount'),
        ('WAIVER', 'Waiver'),
        ('REFUND', 'Refund'),
        ('RESTRUCTURE', 'Restructure'),
        ('CONCESSION', 'Concession'),
        ('MANUAL', 'Manual'),
    ]

    account = models.ForeignKey(StudentFeeAccount, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES)
    amount_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='fee_adjustments_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['adjustment_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.account.student.name} - {self.adjustment_type}"


class FeePolicy(models.Model):
    company = models.CharField(max_length=10, unique=True, default='LP')
    block_without_fee_account = models.BooleanField(default=False)
    pending_if_overdue = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Fee Policies'

    def __str__(self):
        return f"{self.company} Fee Policy"


class ReceiptSettings(models.Model):
    GST_MODE_CHOICES = [
        ('NONE', 'No Tax / Exempt'),
        ('INCLUSIVE', 'GST Inclusive (18%)'),
        ('EXCLUSIVE', 'GST Exclusive (18%)'),
    ]
    TEMPLATE_CHOICES = [
        ('EXECUTIVE', 'FLAG Executive A4'),
        ('GST_INVOICE', 'Classic GST Tax Invoice'),
        ('DUAL_SLIP', 'Compact Dual-Slip Voucher'),
    ]

    company = models.CharField(
        max_length=10,
        choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')],
        default='FLAG',
        db_index=True,
    )
    campus = models.ForeignKey(
        'students.Campus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipt_settings',
    )
    organization_name = models.CharField(max_length=200, default='FLAG German Language Academy')
    subtitle = models.CharField(max_length=250, blank=True, default='Foreign Language Academy for Global Careers')
    address = models.TextField(blank=True, default='Kochi | Kottayam | Kerala, India')
    phone = models.CharField(max_length=50, blank=True, default='+91 98460 00000')
    email = models.EmailField(blank=True, default='accounts@flagacademy.in')
    website = models.CharField(max_length=150, blank=True, default='www.flagacademy.in')

    gstin = models.CharField(max_length=30, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    place_of_supply = models.CharField(max_length=100, blank=True, default='Kerala (32)')
    sac_code = models.CharField(max_length=20, blank=True, default='999293')
    default_gst_mode = models.CharField(max_length=20, choices=GST_MODE_CHOICES, default='INCLUSIVE')
    default_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))

    receipt_prefix = models.CharField(max_length=40, default='FLAG')
    next_sequence_number = models.PositiveIntegerField(default=1)

    logo_url = models.TextField(blank=True)
    signature_image = models.TextField(blank=True)
    stamp_image = models.TextField(blank=True)
    watermark_text = models.CharField(max_length=120, blank=True, default='FLAG GERMAN ACADEMY')
    authorized_signatory_name = models.CharField(max_length=120, blank=True, default='Authorized Signatory')
    authorized_signatory_designation = models.CharField(max_length=120, blank=True, default='Accounts & Finance Department')

    bank_name = models.CharField(max_length=120, blank=True)
    account_name = models.CharField(max_length=150, blank=True)
    account_number = models.CharField(max_length=60, blank=True)
    ifsc_code = models.CharField(max_length=30, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)

    default_terms_and_conditions = models.TextField(
        blank=True,
        default=(
            '1. Fees once paid are non-refundable and non-transferable unless specified in the academy policy.\n'
            '2. This is a computer-generated digital receipt with cryptographic QR verification.\n'
            '3. Subject to Kochi jurisdiction.'
        ),
    )
    footer_note = models.CharField(max_length=255, blank=True, default='Thank you for choosing FLAG German Academy.')
    default_template = models.CharField(max_length=30, choices=TEMPLATE_CHOICES, default='EXECUTIVE')
    brand_color = models.CharField(max_length=20, default='#312e81')
    default_display_options = models.JSONField(default=dict, blank=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_receipt_settings',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Receipt Settings'
        ordering = ['company', 'campus_id']

    def __str__(self):
        campus_label = f" - {self.campus.name}" if self.campus else " (Default)"
        return f"{self.company}{campus_label} Receipt Settings"


class FeeReceipt(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('RECEIPT', 'Official Fee Receipt'),
        ('TAX_INVOICE', 'Tax Invoice'),
        ('PROFORMA', 'Proforma Invoice'),
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('VOID', 'Void / Cancelled'),
        ('REFUNDED', 'Refunded'),
    ]
    TAX_MODE_CHOICES = [
        ('NONE', 'No Tax / Exempt'),
        ('INCLUSIVE', 'GST Inclusive'),
        ('EXCLUSIVE', 'GST Exclusive'),
    ]
    SUPPLY_TYPE_CHOICES = [
        ('INTRA_STATE', 'Intra-State (CGST + SGST)'),
        ('INTER_STATE', 'Inter-State (IGST)'),
    ]
    BILLED_TO_CHOICES = [
        ('STUDENT', 'Student'),
        ('PARENT', 'Parent / Guardian'),
        ('SPONSOR', 'Corporate Sponsor / Third Party'),
    ]
    TEMPLATE_CHOICES = ReceiptSettings.TEMPLATE_CHOICES

    company = models.CharField(
        max_length=10,
        choices=[('LP', 'LP'), ('FLAG', 'FLAG'), ('FDS', 'FILMAATIC')],
        default='FLAG',
        db_index=True,
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_receipts',
    )
    account = models.ForeignKey(
        StudentFeeAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts',
    )
    payment = models.ForeignKey(
        FeePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts',
    )

    receipt_number = models.CharField(max_length=80, unique=True, db_index=True)
    financial_year = models.CharField(max_length=20, blank=True, db_index=True)
    sequence_number = models.PositiveIntegerField(null=True, blank=True)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='RECEIPT', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED', db_index=True)
    issue_date = models.DateTimeField(default=timezone.now, db_index=True)
    verification_token = models.CharField(max_length=64, unique=True, db_index=True)
    signature_hash = models.CharField(max_length=128, blank=True)
    is_manual_override = models.BooleanField(default=False)

    # Recipient Snapshot
    billed_to_type = models.CharField(max_length=20, choices=BILLED_TO_CHOICES, default='STUDENT')
    recipient_name = models.CharField(max_length=200)
    recipient_phone = models.CharField(max_length=30, blank=True)
    recipient_email = models.EmailField(blank=True)
    parent_or_sponsor_name = models.CharField(max_length=200, blank=True)
    recipient_address = models.TextField(blank=True)
    recipient_gstin = models.CharField(max_length=30, blank=True)
    place_of_supply = models.CharField(max_length=100, blank=True, default='Kerala (32)')
    student_enrollment_code = models.CharField(max_length=80, blank=True)

    # Academic Snapshot
    course_or_package_name = models.CharField(max_length=200, blank=True)
    batch_name = models.CharField(max_length=150, blank=True)
    campus_name = models.CharField(max_length=150, blank=True)
    grade_level = models.CharField(max_length=80, blank=True)
    mode_of_study = models.CharField(max_length=50, blank=True)

    # Financial Snapshot
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_mode = models.CharField(max_length=20, choices=TAX_MODE_CHOICES, default='NONE')
    supply_type = models.CharField(max_length=20, choices=SUPPLY_TYPE_CHOICES, default='INTRA_STATE')
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount_in_words = models.CharField(max_length=500, blank=True)

    # Payment Snapshot
    payment_method = models.CharField(max_length=20, choices=FeePayment.PAYMENT_METHOD_CHOICES, default='UPI')
    payment_reference = models.CharField(max_length=150, blank=True)
    payment_date = models.DateTimeField(default=timezone.now)
    installment_label = models.CharField(max_length=150, blank=True)
    payment_status_badge = models.CharField(max_length=30, default='PAID')

    # Account Ledger Summary Snapshot
    ledger_total_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ledger_discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ledger_previously_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ledger_current_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ledger_total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ledger_balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ledger_next_due_date = models.DateField(null=True, blank=True)
    installment_schedule_snapshot = models.JSONField(default=list, blank=True)

    # Presentation & JSON Snapshots
    template_style = models.CharField(max_length=30, choices=TEMPLATE_CHOICES, default='EXECUTIVE')
    display_options = models.JSONField(default=dict, blank=True)
    line_items = models.JSONField(default=list, blank=True)
    issuer_snapshot = models.JSONField(default=dict, blank=True)
    snapshot_data = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    terms_and_conditions = models.TextField(blank=True)

    # Audit & Lifecycle
    version = models.PositiveIntegerField(default=1)
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_receipts_voided',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_receipts_created',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_receipts_updated',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'issue_date']),
            models.Index(fields=['company', 'document_type']),
            models.Index(fields=['student', 'issue_date']),
        ]

    def __str__(self):
        return f"{self.receipt_number} - {self.recipient_name}"

    def save(self, *args, **kwargs):
        from .receipt_engine import (
            amount_to_words,
            compute_receipt_signature,
            generate_verification_token,
            get_indian_financial_year,
            to_decimal,
        )

        if not self.issue_date:
            self.issue_date = timezone.now()
        if not self.verification_token:
            self.verification_token = generate_verification_token()
        if not self.financial_year:
            self.financial_year = get_indian_financial_year(self.issue_date)
        self.subtotal_amount = to_decimal(self.subtotal_amount, Decimal('0.00'))
        self.discount_amount = to_decimal(self.discount_amount, Decimal('0.00'))
        self.total_tax_amount = to_decimal(self.total_tax_amount, Decimal('0.00'))
        self.total_amount = to_decimal(self.total_amount, Decimal('0.00'))
        if not self.amount_in_words:
            self.amount_in_words = amount_to_words(self.total_amount)
        self.signature_hash = compute_receipt_signature(self)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {
                'verification_token',
                'financial_year',
                'amount_in_words',
                'signature_hash',
            }
        super().save(*args, **kwargs)
