from django.db import models


class VoxbayAgent(models.Model):
    name         = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=30, unique=True, db_index=True,help_text="Full phone number as sent by Voxbay, e.g. 918089040107")
    extension    = models.CharField(max_length=20, null=True, blank=True,help_text="Ext No. from Voxbay, e.g. 513")
    did_number   = models.CharField(max_length=30, null=True, blank=True,help_text="DID No. from Voxbay, e.g. 914847173519")
    department   = models.CharField(max_length=100, null=True, blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone_number})"


class VoxbayCallLog(models.Model):
    CALL_TYPE_CHOICES = [
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
    ]

    call_uuid       = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    call_type       = models.CharField(max_length=10, choices=CALL_TYPE_CHOICES, null=True, blank=True)
    called_number   = models.CharField(max_length=30, null=True, blank=True)
    caller_number   = models.CharField(max_length=30, null=True, blank=True)
    agent_number    = models.CharField(max_length=50, null=True, blank=True)
    extension       = models.CharField(max_length=50, null=True, blank=True)
    destination     = models.CharField(max_length=30, null=True, blank=True)
    caller_id       = models.CharField(max_length=30, null=True, blank=True)
    call_status             = models.CharField(max_length=20, null=True, blank=True)
    duration                = models.IntegerField(null=True, blank=True)
    conversation_duration   = models.IntegerField(null=True, blank=True)
    recording_url           = models.TextField(null=True, blank=True)
    call_start              = models.DateTimeField(null=True, blank=True)
    call_end                = models.DateTimeField(null=True, blank=True)
    dtmf                = models.CharField(max_length=100, null=True, blank=True)
    transferred_number  = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['call_status']),
            models.Index(fields=['call_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        if self.call_type == 'outgoing':
            return f"OUT {self.extension} → {self.destination} [{self.call_status}]"
        return f"IN  {self.caller_number} → {self.called_number} [{self.call_status}]"


class VoxbayDailySnapshot(models.Model):
    date = models.DateField(unique=True, db_index=True)
    report_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Voxbay Snapshot - {self.date}"