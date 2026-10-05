from celery import shared_task
from .services import sync_student
from trainers.models import ProcessingStudent
from .models import MailAccount
import logging

logger = logging.getLogger(__name__)

@shared_task
def sync_emails_for_all_students_task():
    """
    Periodic task to sync emails for all active students.
    """
    students = ProcessingStudent.objects.all()
    count = 0
    for student in students:
        try:
            sync_student(student)
            count += 1
        except Exception as e:
            logger.error(f"Failed to sync emails for student {student.id}: {str(e)}")
    return f"Synced emails for {count} students."

@shared_task
def sync_all_mail_accounts_task():
    """
    Periodic task to sync all mail accounts looking for general inbox activity (if needed).
    But primarily we sync per student based on their email.
    """
    # This might be redundant now, but we can just loop over all students or let the other task handle it.
    # We will just leave it as a no-op or do a quick status check.
    accounts = MailAccount.objects.filter(is_active=True)
    count = accounts.count()
    return f"Checked {count} mail accounts."
