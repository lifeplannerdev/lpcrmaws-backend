from accounts.permissions import has_dynamic_permission
from rest_framework import serializers
from .models import (
    Trainer, Student, Attendance, AcademicBatch, AcademicPackage, Branch,
    ExamResult, ProcessingStudent, ProcessingDynamicField, ProcessingStudentDocument,
    StudentTimeline, CourseLevel, CourseModule, StudentModuleProgress,
    StudentPackageEnrollment, StudentAcademicPlacement,
)
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
    grade = serializers.CharField(read_only=True)
    starting_level_name = serializers.CharField(source='starting_level.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = AcademicBatch
        fields = [
            'id', 'name', 'academic_year', 'grade', 'starting_level', 'starting_level_name',
            'branch', 'branch_name', 'admission_date', 'model_exam_date', 'final_exam_date',
            'default_fee_template'
        ]

    def validate(self, attrs):
        starting_level = attrs.get('starting_level') or getattr(self.instance, 'starting_level', None)
        branch = attrs.get('branch') or getattr(self.instance, 'branch', None)
        if not starting_level:
            raise serializers.ValidationError({'starting_level': 'Starting level is required.'})
        if not branch:
            raise serializers.ValidationError({'branch': 'Branch is required.'})
        if self.instance and self.instance.placements.exists():
            immutable_fields = {'name', 'academic_year', 'starting_level', 'branch'}
            changed = {
                field for field in immutable_fields
                if field in attrs and getattr(self.instance, f'{field}_id' if field in {'starting_level', 'branch'} else field) != (
                    attrs[field].id if field in {'starting_level', 'branch'} else attrs[field]
                )
            }
            if changed:
                raise serializers.ValidationError({
                    field: 'This batch is referenced by academic placements and its identity cannot be changed.'
                    for field in changed
                })
        return attrs

# Student Timeline Serializer
class StudentTimelineSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = StudentTimeline
        fields = ['id', 'student', 'event_type', 'description', 'created_at', 'created_by', 'created_by_name']
        read_only_fields = ['created_at']

# Academics Serializers
class CourseModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ['id', 'name', 'order']

class CourseLevelSerializer(serializers.ModelSerializer):
    modules = CourseModuleSerializer(many=True, read_only=True)
    
    class Meta:
        model = CourseLevel
        fields = ['id', 'name', 'order', 'modules']


class AcademicPackageSerializer(serializers.ModelSerializer):
    minimum_level_name = serializers.CharField(source='minimum_level.name', read_only=True)
    maximum_level_name = serializers.CharField(source='maximum_level.name', read_only=True)

    class Meta:
        model = AcademicPackage
        fields = [
            'id', 'code', 'name', 'minimum_level', 'minimum_level_name',
            'maximum_level', 'maximum_level_name', 'is_active'
        ]

    def validate(self, attrs):
        minimum = attrs.get('minimum_level') or getattr(self.instance, 'minimum_level', None)
        maximum = attrs.get('maximum_level') or getattr(self.instance, 'maximum_level', None)
        if minimum and maximum and minimum.order > maximum.order:
            raise serializers.ValidationError({'maximum_level': 'Maximum level must not precede minimum level.'})
        if self.instance and self.instance.student_enrollments.exists():
            immutable_fields = {'code', 'name', 'minimum_level', 'maximum_level'}
            changed = {
                field for field in immutable_fields
                if field in attrs and getattr(self.instance, f'{field}_id' if field in {'minimum_level', 'maximum_level'} else field) != (
                    attrs[field].id if field in {'minimum_level', 'maximum_level'} else attrs[field]
                )
            }
            if changed:
                raise serializers.ValidationError({
                    field: 'This package is already assigned to students and its academic definition cannot be changed.'
                    for field in changed
                })
        return attrs


class StudentPackageEnrollmentSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(source='package.name', read_only=True)
    package_code = serializers.CharField(source='package.code', read_only=True)
    minimum_level_name = serializers.CharField(source='package.minimum_level.name', read_only=True)
    maximum_level_name = serializers.CharField(source='package.maximum_level.name', read_only=True)

    class Meta:
        model = StudentPackageEnrollment
        fields = [
            'id', 'student', 'package', 'package_name', 'package_code',
            'minimum_level_name', 'maximum_level_name', 'status', 'started_on',
            'ended_on', 'assigned_by', 'created_at'
        ]
        read_only_fields = ['student', 'status', 'ended_on', 'assigned_by', 'created_at']


class StudentAcademicPlacementSerializer(serializers.ModelSerializer):
    academic_batch_name = serializers.CharField(source='academic_batch.name', read_only=True)
    branch_id = serializers.IntegerField(source='academic_batch.branch_id', read_only=True)
    branch_name = serializers.CharField(source='academic_batch.branch.name', read_only=True)
    level_name = serializers.CharField(source='level.name', read_only=True)
    package_name = serializers.CharField(source='package_enrollment.package.name', read_only=True)
    attendance_summary = serializers.SerializerMethodField()

    class Meta:
        model = StudentAcademicPlacement
        fields = [
            'id', 'student', 'academic_batch', 'academic_batch_name', 'branch_id',
            'branch_name', 'level', 'level_name', 'package_enrollment', 'package_name',
            'status', 'entry_reason', 'exit_reason', 'entered_on', 'exited_on',
            'created_at', 'updated_at', 'attendance_summary'
        ]

    def get_attendance_summary(self, obj):
        stats = obj.attendance_records.values('status').annotate(count=Count('id'))
        summary = {'total': 0, 'PRESENT': 0, 'ABSENT': 0, 'NO_SESSION': 0}
        for item in stats:
            summary[item['status']] = item['count']
            summary['total'] += item['count']
        return summary

class StudentModuleProgressSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    
    class Meta:
        model = StudentModuleProgress
        fields = ['id', 'student', 'module', 'module_name', 'academic_batch', 'status', 'score', 'remarks', 'recorded_at']

# Student Serializer
class StudentSerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source='trainer.user.get_full_name', read_only=True)
    academic_batch_details = AcademicBatchSerializer(source='academic_batch', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    current_level_details = CourseLevelSerializer(source='current_level', read_only=True)
    fee_summary = serializers.SerializerMethodField()
    attendance_summary = serializers.SerializerMethodField()
    fee_setup_status = serializers.SerializerMethodField()
    fee_template = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    academic_package = serializers.PrimaryKeyRelatedField(
        queryset=AcademicPackage.objects.filter(is_active=True),
        write_only=True,
        required=False,
    )
    active_academic_package = serializers.SerializerMethodField()
    active_placement_id = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            'id', 'name', 'batch', 'academic_batch', 'academic_batch_details', 
            'current_level', 'current_level_details',
            'trainer', 'trainer_name', 'branch', 'branch_name',
            'status', 'admission_date', 'notes',
            'email', 'phone_number', 'drive_link', 'student_class', 'company',
            'fee_summary', 'attendance_summary', 'fee_setup_status', 'fee_template',
            'parent_name', 'parent_phone', 'mode_of_study', 'preferred_level',
            'fee_attendance_policy', 'academic_package', 'active_academic_package',
            'active_placement_id'
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

    def get_active_academic_package(self, obj):
        enrollment = obj.package_enrollments.select_related('package').filter(status='ACTIVE').first()
        if not enrollment:
            return None
        return {
            'id': enrollment.package_id,
            'code': enrollment.package.code,
            'name': enrollment.package.name,
            'minimum_level': enrollment.package.minimum_level.name,
            'maximum_level': enrollment.package.maximum_level.name,
        }

    def get_active_placement_id(self, obj):
        placement = obj.academic_placements.filter(status='ACTIVE').only('id').first()
        return placement.id if placement else None

    def validate(self, attrs):
        protected_fields = {'academic_batch', 'current_level', 'batch', 'academic_package'}
        if self.instance:
            supplied = protected_fields.intersection(self.initial_data.keys())
            if supplied:
                raise serializers.ValidationError({
                    field: 'Academic batch, level, and package changes must use the academic workflow endpoints.'
                    for field in supplied
                })
            return attrs

        academic_batch = attrs.get('academic_batch')
        academic_package = attrs.get('academic_package')
        if not academic_batch:
            raise serializers.ValidationError({'academic_batch': 'Academic batch is required for enrollment.'})
        if not academic_package:
            raise serializers.ValidationError({'academic_package': 'Academic package is required for enrollment.'})
        if attrs.get('company', 'LP') != 'FLAG':
            raise serializers.ValidationError({'company': 'Academic enrollment is available only for FLAG students.'})
        if not attrs.get('branch') or attrs['branch'].id != academic_batch.branch_id:
            raise serializers.ValidationError({'academic_batch': 'Student branch must match the academic batch branch.'})
        if not academic_package.allows_level(academic_batch.starting_level):
            raise serializers.ValidationError({'academic_package': 'Package does not include the batch starting level.'})
        if 'batch' in self.initial_data or 'current_level' in self.initial_data:
            raise serializers.ValidationError({'batch': 'Grade is derived from the academic batch and cannot be submitted.'})
        return attrs

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
        academic_package = validated_data.pop('academic_package')
        academic_batch = validated_data.pop('academic_batch')
        request = self.context.get('request')
        
        # Auto-assign branch if missing
        if not validated_data.get('branch') and validated_data.get('trainer'):
            validated_data['branch'] = validated_data['trainer'].branch
            
        with transaction.atomic():
            student = Student.objects.create(**validated_data)

            from .academic_services import create_initial_academic_enrollment
            create_initial_academic_enrollment(
                student,
                academic_package,
                academic_batch,
                actor=request.user if request else None,
            )

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
    placement = serializers.PrimaryKeyRelatedField(read_only=True)
    level = serializers.IntegerField(source='placement.level_id', read_only=True)
    level_name = serializers.CharField(source='placement.level.name', read_only=True)
    academic_batch_name = serializers.CharField(source='placement.academic_batch.name', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'date', 'trainer', 'trainer_name',
            'student', 'student_name', 'placement', 'academic_batch', 'academic_batch_name',
            'level', 'level_name',
            'status', 'marked_at', 'company',
            'approval_status', 'approved_by', 'approval_notes'
        ]
        read_only_fields = ['trainer', 'marked_at', 'academic_batch', 'company']
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
    placement = serializers.PrimaryKeyRelatedField(
        queryset=StudentAcademicPlacement.objects.select_related('student', 'academic_batch', 'level'),
        required=False,
    )
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), required=False)
    academic_batch = serializers.PrimaryKeyRelatedField(queryset=AcademicBatch.objects.all(), required=False)
    level = serializers.IntegerField(source='placement.level_id', read_only=True)
    level_name = serializers.CharField(source='placement.level.name', read_only=True)

    class Meta:
        model = ExamResult
        fields = [
            'id', 'student', 'student_name', 'placement', 'academic_batch',
            'academic_batch_name', 'level', 'level_name', 'exam_type', 'score',
            'outcome', 'remarks', 'recorded_at', 'processed_at', 'processed_by'
        ]
        read_only_fields = ['recorded_at', 'processed_at', 'processed_by']

    def validate(self, attrs):
        placement = attrs.get('placement') or getattr(self.instance, 'placement', None)
        student = attrs.get('student') or getattr(self.instance, 'student', None)
        academic_batch = attrs.get('academic_batch') or getattr(self.instance, 'academic_batch', None)

        if self.instance and 'placement' in attrs and attrs['placement'].id != self.instance.placement_id:
            raise serializers.ValidationError({'placement': 'Exam results cannot be moved to another placement.'})

        if not placement:
            if not student or not academic_batch:
                raise serializers.ValidationError({'placement': 'Provide placement, or both student and academic_batch.'})
            placement = StudentAcademicPlacement.objects.filter(
                student=student,
                academic_batch=academic_batch,
                status='ACTIVE',
            ).select_related('level').first()
            if not placement:
                raise serializers.ValidationError({'placement': 'Student has no active placement in this academic batch.'})
            attrs['placement'] = placement

        if student and student.id != placement.student_id:
            raise serializers.ValidationError({'student': 'Student must match the selected placement.'})
        if academic_batch and academic_batch.id != placement.academic_batch_id:
            raise serializers.ValidationError({'academic_batch': 'Academic batch must match the selected placement.'})

        attrs['student'] = placement.student
        attrs['academic_batch'] = placement.academic_batch
        exam_type = attrs.get('exam_type') or getattr(self.instance, 'exam_type', None)
        outcome = attrs.get('outcome') or getattr(self.instance, 'outcome', 'PENDING')
        if exam_type != 'FINAL' and outcome != 'PENDING':
            raise serializers.ValidationError({'outcome': 'Only final exams may have a PASS or FAIL outcome.'})
        return attrs


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
