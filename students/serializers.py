from rest_framework import serializers
from .models import AcademicGrade, AcademicPackage, AcademicBatch, Student, ExamResult, BatchAttendance, DailyRemark

class AcademicGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicGrade
        fields = '__all__'

class AcademicPackageSerializer(serializers.ModelSerializer):
    starting_grade_detail = AcademicGradeSerializer(source='starting_grade', read_only=True)
    ending_grade_detail = AcademicGradeSerializer(source='ending_grade', read_only=True)

    class Meta:
        model = AcademicPackage
        fields = '__all__'

class AcademicBatchSerializer(serializers.ModelSerializer):
    starting_grade_detail = AcademicGradeSerializer(source='starting_grade', read_only=True)
    current_grade_detail = AcademicGradeSerializer(source='current_grade', read_only=True)
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = AcademicBatch
        fields = '__all__'
        
    def get_student_count(self, obj):
        return obj.students.filter(is_active=True).count()

class StudentSerializer(serializers.ModelSerializer):
    package_detail = AcademicPackageSerializer(source='package', read_only=True)
    batch_detail = AcademicBatchSerializer(source='batch', read_only=True)
    has_fee_due = serializers.SerializerMethodField()
    trainer_name = serializers.CharField(source='trainer.get_full_name', read_only=True)
    trainer_location = serializers.CharField(source='trainer.location', read_only=True)

    class Meta:
        model = Student
        fields = '__all__'

    def get_has_fee_due(self, obj):
        if hasattr(obj, 'fee_account') and obj.fee_account:
            return obj.fee_account.is_overdue
        return False

class ExamResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)

    class Meta:
        model = ExamResult
        fields = '__all__'

class BatchAttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    marked_by_name = serializers.SerializerMethodField()
    batch_detail = AcademicBatchSerializer(source='batch', read_only=True)

    class Meta:
        model = BatchAttendance
        fields = '__all__'

    def get_marked_by_name(self, obj):
        if obj.marked_by:
            return obj.marked_by.get_full_name() or obj.marked_by.username
        return None

class DailyRemarkSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    trainer_name = serializers.CharField(source='trainer.get_full_name', read_only=True)

    class Meta:
        model = DailyRemark
        fields = '__all__'

# Custom Serializers for Batch Promotion and Attendance submission
class BatchPromotionSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    # No extra fields needed, it's an action

class BulkAttendanceSubmitSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    date = serializers.DateField()
    attendances = serializers.ListField(
        child=serializers.DictField() # e.g. {'student_id': 1, 'status': 'PRESENT'}
    )
