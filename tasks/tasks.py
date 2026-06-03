from celery import shared_task
from django.utils import timezone
from .models import Task
import logging

logger = logging.getLogger(__name__)

@shared_task
def update_overdue_tasks():
    """
    Checks all pending and in_progress tasks and marks them as overdue
    if their deadline has passed.
    """
    now = timezone.now()
    # Assuming Task model has 'status' and 'deadline' fields
    overdue_tasks = Task.objects.filter(
        status__in=['pending', 'in_progress'],
        deadline__lt=now
    )
    
    count = overdue_tasks.count()
    if count > 0:
        overdue_tasks.update(status='overdue')
        logger.info(f"Marked {count} tasks as overdue.")
    return count
