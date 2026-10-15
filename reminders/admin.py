from django.contrib import admin
from .models import Reminder, ReminderUpdate


class ReminderUpdateInline(admin.TabularInline):
    model = ReminderUpdate
    extra = 0
    readonly_fields = ('author', 'notes', 'previous_status', 'new_status', 'is_system_event', 'created_at')


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'company', 'reminder_date', 'deadline', 'priority', 'status', 'created_at')
    list_filter = ('status', 'priority', 'company', 'category', 'reminder_date')
    search_fields = ('title', 'description', 'user__username', 'user__first_name', 'user__last_name')
    inlines = [ReminderUpdateInline]


@admin.register(ReminderUpdate)
class ReminderUpdateAdmin(admin.ModelAdmin):
    list_display = ('reminder', 'author', 'previous_status', 'new_status', 'is_system_event', 'created_at')
    list_filter = ('is_system_event', 'created_at')
    search_fields = ('reminder__title', 'author__username', 'notes')
