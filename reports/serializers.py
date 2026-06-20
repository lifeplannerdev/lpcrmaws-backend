from rest_framework import serializers
from .models import DailyReport, DailyReportAttachment, ReportTimingSettings

class ReportTimingSettingsSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = ReportTimingSettings
        fields = ['id', 'user', 'user_name', 'agenda_policy', 'agenda_deadline', 'report_deadline']
class DailyReportAttachmentSerializer(serializers.ModelSerializer):
    view_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DailyReportAttachment
        fields = [
            "id",
            "attached_file",
            "view_url",
            "download_url",
            "original_filename",
            "uploaded_at",
        ]
        read_only_fields = ["uploaded_at"]

    def get_view_url(self, obj):
        if obj.attached_file:
            return obj.attached_file.url
        return None

    def get_download_url(self, obj):
        return obj.get_download_url()


class DailyReportSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True
    )
    attachments = DailyReportAttachmentSerializer(many=True, read_only=True)
    file_url = serializers.SerializerMethodField()
    view_url = serializers.SerializerMethodField()

    completion_percentage = serializers.ReadOnlyField()
    is_report_late = serializers.ReadOnlyField()
    is_agenda_late = serializers.ReadOnlyField()
    agenda_late_by = serializers.ReadOnlyField()
    report_late_by = serializers.ReadOnlyField()

    class Meta:
        model = DailyReport
        fields = [
            "id", "user", "user_name", "name", 
            "report_heading", "report_text", "report_submitted_at",
            "agenda_heading", "next_day_agenda", "agenda_submitted_at",
            "completion_percentage", "is_report_late", "is_agenda_late",
            "agenda_late_by", "report_late_by",
            "file_url", "view_url",   
            "attachments",
            "report_date", "status", "review_comment",
            "reviewed_by", "reviewed_by_name",
            "report_type",
            "created_at", "updated_at", "company"
        ]
        read_only_fields = [
            "user", "status", "reviewed_by", "review_comment",
            "created_at", "updated_at",
            "report_submitted_at", "agenda_submitted_at"
        ]

    def get_file_url(self, obj):
        first = obj.attachments.first()
        return first.get_download_url() if first else None

    def get_view_url(self, obj):
        first = obj.attachments.first()
        if first and first.attached_file:
            return first.attached_file.url
        return None

    def _save_attachments(self, report, files):
        for file in files:
            original_name = file.name 
            DailyReportAttachment.objects.create(
                report=report,
                attached_file=file,         
                original_filename=original_name, 
            )

    def create(self, validated_data):
        request = self.context.get("request")
        files = request.FILES.getlist("attached_files") if request else []
        report = DailyReport.objects.create(**validated_data)
        self._save_attachments(report, files)
        return report

    def update(self, instance, validated_data):
        request = self.context.get("request")
        files = request.FILES.getlist("attached_files") if request else []

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        self._save_attachments(instance, files)
        return instance
