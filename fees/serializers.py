from accounts.permissions import has_dynamic_permission
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import ActivityLog, User
from notifications.models import Notification

from .models import FeePlanTemplate, StudentFeeAccount, FeeInstallment, FeePayment, FeeAdjustment


def _notify_fee_stakeholders(account, message, by='System'):
    recipients = [
        user for user in User.objects.filter(is_active=True, company=account.company)
        if has_dynamic_permission(user, 'fees:manage')
    ]
    raw_trainer = getattr(account.student, 'trainer', None)
    trainer_user = getattr(raw_trainer, 'user', None) or (raw_trainer if isinstance(raw_trainer, User) else None)
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
    latest_receipt_id = serializers.SerializerMethodField()
    latest_receipt_number = serializers.SerializerMethodField()
    latest_receipt_token = serializers.SerializerMethodField()
    latest_receipt_status = serializers.SerializerMethodField()

    class Meta:
        model = FeePayment
        fields = [
            'id', 'company', 'account', 'installment', 'receipt_number', 'amount',
            'payment_method', 'payment_date', 'reference', 'notes', 'created_by',
            'created_by_name', 'created_at',
            'latest_receipt_id', 'latest_receipt_number', 'latest_receipt_token', 'latest_receipt_status',
        ]
        read_only_fields = ['created_by', 'created_at']
        extra_kwargs = {
            'receipt_number': {'required': False, 'allow_blank': True},
        }

    def _get_latest_receipt(self, obj):
        if hasattr(obj, '_cached_latest_receipt'):
            return obj._cached_latest_receipt
        prefetched = getattr(obj, '_prefetched_objects_cache', {}).get('receipts')
        if prefetched is not None:
            non_void = [r for r in prefetched if r.status != 'VOID']
            obj._cached_latest_receipt = non_void[0] if non_void else (prefetched[0] if prefetched else None)
        else:
            obj._cached_latest_receipt = obj.receipts.exclude(status='VOID').order_by('-created_at').first() or obj.receipts.order_by('-created_at').first()
        return obj._cached_latest_receipt

    def get_latest_receipt_id(self, obj):
        r = self._get_latest_receipt(obj)
        return r.id if r else None

    def get_latest_receipt_number(self, obj):
        r = self._get_latest_receipt(obj)
        return r.receipt_number if r else None

    def get_latest_receipt_token(self, obj):
        r = self._get_latest_receipt(obj)
        return r.verification_token if r else None

    def get_latest_receipt_status(self, obj):
        r = self._get_latest_receipt(obj)
        return r.status if r else None

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
                'total_paid', 'total_due', 'balance_due', 'overdue_amount', 'status',
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
    trainer_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
    template_name = serializers.CharField(source='template.name', read_only=True)

    def get_trainer_name(self, obj):
        student = getattr(obj, 'student', None)
        if not student:
            return ""
        trainer = getattr(student, 'trainer', None)
        if not trainer:
            return ""
        if hasattr(trainer, 'get_full_name'):
            return trainer.get_full_name() or getattr(trainer, 'username', '')
        if hasattr(trainer, 'user') and trainer.user:
            return trainer.user.get_full_name() or getattr(trainer.user, 'username', '')
        return str(trainer)

    def get_branch_name(self, obj):
        student = getattr(obj, 'student', None)
        if not student:
            return ""
        if hasattr(student, 'campus') and student.campus:
            return student.campus.name
        if hasattr(student, 'branch') and student.branch:
            return student.branch.name
        return ""
    grade_name = serializers.CharField(source='grade.code', read_only=True)
    installments = FeeInstallmentSerializer(many=True, read_only=True)
    payments = FeePaymentSerializer(many=True, read_only=True)
    adjustments = FeeAdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = StudentFeeAccount
        fields = [
            'id', 'student', 'student_name', 'student_status', 'trainer_name', 'branch_name',
            'company', 'template', 'template_name', 'grade', 'grade_name', 'plan_code', 'plan_name', 'plan_type',
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
            'student', 'template', 'grade', 'plan_code', 'plan_name', 'plan_type', 'total_due',
            'registration_amount', 'due_day', 'start_date', 'next_due_date', 'notes',
            'plan_snapshot', 'source_label', 'first_installment_date'
    ]

    first_installment_date = serializers.DateField(required=False, allow_null=True, write_only=True)

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

    def _generate_installments(self, account, template, first_installment_date=None):
        import datetime
        from decimal import Decimal
        from calendar import monthrange
        
        start_date = account.start_date or datetime.date.today()
        due_day = account.due_day or 10

        installments = []
        seq = 1

        if account.registration_amount and account.registration_amount > 0:
            installments.append(FeeInstallment(
                account=account,
                sequence_number=seq,
                label="Registration Fee",
                due_date=start_date,
                scheduled_amount=account.registration_amount,
                balance_amount=account.registration_amount,
                status='PENDING'
            ))
            seq += 1

        if template.plan_type in ('MONTHLY', 'INSTALLMENT'):
            count = 0
            amount = Decimal('0')

            if template.plan_type == 'MONTHLY':
                count = template.duration_months or 0
                amount = template.monthly_amount or Decimal('0')
            elif template.plan_type == 'INSTALLMENT':
                count = template.installment_count or 0
                amount = template.installment_amount or Decimal('0')

            if count > 0 and amount > 0:
                base_date = first_installment_date or start_date
                installment_due_day = base_date.day if first_installment_date else due_day
                
                # If no first_installment_date provided, start next month
                base_month_offset = 0 if first_installment_date else 1

                for i in range(count):
                    month_offset = base_month_offset + i
                    month = base_date.month - 1 + month_offset
                    year = base_date.year + month // 12
                    month = month % 12 + 1
                    
                    days_in_month = monthrange(year, month)[1]
                    day = min(installment_due_day, days_in_month)
                    
                    due_date = datetime.date(year, month, day)
                    
                    installments.append(FeeInstallment(
                        account=account,
                        sequence_number=seq,
                        label=f"Installment {i + 1} of {count}",
                        due_date=due_date,
                        scheduled_amount=amount,
                        balance_amount=amount,
                        status='PENDING'
                    ))
                    seq += 1

        if installments:
            FeeInstallment.objects.bulk_create(installments)

    def create(self, validated_data):
        first_installment_date = validated_data.pop('first_installment_date', None)
        request = self.context['request']
        student = validated_data['student']
        template = validated_data.get('template')
        validated_data = self._apply_template_defaults(validated_data, template)
        
        student_company = getattr(student, 'company', None)
        if callable(student_company):
            student_company = student_company()
        company = (
            request.data.get('company') or
            student_company or
            (template.company if template else None) or
            getattr(request.user, 'company', None) or
            'FLAG'
        )

        validated_data['company'] = company
        validated_data['created_by'] = request.user
        validated_data['updated_by'] = request.user
        account = StudentFeeAccount.objects.create(**validated_data)

        account.plan_snapshot = account.plan_snapshot or {}
        if template:
            account.plan_snapshot.setdefault('template', self._template_snapshot(template))
        account.save()
        
        if template:
            self._generate_installments(account, template, first_installment_date)

        account.recalculate(save=True)
        return account

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            instance.updated_by = request.user
        instance.version = (instance.version or 1) + 1
        return super().update(instance, validated_data)


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



from .models import FeePolicy, ReceiptSettings, FeeReceipt
from .permissions import _can_manage_receipt_admin_actions, _can_view_fee_account
from .receipt_engine import (
    DEFAULT_DISPLAY_OPTIONS,
    allocate_receipt_number,
    amount_to_words,
    build_issuer_snapshot,
    calculate_receipt_financials,
    extract_account_ledger_snapshot,
    extract_student_metadata,
    get_indian_financial_year,
    get_or_create_receipt_settings,
    to_decimal,
    verify_receipt_signature,
)


class FeePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = FeePolicy
        fields = '__all__'


class ReceiptSettingsSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source='campus.name', read_only=True)

    class Meta:
        model = ReceiptSettings
        fields = [
            'id', 'company', 'campus', 'campus_name',
            'organization_name', 'subtitle', 'address', 'phone', 'email', 'website',
            'gstin', 'pan_number', 'place_of_supply', 'sac_code',
            'default_gst_mode', 'default_gst_rate',
            'receipt_prefix', 'next_sequence_number',
            'logo_url', 'signature_image', 'stamp_image', 'watermark_text',
            'authorized_signatory_name', 'authorized_signatory_designation',
            'bank_name', 'account_name', 'account_number', 'ifsc_code', 'upi_id',
            'default_terms_and_conditions', 'footer_note',
            'default_template', 'brand_color', 'default_display_options',
            'updated_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['updated_by', 'created_at', 'updated_at']

    def validate_next_sequence_number(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError('Next sequence number must be at least 1.')
        return value

    def validate_default_gst_rate(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Default GST rate cannot be negative.')
        return value


class FeeReceiptSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    voided_by_name = serializers.SerializerMethodField()
    student_display_name = serializers.CharField(source='student.name', read_only=True)
    is_signature_valid = serializers.SerializerMethodField()
    signature_prefix = serializers.SerializerMethodField()

    # Optional write-only control flags for manual overrides
    manual_financial_override = serializers.BooleanField(write_only=True, required=False, default=False)
    manual_ledger_override = serializers.BooleanField(write_only=True, required=False, default=False)
    manual_words_override = serializers.BooleanField(write_only=True, required=False, default=False)
    gst_rate = serializers.DecimalField(max_digits=5, decimal_places=2, write_only=True, required=False)

    class Meta:
        model = FeeReceipt
        fields = [
            'id', 'company', 'student', 'student_display_name', 'account', 'payment',
            'receipt_number', 'financial_year', 'sequence_number',
            'document_type', 'status', 'issue_date',
            'verification_token', 'signature_hash', 'signature_prefix', 'is_signature_valid',
            'is_manual_override',
            'billed_to_type', 'recipient_name', 'recipient_phone', 'recipient_email',
            'parent_or_sponsor_name', 'recipient_address', 'recipient_gstin',
            'place_of_supply', 'student_enrollment_code',
            'course_or_package_name', 'batch_name', 'campus_name',
            'grade_level', 'mode_of_study',
            'subtotal_amount', 'discount_amount', 'taxable_amount',
            'tax_mode', 'supply_type',
            'cgst_rate', 'cgst_amount', 'sgst_rate', 'sgst_amount',
            'igst_rate', 'igst_amount', 'total_tax_amount', 'total_amount',
            'amount_in_words',
            'payment_method', 'payment_reference', 'payment_date',
            'installment_label', 'payment_status_badge',
            'ledger_total_fee', 'ledger_discount', 'ledger_previously_paid',
            'ledger_current_paid', 'ledger_total_paid', 'ledger_balance_due',
            'ledger_next_due_date', 'installment_schedule_snapshot',
            'template_style', 'display_options', 'line_items',
            'issuer_snapshot', 'snapshot_data', 'notes', 'terms_and_conditions',
            'version', 'void_reason', 'voided_at', 'voided_by', 'voided_by_name',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at',
            'manual_financial_override', 'manual_ledger_override', 'manual_words_override', 'gst_rate',
        ]
        read_only_fields = [
            'verification_token', 'signature_hash', 'version',
            'voided_at', 'voided_by', 'created_by', 'updated_by',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'receipt_number': {'required': False, 'allow_blank': True},
            'recipient_name': {'required': False, 'allow_blank': True},
        }

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'System'

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return ''

    def get_voided_by_name(self, obj):
        if obj.voided_by:
            return obj.voided_by.get_full_name() or obj.voided_by.username
        return ''

    def get_is_signature_valid(self, obj):
        return verify_receipt_signature(obj)

    def get_signature_prefix(self, obj):
        return (obj.signature_hash or '')[:16].upper()

    def validate(self, attrs):
        from rest_framework.exceptions import PermissionDenied

        instance = self.instance
        request = self.context.get('request')
        user = request.user if (request and hasattr(request, 'user') and request.user.is_authenticated) else None

        if instance:
            new_status = attrs.get('status', instance.status)
            if instance.status in ('ISSUED', 'VOID', 'REFUNDED', 'PARTIALLY_PAID') and new_status == 'DRAFT':
                raise serializers.ValidationError({'status': 'An issued or finalized receipt cannot be reverted to DRAFT.'})

        target_status = attrs.get('status', getattr(instance, 'status', 'ISSUED'))
        if target_status == 'VOID':
            if user and not _can_manage_receipt_admin_actions(user):
                raise PermissionDenied('Only fee administrators can void receipts.')
            raw_reason = attrs['void_reason'] if 'void_reason' in attrs else getattr(instance, 'void_reason', '')
            void_reason = (raw_reason or '').strip()
            if not void_reason:
                raise serializers.ValidationError({'void_reason': 'A mandatory reason is required to void an official receipt.'})
            attrs['void_reason'] = void_reason

        if instance and instance.status == 'VOID':
            raise serializers.ValidationError({'detail': 'Voided receipts are locked and cannot be edited.'})

        for num_field in (
            'gst_rate', 'cgst_rate', 'sgst_rate', 'igst_rate',
            'subtotal_amount', 'discount_amount', 'total_amount',
        ):
            val = attrs.get(num_field)
            if val is not None and to_decimal(val) < Decimal('0.00'):
                raise serializers.ValidationError({num_field: f'{num_field} cannot be negative.'})

        receipt_number = (attrs.get('receipt_number') or '').strip()
        if receipt_number:
            qs = FeeReceipt.objects.filter(receipt_number=receipt_number)
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'receipt_number': f'Receipt number "{receipt_number}" is already in use.'})
            attrs['receipt_number'] = receipt_number

        payment = attrs.get('payment', getattr(instance, 'payment', None))
        account = attrs.get('account', getattr(instance, 'account', None))
        student = attrs.get('student', getattr(instance, 'student', None))

        if payment and account and payment.account_id != account.id:
            raise serializers.ValidationError({'account': 'Selected payment does not belong to the specified fee account.'})
        if payment and not account:
            account = payment.account
            attrs['account'] = account

        if account and student and account.student_id != student.id:
            raise serializers.ValidationError({'student': 'Selected fee account does not belong to the specified student.'})
        if account and not student:
            student = account.student
            attrs['student'] = student

        if user and account and not _can_view_fee_account(user, account):
            raise PermissionDenied('You do not have permission to access this student fee account.')

        recipient_name = (attrs.get('recipient_name') or getattr(instance, 'recipient_name', '') or '').strip()
        if not recipient_name and student:
            recipient_name = student.name
            attrs['recipient_name'] = recipient_name

        if not recipient_name:
            raise serializers.ValidationError({'recipient_name': 'Recipient / Student name is required.'})

        return attrs

    def _build_revision_snapshot(self, data_dict, user, action='CREATED', version=1):
        actor = (user.get_full_name() or user.username) if (user and getattr(user, 'is_authenticated', False)) else 'System'
        return {
            'version': version,
            'action': action,
            'timestamp': timezone.now().isoformat(),
            'actor': actor,
            'receipt_number': data_dict.get('receipt_number', ''),
            'status': data_dict.get('status', 'ISSUED'),
            'document_type': data_dict.get('document_type', 'RECEIPT'),
            'recipient_name': data_dict.get('recipient_name', ''),
            'subtotal_amount': str(data_dict.get('subtotal_amount', '0.00')),
            'discount_amount': str(data_dict.get('discount_amount', '0.00')),
            'tax_mode': data_dict.get('tax_mode', 'NONE'),
            'total_tax_amount': str(data_dict.get('total_tax_amount', '0.00')),
            'total_amount': str(data_dict.get('total_amount', '0.00')),
            'line_items': data_dict.get('line_items', []),
        }

    def _recalculate_or_respect_overrides(
        self,
        instance,
        validated_data,
        explicit_gst_rate=None,
        manual_financial_override=False,
        manual_words_override=False,
        manual_ledger_override=False,
    ):
        line_items = validated_data.get('line_items', instance.line_items)
        subtotal_in = validated_data.get('subtotal_amount', instance.subtotal_amount)

        if (
            instance is not None
            and 'line_items' not in validated_data
            and 'line_items' not in self.initial_data
            and 'subtotal_amount' in validated_data
            and not manual_financial_override
            and len(instance.line_items or []) <= 1
        ):
            if instance.line_items and len(instance.line_items) == 1 and isinstance(instance.line_items[0], dict):
                single_item = dict(instance.line_items[0])
                single_item['quantity'] = '1.00'
                single_item['discount'] = '0.00'
                single_item['unit_price'] = str(validated_data['subtotal_amount'])
                single_item['amount'] = str(validated_data['subtotal_amount'])
                line_items = [single_item]
            else:
                line_items = None
        elif (
            'total_amount' in self.initial_data
            and 'subtotal_amount' not in self.initial_data
            and 'line_items' not in self.initial_data
            and not manual_financial_override
            and len(instance.line_items or []) <= 1
        ):
            subtotal_in = validated_data['total_amount']
            line_items = None

        eff_supply = validated_data.get('supply_type', instance.supply_type)
        eff_tax_mode = validated_data.get('tax_mode', instance.tax_mode)
        if explicit_gst_rate is not None:
            resolved_gst_rate = explicit_gst_rate
        elif (eff_supply == 'INTER_STATE' or eff_tax_mode == 'INTER_STATE') and to_decimal(instance.igst_rate) > Decimal('0.00'):
            resolved_gst_rate = to_decimal(instance.igst_rate)
        elif (to_decimal(instance.cgst_rate) + to_decimal(instance.sgst_rate)) > Decimal('0.00'):
            resolved_gst_rate = to_decimal(instance.cgst_rate) + to_decimal(instance.sgst_rate)
        elif to_decimal(instance.igst_rate) > Decimal('0.00'):
            resolved_gst_rate = to_decimal(instance.igst_rate)
        else:
            resolved_gst_rate = Decimal('18.00')

        fin = calculate_receipt_financials(
            line_items=line_items,
            subtotal_amount=subtotal_in,
            discount_amount=validated_data.get('discount_amount', instance.discount_amount),
            tax_mode=eff_tax_mode,
            supply_type=eff_supply,
            gst_rate=resolved_gst_rate,
            cgst_rate=validated_data.get('cgst_rate') if 'cgst_rate' in self.initial_data else None,
            sgst_rate=validated_data.get('sgst_rate') if 'sgst_rate' in self.initial_data else None,
            igst_rate=validated_data.get('igst_rate') if 'igst_rate' in self.initial_data else None,
            default_sac=(instance.issuer_snapshot or {}).get('sac_code', '999293'),
            fallback_title=validated_data.get('course_or_package_name', instance.course_or_package_name) or 'Course Fee',
            fallback_period=validated_data.get('installment_label', instance.installment_label) or '',
        )
        if not manual_financial_override:
            validated_data['line_items'] = fin['line_items']
            for k in (
                'subtotal_amount', 'discount_amount', 'taxable_amount',
                'tax_mode', 'supply_type',
                'cgst_rate', 'cgst_amount', 'sgst_rate', 'sgst_amount',
                'igst_rate', 'igst_amount', 'total_tax_amount', 'total_amount',
            ):
                validated_data[k] = fin[k]
        elif 'line_items' in self.initial_data:
            validated_data['line_items'] = fin['line_items']

        new_total = validated_data.get('total_amount', instance.total_amount)
        if not (manual_words_override and 'amount_in_words' in self.initial_data):
            validated_data['amount_in_words'] = amount_to_words(new_total)

        if not manual_ledger_override:
            passed_ledger_curr = self.initial_data.get('ledger_current_paid')
            if (
                'ledger_current_paid' not in self.initial_data
                or to_decimal(passed_ledger_curr) == to_decimal(instance.ledger_current_paid)
            ) and to_decimal(new_total) != to_decimal(instance.total_amount):
                validated_data['ledger_current_paid'] = new_total
                target_account = validated_data.get('account', instance.account)
                if not target_account:
                    if 'ledger_total_fee' not in self.initial_data or to_decimal(self.initial_data.get('ledger_total_fee')) == to_decimal(instance.ledger_total_fee):
                        validated_data['ledger_total_fee'] = new_total
                    if 'ledger_total_paid' not in self.initial_data or to_decimal(self.initial_data.get('ledger_total_paid')) == to_decimal(instance.ledger_total_paid):
                        validated_data['ledger_total_paid'] = new_total

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if (request and hasattr(request, 'user') and request.user.is_authenticated) else None

        manual_financial_override = validated_data.pop('manual_financial_override', False)
        manual_ledger_override = validated_data.pop('manual_ledger_override', False)
        manual_words_override = validated_data.pop('manual_words_override', False)
        explicit_gst_rate = validated_data.pop('gst_rate', None)

        if manual_ledger_override:
            validated_data['is_manual_override'] = True

        payment = validated_data.get('payment')
        account = validated_data.get('account')
        student = validated_data.get('student')

        company = (
            validated_data.get('company')
            or (payment.company if payment else None)
            or (account.company if account else None)
            or (getattr(student, 'company', None) if student else None)
            or (getattr(user, 'company', None) if user else None)
            or 'FLAG'
        )
        validated_data['company'] = company

        campus = getattr(student, 'campus', None) if student else None
        settings_obj = get_or_create_receipt_settings(company=company, campus=campus)

        # Auto-fill Student metadata for any fields not explicitly overridden
        if student:
            student_meta = extract_student_metadata(student)
            for k, v in student_meta.items():
                if not validated_data.get(k) and v:
                    validated_data[k] = v

        if account and not validated_data.get('course_or_package_name'):
            validated_data['course_or_package_name'] = account.plan_name or account.plan_code or account.plan_type

        # Auto-fill Payment metadata if linked
        if payment:
            if not validated_data.get('payment_method'):
                validated_data['payment_method'] = payment.payment_method
            if not validated_data.get('payment_reference') and payment.reference:
                validated_data['payment_reference'] = payment.reference
            if 'payment_date' not in self.initial_data and payment.payment_date:
                validated_data['payment_date'] = payment.payment_date
            if not validated_data.get('installment_label') and payment.installment:
                inst = payment.installment
                validated_data['installment_label'] = inst.label or f"Installment #{inst.sequence_number}"
            if not validated_data.get('notes') and payment.notes:
                validated_data['notes'] = payment.notes

        # Auto-fill Ledger snapshot if not manually overridden
        ledger_defaults = extract_account_ledger_snapshot(account, payment=payment)
        for k, v in ledger_defaults.items():
            if k not in self.initial_data or validated_data.get(k) is None:
                validated_data[k] = v

        # Defaults from ReceiptSettings
        if 'tax_mode' not in self.initial_data:
            validated_data['tax_mode'] = settings_obj.default_gst_mode or 'NONE'
        if 'template_style' not in self.initial_data:
            validated_data['template_style'] = settings_obj.default_template or 'EXECUTIVE'
        if not validated_data.get('place_of_supply'):
            validated_data['place_of_supply'] = settings_obj.place_of_supply or 'Kerala (32)'
        if 'terms_and_conditions' not in self.initial_data:
            validated_data['terms_and_conditions'] = settings_obj.default_terms_and_conditions

        merged_display_options = dict(DEFAULT_DISPLAY_OPTIONS)
        if isinstance(settings_obj.default_display_options, dict):
            for k, v in settings_obj.default_display_options.items():
                if k not in ('fy_sequences', 'active_fy'):
                    merged_display_options[k] = v
        if isinstance(validated_data.get('display_options'), dict):
            for k, v in validated_data['display_options'].items():
                if k not in ('fy_sequences', 'active_fy'):
                    merged_display_options[k] = v
        validated_data['display_options'] = merged_display_options

        issuer_snap = build_issuer_snapshot(settings_obj, company=company)
        if isinstance(validated_data.get('issuer_snapshot'), dict) and validated_data['issuer_snapshot']:
            issuer_snap.update(validated_data['issuer_snapshot'])
        validated_data['issuer_snapshot'] = issuer_snap

        # Determine fallback amount & title for line items
        fallback_amount = (
            validated_data.get('subtotal_amount')
            or validated_data.get('total_amount')
            or (payment.amount if payment else Decimal('0.00'))
        )
        fallback_title = (
            validated_data.get('course_or_package_name')
            or (account.plan_name if account else '')
            or 'Course Tuition Fee'
        )
        fallback_period = validated_data.get('installment_label') or ''

        fin = calculate_receipt_financials(
            line_items=validated_data.get('line_items'),
            subtotal_amount=fallback_amount,
            discount_amount=validated_data.get('discount_amount', Decimal('0.00')),
            tax_mode=validated_data.get('tax_mode', 'NONE'),
            supply_type=validated_data.get('supply_type', 'INTRA_STATE'),
            gst_rate=explicit_gst_rate if explicit_gst_rate is not None else settings_obj.default_gst_rate,
            cgst_rate=validated_data.get('cgst_rate') if 'cgst_rate' in self.initial_data else None,
            sgst_rate=validated_data.get('sgst_rate') if 'sgst_rate' in self.initial_data else None,
            igst_rate=validated_data.get('igst_rate') if 'igst_rate' in self.initial_data else None,
            default_sac=settings_obj.sac_code or '999293',
            fallback_title=fallback_title,
            fallback_period=fallback_period,
        )

        validated_data['line_items'] = fin['line_items']
        if not manual_financial_override:
            for k in (
                'subtotal_amount', 'discount_amount', 'taxable_amount',
                'tax_mode', 'supply_type',
                'cgst_rate', 'cgst_amount', 'sgst_rate', 'sgst_amount',
                'igst_rate', 'igst_amount', 'total_tax_amount', 'total_amount',
            ):
                validated_data[k] = fin[k]
        else:
            validated_data['is_manual_override'] = True
            for k in (
                'subtotal_amount', 'discount_amount', 'taxable_amount',
                'cgst_rate', 'cgst_amount', 'sgst_rate', 'sgst_amount',
                'igst_rate', 'igst_amount', 'total_tax_amount', 'total_amount',
            ):
                if k not in self.initial_data:
                    validated_data[k] = fin[k]

        if not (manual_words_override and validated_data.get('amount_in_words')):
            validated_data['amount_in_words'] = amount_to_words(validated_data.get('total_amount', Decimal('0.00')))

        # Sync ledger_current_paid and Mode B / Standalone ledger totals if not explicitly overridden
        if not manual_ledger_override:
            if 'ledger_current_paid' not in self.initial_data or to_decimal(validated_data.get('ledger_current_paid')) == Decimal('0.00'):
                validated_data['ledger_current_paid'] = validated_data['total_amount']

            if not account:
                if 'ledger_total_fee' not in self.initial_data:
                    validated_data['ledger_total_fee'] = validated_data['total_amount']
                if 'ledger_total_paid' not in self.initial_data:
                    validated_data['ledger_total_paid'] = validated_data['total_amount']
                if 'ledger_balance_due' not in self.initial_data:
                    validated_data['ledger_balance_due'] = Decimal('0.00')
            elif not payment:
                # Mode B: Account-linked without a specific FeePayment row
                prev_paid = to_decimal(validated_data.get('ledger_previously_paid'))
                curr_paid = to_decimal(validated_data.get('ledger_current_paid'))
                if 'ledger_total_paid' not in self.initial_data:
                    validated_data['ledger_total_paid'] = prev_paid + curr_paid
                if 'ledger_balance_due' not in self.initial_data:
                    total_fee = to_decimal(validated_data.get('ledger_total_fee'))
                    disc = to_decimal(validated_data.get('ledger_discount'))
                    validated_data['ledger_balance_due'] = max(
                        Decimal('0.00'),
                        total_fee - disc - to_decimal(validated_data.get('ledger_total_paid')),
                    )

        doc_type = validated_data.get('document_type', 'RECEIPT')
        rec_status = validated_data.get('status', 'ISSUED')
        if rec_status == 'VOID':
            validated_data['payment_status_badge'] = 'VOID'
            validated_data['voided_at'] = timezone.now()
            if user:
                validated_data['voided_by'] = user
        elif rec_status == 'REFUNDED':
            validated_data['payment_status_badge'] = 'REFUNDED'
        elif doc_type == 'PROFORMA':
            validated_data['payment_status_badge'] = 'PROFORMA'
        elif 'payment_status_badge' not in self.initial_data:
            if to_decimal(validated_data.get('ledger_balance_due')) > 0:
                validated_data['payment_status_badge'] = 'PARTIAL'
            else:
                validated_data['payment_status_badge'] = 'PAID'

        with transaction.atomic():
            issue_dt = validated_data.get('issue_date') or timezone.now()
            manual_number = (validated_data.get('receipt_number') or '').strip()
            if manual_number:
                validated_data['receipt_number'] = manual_number
                validated_data['financial_year'] = get_indian_financial_year(issue_dt)
                validated_data['is_manual_override'] = True
            else:
                number, fy, seq, _ = allocate_receipt_number(company=company, campus=campus, issue_date=issue_dt)
                validated_data['receipt_number'] = number
                validated_data['financial_year'] = fy
                validated_data['sequence_number'] = seq

            validated_data['created_by'] = user
            validated_data['updated_by'] = user

            rev = self._build_revision_snapshot(validated_data, user, action='CREATED', version=1)
            validated_data['snapshot_data'] = {'revisions': [rev]}

            receipt = super().create(validated_data)

            if user:
                ActivityLog.objects.create(
                    user=user,
                    company=receipt.company,
                    action='STUDENT_UPDATED',
                    entity_type='FeeReceipt',
                    entity_id=receipt.id,
                    entity_name=receipt.recipient_name,
                    description=f"Digital receipt {receipt.receipt_number} issued for {receipt.recipient_name}",
                    metadata={
                        'receipt_number': receipt.receipt_number,
                        'total_amount': str(receipt.total_amount),
                        'document_type': receipt.document_type,
                        'status': receipt.status,
                    },
                )

        return receipt

    def update(self, instance, validated_data):
        from rest_framework.exceptions import PermissionDenied

        request = self.context.get('request')
        user = request.user if (request and hasattr(request, 'user') and request.user.is_authenticated) else None

        manual_financial_override = validated_data.pop('manual_financial_override', False)
        manual_ledger_override = validated_data.pop('manual_ledger_override', False)
        manual_words_override = validated_data.pop('manual_words_override', False)
        explicit_gst_rate = validated_data.pop('gst_rate', None)

        financial_triggers = {
            'line_items', 'subtotal_amount', 'discount_amount', 'taxable_amount', 'tax_mode',
            'supply_type', 'cgst_rate', 'sgst_rate', 'igst_rate', 'cgst_amount', 'sgst_amount',
            'igst_amount', 'total_tax_amount', 'total_amount', 'gst_rate',
        }
        has_financial_change = any(k in self.initial_data for k in financial_triggers)

        if has_financial_change:
            self._recalculate_or_respect_overrides(
                instance,
                validated_data,
                explicit_gst_rate=explicit_gst_rate,
                manual_financial_override=manual_financial_override,
                manual_words_override=manual_words_override,
                manual_ledger_override=manual_ledger_override,
            )

        target_status = validated_data.get('status', instance.status)
        target_doc_type = validated_data.get('document_type', instance.document_type)

        if target_status == 'VOID':
            if user and not _can_manage_receipt_admin_actions(user):
                raise PermissionDenied('Only fee administrators can void receipts.')
            validated_data['payment_status_badge'] = 'VOID'
            if instance.status != 'VOID':
                validated_data['voided_at'] = timezone.now()
                if user:
                    validated_data['voided_by'] = user
        elif target_status == 'REFUNDED':
            validated_data['payment_status_badge'] = 'REFUNDED'
        elif target_doc_type == 'PROFORMA':
            validated_data['payment_status_badge'] = 'PROFORMA'

        if 'issue_date' in validated_data and 'financial_year' not in self.initial_data:
            validated_data['financial_year'] = get_indian_financial_year(validated_data['issue_date'])

        if isinstance(validated_data.get('display_options'), dict):
            merged_opts = dict(DEFAULT_DISPLAY_OPTIONS)
            if isinstance(instance.display_options, dict):
                for k, v in instance.display_options.items():
                    if k not in ('fy_sequences', 'active_fy'):
                        merged_opts[k] = v
            for k, v in validated_data['display_options'].items():
                if k not in ('fy_sequences', 'active_fy'):
                    merged_opts[k] = v
            validated_data['display_options'] = merged_opts

        if isinstance(validated_data.get('issuer_snapshot'), dict):
            merged_issuer = dict(instance.issuer_snapshot or {})
            merged_issuer.update(validated_data['issuer_snapshot'])
            validated_data['issuer_snapshot'] = merged_issuer

        with transaction.atomic():
            new_version = (instance.version or 1) + 1
            validated_data['version'] = new_version
            validated_data['is_manual_override'] = True
            if user:
                validated_data['updated_by'] = user

            action_label = 'VOIDED' if (target_status == 'VOID' and instance.status != 'VOID') else 'UPDATED'
            snapshot_state = {
                'receipt_number': validated_data.get('receipt_number', instance.receipt_number),
                'status': target_status,
                'document_type': target_doc_type,
                'recipient_name': validated_data.get('recipient_name', instance.recipient_name),
                'subtotal_amount': validated_data.get('subtotal_amount', instance.subtotal_amount),
                'discount_amount': validated_data.get('discount_amount', instance.discount_amount),
                'tax_mode': validated_data.get('tax_mode', instance.tax_mode),
                'total_tax_amount': validated_data.get('total_tax_amount', instance.total_tax_amount),
                'total_amount': validated_data.get('total_amount', instance.total_amount),
                'line_items': validated_data.get('line_items', instance.line_items),
            }
            existing_snap = dict(instance.snapshot_data or {})
            revisions = list(existing_snap.get('revisions') or [])
            revisions.append(self._build_revision_snapshot(snapshot_state, user, action=action_label, version=new_version))
            existing_snap['revisions'] = revisions
            validated_data['snapshot_data'] = existing_snap

            receipt = super().update(instance, validated_data)

            if user:
                ActivityLog.objects.create(
                    user=user,
                    company=receipt.company,
                    action='STUDENT_UPDATED',
                    entity_type='FeeReceipt',
                    entity_id=receipt.id,
                    entity_name=receipt.recipient_name,
                    description=f"Digital receipt {receipt.receipt_number} updated (v{receipt.version})",
                    metadata={
                        'receipt_number': receipt.receipt_number,
                        'version': receipt.version,
                        'total_amount': str(receipt.total_amount),
                    },
                )

        return receipt


class PublicReceiptVerificationSerializer(serializers.ModelSerializer):
    verified = serializers.SerializerMethodField()
    is_authentic = serializers.SerializerMethodField()
    verification_status = serializers.SerializerMethodField()
    signature_prefix = serializers.SerializerMethodField()
    issued_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FeeReceipt
        fields = [
            'verified', 'is_authentic', 'verification_status', 'signature_prefix',
            'receipt_number', 'financial_year', 'document_type', 'status', 'issue_date',
            'verification_token', 'version',
            'billed_to_type', 'recipient_name', 'student_enrollment_code',
            'course_or_package_name', 'batch_name', 'campus_name', 'grade_level', 'mode_of_study',
            'subtotal_amount', 'discount_amount', 'taxable_amount',
            'tax_mode', 'supply_type',
            'cgst_rate', 'cgst_amount', 'sgst_rate', 'sgst_amount',
            'igst_rate', 'igst_amount', 'total_tax_amount', 'total_amount',
            'amount_in_words',
            'payment_method', 'payment_reference', 'payment_date',
            'installment_label', 'payment_status_badge',
            'line_items', 'issuer_snapshot',
            'void_reason', 'voided_at', 'issued_by_name',
        ]

    def get_verified(self, obj):
        return obj.status == 'ISSUED' and verify_receipt_signature(obj)

    def get_is_authentic(self, obj):
        return obj.status == 'ISSUED' and verify_receipt_signature(obj)

    def get_verification_status(self, obj):
        if not verify_receipt_signature(obj):
            return 'TAMPER_WARNING'
        if obj.status == 'VOID':
            return 'VOID'
        if obj.status == 'DRAFT':
            return 'DRAFT'
        if obj.status == 'REFUNDED':
            return 'REFUNDED'
        return 'VALID'

    def get_signature_prefix(self, obj):
        return (obj.signature_hash or '')[:16].upper()

    def get_issued_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'FLAG Accounts Department'
