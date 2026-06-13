from django.contrib import admin
from .models import Penalty, AttendanceDocument, Candidate, Location, AssetCategory, Asset
# Register your models here.

@admin.register(Penalty)
class PenaltyAdmin(admin.ModelAdmin):
    list_display = ['user', 'act', 'amount', 'month', 'date']
    list_filter = ['month', 'date', 'user']
    search_fields = ['user__username', 'act']
    date_hierarchy = 'date'

@admin.register(AttendanceDocument)
class AttendanceDocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'month', 'uploaded_at']
    list_filter = ['month', 'date']
    search_fields = ['name']

admin.site.register(Candidate)

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'created_at']
    list_filter = ['company']
    search_fields = ['name']

@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'status', 'company', 'assigned_to', 'assigned_location']
    list_filter = ['status', 'company', 'category']
    search_fields = ['name', 'serial_number', 'primary_phone_number', 'secondary_phone_number']
