from django.contrib import admin
from .models import (
    FdsFeeStructure, FdsBatch, FdsEnquiry, FdsTrial,
    FdsStudent, FdsWeddingGroup, FdsAttendance, FdsFeesCollection
)


@admin.register(FdsFeeStructure)
class FdsFeeStructureAdmin(admin.ModelAdmin):
    list_display = ['category', 'details', 'amount', 'is_active', 'updated_at']
    list_filter = ['is_active', 'category']
    search_fields = ['category', 'details']


@admin.register(FdsBatch)
class FdsBatchAdmin(admin.ModelAdmin):
    list_display = ['name', 'class_category', 'batch_type', 'time_display', 'trainer', 'status', 'enrolled_count']
    list_filter = ['class_category', 'batch_type', 'status']
    search_fields = ['name']


@admin.register(FdsEnquiry)
class FdsEnquiryAdmin(admin.ModelAdmin):
    list_display = ['enquiry_id', 'name', 'class_interest', 'phone', 'status', 'date', 'joined']
    list_filter = ['status', 'class_interest', 'source', 'date']
    search_fields = ['name', 'phone', 'whatsapp_no', 'enquiry_id']
    date_hierarchy = 'date'


@admin.register(FdsTrial)
class FdsTrialAdmin(admin.ModelAdmin):
    list_display = ['trial_id', 'name', 'class_category', 'date', 'time', 'status', 'converted', 'trainer_rating']
    list_filter = ['status', 'class_category', 'converted', 'date']
    search_fields = ['name', 'phone', 'trial_id']


@admin.register(FdsStudent)
class FdsStudentAdmin(admin.ModelAdmin):
    list_display = ['student_id', 'name', 'class_category', 'batch', 'joining_date', 'is_active']
    list_filter = ['is_active', 'batch__class_category', 'student_type']
    search_fields = ['name', 'contact_no', 'student_id']
    date_hierarchy = 'joining_date'


@admin.register(FdsWeddingGroup)
class FdsWeddingGroupAdmin(admin.ModelAdmin):
    list_display = ['group_id', 'event_name', 'package_type', 'lead_contact_name', 'status', 'fee_amount', 'balance']
    list_filter = ['status', 'package_type']
    search_fields = ['event_name', 'lead_contact_name', 'group_id']


@admin.register(FdsAttendance)
class FdsAttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'batch', 'date', 'class_category', 'status', 'late_arrival', 'marked_by']
    list_filter = ['status', 'class_category', 'date', 'late_arrival']
    search_fields = ['student__name']
    date_hierarchy = 'date'


@admin.register(FdsFeesCollection)
class FdsFeesCollectionAdmin(admin.ModelAdmin):
    list_display = ['payment_id', 'student', 'fees_type', 'paid_amount', 'balance', 'mode_of_pay', 'status', 'pay_date']
    list_filter = ['status', 'mode_of_pay', 'fees_type']
    search_fields = ['payment_id', 'student__name']
    date_hierarchy = 'pay_date'
