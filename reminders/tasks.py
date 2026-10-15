import logging
from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from .models import Reminder, ReminderNotificationSetting
from utils.pusher import save_notification, trigger_pusher

logger = logging.getLogger(__name__)


@shared_task
def check_due_reminders_and_notify():
    """
    Periodic task to check active reminders that are due according to their
    per-reminder notification settings (custom start dates and intervals)
    and dispatch notification alerts across configured channels.
    """
    now = timezone.now()
    today = now.date()

    # Query active reminders
    active_reminders = Reminder.objects.filter(
        status__in=['PENDING', 'IN_PROGRESS']
    ).select_related('user', 'student', 'notification_setting')

    count = 0
    for reminder in active_reminders:
        user = reminder.user
        setting, _ = ReminderNotificationSetting.objects.get_or_create(
            reminder=reminder,
            defaults={
                'is_enabled': True,
                'interval_minutes': 30,
                'notify_start_date': reminder.reminder_date,
            }
        )

        should_notify, reason = setting.should_notify(now=now)
        if not should_notify:
            logger.debug(f"[Reminder Task] Skipping #{reminder.id} '{reminder.title}': {reason}")
            continue

        deadline_str = str(reminder.deadline) if reminder.deadline else str(reminder.reminder_date)
        is_overdue = (reminder.deadline and reminder.deadline < today) or (reminder.reminder_date < today)
        urgency_prefix = "OVERDUE" if is_overdue else "DUE TODAY" if (reminder.deadline == today or reminder.reminder_date == today) else "UPCOMING"
        
        message = f"[{urgency_prefix}] Reminder: \"{reminder.title}\" (Due: {deadline_str})"
        if reminder.student:
            message += f" - Student: {reminder.student.name}"
        if setting.notes:
            message += f" | {setting.notes}"

        # Save DB notification if in-app enabled
        if setting.enable_in_app:
            save_notification.delay(
                user_id=user.id,
                type='reminder',
                message=message,
                by="System",
                related_id=reminder.id,
                title=f"Reminder {urgency_prefix.title()}"
            )

        # Trigger Pusher real-time alert (handles popup, desktop, audio)
        trigger_pusher.delay(
            channel=f"private-user-{user.id}",
            event="reminder.alert",
            data={
                "reminder_id": reminder.id,
                "title": reminder.title,
                "priority": reminder.priority,
                "deadline": deadline_str,
                "is_overdue": is_overdue,
                "enable_sound": setting.enable_sound,
                "enable_desktop": setting.enable_desktop,
                "enable_in_app": setting.enable_in_app,
                "interval_minutes": setting.interval_minutes,
                "message": message,
            }
        )

        # Update last_notified_at to enforce interval timing
        setting.last_notified_at = now
        setting.save(update_fields=['last_notified_at', 'updated_at'])
        count += 1

    logger.info(f"[Reminders Task] Checked reminders against notification settings. Dispatched {count} alerts.")
    return count
