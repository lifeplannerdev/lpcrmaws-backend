"""
Independent Script: Add 'admin:dashboard' Permission
File: lpcrmbackend-main/scripts/add_admin_dashboard_perm.py

CRITICAL INTEGRITY INSTRUCTION:
- Implemented completely independently without importing or referencing any template files.
- NEVER imports accounts.permission_templates or ROLE_PERMISSIONS.
- NEVER calls role.permissions.clear() or deletes any existing role permissions.
- Strictly idempotent: safe to execute multiple times in production and development environments.
"""
import os
import sys

# Ensure backend root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# EC2 server backend path fallback
EC2_BACKEND_DIR = '/home/lpcrm/lpcrmaws-backend'
if os.path.exists(EC2_BACKEND_DIR) and EC2_BACKEND_DIR not in sys.path:
    sys.path.insert(0, EC2_BACKEND_DIR)

# Setup Django environment if not already loaded
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
    import django
    django.setup()

from accounts.models import AppPermission, Role

PERMISSION_NAME = "admin:dashboard"
PERMISSION_DESCRIPTION = "Full administrative access to CRM overview dashboard, metrics, analytics, and operational aggregations"
ADMIN_ROLES_TO_ASSIGN = ["ADMIN", "CEO", "managing_director"]

def add_admin_dashboard_permission():
    print("=" * 70)
    print("INDEPENDENT PERMISSION REGISTRATION: admin:dashboard")
    print("=" * 70)

    # 1. Register permission idempotently in AppPermission
    perm_obj, created = AppPermission.objects.get_or_create(
        name=PERMISSION_NAME,
        defaults={"description": PERMISSION_DESCRIPTION}
    )

    if created:
        print(f" [CREATED] Successfully registered permission: {PERMISSION_NAME}")
        print(f"           ID: {perm_obj.id}")
        print(f"           Description: {PERMISSION_DESCRIPTION}")
    else:
        if not perm_obj.description or perm_obj.description != PERMISSION_DESCRIPTION:
            perm_obj.description = PERMISSION_DESCRIPTION
            perm_obj.save(update_fields=['description'])
            print(f" [UPDATED] Permission already exists (ID: {perm_obj.id}); updated description.")
        else:
            print(f" [EXISTS]  Permission already exists in database (ID: {perm_obj.id}).")

    # 2. Assign to administrative roles non-destructively
    assigned_count = 0
    already_assigned_count = 0
    skipped_count = 0

    print("-" * 70)
    print("Assigning permission to administrative roles...")
    for role_name in ADMIN_ROLES_TO_ASSIGN:
        role = Role.objects.filter(name=role_name).first()
        if role:
            if not role.permissions.filter(id=perm_obj.id).exists():
                role.permissions.add(perm_obj)
                assigned_count += 1
                print(f" [+] Assigned '{PERMISSION_NAME}' to role '{role_name}' (Role ID: {role.id})")
            else:
                already_assigned_count += 1
                print(f" [=] Role '{role_name}' already possesses '{PERMISSION_NAME}'")
        else:
            skipped_count += 1
            print(f" [!] Role '{role_name}' does not exist in this database (skipped)")

    print("-" * 70)
    print(f"SUMMARY:")
    print(f"  Permission: {PERMISSION_NAME} (ID: {perm_obj.id})")
    print(f"  Newly assigned roles: {assigned_count}")
    print(f"  Already had permission: {already_assigned_count}")
    print(f"  Roles skipped (not found): {skipped_count}")
    print(f"  Existing role permissions untouched: True")
    print(f"  Template usage: NONE (Independent execution)")
    print("=" * 70)
    return perm_obj

if __name__ == '__main__':
    add_admin_dashboard_permission()
