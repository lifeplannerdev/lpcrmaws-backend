from rest_framework import serializers
from .models import (
    FdsFeeStructure, FdsBatch, FdsEnquiry, FdsTrial,
    FdsStudent, FdsWeddingGroup, FdsAttendance, FdsFeesCollection
)


# ── Minimal nested serializers ──────────────────────────────────

class FdsFeeStructureMinSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = FdsFeeStructure
        fields = ['id', 'category', 'category_display', 'amount']


class FdsBatchMinSerializer(serializers.ModelSerializer):
    class_category_display = serializers.CharField(source='get_class_category_display', read_only=True)
    time_display = serializers.CharField(read_only=True)
    enrolled_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = FdsBatch
        fields = ['id', 'name', 'class_category', 'class_category_display', 'time_display', 'enrolled_count']


# ── Fee Structure ────────────────────────────────────────────────

class FdsFeeStructureSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = FdsFeeStructure
        fields = '__all__'


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

from .models import FdsStudentFeeAccount

class FdsStudentFeeAccountSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    active_package_detail = FdsFeeStructureMinSerializer(source='active_package', read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)

    class Meta:
        model = FdsStudentFeeAccount
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'total_paid', 'total_due', 'balance_due']

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
