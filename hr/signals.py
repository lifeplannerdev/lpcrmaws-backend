from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver

from .models import Penalty, AttendanceDocument, Asset
from accounts.utils import log_activity


def _user_label(user):
    if not user:
        return 'Unknown'
    return user.get_full_name() or user.username


# ── Penalty Signals ───────────────────────────────────────────────────────────

@receiver(pre_save, sender=Penalty)
def capture_penalty_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Penalty.objects.get(pk=instance.pk)
            instance._old_penalty_amount = old.amount
            instance._old_penalty_act    = old.act
        except Penalty.DoesNotExist:
            instance._old_penalty_amount = None
            instance._old_penalty_act    = None
    else:
        instance._old_penalty_amount = None
        instance._old_penalty_act    = None


@receiver(post_save, sender=Penalty)
def log_penalty_activity(sender, instance, created, **kwargs):
    staff_name = _user_label(instance.user)
    label      = f"Penalty — {staff_name}"

    if created:
        log_activity(
            action='PENALTY_ISSUED',
            entity_type='Penalty',
            entity_id=instance.pk,
            entity_name=staff_name,
            description=f'Penalty of ₹{instance.amount} issued to "{staff_name}" for: {instance.act}.',
            metadata={
                'amount': instance.amount,
                'month':  instance.month,
                'act':    instance.act,
                'date':   str(instance.date),
            },
        )
    else:
        log_activity(
            action='PENALTY_UPDATED',
            entity_type='Penalty',
            entity_id=instance.pk,
            entity_name=staff_name,
            description=f'Penalty for "{staff_name}" updated. Amount: ₹{instance.amount}.',
            metadata={
                'old_amount': getattr(instance, '_old_penalty_amount', None),
                'new_amount': instance.amount,
                'month':      instance.month,
            },
        )


@receiver(post_delete, sender=Penalty)
def log_penalty_deleted(sender, instance, **kwargs):
    staff_name = _user_label(instance.user)
    log_activity(
        action='PENALTY_DELETED',
        entity_type='Penalty',
        entity_id=instance.pk,
        entity_name=staff_name,
        description=f'Penalty of ₹{instance.amount} for "{staff_name}" was deleted.',
    )


# ── AttendanceDocument Signals ────────────────────────────────────────────────

@receiver(post_save, sender=AttendanceDocument)
def log_attendance_doc_activity(sender, instance, created, **kwargs):
    if created:
        log_activity(
            action='ATTENDANCE_DOC_UPLOADED',
            entity_type='AttendanceDocument',
            entity_id=instance.pk,
            entity_name=instance.name,
            description=f'Attendance document "{instance.name}" uploaded for {instance.month}.',
            metadata={
                'month': instance.month,
                'date':  str(instance.date),
            },
        )


@receiver(post_delete, sender=AttendanceDocument)
def log_attendance_doc_deleted(sender, instance, **kwargs):
    log_activity(
        action='ATTENDANCE_DOC_DELETED',
        entity_type='AttendanceDocument',
        entity_id=instance.pk,
        entity_name=instance.name,
        description=f'Attendance document "{instance.name}" for {instance.month} was deleted.',
    )


# ── Asset Signals ─────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Asset)
def capture_asset_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Asset.objects.get(pk=instance.pk)
            instance._old_assigned_to = old.assigned_to
            instance._old_company_phone = None  # placeholder if asset impacts staff
        except Asset.DoesNotExist:
            instance._old_assigned_to = None
    else:
        instance._old_assigned_to = None


@receiver(post_save, sender=Asset)
def log_asset_activity(sender, instance, created, **kwargs):
    staff_name = _user_label(instance.assigned_to) if instance.assigned_to else 'None'
    category_name = instance.category.name if instance.category else 'Uncategorized'
    metadata = {
        'asset_type': category_name,
        'staff_id': instance.assigned_to.pk if instance.assigned_to else None,
    }

    if created:
        action = 'ASSET_ASSIGNED' if instance.assigned_to else 'ASSET_CREATED'
        desc = f'Asset "{instance.name}" ({category_name}) created.'
        if instance.assigned_to:
            desc = f'Asset "{instance.name}" ({category_name}) assigned to {staff_name}.'

        log_activity(
            action=action,
            entity_type='Asset',
            entity_id=instance.pk,
            entity_name=instance.name,
            description=desc,
            metadata=metadata
        )
    else:
        old_assigned = getattr(instance, '_old_assigned_to', None)

        if old_assigned != instance.assigned_to:
            if instance.assigned_to:
                log_activity(
                    action='ASSET_ASSIGNED',
                    entity_type='Asset',
                    entity_id=instance.pk,
                    entity_name=instance.name,
                    description=f'Asset "{instance.name}" assigned to {staff_name}.',
                    metadata=metadata
                )
            elif old_assigned:
                log_activity(
                    action='ASSET_UNASSIGNED',
                    entity_type='Asset',
                    entity_id=instance.pk,
                    entity_name=instance.name,
                    description=f'Asset "{instance.name}" unassigned from {_user_label(old_assigned)}.',
                    metadata={'staff_id': old_assigned.pk}
                )
        else:
            log_activity(
                action='ASSET_UPDATED',
                entity_type='Asset',
                entity_id=instance.pk,
                entity_name=instance.name,
                description=f'Asset "{instance.name}" updated.',
                metadata=metadata
            )


@receiver(post_delete, sender=Asset)
def log_asset_deleted(sender, instance, **kwargs):
    category_name = instance.category.name if instance.category else 'Uncategorized'
    log_activity(
        action='ASSET_DELETED',
        entity_type='Asset',
        entity_id=instance.pk,
        entity_name=instance.name,
        description=f'Asset "{instance.name}" ({category_name}) was deleted.',
    )


@receiver(post_save, sender=Asset)
def sync_staff_contact_from_asset(sender, instance, **kwargs):
    """
    If a SIM asset is assigned/unassigned, update the user's office_phone.
    We assume the asset 'name' or 'serial_number' holds the phone number.
    """
    if instance.category and instance.category.name == 'SIM':
        # If assigned, update the staff's office_phone
        if instance.assigned_to:
            user = instance.assigned_to
            # Assuming 'name' holds the phone number for SIM
            user.office_phone = instance.name
            user.save(update_fields=['office_phone'])
        else:
            # If unassigned, we might want to clear it from the OLD user.
            old_assigned = getattr(instance, '_old_assigned_to', None)
            if old_assigned:
                old_assigned.office_phone = None
                old_assigned.save(update_fields=['office_phone'])