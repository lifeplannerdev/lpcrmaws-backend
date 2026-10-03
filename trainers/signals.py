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

from .models import ProcessingStudent
from accounts.gmail_service import create_gmail_draft
import threading

def run_in_thread(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
    return wrapper

@run_in_thread
def handle_processing_student_gmail(instance, status_updates):
    # Try to find assigned user to draft the email for
    user = instance.assigned_to
    if not user:
        return # No assigned user to draft email for
        
    student_email = instance.email
    if not student_email:
        return # Student has no email
        
    subject = f"Your Application Processing Updates - {instance.name}"
    
    body = f"Hello {instance.name},\n\nWe have some updates regarding your application to {instance.university or 'our partner universities'}.\n\n"
    for field, vals in status_updates.items():
        body += f"- {field.replace('_', ' ').title()} changed from {vals['old']} to {vals['new']}\n"
        
    body += "\n\nBest regards,\n"
    body += user.get_full_name() or user.username
    
    try:
        new_thread_id = create_gmail_draft(user, student_email, subject, body, thread_id=instance.gmail_thread_id)
        if new_thread_id and new_thread_id != instance.gmail_thread_id:
            # Note: updating model inside a thread can cause race conditions if not careful,
            # but since it's just updating the thread_id, we can use update()
            ProcessingStudent.objects.filter(pk=instance.pk).update(gmail_thread_id=new_thread_id)
    except Exception as e:
        print(f"Error creating Gmail draft: {e}")

@receiver(pre_save, sender=ProcessingStudent)
def capture_processing_student_old_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = ProcessingStudent.objects.get(pk=instance.pk)
            instance._old_state = {
                'enrollment_process_status': old.enrollment_process_status,
                'application_documents_status': old.application_documents_status,
                'application_status': old.application_status,
                'visa_results': old.visa_results,
            }
        except ProcessingStudent.DoesNotExist:
            instance._old_state = None
    else:
        instance._old_state = None


@receiver(post_save, sender=ProcessingStudent)
def process_student_status_changes_for_gmail(sender, instance, created, **kwargs):
    if created:
        status_updates = {'account_creation': {'old': 'None', 'new': 'Created'}}
        handle_processing_student_gmail(instance, status_updates)
        return
        
    if getattr(instance, '_old_state', None):
        status_updates = {}
        for field, old_val in instance._old_state.items():
            new_val = getattr(instance, field)
            if old_val != new_val:
                status_updates[field] = {'old': old_val, 'new': new_val}
                
        if status_updates:
            handle_processing_student_gmail(instance, status_updates)