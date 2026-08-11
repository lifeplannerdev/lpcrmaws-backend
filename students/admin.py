from django.contrib import admin
from .models import AcademicGrade, AcademicPackage, AcademicBatch, Student, ExamResult, BatchAttendance, DailyRemark

@admin.register(AcademicGrade)
class AcademicGradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')

@admin.register(AcademicPackage)
class AcademicPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'starting_grade', 'ending_grade')

@admin.register(AcademicBatch)
class AcademicBatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'current_grade', 'status', 'trainer', 'created_at')
    list_filter = ('status', 'current_grade')

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'batch', 'package', 'fee_attendance_policy', 'is_active')
    list_filter = ('company', 'is_active', 'fee_attendance_policy', 'batch')

@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'batch', 'grade', 'marks', 'status')
    list_filter = ('status', 'grade', 'batch')

@admin.register(BatchAttendance)
class BatchAttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'batch', 'date', 'status', 'approval_status')
    list_filter = ('status', 'approval_status', 'date', 'batch')

@admin.register(DailyRemark)
class DailyRemarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'trainer', 'created_at')
