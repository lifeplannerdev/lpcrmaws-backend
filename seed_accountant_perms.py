import os
import django
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission, Role

permissions = [
    {'name': 'processing_students:manage_fees', 'description': 'Can manage fees for processing students'},
    {'name': 'processing_students:read_any', 'description': 'Can view all processing students'},
    {'name': 'students:manage_attendance_policy', 'description': 'Can manage student attendance policies'},
    {'name': 'students:read_any', 'description': 'Can view all students'},
    {'name': 'fees:read_own', 'description': 'Can view fees for own assigned students'},
    {'name': 'fees:manage', 'description': 'Can fully manage fees (create, edit, delete)'},
    {'name': 'fees:read_tenant', 'description': 'Can view all fees in the tenant/company'},
    {'name': 'fees:restructure', 'description': 'Can restructure fees'},
    {'name': 'penalties:read_tenant', 'description': 'Can view all penalties in the tenant/company'},
    {'name': 'tasks:read_own', 'description': 'Can read own tasks'},
    {'name': 'tasks:edit_own', 'description': 'Can edit own tasks'},
    {'name': 'assets:read_tenant', 'description': 'Can view all assets'},
    {'name': 'reports:read_own', 'description': 'Can read own reports'},
    {'name': 'reports:create', 'description': 'Can create reports'},
    {'name': 'credentials:read_tenant', 'description': 'Can view all credentials'},
]

for p in permissions:
    obj, created = AppPermission.objects.get_or_create(name=p['name'], defaults={'description': p['description']})
    print(f"{'Added' if created else 'Verified'} {p['name']}")

