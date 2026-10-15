from django.contrib import admin
from .models import Reminder, ReminderUpdate, ReminderNotificationSetting


class ReminderNotificationSettingInline(admin.StackedInline):
    model = ReminderNotificationSetting
    can_delete = False
    extra = 0


class ReminderUpdateInline(admin.TabularInline):
    model = ReminderUpdate
    extra = 0
    readonly_fields = ('author', 'notes', 'previous_status', 'new_status', 'is_system_event', 'created_at')


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'company', 'reminder_date', 'deadline', 'priority', 'status', 'created_at')
    list_filter = ('status', 'priority', 'company', 'category', 'reminder_date')
    search_fields = ('title', 'description', 'user__username', 'user__first_name', 'user__last_name')
    inlines = [ReminderNotificationSettingInline, ReminderUpdateInline]


@admin.register(ReminderNotificationSetting)
class ReminderNotificationSettingAdmin(admin.ModelAdmin):
    list_display = ('reminder', 'is_enabled', 'notify_start_date', 'lead_days', 'interval_minutes', 'last_notified_at', 'enable_in_app', 'enable_desktop', 'enable_sound')
    list_filter = ('is_enabled', 'interval_minutes', 'enable_in_app', 'enable_desktop', 'enable_sound')
    search_fields = ('reminder__title', 'reminder__user__username')


@admin.register(ReminderUpdate)
class ReminderUpdateAdmin(admin.ModelAdmin):
    list_display = ('reminder', 'author', 'previous_status', 'new_status', 'is_system_event', 'created_at')
    list_filter = ('is_system_event', 'created_at')
    search_fields = ('reminder__title', 'author__username', 'notes')
