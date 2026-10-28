from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Reminder, ReminderUpdate, ReminderNotificationSetting

User = get_user_model()


class ReminderUserBriefSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role_names = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'full_name', 'company', 'location', 'role_names']

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username

    def get_role_names(self, obj):
        names = list(obj.db_roles.values_list('name', flat=True))
        if getattr(obj, 'role', None) and obj.role not in names:
            names.append(obj.role)
        return names


class ReminderUpdateSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_email = serializers.CharField(source='author.email', read_only=True)

    class Meta:
        model = ReminderUpdate
        fields = [
            'id',
            'reminder',
            'author',
            'author_name',
            'author_email',
            'notes',
            'previous_status',
            'new_status',
            'is_system_event',
            'created_at',
        ]
        read_only_fields = ['id', 'reminder', 'author', 'author_name', 'author_email', 'created_at']

    def get_author_name(self, obj):
        name = f"{obj.author.first_name} {obj.author.last_name}".strip()
        return name if name else obj.author.username


class ReminderProcessingStudentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        from trainers.models import ProcessingStudent
        model = ProcessingStudent
        fields = ['id', 'name', 'mobile_number', 'email', 'university', 'intake', 'program_applied']


class ReminderNotificationSettingSerializer(serializers.ModelSerializer):
    interval_display = serializers.CharField(source='get_interval_minutes_display', read_only=True)

    class Meta:
        model = ReminderNotificationSetting
        fields = [
            'id',
            'reminder',
            'is_enabled',
            'notify_start_date',
            'notify_start_time',
            'lead_days',
            'interval_minutes',
            'interval_display',
            'last_notified_at',
            'enable_in_app',
            'enable_desktop',
            'enable_sound',
            'notify_overdue_repeatedly',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reminder', 'last_notified_at', 'created_at', 'updated_at']


class ReminderSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    user_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    completed_by_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    student_phone = serializers.SerializerMethodField()
    briefing_completed_by_name = serializers.SerializerMethodField()
    is_backdated = serializers.BooleanField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    updates_count = serializers.SerializerMethodField()
    notification_setting = serializers.SerializerMethodField()

    class Meta:
        model = Reminder
        fields = [
            'id',
            'title',
            'description',
            'briefing_completed',
            'briefing_completed_at',
            'briefing_remarks',
            'briefing_completed_by',
            'briefing_completed_by_name',
            'user',
            'user_name',
            'created_by',
            'created_by_name',
            'student',
            'student_name',
            'student_phone',
            'company',
            'category',
            'reminder_date',
            'reminder_time',
            'deadline',
            'deadline_time',
            'priority',
            'status',
            'checklist',
            'completion_remarks',
            'completed_by',
            'completed_by_name',
            'completed_at',
            'approved_by',
            'approved_by_name',
            'approved_at',
            'rejection_reason',
            'is_backdated',
            'is_overdue',
            'updates_count',
            'notification_setting',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_by',
            'created_by_name',
            'user_name',
            'student_name',
            'student_phone',
            'briefing_completed_at',
            'briefing_completed_by',
            'briefing_completed_by_name',
            'completed_by',
            'completed_by_name',
            'approved_by',
            'approved_by_name',
            'approved_at',
            'completed_at',
            'is_backdated',
            'is_overdue',
            'updates_count',
            'created_at',
            'updated_at',
        ]

    def get_user_name(self, obj):
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name if name else obj.user.username

    def get_created_by_name(self, obj):
        name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return name if name else obj.created_by.username

    def get_completed_by_name(self, obj):
        if not obj.completed_by:
            return None
        name = f"{obj.completed_by.first_name} {obj.completed_by.last_name}".strip()
        return name if name else obj.completed_by.username

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return None
        name = f"{obj.approved_by.first_name} {obj.approved_by.last_name}".strip()
        return name if name else obj.approved_by.username

    def get_student_name(self, obj):
        if not obj.student:
            return None
        return obj.student.name

    def get_student_phone(self, obj):
        if not obj.student:
            return None
        return obj.student.mobile_number

    def get_briefing_completed_by_name(self, obj):
        if not obj.briefing_completed_by:
            return None
        name = f"{obj.briefing_completed_by.first_name} {obj.briefing_completed_by.last_name}".strip()
        return name if name else obj.briefing_completed_by.username

    def get_updates_count(self, obj):
        return obj.updates.count()

    def get_notification_setting(self, obj):
        setting = getattr(obj, 'notification_setting', None)
        if not setting:
            try:
                setting, _ = ReminderNotificationSetting.objects.get_or_create(
                    reminder=obj,
                    defaults={
                        'is_enabled': True,
                        'interval_minutes': 30,
                        'notify_start_date': obj.reminder_date,
                        'notify_start_time': obj.reminder_time,
                    }
                )
            except Exception:
                return None
        return ReminderNotificationSettingSerializer(setting).data

    def validate_checklist(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Checklist must be a list of items.")
        return value


class ReminderDetailSerializer(ReminderSerializer):
    updates = ReminderUpdateSerializer(many=True, read_only=True)

    class Meta(ReminderSerializer.Meta):
        fields = ReminderSerializer.Meta.fields + ['updates']
