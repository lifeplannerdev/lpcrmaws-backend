import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from leads.models import Lead, FollowUp
from django.utils import timezone

def unassign_todays_missed_calls():
    today = timezone.now().date()
    
    # Find all follow-ups created today for missed call assignments
    followups = FollowUp.objects.filter(
        created_at__date=today,
        notes__startswith="Missed Call assigned by"
    )
    
    count = 0
    for followup in followups:
        lead = followup.lead
        if lead.assigned_to is not None:
            lead.assigned_to = None
            lead.save()
            count += 1
            print(f"Unassigned lead: {lead.phone}")
            
        followup.delete()
        
    print(f"Successfully unassigned {count} leads that were assigned from missed calls today.")

if __name__ == '__main__':
    unassign_todays_missed_calls()
