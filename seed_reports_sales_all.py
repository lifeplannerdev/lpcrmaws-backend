import os
import sys
import django

# Setup django environment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lpcrm.settings")
django.setup()

from accounts.models import AppPermission

p, created = AppPermission.objects.get_or_create(
    name='reports:sales_all',
    defaults={'description': 'View sales staff reports (ADM_COUNSELLOR, ADM_MANAGER, BMCO, FLAG COORDINATOR)'}
)

if created:
    print("Permission 'reports:sales_all' seeded successfully.")
else:
    print("Permission 'reports:sales_all' already exists.")
