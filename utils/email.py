from django.core.mail import send_mail
from celery import shared_task
from django.conf import settings

@shared_task
def send_background_email(subject, message, recipient_list, html_message=None):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        print(f"[Email] Failed to send email to {recipient_list}: {e}")
