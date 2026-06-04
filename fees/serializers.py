from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import ActivityLog, User
from notifications.models import Notification
from trainers.models import Student, AcademicBatch

from .models import FeePlanTemplate, StudentFeeAccount, FeeInstallment, FeePayment, FeeAdjustment


def _notify_fee_stakeholders(account, message, by='System'):
    recipients = [
        user for user in User.objects.filter(is_active=True, company=account.company)
        if 'manage_fees' in (user.permissions or [])
    ]
    trainer_user = getattr(getattr(account.student, 'trainer', None), 'user', None)
    if trainer_user and trainer_user.is_active:
        recipients.append(trainer_user)

    seen = set()
    for user in recipients:
        if user.id in seen:
            continue
        seen.add(user.id)
        Notification.objects.create(user=user, type='fee', message=message, by=by)


class FeePlanTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeePlanTemplate
        fields = [
            'id', 'company', 'code', 'name', 'course_label', 'plan_type', 'total_amount',
            'registration_amount', 'installment_count', 'installment_amount', 'monthly_amount',
            'duration_months', 'due_day', 'is_active', 'notes', 'metadata'
        ]


class FeeInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeInstallment
        fields = [
            'id', 'account', 'sequence_number', 'label', 'due_date', 'scheduled_amount',
            'paid_amount', 'balance_amount', 'status', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['paid_amount', 'balance_amount', 'status', 'created_at', 'updated_at']
        extra_kwargs = {
            'account': {'read_only': True},
        }


class FeePaymentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = FeePayment
        fields = [
            'id', 'company', 'account', 'installment', 'receipt_number', 'amount',
            'payment_method', 'payment_date', 'reference', 'notes', 'created_by',
            'created_by_name', 'created_at'
        ]
        read_only_fields = ['created_by', 'created_at']
        extra_kwargs = {
            'receipt_number': {'required': False, 'allow_blank': True},
        }

    def validate(self, attrs):
        amount = attrs.get('amount')
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({'amount': 'Payment amount must be greater than zero.'})
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        account = validated_data['account']
        installment = validated_data.get('installment')

        with transaction.atomic():
            previous_status = account.status
            if not validated_data.get('receipt_number'):
                validated_data['receipt_number'] = self._generate_receipt_number(account)
            validated_data['created_by'] = request.user
            validated_data['company'] = account.company
            payment = super().create(validated_data)

            if installment:
                installment.paid_amount = (installment.paid_amount or Decimal('0')) + payment.amount
                installment.recalculate(save=True)

            account.recalculate(save=False)
            account.last_payment_date = timezone.localdate(payment.payment_date)
            account.updated_by = request.user
            account.save(update_fields=[
                'total_paid', 'balance_due', 'overdue_amount', 'status',
                'last_payment_date', 'updated_by', 'updated_at'
            ])

            ActivityLog.objects.create(
                user=request.user,
                company=account.company,
                action='STUDENT_UPDATED',
                entity_type='StudentFeeAccount',
                entity_id=account.id,
                entity_name=account.student.name,
                description=f"Fee payment recorded for {account.student.name}",
                metadata={
                    'receipt_number': payment.receipt_number,
                    'amount': str(payment.amount),
                    'installment_id': installment.id if installment else None,
                    'payment_method': payment.payment_method,
                },
            )

            if previous_status != account.status or previous_status == 'OVERDUE' or account.status in ('OVERDUE', 'SETTLED', 'PARTIAL'):
                _notify_fee_stakeholders(
                    account,
                    f"Fee status updated for {account.student.name}: {previous_status} -> {account.status}",
                    by=request.user.get_full_name() or request.user.username,
                )

        return payment

    def _generate_receipt_number(self, account):
        prefix = f"{account.company}-{account.student_id}"
        last = FeePayment.objects.filter(account=account).order_by('-id').first()
        next_seq = 1 if not last else last.id + 1
        return f"{prefix}-{next_seq}"


class FeeAdjustmentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = FeeAdjustment
        fields = [
            'id', 'account', 'adjustment_type', 'amount_delta', 'reason',
            'metadata', 'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['created_by', 'created_at']


class StudentFeeAccountSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_status = serializers.CharField(source='student.status', read_only=True)
    trainer_name = serializers.CharField(source='student.trainer.user.get_full_name', read_only=True)
    branch_name = serializers.CharField(source='student.branch.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    installments = FeeInstallmentSerializer(many=True, read_only=True)
    payments = FeePaymentSerializer(many=True, read_only=True)
    adjustments = FeeAdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = StudentFeeAccount
        fields = [
            'id', 'student', 'student_name', 'student_status', 'trainer_name', 'branch_name',
            'company', 'template', 'template_name', 'plan_code', 'plan_name', 'plan_type',
            'status', 'total_due', 'total_paid', 'balance_due', 'overdue_amount',
            'registration_amount', 'due_day', 'start_date', 'next_due_date', 'last_payment_date',
            'last_restructure_date', 'closed_at', 'version', 'source_label', 'notes',
            'plan_snapshot', 'installments', 'payments', 'adjustments', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'company', 'status', 'total_paid', 'balance_due', 'overdue_amount',
            'last_payment_date', 'last_restructure_date', 'closed_at', 'version',
            'created_at', 'updated_at'
        ]


class FeeSummarySerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    company = serializers.CharField()
    plan_name = serializers.CharField(allow_blank=True, required=False)
    plan_type = serializers.CharField(allow_blank=True, required=False)
    total_due = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()
    next_due_date = serializers.DateField(allow_null=True, required=False)
    last_payment_date = serializers.DateField(allow_null=True, required=False)


class StudentFeeAccountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentFeeAccount
        fields = [
            'student', 'template', 'plan_code', 'plan_name', 'plan_type', 'total_due',
            'registration_amount', 'due_day', 'start_date', 'next_due_date', 'notes',
            'plan_snapshot', 'source_label'
    ]

    def _template_snapshot(self, template):
        if not template:
            return None

        return {
            'id': template.id,
            'company': template.company,
            'code': template.code,
            'name': template.name,
            'course_label': template.course_label,
            'plan_type': template.plan_type,
            'total_amount': str(template.total_amount),
            'registration_amount': str(template.registration_amount),
            'installment_count': template.installment_count,
            'installment_amount': str(template.installment_amount) if template.installment_amount is not None else None,
            'monthly_amount': str(template.monthly_amount) if template.monthly_amount is not None else None,
            'duration_months': template.duration_months,
            'due_day': template.due_day,
            'is_active': template.is_active,
        }

    def _apply_template_defaults(self, validated_data, template):
        if not template:
            return validated_data

        defaults = {
            'plan_code': template.code,
            'plan_name': template.name,
            'plan_type': template.plan_type,
            'total_due': template.total_amount,
            'registration_amount': template.registration_amount,
            'due_day': template.due_day,
        }
        defaults.update(validated_data)
        defaults['plan_snapshot'] = defaults.get('plan_snapshot') or {}
        defaults['plan_snapshot'].setdefault('template', self._template_snapshot(template))
        return defaults

    def create(self, validated_data):
        request = self.context['request']
        student = validated_data['student']
        template = validated_data.get('template')
        validated_data = self._apply_template_defaults(validated_data, template)
        account, created = StudentFeeAccount.objects.get_or_create(student=student, defaults={
            'company': student.company,
            'created_by': request.user,
            'updated_by': request.user,
            **validated_data,
        })

        if not created:
            validated_data = self._apply_template_defaults(validated_data, template)
            for key, value in validated_data.items():
                setattr(account, key, value)
            account.updated_by = request.user
            account.version = account.version + 1
            account.save()
        else:
            account.plan_snapshot = account.plan_snapshot or {}
            if template:
                account.plan_snapshot.setdefault('template', self._template_snapshot(template))
            account.save()

        return account


class FeeRestructureSerializer(serializers.Serializer):
    plan_type = serializers.CharField()
    template_id = serializers.IntegerField(required=False, allow_null=True)
    total_due = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    registration_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    due_day = serializers.IntegerField(required=False, default=10)
    notes = serializers.CharField(required=False, allow_blank=True)
    next_due_date = serializers.DateField(required=False, allow_null=True)
    installments = serializers.ListField(child=serializers.DictField(), required=False)

    def validate_installments(self, value):
        for idx, item in enumerate(value, start=1):
            if 'due_date' not in item or 'scheduled_amount' not in item:
                raise serializers.ValidationError(f'Installment #{idx} requires due_date and scheduled_amount.')
        return value
