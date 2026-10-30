from rest_framework import serializers
from django.contrib.auth import get_user_model
from accounts.models import Role
from .models import MailAccount, EmailSignature, EmailTemplate, EmailMessage, EmailAttachment

User = get_user_model()


class MailAccountSerializer(serializers.ModelSerializer):
    assigned_roles = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Role.objects.all(), required=False
    )
    assigned_users = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), required=False
    )
    assigned_role_details = serializers.SerializerMethodField()
    assigned_user_details = serializers.SerializerMethodField()
    sender_identities = serializers.SerializerMethodField()

    class Meta:
        model = MailAccount
        fields = [
            'id', 'email', 'display_name', 'send_as_email', 'custom_aliases',
            'module_scope', 'company',
            'assigned_roles', 'assigned_role_details',
            'assigned_users', 'assigned_user_details',
            'allowed_pages', 'sender_identities',
            'status', 'status_message', 'is_default', 'is_active',
            'last_sync_at', 'connected_at',
        ]
        read_only_fields = ['status', 'status_message', 'last_sync_at', 'connected_at']

    def get_assigned_role_details(self, obj):
        return [
            {'id': r.id, 'name': r.name, 'description': r.description or ''}
            for r in obj.assigned_roles.all()
        ]

    def get_assigned_user_details(self, obj):
        return [
            {
                'id': u.id,
                'username': u.username,
                'full_name': u.get_full_name() or u.username,
                'email': u.email or '',
            }
            for u in obj.assigned_users.all()
        ]

    def get_sender_identities(self, obj):
        """
        Return all available 'From' identities for this mailbox:
        1. Primary send_as_email (if configured)
        2. Primary Gmail address
        3. Any additional custom_aliases configured on this mailbox
        """
        identities = []
        seen = set()

        if obj.send_as_email:
            sa = obj.send_as_email.strip().lower()
            seen.add(sa)
            identities.append({
                'key': f"{obj.id}:{sa}",
                'account_id': obj.id,
                'email': sa,
                'display_name': obj.display_name or '',
                'label': f"{obj.display_name} <{sa}>" if obj.display_name else sa,
                'is_alias': True,
                'is_primary_alias': True,
                'module_scope': obj.module_scope,
                'company': obj.company,
            })

        primary = (obj.email or '').strip().lower()
        if primary and primary not in seen:
            seen.add(primary)
            identities.append({
                'key': f"{obj.id}:{primary}",
                'account_id': obj.id,
                'email': primary,
                'display_name': obj.display_name or '',
                'label': f"{obj.display_name} <{primary}>" if obj.display_name else primary,
                'is_alias': False,
                'is_primary_alias': not bool(obj.send_as_email),
                'module_scope': obj.module_scope,
                'company': obj.company,
            })

        if isinstance(obj.custom_aliases, list):
            for item in obj.custom_aliases:
                if not isinstance(item, dict):
                    continue
                al_email = (item.get('email') or '').strip().lower()
                if not al_email or al_email in seen:
                    continue
                seen.add(al_email)
                al_name = (item.get('display_name') or obj.display_name or '').strip()
                identities.append({
                    'key': f"{obj.id}:{al_email}",
                    'account_id': obj.id,
                    'email': al_email,
                    'display_name': al_name,
                    'label': f"{al_name} <{al_email}>" if al_name else al_email,
                    'is_alias': True,
                    'is_primary_alias': bool(item.get('is_default')),
                    'module_scope': obj.module_scope,
                    'company': obj.company,
                })

        return identities


class EmailSignatureSerializer(serializers.ModelSerializer):
    is_shared = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    scope_roles = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Role.objects.all(), required=False
    )
    scope_role_names = serializers.SerializerMethodField()
    account_email = serializers.CharField(source='account.email', read_only=True)

    class Meta:
        model = EmailSignature
        fields = [
            'id', 'name', 'body_html', 'is_default', 'owner', 'owner_name',
            'is_shared', 'module_scope', 'scope_roles', 'scope_role_names',
            'account', 'account_email',
        ]
        read_only_fields = ['owner', 'owner_name', 'is_shared']

    def get_is_shared(self, obj):
        return obj.owner is None

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.get_full_name() or obj.owner.username
        return 'Shared'

    def get_scope_role_names(self, obj):
        return list(obj.scope_roles.values_list('name', flat=True))


class EmailTemplateSerializer(serializers.ModelSerializer):
    scope_roles = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Role.objects.all(), required=False
    )
    scope_role_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EmailTemplate
        fields = [
            'id', 'name', 'category', 'module_scope', 'scope_roles', 'scope_role_names',
            'subject', 'body_html', 'is_active', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['created_at', 'created_by', 'created_by_name']

    def get_scope_role_names(self, obj):
        return list(obj.scope_roles.values_list('name', flat=True))

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return ''


class EmailAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    document_name = serializers.CharField(source='student_document.title', read_only=True)

    class Meta:
        model = EmailAttachment
        fields = [
            'id', 'filename', 'content_type', 'size', 'file',
            'student_document', 'gmail_attachment_id', 'file_url', 'document_name'
        ]
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
    account_scope = serializers.CharField(source='account.module_scope', read_only=True)
    sender_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)
    recipient_staff_name = serializers.SerializerMethodField()
    recipient_staff_email = serializers.EmailField(source='recipient_staff.email', read_only=True)
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    display_target_name = serializers.SerializerMethodField()

    class Meta:
        model = EmailMessage
        fields = [
            'id', 'student', 'student_name',
            'recipient_staff', 'recipient_staff_name', 'recipient_staff_email',
            'lead', 'lead_name',
            'context_module', 'context_id', 'context_label', 'custom_variables',
            'account', 'account_email', 'account_scope',
            'sender_alias_email', 'sender_display_name',
            'direction', 'state',
            'gmail_message_id', 'gmail_thread_id', 'new_thread',
            'from_email', 'to', 'cc', 'bcc', 'subject', 'body_html', 'body_text', 'signature_html', 'snippet',
            'template', 'error', 'sent_at', 'created_at', 'effective_time',
            'attachments', 'sender_name', 'display_target_name',
        ]
        read_only_fields = [
            'direction', 'state', 'gmail_message_id',
            'from_email', 'error', 'sent_at', 'created_at', 'effective_time'
        ]

    def get_recipient_staff_name(self, obj):
        if obj.recipient_staff:
            return obj.recipient_staff.get_full_name() or obj.recipient_staff.username
        return ''

    def get_display_target_name(self, obj):
        if obj.context_label:
            return obj.context_label
        if obj.student:
            return obj.student.name
        if obj.recipient_staff:
            return obj.recipient_staff.get_full_name() or obj.recipient_staff.username
        if obj.lead:
            return f"Lead: {obj.lead.name}"
        if obj.direction == 'in':
            return obj.from_email or 'External Sender'
        if obj.to:
            return ', '.join(obj.to)
        return 'General'


class EmailMessageCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailMessage
        fields = [
            'student', 'recipient_staff', 'lead',
            'context_module', 'context_id', 'context_label', 'custom_variables',
            'account', 'sender_alias_email', 'sender_display_name',
            'to', 'cc', 'bcc', 'subject', 'body_html', 'signature_html',
            'template', 'new_thread', 'gmail_thread_id',
        ]
        extra_kwargs = {
            'student': {'required': False, 'allow_null': True},
            'recipient_staff': {'required': False, 'allow_null': True},
            'lead': {'required': False, 'allow_null': True},
        }
