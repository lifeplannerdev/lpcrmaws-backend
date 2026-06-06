# academy/signals.py
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import Trainer, Student, Attendance
from accounts.utils import log_activity

User = get_user_model()

from django.db.models.signals import m2m_changed
from accounts.models import Role

@receiver(m2m_changed, sender=User.db_roles.through)
def create_trainer_profile(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "post_add":
        if not reverse:
            trainer_role = Role.objects.filter(name="TRAINER").first()
            if trainer_role and trainer_role.pk in pk_set:
                Trainer.objects.get_or_create(user=instance)
        else:
            if instance.name == "TRAINER":
                for user_id in pk_set:
                    Trainer.objects.get_or_create(user_id=user_id)



def _user_label(user):
    if not user:
        return 'Unknown'
    return user.get_full_name() or user.username


# ── Trainer Signals ───────────────────────────────────────────────────────────

@receiver(pre_save, sender=Trainer)
def capture_trainer_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_trainer_status = Trainer.objects.get(pk=instance.pk).status
        except Trainer.DoesNotExist:
            instance._old_trainer_status = None
    else:
        instance._old_trainer_status = None


@receiver(post_save, sender=Trainer)
def log_trainer_activity(sender, instance, created, **kwargs):
    name = _user_label(instance.user)

    if created:
        log_activity(
            action='TRAINER_CREATED',
            entity_type='Trainer',
            entity_id=instance.pk,
            entity_name=name,
            description=f'Trainer profile created for "{name}".',
            metadata={'status': instance.status},
        )
    else:
        old_status = getattr(instance, '_old_trainer_status', None)
        if old_status and old_status != instance.status:
            log_activity(
                action='TRAINER_STATUS_CHANGED',
                entity_type='Trainer',
                entity_id=instance.pk,
                entity_name=name,
                description=f'Trainer "{name}" status changed from {old_status} → {instance.status}.',
                metadata={'old_status': old_status, 'new_status': instance.status},
            )
        else:
            log_activity(
                action='TRAINER_UPDATED',
                entity_type='Trainer',
                entity_id=instance.pk,
                entity_name=name,
                description=f'Trainer profile updated for "{name}".',
            )


@receiver(post_delete, sender=Trainer)
def log_trainer_deleted(sender, instance, **kwargs):
    name = _user_label(instance.user)
    log_activity(
        action='TRAINER_DELETED',
        entity_type='Trainer',
        entity_id=instance.pk,
        entity_name=name,
        description=f'Trainer profile deleted for "{name}".',
    )


# ── Student Signals ───────────────────────────────────────────────────────────

@receiver(pre_save, sender=Student)
def capture_student_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Student.objects.get(pk=instance.pk)
            instance._old_student_status  = old.status
            instance._old_student_trainer = old.trainer_id
            instance._old_student_batch   = old.batch
        except Student.DoesNotExist:
            instance._old_student_status  = None
            instance._old_student_trainer = None
            instance._old_student_batch   = None
    else:
        instance._old_student_status  = None
        instance._old_student_trainer = None
        instance._old_student_batch   = None


@receiver(post_save, sender=Student)
def log_student_activity(sender, instance, created, **kwargs):
    label        = instance.name
    trainer_name = _user_label(instance.trainer.user) if instance.trainer else 'Unknown'

    if created:
        log_activity(
            action='STUDENT_ENROLLED',
            entity_type='Student',
            entity_id=instance.pk,
            entity_name=label,
            description=f'New student "{label}" enrolled in batch {instance.get_batch_display()} under trainer "{trainer_name}".',
            metadata={
                'batch':          instance.batch,
                'trainer':        trainer_name,
                'admission_date': str(instance.admission_date),
                'status':         instance.status,
            },
        )
        return

    # Status changed
    if getattr(instance, '_old_student_status', None) != instance.status:
        action_map = {
            'COMPLETED': 'STUDENT_COMPLETED',
            'DROPPED':   'STUDENT_DROPPED',
            'PAUSED':    'STUDENT_PAUSED',
            'ACTIVE':    'STUDENT_REACTIVATED',
        }
        action = action_map.get(instance.status, 'STUDENT_UPDATED')
        log_activity(
            action=action,
            entity_type='Student',
            entity_id=instance.pk,
            entity_name=label,
            description=f'Student "{label}" status changed from {instance._old_student_status} → {instance.status}.',
            metadata={
                'old_status': instance._old_student_status,
                'new_status': instance.status,
            },
        )

    # Trainer changed
    if getattr(instance, '_old_student_trainer', None) != instance.trainer_id:
        log_activity(
            action='STUDENT_TRAINER_CHANGED',
            entity_type='Student',
            entity_id=instance.pk,
            entity_name=label,
            description=f'Student "{label}" was reassigned to trainer "{trainer_name}".',
            metadata={'new_trainer': trainer_name},
        )

    # Batch changed
    if getattr(instance, '_old_student_batch', None) != instance.batch:
        log_activity(
            action='STUDENT_BATCH_CHANGED',
            entity_type='Student',
            entity_id=instance.pk,
            entity_name=label,
            description=f'Student "{label}" batch changed from {instance._old_student_batch} → {instance.batch}.',
            metadata={
                'old_batch': instance._old_student_batch,
                'new_batch': instance.batch,
            },
        )


@receiver(post_delete, sender=Student)
def log_student_deleted(sender, instance, **kwargs):
    log_activity(
        action='STUDENT_DELETED',
        entity_type='Student',
        entity_id=instance.pk,
        entity_name=instance.name,
        description=f'Student "{instance.name}" was removed from the system.',
    )


# ── Attendance Signals ────────────────────────────────────────────────────────

@receiver(post_save, sender=Attendance)
def log_attendance_activity(sender, instance, created, **kwargs):
    student_name = instance.student.name
    trainer_name = _user_label(instance.trainer.user) if instance.trainer else 'Unknown'

    if created:
        log_activity(
            action='ATTENDANCE_MARKED',
            entity_type='Attendance',
            entity_id=instance.pk,
            entity_name=student_name,
            user=instance.trainer.user if instance.trainer else None,
            description=f'Attendance marked for "{student_name}" on {instance.date} — {instance.status}.',
            metadata={
                'date':    str(instance.date),
                'status':  instance.status,
                'trainer': trainer_name,
            },
        )
    else:
        log_activity(
            action='ATTENDANCE_UPDATED',
            entity_type='Attendance',
            entity_id=instance.pk,
            entity_name=student_name,
            user=instance.trainer.user if instance.trainer else None,
            description=f'Attendance updated for "{student_name}" on {instance.date} — {instance.status}.',
            metadata={
                'date':   str(instance.date),
                'status': instance.status,
            },
        )