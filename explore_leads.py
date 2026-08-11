import os
import django
from datetime import datetime
import pytz

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lpcrm.settings")
django.setup()

from leads.models import Lead, RemarkHistory
from accounts.models import User

# Let's assume current year and month for 8th to 10th
start_date = datetime(2026, 8, 8, tzinfo=pytz.UTC)
end_date = datetime(2026, 8, 11, tzinfo=pytz.UTC)

print("--- Querying leads created or assigned between 8th and 10th ---")
leads_by_assigned_date = Lead.objects.filter(assigned_date__gte=start_date, assigned_date__lt=end_date)
print(f"Count by assigned_date: {leads_by_assigned_date.count()}")

leads_by_created_at = Lead.objects.filter(created_at__gte=start_date, created_at__lt=end_date)
print(f"Count by created_at: {leads_by_created_at.count()}")

# Inspect remarks for a few leads to understand the structure
print("\n--- Inspecting a few leads to understand remarks structure ---")
for l in leads_by_assigned_date[:5]:
    print(f"Lead {l.id}: {l.name}")
    print(f"  Assigned by: {l.assigned_by}, Assigned to: {l.assigned_to}")
    print(f"  Remarks: {l.remarks}")
    history = RemarkHistory.objects.filter(lead=l).order_by('changed_at')
    for h in history:
        print(f"  - History at {h.changed_at} by {h.changed_by}: {h.new_remarks}")

