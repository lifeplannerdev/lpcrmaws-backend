from rest_framework import serializers
from .models import (
    Grade, Campus, AcademicPackage,
    AcademicBatch, GradeBatch, Student, StudentBatchHistory,
    ExamRecord, AttendanceSession, AttendanceRecord
)
from django.contrib.auth import get_user_model

User = get_user_model()

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

class GradeBatchSerializer(serializers.ModelSerializer):
    grade_code = serializers.CharField(source='grade.code', read_only=True)
    academic_batch_name = serializers.CharField(source='academic_batch.name', read_only=True)
    class Meta:
        model = GradeBatch
        fields = '__all__'

class AcademicBatchSerializer(serializers.ModelSerializer):
    student_count = serializers.ReadOnlyField()
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    package_name = serializers.CharField(source='package.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    grade_batches = GradeBatchSerializer(many=True, read_only=True)
    
    def get_trainer_name(self, obj):
        if obj.trainer:
            return obj.trainer.get_full_name().strip() or obj.trainer.username
        return None

    class Meta:
        model = AcademicBatch
        fields = '__all__'

class StudentSerializer(serializers.ModelSerializer):
    campus = serializers.PrimaryKeyRelatedField(read_only=True)
    academic_package = serializers.PrimaryKeyRelatedField(read_only=True)
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    grade_batch_id = serializers.IntegerField(source='grade_batch.id', read_only=True)
    current_grade = serializers.CharField(source='grade_batch.grade.code', read_only=True)
    package_name = serializers.CharField(source='academic_package.name', read_only=True)
    trainer_name = serializers.SerializerMethodField()
    has_pending_fees = serializers.ReadOnlyField()
    pending_fee_amount = serializers.ReadOnlyField()
    fee_status = serializers.ReadOnlyField()
    fee_account_id = serializers.ReadOnlyField()

    def get_trainer_name(self, obj):
        trainer = obj.trainer or (obj.batch.trainer if obj.batch else None)
        if trainer:
            return trainer.get_full_name().strip() or trainer.username
        return None

    class Meta:
        model = Student
        fields = '__all__'

class StudentBatchHistorySerializer(serializers.ModelSerializer):
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    grade_code = serializers.CharField(source='grade_batch.grade.code', read_only=True)
    class Meta:
        model = StudentBatchHistory
        fields = '__all__'

class ExamRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    grade_code = serializers.CharField(source='grade_batch.grade.code', read_only=True)
    batch_name = serializers.CharField(source='grade_batch.academic_batch.name', read_only=True)

    class Meta:
        model = ExamRecord
        fields = '__all__'

class AttendanceSessionSerializer(serializers.ModelSerializer):
    present_count = serializers.ReadOnlyField()
    absent_count = serializers.ReadOnlyField()
    pending_count = serializers.ReadOnlyField()
    total_count = serializers.ReadOnlyField()
    batch_name = serializers.CharField(source='grade_batch.academic_batch.name', read_only=True)
    grade_name = serializers.CharField(source='grade_batch.grade.name', read_only=True)
    
    class Meta:
        model = AttendanceSession
        fields = '__all__'

class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    session_date = serializers.DateField(source='session.date', read_only=True)
    grade_batch_name = serializers.CharField(source='session.grade_batch.academic_batch.name', read_only=True)
    class Meta:
        model = AttendanceRecord
        fields = '__all__'
