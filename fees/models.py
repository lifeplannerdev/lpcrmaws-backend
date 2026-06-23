from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from trainers.models import Student


User = settings.AUTH_USER_MODEL


class FeePlanTemplate(models.Model):
    PLAN_TYPE_CHOICES = [
        ('ONE_TIME', 'One Time'),
        ('INSTALLMENT', 'Installment'),
        ('MONTHLY', 'Monthly'),
        ('CUSTOM', 'Custom'),
        ('PACKAGE', 'Package'),
    ]

    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
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

    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='fee_account')
    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
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

    company = models.CharField(max_length=10, choices=[('LP', 'LP'), ('FLAG', 'FLAG')], default='LP', db_index=True)
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
