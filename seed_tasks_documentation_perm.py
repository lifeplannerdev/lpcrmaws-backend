"""
Individual script to seed the 'tasks:documentation' permission into the system.

Permission:
- tasks:documentation: "Assign, approve and view all tasks for staff with DOCUMENTATION role (cannot approve own task)"

This script:
1. Directly registers the permission in the `permissions` table (`AppPermission` model).
2. Seeds it to the SYSTEM, NOT to any user or role automatically.
3. Once seeded, it immediately appears in the Role Management Page under the 'TASKS' section,
   where administrators can tick it off to any role.

Usage:
    python seed_tasks_documentation_perm.py
or:
    python manage.py shell < seed_tasks_documentation_perm.py
"""

import os
import sys

# Ensure backend directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Also support execution from /home/lpcrm on EC2
ec2_backend_dir = '/home/lpcrm/lpcrmaws-backend'
if os.path.exists(ec2_backend_dir) and ec2_backend_dir not in sys.path:
    sys.path.insert(0, ec2_backend_dir)

if __name__ == '__main__' or not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
    import django
    django.setup()

from accounts.models import AppPermission

PERMISSION_NAME = "tasks:documentation"
PERMISSION_DESC = "Assign, approve and view all tasks for staff with DOCUMENTATION role (cannot approve own task)"

def seed_permission():
    print("=" * 60)
    print("Seeding 'tasks:documentation' permission into database...")
    print("=" * 60)

    perm_obj, created = AppPermission.objects.get_or_create(
        name=PERMISSION_NAME,
        defaults={"description": PERMISSION_DESC}
    )

    if created:
        print(f" [CREATED] Successfully created permission: {PERMISSION_NAME}")
        print(f"           Description: {PERMISSION_DESC}")
    else:
        if not perm_obj.description:
            perm_obj.description = PERMISSION_DESC
            perm_obj.save(update_fields=['description'])
            print(f" [UPDATED] Permission already existed, updated description: {PERMISSION_NAME}")
        else:
            print(f" [EXISTS]  Permission already exists: {PERMISSION_NAME}")
            print(f"           Description: {perm_obj.description}")

    print("-" * 60)
    print("Permission is registered in the system (not assigned to any user).")
    print("It will now appear in the Role Management page under 'TASKS'.")
    print("=" * 60)

if __name__ == '__main__':
    seed_permission()
