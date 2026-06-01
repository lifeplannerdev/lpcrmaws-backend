import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from leads.models import FollowUp, LeadAssignment
from notifications.models import Notification
from utils.pusher import trigger_pusher

class Command(BaseCommand):
    help = 'Escalates overdue follow-ups (24h notification, 72h reassignment)'

    def handle(self, *args, **options):
        now = timezone.now()
        
        overdue_followups = FollowUp.objects.filter(status='pending', follow_up_date__lte=now.date())
        
        for fu in overdue_followups:
            # Combine date and time to create aware datetime
            fu_time = fu.follow_up_time or datetime.time.min
            combined_dt = timezone.make_aware(datetime.datetime.combine(fu.follow_up_date, fu_time))
            time_diff = now - combined_dt

            # Ensure we only process if it's actually past the time
            if time_diff.total_seconds() > 0:
                if time_diff.days >= 3:
                    # 72h reassignment logic
                    lead = fu.lead
                    if lead and lead.assigned_by and lead.assigned_to != lead.assigned_by:
                        lead.assigned_to = lead.assigned_by
                        lead.save()
                        
                        LeadAssignment.objects.create(
                            lead=lead,
                            assigned_to=lead.assigned_by,
                            assigned_by=None,
                            assignment_type='REASSIGNMENT',
                            notes='Automatically reassigned due to 72h overdue follow-up'
                        )
                        self.stdout.write(self.style.SUCCESS(f'Reassigned lead {lead.id} to {lead.assigned_by}'))

                elif time_diff.days >= 1:
                    # 24h notification logic
                    msg = f"Follow-up for {fu.contact_display} is overdue by 24 hours!"
                    notif, created = Notification.objects.get_or_create(
                        user=fu.assigned_to,
                        type='lead',
                        message=msg,
                        by='System'
                    )
                    if created:
                        trigger_pusher(f'private-user-{fu.assigned_to.id}', 'new-notification', {
                            'id': notif.id,
                            'message': msg,
                            'type': 'lead'
                        })
                        self.stdout.write(self.style.SUCCESS(f'Notified {fu.assigned_to} for follow-up {fu.id}'))
