import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission

def seed_reminders_permissions():
    print("Seeding reminders permissions...")
    admin_perm, created1 = AppPermission.objects.get_or_create(
        name='processing:reminders_admin',
        defaults={'description': 'Full admin access to all employee reminders, approvals, updates, and checklist management'}
    )
    user_perm, created2 = AppPermission.objects.get_or_create(
        name='processing:reminders_users',
        defaults={'description': 'Employee access to create personal reminders, checklists, mark complete for approval, and post updates'}
    )
    print(f"processing:reminders_admin: {'Created' if created1 else 'Already exists'}")
    print(f"processing:reminders_users: {'Created' if created2 else 'Already exists'}")

if __name__ == '__main__':
    seed_reminders_permissions()
