from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import user_logged_in, user_logged_out

from .models import User, MicroWork
from .utils import log_activity


# ── Helpers ─────────────────────────────────────────────────────────────────

def _user_label(user):
    if not user:
        return 'Unknown'
    return user.get_full_name() or user.username


# ── User / Staff Signals ─────────────────────────────────────────────────────

@receiver(pre_save, sender=User)
def capture_user_old_state(sender, instance, **kwargs):
    """Snapshot old state."""
    if instance.pk:
        try:
            orig = User.objects.get(pk=instance.pk)
            instance._old_is_active = orig.is_active
        except User.DoesNotExist:
            instance._old_is_active = None
    else:
        instance._old_is_active = None


@receiver(post_save, sender=User)
def log_user_activity(sender, instance, created, **kwargs):
    name = _user_label(instance)

    if created:
        log_activity(
            action='STAFF_CREATED',
            entity_type='Staff',
            entity_id=instance.pk,
            entity_name=name,
            description=f'New staff member "{name}" was created.',
            metadata={'username': instance.username},
        )
    else:
        old_active = getattr(instance, '_old_is_active', None)

        if old_active is not None and old_active != instance.is_active:
            if instance.is_active:
                log_activity(
                    action='STAFF_ACTIVATED',
                    entity_type='Staff',
                    entity_id=instance.pk,
                    entity_name=name,
                    description=f'Staff member "{name}" account was activated.',
                )
            else:
                log_activity(
                    action='STAFF_DEACTIVATED',
                    entity_type='Staff',
                    entity_id=instance.pk,
                    entity_name=name,
                    description=f'Staff member "{name}" account was deactivated.',
                )
        else:
            log_activity(
                action='STAFF_UPDATED',
                entity_type='Staff',
                entity_id=instance.pk,
                entity_name=name,
                description=f'Staff member "{name}" profile was updated.',
            )


@receiver(post_delete, sender=User)
def log_user_deleted(sender, instance, **kwargs):
    name = _user_label(instance)
    log_activity(
        action='STAFF_DELETED',
        entity_type='Staff',
        entity_id=instance.pk,
        entity_name=name,
        description=f'Staff member "{name}" was deleted.',
    )


# ── Login / Logout Signals ───────────────────────────────────────────────────

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    log_activity(
        action='USER_LOGIN',
        entity_type='Staff',
        entity_id=user.pk,
        entity_name=_user_label(user),
        user=user,
        description=f'"{_user_label(user)}" logged in.',
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        log_activity(
            action='USER_LOGOUT',
            entity_type='Staff',
            entity_id=user.pk,
            entity_name=_user_label(user),
            user=user,
            description=f'"{_user_label(user)}" logged out.',
        )


# ── MicroWork Signals ────────────────────────────────────────────────────────

@receiver(pre_save, sender=MicroWork)
def capture_microwork_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = MicroWork.objects.get(pk=instance.pk).status
        except MicroWork.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=MicroWork)
def log_microwork_activity(sender, instance, created, **kwargs):
    user = instance.user
    label = instance.job_title

    if created:
        log_activity(
            action='MICROWORK_CREATED',
            entity_type='MicroWork',
            entity_id=instance.pk,
            entity_name=label,
            user=user,
            description=f'"{_user_label(user)}" created micro work "{label}".',
            metadata={'time_required': instance.time_required},
        )
    else:
        old_status = getattr(instance, '_old_status', None)
        if old_status and old_status != instance.status and instance.status == 'COMPLETED':
            log_activity(
                action='MICROWORK_COMPLETED',
                entity_type='MicroWork',
                entity_id=instance.pk,
                entity_name=label,
                user=user,
                description=f'"{_user_label(user)}" completed micro work "{label}".',
            )


@receiver(post_delete, sender=MicroWork)
def log_microwork_deleted(sender, instance, **kwargs):
    log_activity(
        action='MICROWORK_DELETED',
        entity_type='MicroWork',
        entity_id=instance.pk,
        entity_name=instance.job_title,
        user=instance.user,
        description=f'Micro work "{instance.job_title}" was deleted.',
    )