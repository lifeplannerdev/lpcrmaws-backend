from rest_framework import serializers
from .models import MailAccount, EmailSignature, EmailTemplate, EmailMessage, EmailAttachment

class MailAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = MailAccount
        fields = ['id', 'email', 'display_name', 'status', 'status_message', 'is_default', 'is_active', 'last_sync_at']
        read_only_fields = ['status', 'status_message', 'last_sync_at']


class EmailSignatureSerializer(serializers.ModelSerializer):
    is_shared = serializers.SerializerMethodField()

    class Meta:
        model = EmailSignature
        fields = ['id', 'name', 'body_html', 'is_default', 'owner', 'is_shared']
        read_only_fields = ['owner', 'is_shared']

    def get_is_shared(self, obj):
        return obj.owner is None


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ['id', 'name', 'category', 'subject', 'body_html', 'is_active', 'created_at']
        read_only_fields = ['created_at']


class EmailAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    document_name = serializers.CharField(source='student_document.title', read_only=True)

    class Meta:
        model = EmailAttachment
        fields = ['id', 'filename', 'content_type', 'size', 'file', 'student_document', 'gmail_attachment_id', 'file_url', 'document_name']
        read_only_fields = ['size', 'content_type', 'gmail_attachment_id', 'file_url', 'document_name']

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        elif obj.student_document and obj.student_document.document:
            return obj.student_document.document.url
        return None


class EmailMessageSerializer(serializers.ModelSerializer):
    attachments = EmailAttachmentSerializer(many=True, read_only=True)
    account_email = serializers.CharField(source='account.email', read_only=True)
    sender_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)

    class Meta:
        model = EmailMessage
        fields = [
            'id', 'student', 'student_name', 'account', 'account_email', 'direction', 'state',
            'gmail_message_id', 'gmail_thread_id', 'new_thread',
            'from_email', 'to', 'cc', 'bcc', 'subject', 'body_html', 'body_text', 'signature_html', 'snippet',
            'template', 'error', 'sent_at', 'created_at', 'effective_time', 'attachments', 'sender_name'
        ]
        read_only_fields = [
            'direction', 'state', 'gmail_message_id', 'gmail_thread_id',
            'from_email', 'error', 'sent_at', 'created_at', 'effective_time'
        ]

class EmailMessageCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailMessage
        fields = [
            'student', 'account', 'to', 'cc', 'bcc', 'subject', 'body_html', 'signature_html', 'template', 'new_thread'
        ]
