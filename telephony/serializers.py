from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import VoxbayCallLog, VoxbayAgent

User = get_user_model()

class VoxbayAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VoxbayAgent
        fields = [
            'id',
            'name',
            'phone_number',
            'extension',
            'did_number',
            'department',
            'is_active',
        ]


class VoxbayCallLogSerializer(serializers.ModelSerializer):
    duration_display              = serializers.SerializerMethodField()
    conversation_duration_display = serializers.SerializerMethodField()
    is_lead                       = serializers.SerializerMethodField()
    lead_id                       = serializers.SerializerMethodField()
    agent_name                    = serializers.SerializerMethodField()

    class Meta:
        model  = VoxbayCallLog
        fields = [
            'id',
            'call_uuid',
            'call_type',
            'called_number',
            'caller_number',
            'agent_number',
            'extension',
            'destination',
            'caller_id',
            'call_status',
            'duration',
            'duration_display',
            'conversation_duration',
            'conversation_duration_display',
            'recording_url',
            'call_start',
            'call_end',
            'dtmf',
            'transferred_number',
            'created_at',
            'updated_at',
            'is_lead',
            'lead_id',
            'agent_name',
        ]
        read_only_fields = fields

    def get_agent_name(self, obj):
        if not obj.agent_number:
            return None
        user = User.objects.filter(voxbay_number=obj.agent_number).first()
        if user:
            return user.get_full_name() or user.username
        return None

    def get_is_lead(self, obj):
        if not obj.caller_number:
            return False
        from leads.models import Lead
        return Lead.objects.filter(phone=obj.caller_number).exists()

    def get_lead_id(self, obj):
        if not obj.caller_number:
            return None
        from leads.models import Lead
        lead = Lead.objects.filter(phone=obj.caller_number).first()
        return lead.id if lead else None

    def get_duration_display(self, obj):
        if not obj.duration:
            return None
        m, s = divmod(obj.duration, 60)
        return f"{m}m {s}s" if m else f"{s}s"

    def get_conversation_duration_display(self, obj):
        if not obj.conversation_duration:
            return None
        m, s = divmod(obj.conversation_duration, 60)
        return f"{m}m {s}s" if m else f"{s}s"


class CallStatsSerializer(serializers.Serializer):
    total        = serializers.IntegerField()
    answered     = serializers.IntegerField()
    missed       = serializers.IntegerField()
    busy         = serializers.IntegerField()
    congestion   = serializers.IntegerField()
    chanunavail  = serializers.IntegerField()
    incoming     = serializers.IntegerField()
    outgoing     = serializers.IntegerField()
    avg_duration = serializers.FloatField()
    success_rate = serializers.FloatField()


class ClickToCallSerializer(serializers.Serializer):
    uid         = serializers.CharField(max_length=100)
    upin        = serializers.CharField(max_length=100)
    user_no     = serializers.CharField(max_length=50,  help_text="Extension number")
    destination = serializers.CharField(max_length=30,  help_text="Destination mobile number")
    callerid    = serializers.CharField(max_length=30,  help_text="DID number to show as caller ID")
    source      = serializers.CharField(
                      max_length=30,
                      required=False,
                      allow_blank=True,
                      help_text="Source mobile number (mobile-to-mobile / FORMAT 2 only)",
                  )