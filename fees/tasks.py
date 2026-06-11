from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from notifications.models import Notification
from accounts.models import User
from accounts.permissions import has_dynamic_permission
from fees.models import FeeInstallment

@shared_task
def send_daily_fee_reminders():
    # Remind 3 days before due date
    target_date = timezone.localdate() + timedelta(days=3)
    
    installments = FeeInstallment.objects.filter(
        status__in=['PENDING', 'PARTIAL'],
        due_date=target_date
    ).select_related('account__student', 'account')

    count = 0
    for installment in installments:
        student = installment.account.student
        amount = installment.balance_amount
        company = installment.account.company
        
        message = f"Reminder: Fee installment of {amount} for {student.name} is due on {installment.due_date}."
        
        recipients = [
            user for user in User.objects.filter(is_active=True, company=company)
            if has_dynamic_permission(user, 'fees:manage')
        ]
        
        seen = set()
        for user in recipients:
            if user.id in seen: continue
            seen.add(user.id)
            Notification.objects.create(
                user=user,
                type='fee',
                message=message,
                by='System'
            )
        count += 1
            
    return f"Sent reminders for {count} upcoming installments."
