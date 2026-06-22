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
    lead_name                     = serializers.SerializerMethodField()
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
            'lead_name',
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

    def _get_target_number(self, obj):
        if obj.call_type == 'outgoing':
            return obj.destination or obj.called_number
        return obj.caller_number

    def get_is_lead(self, obj):
        target = self._get_target_number(obj)
        if not target:
            return False
        from leads.models import Lead
        return Lead.objects.filter(phone=target).exists()

    def get_lead_id(self, obj):
        target = self._get_target_number(obj)
        if not target:
            return None
        from leads.models import Lead
        lead = Lead.objects.filter(phone=target).first()
        return lead.id if lead else None

    def get_lead_name(self, obj):
        target = self._get_target_number(obj)
        if not target:
            return None
        from leads.models import Lead
        lead = Lead.objects.filter(phone=target).first()
        return lead.name if lead else None

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
    destination = serializers.CharField(max_length=30,  help_text="Destination mobile number")
    source      = serializers.CharField(
                      max_length=30,
                      required=False,
                      allow_blank=True,
                      help_text="Source mobile number (mobile-to-mobile / FORMAT 2 only)",
                  )