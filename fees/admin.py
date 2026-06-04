from django.contrib import admin

from .models import FeePlanTemplate, StudentFeeAccount, FeeInstallment, FeePayment, FeeAdjustment


@admin.register(FeePlanTemplate)
class FeePlanTemplateAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'plan_type', 'total_amount', 'is_active')
    list_filter = ('company', 'plan_type', 'is_active')
    search_fields = ('code', 'name', 'course_label')


@admin.register(StudentFeeAccount)
class StudentFeeAccountAdmin(admin.ModelAdmin):
    list_display = ('student', 'company', 'plan_name', 'plan_type', 'status', 'total_due', 'balance_due', 'next_due_date')
    list_filter = ('company', 'plan_type', 'status')
    search_fields = ('student__name', 'plan_name', 'plan_code')


@admin.register(FeeInstallment)
class FeeInstallmentAdmin(admin.ModelAdmin):
    list_display = ('account', 'sequence_number', 'due_date', 'scheduled_amount', 'paid_amount', 'balance_amount', 'status')
    list_filter = ('status', 'due_date')


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'account', 'amount', 'payment_method', 'payment_date')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('receipt_number', 'reference')


@admin.register(FeeAdjustment)
class FeeAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('account', 'adjustment_type', 'amount_delta', 'created_at')
    list_filter = ('adjustment_type',)
