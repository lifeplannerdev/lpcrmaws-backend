from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
import re

from .models import Lead, LeadAssignment, FollowUp, RemarkHistory
from accounts.utils import log_activity
from notifications.models import Notification
from utils.pusher import trigger_pusher

User = get_user_model()
 
 
def _user_label(user):
    if not user:
        return 'Unknown'
    return user.get_full_name() or user.username
 
 
@receiver(pre_save, sender=Lead)
def capture_lead_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Lead.objects.get(pk=instance.pk)
            instance._old_status            = old.status
            instance._old_processing_status = old.processing_status
            instance._old_assigned_to       = old.assigned_to_id
            instance._old_sub_assigned_to   = old.sub_assigned_to_id
            instance._old_remarks           = old.remarks
        except Lead.DoesNotExist:
            instance._old_status = instance._old_processing_status = None
            instance._old_assigned_to = instance._old_sub_assigned_to = None
            instance._old_remarks = None
    else:
        instance._old_status = instance._old_processing_status = None
        instance._old_assigned_to = instance._old_sub_assigned_to = None
        instance._old_remarks = None
 
 
@receiver(post_save, sender=Lead)
def log_lead_activity(sender, instance, created, **kwargs):
    from utils.pusher import notify_lead_created, notify_lead_updated
    from leads.serializers import LeadListSerializer
    
    label = instance.name
    # Use assigned_by as the acting user (whoever created/modified)
    acting_user = instance.assigned_by or instance.assigned_to
    
    # Trigger pusher
    try:
        # Pass a mock context for the serializer to avoid requiring full request context if possible
        lead_data = LeadListSerializer(instance).data
        if created:
            notify_lead_created(lead_data)
        else:
            notify_lead_updated(lead_data)
    except Exception as e:
        print(f"[Pusher Signal Error] {e}")

    if created:
        log_activity(
            action='LEAD_CREATED',
            entity_type='Lead',
            entity_id=instance.pk,
            entity_name=label,
            user=acting_user,   # ← FIXED: was missing before
            description=f'New lead "{label}" was created.',
            metadata={
                'phone': instance.phone,
                'source': instance.source,
                'status': instance.status,
                'priority': instance.priority,
            },
        )
        return

    if getattr(instance, '_old_status', None) != instance.status:
        log_activity(
            action='LEAD_STATUS_CHANGED',
            entity_type='Lead',
            entity_id=instance.pk,
            entity_name=label,
            user=acting_user,   # ← FIXED
            description=f'Lead "{label}" status changed from {instance._old_status} → {instance.status}.',
            metadata={'old_status': instance._old_status, 'new_status': instance.status},
        )

    if getattr(instance, '_old_processing_status', None) != instance.processing_status:
        log_activity(
            action='LEAD_PROCESSING_UPDATED',
            entity_type='Lead',
            entity_id=instance.pk,
            entity_name=label,
            user=acting_user,   # ← FIXED
            description=f'Lead "{label}" processing status changed from {instance._old_processing_status} → {instance.processing_status}.',
            metadata={
                'old_processing_status': instance._old_processing_status,
                'new_processing_status': instance.processing_status,
            },
        )

    if getattr(instance, '_old_assigned_to', None) != instance.assigned_to_id:
        assignee = _user_label(instance.assigned_to)
        log_activity(
            action='LEAD_ASSIGNED',
            entity_type='Lead',
            entity_id=instance.pk,
            entity_name=label,
            user=instance.assigned_by,  # ← FIXED: the person who assigned
            description=f'Lead "{label}" was assigned to "{assignee}".',
            metadata={'assigned_to': assignee},
        )

    if getattr(instance, '_old_sub_assigned_to', None) != instance.sub_assigned_to_id:
        if instance.sub_assigned_to:
            sub = _user_label(instance.sub_assigned_to)
            log_activity(
                action='LEAD_SUB_ASSIGNED',
                entity_type='Lead',
                entity_id=instance.pk,
                entity_name=label,
                user=instance.sub_assigned_by,  # ← FIXED
                description=f'Lead "{label}" was sub-assigned to "{sub}".',
                metadata={'sub_assigned_to': sub},
            )
        else:
            log_activity(
                action='LEAD_UNASSIGNED',
                entity_type='Lead',
                entity_id=instance.pk,
                entity_name=label,
                user=acting_user,
                description=f'Lead "{label}" sub-assignment was removed.',
            )

    if getattr(instance, '_old_remarks', None) != instance.remarks:
        log_activity(
            action='LEAD_REMARK_UPDATED',
            entity_type='Lead',
            entity_id=instance.pk,
            entity_name=label,
            user=acting_user,   # ← FIXED
            description=f'Remarks updated for lead "{label}".',
            metadata={'old_remarks': instance._old_remarks, 'new_remarks': instance.remarks},
        )


@receiver(post_delete, sender=Lead)
def log_lead_deleted(sender, instance, **kwargs):
    from utils.pusher import notify_lead_deleted
    try:
        notify_lead_deleted(instance.pk)
    except Exception as e:
        print(f"[Pusher Signal Error] {e}")

    log_activity(
        action='LEAD_DELETED',
        entity_type='Lead',
        entity_id=instance.pk,
        entity_name=instance.name,
        user=instance.assigned_by,
        description=f'Lead "{instance.name}" ({instance.phone}) was deleted.',
    )
 
 
@receiver(pre_save, sender=FollowUp)
def capture_followup_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = FollowUp.objects.get(pk=instance.pk)
            instance._old_fu_status  = old.status
            instance._old_converted  = old.converted_to_lead
        except FollowUp.DoesNotExist:
            instance._old_fu_status = None
            instance._old_converted = False
    else:
        instance._old_fu_status = None
        instance._old_converted = False
 
 
@receiver(post_save, sender=FollowUp)
def log_followup_activity(sender, instance, created, **kwargs):
    label = instance.name or instance.phone_number
 
    if created:
        log_activity(
            action='FOLLOWUP_CREATED',
            entity_type='FollowUp',
            entity_id=instance.pk,
            entity_name=label,
            user=instance.assigned_to,   # ← FIXED: always set
            description=f'Follow-up created for "{label}" on {instance.follow_up_date}.',
            metadata={'type': instance.followup_type, 'priority': instance.priority, 'date': str(instance.follow_up_date)},
        )
        return
 
    if getattr(instance, '_old_fu_status', None) != instance.status:
        log_activity(
            action='FOLLOWUP_STATUS_CHANGED',
            entity_type='FollowUp',
            entity_id=instance.pk,
            entity_name=label,
            user=instance.assigned_to,   # ← FIXED
            description=f'Follow-up for "{label}" status changed from {instance._old_fu_status} → {instance.status}.',
            metadata={'old_status': instance._old_fu_status, 'new_status': instance.status},
        )
 
    if not getattr(instance, '_old_converted', False) and instance.converted_to_lead:
        log_activity(
            action='FOLLOWUP_CONVERTED',
            entity_type='FollowUp',
            entity_id=instance.pk,
            entity_name=label,
            user=instance.assigned_to,   # ← FIXED
            description=f'Follow-up for "{label}" was converted to a lead.',
        )
 
 
def recalculate_lead_status(lead):
    """Recalculate lead status based on its follow-ups. Prevent downgrading advanced states."""
    if not lead:
        return
    
    # Do not regress leads that have advanced beyond these states
    if lead.status not in ['ENQUIRY', 'CONTACTED', 'NOT_INTERESTED']:
        return

    from .models import FollowUp
    followups = FollowUp.objects.filter(lead=lead)
    has_contacted = followups.filter(status='contacted').exists()
    has_not_interested = followups.filter(status='not_interested').exists()

    new_status = 'ENQUIRY'
    if has_contacted:
        new_status = 'CONTACTED'
    elif has_not_interested:
        new_status = 'NOT_INTERESTED'

    if lead.status != new_status:
        lead.status = new_status
        lead.save(update_fields=['status'])


@receiver(post_save, sender=FollowUp)
def sync_lead_status_from_followup(sender, instance, created, **kwargs):
    """Automatically update the parent Lead status when a follow-up is modified."""
    recalculate_lead_status(instance.lead)
 
 
@receiver(post_delete, sender=FollowUp)
def log_followup_deleted(sender, instance, **kwargs):
    label = instance.name or instance.phone_number
    log_activity(
        action='FOLLOWUP_DELETED',
        entity_type='FollowUp',
        entity_id=instance.pk,
        entity_name=label,
        user=instance.assigned_to,
        description=f'Follow-up for "{label}" was deleted.',
    )
    recalculate_lead_status(instance.lead)
 
@receiver(post_save, sender=RemarkHistory)
def parse_mentions_in_remarks(sender, instance, created, **kwargs):
    if created and instance.new_remarks:
        mentions = set(re.findall(r'@(\w+)', instance.new_remarks))
        for username in mentions:
            try:
                user = User.objects.get(username__iexact=username)
                if user != instance.changed_by:
                    acting_name = instance.changed_by.get_full_name() if instance.changed_by else "System"
                    msg = f"{acting_name} mentioned you in a remark on lead {instance.lead.name}"
                    notif = Notification.objects.create(
                        user=user,
                        type='lead',
                        message=msg,
                        by=acting_name
                    )
                    trigger_pusher(f'private-user-{user.id}', 'new-notification', {
                        'id': notif.id,
                        'message': msg,
                        'type': 'lead'
                    })
            except User.DoesNotExist:
                pass