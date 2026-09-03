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
    name='reports:kochi',
    defaults={'description': 'View staff reports for staff with location assigned KOCHI'}
)

if created:
    print("Permission 'reports:kochi' seeded successfully.")
else:
    print("Permission 'reports:kochi' already exists.")
