from django.contrib import admin
from .models import Trainer, Student, Attendance, ProcessingStudent, ProcessingDynamicField, AcademicBatch, Branch

admin.site.register(Trainer)
admin.site.register(Student)
admin.site.register(Attendance)
admin.site.register(AcademicBatch)
admin.site.register(Branch)

@admin.register(ProcessingStudent)
class ProcessingStudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'mobile_number', 'category', 'assigned_to')
    list_filter = ('category', 'assigned_to', 'enrollment_process_status')
    search_fields = ('name', 'mobile_number', 'email')

@admin.register(ProcessingDynamicField)
class ProcessingDynamicFieldAdmin(admin.ModelAdmin):
    list_display = ('label', 'name', 'field_type', 'is_active', 'order')
    list_filter = ('field_type', 'is_active')
    search_fields = ('name', 'label')