from rest_framework import serializers
from .models import (
    Grade, Campus, AcademicPackage, AttendancePolicy,
    AcademicBatch, Student, StudentBatchHistory,
    GradeExamRecord, AttendanceSession, AttendanceRecord,
    PromotionEvent, DemotionEvent
)
from django.contrib.auth import get_user_model

User = get_user_model()

class UserMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = '__all__'

class CampusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campus
        fields = '__all__'

class AcademicPackageSerializer(serializers.ModelSerializer):
    grade_range = serializers.ReadOnlyField()
    class Meta:
        model = AcademicPackage
        fields = '__all__'

class AttendancePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendancePolicy
        fields = '__all__'

class AcademicBatchSerializer(serializers.ModelSerializer):
    student_count = serializers.ReadOnlyField()
    grade_progress = serializers.ReadOnlyField()
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    
    def get_trainer_name(self, obj):
        if obj.trainer:
            return obj.trainer.get_full_name().strip() or obj.trainer.username
        return None

    class Meta:
        model = AcademicBatch
        fields = '__all__'

class StudentSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    package_name = serializers.CharField(source='academic_package.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    current_grade = serializers.CharField(source='current_grade.code', read_only=True)
    current_grade_id = serializers.IntegerField(source='current_grade.id', read_only=True)
    has_pending_fees = serializers.ReadOnlyField()
    pending_fee_amount = serializers.ReadOnlyField()
    fee_status = serializers.ReadOnlyField()
    fee_account_id = serializers.ReadOnlyField()

    def get_trainer_name(self, obj):
        if obj.trainer:
            return obj.trainer.get_full_name().strip() or obj.trainer.username
        return None

    class Meta:
        model = Student
        fields = '__all__'

class StudentBatchHistorySerializer(serializers.ModelSerializer):
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    grade_code = serializers.CharField(source='grade_at_time.code', read_only=True)
    class Meta:
        model = StudentBatchHistory
        fields = '__all__'

class GradeExamRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    grade_code = serializers.CharField(source='grade.code', read_only=True)
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    model_exam_percentage = serializers.ReadOnlyField()
    grade_exam_percentage = serializers.ReadOnlyField()
    average_percentage = serializers.ReadOnlyField()
    is_eligible_for_promotion = serializers.ReadOnlyField()

    class Meta:
        model = GradeExamRecord
        fields = '__all__'

class AttendanceSessionSerializer(serializers.ModelSerializer):
    present_count = serializers.ReadOnlyField()
    absent_count = serializers.ReadOnlyField()
    pending_count = serializers.ReadOnlyField()
    total_count = serializers.ReadOnlyField()
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    
    class Meta:
        model = AttendanceSession
        fields = '__all__'

class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    session_date = serializers.DateField(source='session.date', read_only=True)
    class Meta:
        model = AttendanceRecord
        fields = '__all__'

class PromotionEventSerializer(serializers.ModelSerializer):
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    from_grade_code = serializers.CharField(source='from_grade.code', read_only=True)
    to_grade_code = serializers.CharField(source='to_grade.code', read_only=True)
    class Meta:
        model = PromotionEvent
        fields = '__all__'

class DemotionEventSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    from_batch_name = serializers.CharField(source='from_batch.name', read_only=True)
    from_grade_code = serializers.CharField(source='from_grade.code', read_only=True)
    class Meta:
        model = DemotionEvent
        fields = '__all__'
