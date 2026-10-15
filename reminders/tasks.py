import logging
from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from .models import Reminder
from utils.pusher import save_notification, trigger_pusher

logger = logging.getLogger(__name__)


@shared_task
def check_due_reminders_and_notify():
    """
    Periodic task to check active reminders that are due today or overdue
    and dispatch notification alerts to ensure staff never miss a date.
    """
    today = timezone.now().date()
    due_reminders = Reminder.objects.filter(
        status__in=['PENDING', 'IN_PROGRESS']
    ).filter(
        Q(deadline__lte=today) | Q(reminder_date__lte=today)
    ).select_related('user', 'student')

    count = 0
    for reminder in due_reminders:
        user = reminder.user
        deadline_str = str(reminder.deadline) if reminder.deadline else str(reminder.reminder_date)
        is_overdue = (reminder.deadline and reminder.deadline < today) or (reminder.reminder_date < today)
        
        urgency_prefix = "OVERDUE" if is_overdue else "DUE TODAY"
        message = f"[{urgency_prefix}] Reminder: \"{reminder.title}\" (Due: {deadline_str})"
        if reminder.student:
            message += f" - Student: {reminder.student.name}"

        save_notification.delay(
            user_id=user.id,
            type='reminder',
            message=message,
            by="System",
            related_id=reminder.id,
            title=f"Reminder {urgency_prefix.title()}"
        )

        trigger_pusher.delay(
            channel=f"private-user-{user.id}",
            event="reminder.alert",
            data={
                "reminder_id": reminder.id,
                "title": reminder.title,
                "priority": reminder.priority,
                "deadline": deadline_str,
                "is_overdue": is_overdue,
                "message": message,
            }
        )
        count += 1

    logger.info(f"[Reminders Task] Checked due reminders. Notified {count} reminders.")
    return count
