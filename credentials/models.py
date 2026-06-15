from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
import uuid

def get_fernet():
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        raise ValueError("FERNET_KEY is not set in Django settings")
    return Fernet(key.encode())

class CredentialCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default="#6B7280")
    icon_name = models.CharField(max_length=50, default="Folder")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Credential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    username = models.CharField(max_length=255, blank=True, null=True)
    web_mail = models.CharField(max_length=255, blank=True, null=True)
    encrypted_password = models.TextField()
    url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    category = models.ForeignKey(CredentialCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='credentials')
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_credentials')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    shared_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='shared_credentials', blank=True)
    shared_roles = models.ManyToManyField('accounts.Role', related_name='shared_credentials', blank=True)

    def set_password(self, raw_password):
        f = get_fernet()
        self.encrypted_password = f.encrypt(raw_password.encode()).decode()

    def get_password(self):
        f = get_fernet()
        return f.decrypt(self.encrypted_password.encode()).decode()

    def __str__(self):
        return self.title

class CredentialHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credential = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name='history')
    encrypted_password = models.TextField()
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='credential_changes')
    changed_at = models.DateTimeField(auto_now_add=True)

    def get_password(self):
        f = get_fernet()
        return f.decrypt(self.encrypted_password.encode()).decode()

class CredentialUpdateRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credential = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name='update_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credential_update_requests')
    proposed_encrypted_password = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_credential_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def set_proposed_password(self, raw_password):
        f = get_fernet()
        self.proposed_encrypted_password = f.encrypt(raw_password.encode()).decode()

    def get_proposed_password(self):
        f = get_fernet()
        return f.decrypt(self.proposed_encrypted_password.encode()).decode()
