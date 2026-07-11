from accounts.permissions import has_dynamic_permission
from rest_framework import serializers
from .models import Trainer, Student, Attendance, AcademicBatch, Branch, ExamResult, ProcessingStudent, ProcessingDynamicField, ProcessingStudentDocument, StudentTimeline
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from decimal import Decimal
from notifications.models import Notification

User = get_user_model()

# Branch Serializer
class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'location']

# Trainer Serializer
class TrainerSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = Trainer
        fields = ['id', 'user', 'user_name', 'email', 'drive_link', 'status', 'branch', 'branch_name']

# Academic Batch Serializer
class AcademicBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicBatch
        fields = ['id', 'name', 'academic_year', 'grade', 'admission_date', 'model_exam_date', 'final_exam_date', 'default_fee_template']

# Student Timeline Serializer
class StudentTimelineSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = StudentTimeline
        fields = ['id', 'student', 'event_type', 'description', 'created_at', 'created_by', 'created_by_name']
        read_only_fields = ['created_at']

# Student Serializer
class StudentSerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source='trainer.user.get_full_name', read_only=True)
    academic_batch_details = AcademicBatchSerializer(source='academic_batch', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    fee_summary = serializers.SerializerMethodField()
    attendance_summary = serializers.SerializerMethodField()
    fee_setup_status = serializers.SerializerMethodField()
    fee_template = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = Student
        fields = [
            'id', 'name', 'batch', 'academic_batch', 'academic_batch_details', 
            'trainer', 'trainer_name', 'branch', 'branch_name',
            'status', 'admission_date', 'notes',
            'email', 'phone_number', 'drive_link', 'student_class', 'company',
            'fee_summary', 'attendance_summary', 'fee_setup_status', 'fee_template',
            'parent_name', 'parent_phone', 'mode_of_study', 'preferred_level',
            'fee_attendance_policy'
        ]
        extra_kwargs = {
            'fee_template': {'write_only': True},
        }

    def get_fee_summary(self, obj):
        try:
            account = obj.fee_account
        except Exception:
            return None

        return {
            'account_id': account.id,
            'plan_name': account.plan_name,
            'plan_code': account.plan_code,
            'plan_type': account.plan_type,
            'status': account.status,
            'total_due': str(account.total_due),
            'total_paid': str(account.total_paid),
            'balance_due': str(account.balance_due),
            'overdue_amount': str(account.overdue_amount),
            'next_due_date': account.next_due_date,
            'last_payment_date': account.last_payment_date,
            'version': account.version,
        }

    def get_fee_setup_status(self, obj):
        try:
            account = obj.fee_account
        except Exception:
            return 'PENDING_FEE_SETUP'

        return account.status

    def get_attendance_summary(self, obj):
        qs = obj.attendance_records.all()
        stats = qs.values('status').annotate(count=Count('id'))
        summary = {'total': qs.count(), 'PRESENT': 0, 'ABSENT': 0, 'NO_SESSION': 0}
        for item in stats:
            summary[item['status']] = item['count']
        return summary

    def _resolve_fee_template(self, student, template_id):
        if not template_id:
            return None

        from fees.models import FeePlanTemplate

        template = FeePlanTemplate.objects.filter(
            pk=template_id,
            company=student.company,
            is_active=True,
        ).first()
        if not template:
            raise serializers.ValidationError({'fee_template': 'Selected fee template is not available for this company.'})
        return template

    def _create_fee_account_from_template(self, student, template, request_user):
        from fees.models import StudentFeeAccount

        account = StudentFeeAccount.objects.create(
            student=student,
            company=student.company,
            template=template,
            plan_code=template.code,
            plan_name=template.name,
            plan_type=template.plan_type,
            total_due=template.total_amount,
            registration_amount=template.registration_amount,
            due_day=template.due_day,
            source_label='student-enrollment',
            plan_snapshot={
                'template': {
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
                }
            },
            created_by=request_user,
            updated_by=request_user,
        )

        recipients = [
            user for user in User.objects.filter(is_active=True, company=student.company)
            if has_dynamic_permission(user, 'fees:manage')
        ]
        trainer_user = getattr(getattr(student, 'trainer', None), 'user', None)
        if trainer_user and trainer_user.is_active:
            recipients.append(trainer_user)

        seen = set()
        if request_user:
            by = request_user.get_full_name() or request_user.username
        else:
            by = 'System'
        for user in recipients:
            if user.id in seen:
                continue
            seen.add(user.id)
            Notification.objects.create(
                user=user,
                type='fee',
                message=f"Fee plan assigned for {student.name}",
                by=by,
            )

        return account

    def create(self, validated_data):
        fee_template_id = validated_data.pop('fee_template', None)
        request = self.context.get('request')
        
        # Auto-assign branch if missing
        if not validated_data.get('branch') and validated_data.get('trainer'):
            validated_data['branch'] = validated_data['trainer'].branch
            
        with transaction.atomic():
            student = Student.objects.create(**validated_data)

            template = self._resolve_fee_template(student, fee_template_id)
            if template:
                self._create_fee_account_from_template(student, template, request.user if request else None)
            else:
                recipients = [
                    user for user in User.objects.filter(is_active=True, company=student.company)
                    if has_dynamic_permission(user, 'fees:manage')
                ]
                by = request.user.get_full_name() or request.user.username if request and hasattr(request, 'user') else 'System'
                for user in recipients:
                    Notification.objects.create(
                        user=user,
                        type='fee',
                        message=f"Action Required: Student {student.name} enrolled without a fee plan.",
                        by=by,
                    )

        return student

    def update(self, instance, validated_data):
        fee_template_id = validated_data.pop('fee_template', None)
        with transaction.atomic():
            student = super().update(instance, validated_data)

            if fee_template_id:
                template = self._resolve_fee_template(student, fee_template_id)
                try:
                    _ = student.fee_account
                except Exception:
                    request = self.context.get('request')
                    self._create_fee_account_from_template(student, template, request.user if request else None)

        return student

# Attendance Serializer
class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    trainer_name = serializers.CharField(source='trainer.user.get_full_name', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'date', 'trainer', 'trainer_name',
            'student', 'student_name',
            'status', 'marked_at', 'company',
            'approval_status', 'approved_by', 'approval_notes'
        ]
        read_only_fields = ['trainer', 'marked_at']  
        extra_kwargs = {
            'trainer': {'required': False}  
        }


class TrainerUserSerializer(serializers.ModelSerializer):
    """Serializer for listing users with TRAINER role"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'phone', 'is_active', 'company'
        ]
    
    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        return obj.username

class ExamResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    academic_batch_name = serializers.CharField(source='academic_batch.name', read_only=True)

    class Meta:
        model = ExamResult
        fields = ['id', 'student', 'student_name', 'academic_batch', 'academic_batch_name', 'exam_type', 'score', 'remarks', 'recorded_at']


class ProcessingDynamicFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingDynamicField
        fields = '__all__'


class ProcessingStudentSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    
    class Meta:
        model = ProcessingStudent
        fields = '__all__'

    def update(self, instance, validated_data):
        fee_fields = ['processing_fee_amount', 'processing_fee_paid', 'processing_fee_status']
        request = self.context.get('request')
        
        updating_fees = any(field in validated_data for field in fee_fields)
        if updating_fees:
            if not (request and getattr(request, 'user', None) and has_dynamic_permission(request.user, 'processing_students:manage_fees')):
                for field in fee_fields:
                    validated_data.pop(field, None)
                    
        return super().update(instance, validated_data)


class ProcessingStudentDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ProcessingStudentDocument
        fields = ['id', 'student', 'title', 'file', 'file_url', 'uploaded_at', 'uploaded_by', 'uploaded_by_name']

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None
