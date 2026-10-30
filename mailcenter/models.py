from django.conf import settings
from django.db import models
from storages.backends.s3boto3 import S3Boto3Storage


class MailAccount(models.Model):
    """
    A shared or role/user-assigned Gmail / Google Workspace mailbox connected to the CRM.
    Supports strict role & user isolation, multi-alias webmail sending, and per-page assignment.
    """
    STATUS_CONNECTED = 'connected'
    STATUS_NEEDS_RECONNECT = 'needs_reconnect'
    STATUS_CHOICES = [
        (STATUS_CONNECTED, 'Connected'),
        (STATUS_NEEDS_RECONNECT, 'Needs reconnect'),
    ]

    SCOPE_PROCESSING = 'PROCESSING'
    SCOPE_FEES = 'FEES'
    SCOPE_EXECUTIVE = 'EXECUTIVE'
    SCOPE_HR = 'HR'
    SCOPE_SALES = 'SALES'
    SCOPE_GLOBAL = 'GLOBAL'
    SCOPE_CHOICES = [
        (SCOPE_PROCESSING, 'Processing & Admissions'),
        (SCOPE_FEES, 'Fees & Accounts'),
        (SCOPE_EXECUTIVE, 'Executive & Management (MD)'),
        (SCOPE_HR, 'HR & Administration'),
        (SCOPE_SALES, 'Sales & Leads'),
        (SCOPE_GLOBAL, 'Global / All Modules'),
    ]

    email = models.EmailField(unique=True)
    display_name = models.CharField(
        max_length=150, blank=True, help_text="Shown as the sender name, e.g. 'FLAG Accounts & Finance'"
    )
    send_as_email = models.EmailField(
        blank=True,
        help_text="Primary custom alias/webmail (e.g. accounts@lifeplanneruniversal.com) configured in Gmail 'Send As'",
    )
    custom_aliases = models.JSONField(
        default=list,
        blank=True,
        help_text="Additional sender aliases [{email, display_name, is_default}] available in the From selector",
    )
    module_scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_PROCESSING, db_index=True)
    company = models.CharField(max_length=20, default='FLAG', db_index=True)

    # Strict Role, Employee & Page Assignment
    assigned_roles = models.ManyToManyField(
        'accounts.Role', blank=True, related_name='mail_accounts',
        help_text="Roles permitted to view and send from this mailbox"
    )
    assigned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='assigned_mail_accounts',
        help_text="Specific employees permitted to use this mailbox irrespective of role"
    )
    allowed_pages = models.JSONField(
        default=list, blank=True,
        help_text="CRM page keys where this mailbox is enabled (e.g. ['tasks', 'penalties', 'reports', 'staff_analysis', 'processing_students', 'receipts'])"
    )

    credentials = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONNECTED)
    status_message = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-is_default', 'email']

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            MailAccount.objects.exclude(pk=self.pk).filter(
                module_scope=self.module_scope, is_default=True
            ).update(is_default=False)


class EmailSignature(models.Model):
    """A signature that can be personal (owner set) or scoped to specific roles/module."""
    name = models.CharField(max_length=120)
    body_html = models.TextField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name='mail_signatures', help_text="Empty = shared within role/module scope"
    )
    module_scope = models.CharField(
        max_length=20, choices=MailAccount.SCOPE_CHOICES, default=MailAccount.SCOPE_PROCESSING, db_index=True
    )
    scope_roles = models.ManyToManyField('accounts.Role', blank=True, related_name='mail_signatures')
    account = models.ForeignKey(
        MailAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='signatures'
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class EmailTemplate(models.Model):
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=80, blank=True, default='General')
    module_scope = models.CharField(
        max_length=20, choices=MailAccount.SCOPE_CHOICES, default=MailAccount.SCOPE_PROCESSING, db_index=True
    )
    scope_roles = models.ManyToManyField('accounts.Role', blank=True, related_name='mail_templates')
    subject = models.CharField(max_length=300, blank=True)
    body_html = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class EmailMessage(models.Model):
    DIRECTION_OUT = 'out'
    DIRECTION_IN = 'in'
    DIRECTION_CHOICES = [(DIRECTION_OUT, 'Outgoing'), (DIRECTION_IN, 'Incoming')]

    STATE_DRAFT = 'draft'
    STATE_SENDING = 'sending'
    STATE_SENT = 'sent'
    STATE_RECEIVED = 'received'
    STATE_FAILED = 'failed'
    STATE_CHOICES = [
        (STATE_DRAFT, 'Draft'),
        (STATE_SENDING, 'Sending'),
        (STATE_SENT, 'Sent'),
        (STATE_RECEIVED, 'Received'),
        (STATE_FAILED, 'Failed'),
    ]

    # Nullable student FK so messages can also belong to Staff, Leads, Tasks, Penalties, Reports, or General threads
    student = models.ForeignKey(
        'trainers.ProcessingStudent', null=True, blank=True, on_delete=models.CASCADE, related_name='mail_messages'
    )
    recipient_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='received_crm_emails'
    )
    lead = models.ForeignKey(
        'leads.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='mail_messages'
    )
    context_module = models.CharField(
        max_length=40, blank=True, default='', db_index=True,
        help_text="e.g. PROCESSING, FEES, TASKS, PENALTIES, REPORTS, STAFF_ANALYSIS, GENERAL"
    )
    context_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    context_label = models.CharField(max_length=255, blank=True, default='')
    custom_variables = models.JSONField(default=dict, blank=True)

    account = models.ForeignKey(MailAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='messages')
    sender_alias_email = models.EmailField(blank=True, default='')
    sender_display_name = models.CharField(max_length=150, blank=True, default='')

    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES, default=DIRECTION_OUT)
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=STATE_DRAFT, db_index=True)

    gmail_message_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    gmail_thread_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    gmail_draft_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    rfc_message_id = models.CharField(max_length=300, blank=True, help_text="RFC 822 Message-ID header")
    references = models.TextField(blank=True, help_text="References header used for threading")
    new_thread = models.BooleanField(default=False, help_text="Draft should start a brand new conversation")

    from_email = models.CharField(max_length=300, blank=True)
    to = models.JSONField(default=list, blank=True)
    cc = models.JSONField(default=list, blank=True)
    bcc = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body_html = models.TextField(blank=True)
    body_text = models.TextField(blank=True)
    signature_html = models.TextField(blank=True)
    snippet = models.CharField(max_length=300, blank=True)

    template = models.ForeignKey(EmailTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'state']),
            models.Index(fields=['recipient_staff', 'state']),
            models.Index(fields=['lead', 'state']),
            models.Index(fields=['context_module', 'context_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['gmail_message_id'], condition=models.Q(gmail_message_id__isnull=False),
                name='unique_gmail_message_id'
            )
        ]

    def __str__(self):
        return f"[{self.state}] {self.subject or '(no subject)'}"

    @property
    def effective_time(self):
        return self.sent_at or self.created_at


class EmailAttachment(models.Model):
    message = models.ForeignKey(EmailMessage, on_delete=models.CASCADE, related_name='attachments')
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    # Outgoing attachments: either an uploaded file or an existing student document.
    file = models.FileField(storage=S3Boto3Storage(), upload_to='mail_attachments/%Y/%m/', blank=True, null=True)
    student_document = models.ForeignKey(
        'trainers.ProcessingStudentDocument', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    # Incoming attachments are fetched from Gmail on demand.
    gmail_attachment_id = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.filename
