from rest_framework import serializers
from .models import (
    FdsFeeStructure, FdsBatch, FdsEnquiry, FdsTrial,
    FdsStudent, FdsWeddingGroup, FdsAttendance, FdsFeesCollection
)


# ── Minimal nested serializers ──────────────────────────────────

class FdsFeeStructureMinSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    batch_type_display = serializers.SerializerMethodField()

    class Meta:
        model = FdsFeeStructure
        fields = ['id', 'name', 'category', 'category_display', 'batch_type', 'batch_type_display', 'admission_fee', 'amount', 'duration_months', 'sessions_per_week']

    def get_category_display(self, obj):
        choices = dict(FdsFeeStructure.FEE_CATEGORY_CHOICES)
        return choices.get(obj.category, obj.category.title() if obj.category else '')

    def get_batch_type_display(self, obj):
        return (obj.batch_type or '').title()


class FdsBatchMinSerializer(serializers.ModelSerializer):
    class_category_display = serializers.CharField(source='get_class_category_display', read_only=True)
    time_display = serializers.CharField(read_only=True)
    enrolled_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = FdsBatch
        fields = ['id', 'name', 'class_category', 'class_category_display', 'time_display', 'enrolled_count']


# ── Fee Structure ────────────────────────────────────────────────

class FdsFeeStructureSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    batch_type_display = serializers.SerializerMethodField()
    category = serializers.CharField(max_length=50, default='DANCE', required=False)

    class Meta:
        model = FdsFeeStructure
        fields = '__all__'

    def get_category_display(self, obj):
        choices = dict(FdsFeeStructure.FEE_CATEGORY_CHOICES)
        return choices.get(obj.category, obj.category.title() if obj.category else '')

    def get_batch_type_display(self, obj):
        return (obj.batch_type or '').title()


# ── Batch ────────────────────────────────────────────────────────

class FdsBatchSerializer(serializers.ModelSerializer):
    class_category_display = serializers.CharField(source='get_class_category_display', read_only=True)
    batch_type_display = serializers.CharField(source='get_batch_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    time_display = serializers.CharField(read_only=True)
    enrolled_count = serializers.IntegerField(read_only=True)
    trainer_name = serializers.SerializerMethodField()

    class Meta:
        model = FdsBatch
        fields = '__all__'

    def get_trainer_name(self, obj):
        if obj.trainer:
            return f"{obj.trainer.first_name} {obj.trainer.last_name}".strip() or obj.trainer.username
        return None


# ── Enquiry ──────────────────────────────────────────────────────

class FdsEnquirySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    class_interest_display = serializers.CharField(source='get_class_interest_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    has_trial = serializers.SerializerMethodField()
    has_student = serializers.SerializerMethodField()

    class Meta:
        model = FdsEnquiry
        fields = '__all__'
        read_only_fields = ['enquiry_id', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.username
        return None

    def get_has_trial(self, obj):
        return obj.trials.exists()

    def get_has_student(self, obj):
        return hasattr(obj, 'converted_student') and obj.converted_student is not None


# ── Trial ────────────────────────────────────────────────────────

class FdsTrialSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class_category_display = serializers.CharField(source='get_class_category_display', read_only=True)
    enquiry_name = serializers.SerializerMethodField()
    conducted_by_name = serializers.SerializerMethodField()
    has_student = serializers.SerializerMethodField()

    class Meta:
        model = FdsTrial
        fields = '__all__'
        read_only_fields = ['trial_id', 'created_at', 'updated_at']

    def get_enquiry_name(self, obj):
        return obj.enquiry.name if obj.enquiry else None

    def get_conducted_by_name(self, obj):
        if obj.conducted_by:
            return f"{obj.conducted_by.first_name} {obj.conducted_by.last_name}".strip() or obj.conducted_by.username
        return None

    def get_has_student(self, obj):
        return hasattr(obj, 'converted_student') and obj.converted_student is not None


# ── Student ──────────────────────────────────────────────────────

class FdsStudentSerializer(serializers.ModelSerializer):
    student_type_display = serializers.CharField(source='get_student_type_display', read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    age = serializers.IntegerField(read_only=True)
    class_category = serializers.CharField(read_only=True)
    batch_detail = FdsBatchMinSerializer(source='batch', read_only=True)
    fee_structure_detail = FdsFeeStructureMinSerializer(source='fee_structure', read_only=True)
    enquiry_detail = FdsEnquirySerializer(source='enquiry', read_only=True)
    trial_detail = FdsTrialSerializer(source='trial', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    attendance_summary = serializers.SerializerMethodField()

    class Meta:
        model = FdsStudent
        fields = '__all__'
        read_only_fields = ['student_id', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.username
        return None

    def get_attendance_summary(self, obj):
        atts = obj.fds_attendances.all()
        total = atts.count()
        present = atts.filter(status='PRESENT').count()
        return {
            'total': total,
            'present': present,
            'absent': atts.filter(status='ABSENT').count(),
            'leave': atts.filter(status='LEAVE').count(),
            'percentage': round((present / total * 100), 1) if total > 0 else 0,
        }


# ── Wedding Group ─────────────────────────────────────────────────

class FdsWeddingGroupSerializer(serializers.ModelSerializer):
    package_type_display = serializers.CharField(source='get_package_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    classes_remaining = serializers.IntegerField(read_only=True)
    batch_detail = FdsBatchMinSerializer(source='batch', read_only=True)
    trainer_name = serializers.SerializerMethodField()

    class Meta:
        model = FdsWeddingGroup
        fields = '__all__'
        read_only_fields = ['group_id', 'created_at', 'updated_at']

    def get_trainer_name(self, obj):
        if obj.trainer:
            return f"{obj.trainer.first_name} {obj.trainer.last_name}".strip() or obj.trainer.username
        return None


# ── Attendance ────────────────────────────────────────────────────

class FdsAttendanceSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class_category_display = serializers.CharField(source='get_class_category_display', read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    marked_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FdsAttendance
        fields = '__all__'
        read_only_fields = ['marked_at']

    def get_marked_by_name(self, obj):
        if obj.marked_by:
            return f"{obj.marked_by.first_name} {obj.marked_by.last_name}".strip() or obj.marked_by.username
        return None


class FdsAttendanceBulkSerializer(serializers.Serializer):
    """For bulk-marking attendance for an entire batch on a date."""
    batch_id = serializers.IntegerField()
    date = serializers.DateField()
    records = serializers.ListField(
        child=serializers.DictField()  # [{student_id, status, late_arrival, notes}]
    )


# ── Fees Collection ───────────────────────────────────────────────

from .models import FdsStudentFeeAccount, FdsFeeInstallment, FdsFeeAdjustment

class FdsFeeInstallmentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = FdsFeeInstallment
        fields = '__all__'
        read_only_fields = ['paid_amount', 'balance_amount', 'created_at', 'updated_at']

class FdsFeeAdjustmentSerializer(serializers.ModelSerializer):
    adjustment_type_display = serializers.CharField(source='get_adjustment_type_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FdsFeeAdjustment
        fields = '__all__'
        read_only_fields = ['created_at', 'created_by']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.username
        return None

class FdsFeesCollectionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    mode_of_pay_display = serializers.CharField(source='get_mode_of_pay_display', read_only=True)
    fees_type_detail = FdsFeeStructureMinSerializer(source='fees_type', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_id_code = serializers.SerializerMethodField()
    wedding_group_name = serializers.SerializerMethodField()
    collected_by_name = serializers.SerializerMethodField()
    fee_month_display = serializers.SerializerMethodField()

    class Meta:
        model = FdsFeesCollection
        fields = '__all__'
        read_only_fields = ['payment_id', 'created_at', 'balance']

    def get_student_name(self, obj):
        return obj.student.name if obj.student else None

    def get_student_id_code(self, obj):
        return obj.student.student_id if obj.student else None

    def get_wedding_group_name(self, obj):
        return obj.wedding_group.event_name if obj.wedding_group else None

    def get_collected_by_name(self, obj):
        if obj.collected_by:
            return f"{obj.collected_by.first_name} {obj.collected_by.last_name}".strip() or obj.collected_by.username
        return None

    def get_fee_month_display(self, obj):
        if obj.fee_month and obj.fee_year:
            import calendar
            return f"{calendar.month_name[obj.fee_month]} {obj.fee_year}"
        return None

class FdsStudentFeeAccountSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    plan_type_display = serializers.CharField(source='get_plan_type_display', read_only=True)
    active_package_detail = FdsFeeStructureMinSerializer(source='active_package', read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    class_category = serializers.CharField(source='student.class_category', read_only=True)
    contact_no = serializers.CharField(source='student.contact_no', read_only=True)
    whatsapp_no = serializers.CharField(source='student.whatsapp_no', read_only=True)
    batch_name = serializers.CharField(source='student.batch.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    installments = FdsFeeInstallmentSerializer(many=True, read_only=True)
    payments = FdsFeesCollectionSerializer(many=True, read_only=True)
    adjustments = FdsFeeAdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = FdsStudentFeeAccount
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'total_paid', 'total_due', 'balance_due', 'overdue_amount']

    def get_trainer_name(self, obj):
        if obj.student and obj.student.batch and obj.student.batch.trainer:
            t = obj.student.batch.trainer
            return f"{t.first_name} {t.last_name}".strip() or t.username
        return None

class FdsStudentFeeAccountCreateSerializer(serializers.ModelSerializer):
    first_installment_date = serializers.DateField(required=False, allow_null=True, write_only=True)
    installment_count = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    installment_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, write_only=True)

    class Meta:
        model = FdsStudentFeeAccount
        fields = [
            'student', 'active_package', 'plan_code', 'plan_name', 'plan_type',
            'total_due', 'registration_amount', 'due_day', 'start_date', 'next_due_date',
            'notes', 'status', 'first_installment_date', 'installment_count', 'installment_amount'
        ]
        extra_kwargs = {
            'student': {'required': False}
        }

    def update(self, instance, validated_data):
        validated_data.pop('first_installment_date', None)
        validated_data.pop('installment_count', None)
        validated_data.pop('installment_amount', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        instance.recalculate(save=True)
        return instance

    def create(self, validated_data):
        first_installment_date = validated_data.pop('first_installment_date', None)
        installment_count = validated_data.pop('installment_count', None)
        installment_amount = validated_data.pop('installment_amount', None)

        student = validated_data['student']
        package = validated_data.get('active_package')
        if package and not validated_data.get('total_due'):
            validated_data['total_due'] = package.amount
            if not validated_data.get('plan_name'):
                validated_data['plan_name'] = package.get_category_display()

        account, created = FdsStudentFeeAccount.objects.get_or_create(
            student=student,
            defaults=validated_data
        )
        if not created:
            for k, v in validated_data.items():
                setattr(account, k, v)
            account.save()

        # Generate installments if specified or if plan_type is INSTALLMENT or MONTHLY
        if installment_count and installment_amount and installment_count > 0 and installment_amount > 0:
            from calendar import monthrange
            import datetime
            base_date = first_installment_date or account.start_date or timezone.localdate()
            due_day = account.due_day or 10
            installments = []
            for i in range(installment_count):
                month = (base_date.month - 1 + i)
                year = base_date.year + month // 12
                month = month % 12 + 1
                days_in_month = monthrange(year, month)[1]
                day = min(due_day, days_in_month)
                due_date = datetime.date(year, month, day)

                installments.append(FdsFeeInstallment(
                    account=account,
                    sequence_number=i + 1,
                    label=f"Month {i + 1} ({due_date.strftime('%B %Y')})",
                    due_date=due_date,
                    scheduled_amount=installment_amount,
                    balance_amount=installment_amount,
                    status='PENDING'
                ))
            if installments:
                account.installments.all().delete()
                FdsFeeInstallment.objects.bulk_create(installments)
                account.recalculate(save=True)
        else:
            account.recalculate(save=True)

        return account
