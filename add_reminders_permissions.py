"""
Script to create the Reminders permissions directly in the database.

Permissions added:
- processing:reminders_admin
- processing:reminders_users

This script:
1. Adds these records directly into the `permissions` table (`AppPermission` model).
2. Does NOT assign them to any users or roles automatically.
3. Once created, they appear in the Role Management page so an admin can assign them to any role.

Usage:
    python add_reminders_permissions.py
or:
    python manage.py shell < add_reminders_permissions.py
"""

import os
import sys

# Setup Django environment if run as a standalone script
if __name__ == '__main__' or not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
    import django
    django.setup()

from accounts.models import AppPermission

PERMISSIONS_TO_ADD = [
    {
        "name": "processing:reminders_admin",
        "description": "Full admin access to all employee reminders, approvals, updates, and checklist management"
    },
    {
        "name": "processing:reminders_users",
        "description": "Employee access to create personal reminders, checklists, mark complete for approval, and post updates"
    },
]

def add_permissions():
    print("=" * 60)
    print("Adding Reminders permissions to the database...")
    print("=" * 60)
    
    created_count = 0
    existing_count = 0

    for perm_data in PERMISSIONS_TO_ADD:
        perm_name = perm_data["name"]
        perm_desc = perm_data["description"]
        
        perm_obj, created = AppPermission.objects.get_or_create(
            name=perm_name,
            defaults={"description": perm_desc}
        )
        
        if created:
            created_count += 1
            print(f" [CREATED]  {perm_name}")
            print(f"            Description: {perm_desc}")
        else:
            existing_count += 1
            if not perm_obj.description:
                perm_obj.description = perm_desc
                perm_obj.save(update_fields=['description'])
            print(f" [EXISTS]   {perm_name}")

    print("-" * 60)
    print(f"Summary: {created_count} created, {existing_count} already existed.")
    print("Permissions are now available in the database and visible in Role Management.")
    print("No users or roles were modified.")
    print("=" * 60)

if __name__ == '__main__':
    add_permissions()
