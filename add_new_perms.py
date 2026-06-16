import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission

new_perms = [
    {"name": "tasks:read_own", "description": "View My Tasks"},
    {"name": "tasks:read_all", "description": "View All Tasks"},
    {"name": "report_settings:manage", "description": "Manage Report Settings"},
    {"name": "roles:manage", "description": "Manage Roles"},
]

for perm in new_perms:
    obj, created = AppPermission.objects.get_or_create(name=perm['name'], defaults={'description': perm['description']})
    if created:
        print(f"Created permission: {perm['name']}")
    else:
        print(f"Permission already exists: {perm['name']}")

print("Done.")
