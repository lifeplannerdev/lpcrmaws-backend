from rest_framework import serializers
from .models import Trainer, Student, Attendance, AcademicBatch, Branch, ExamResult
from django.contrib.auth import get_user_model

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
        fields = ['id', 'name', 'academic_year', 'grade', 'admission_date', 'model_exam_date', 'final_exam_date']

# Student Serializer
class StudentSerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source='trainer.user.get_full_name', read_only=True)
    academic_batch_details = AcademicBatchSerializer(source='academic_batch', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = Student
        fields = [
            'id', 'name', 'batch', 'academic_batch', 'academic_batch_details', 
            'trainer', 'trainer_name', 'branch', 'branch_name',
            'status', 'admission_date', 'notes',
            'email', 'phone_number', 'drive_link', 'student_class'
        ]

# Attendance Serializer
class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    trainer_name = serializers.CharField(source='trainer.user.get_full_name', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'date', 'trainer', 'trainer_name',
            'student', 'student_name',
            'status', 'marked_at'
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
            'full_name', 'role', 'phone', 'is_active'
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
