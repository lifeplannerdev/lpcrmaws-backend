import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission

FEE_PERMISSIONS = [
    (
        'fees:accounts',
        'Full authority to access, generate receipts, and manage settings across ALL companies (FLAG, FDS, LP)'
    ),
    (
        'fees:fds',
        'Access, generate receipts, and manage settings for FDS (Filmaatic Dance Studio)'
    ),
    (
        'fees:flag',
        'Access, generate receipts, and manage settings for FLAG (German Language Academy)'
    ),
    (
        'fees:lp',
        'Access, generate receipts, and manage settings for LP (Life Planner Universal)'
    ),
    (
        'fees:manage',
        'Full administrative access to manage student fees, plans, and receipts'
    ),
    (
        'fees:view',
        'View fee accounts, ledgers, and digital receipts'
    ),
    (
        'fees:partial_payment',
        'Record partial fee installments and generate interim receipts'
    ),
    (
        'flag:fees',
        'Access and manage FLAG language academy fee accounts and receipts'
    ),
    (
        'fds_fees:manage',
        'Manage FDS fees, collections, and receipt settings'
    ),
    (
        'fds_fees:view',
        'View FDS student fee accounts and payment ledgers'
    ),
    (
        'processing_students:manage_fees',
        'Manage LP processing student fee payments and receipts'
    ),
]

def main():
    print("Loading multi-company fee permissions to DB via separate script...")
    created_count = 0
    existing_count = 0

    for name, desc in FEE_PERMISSIONS:
        perm_obj, created = AppPermission.objects.get_or_create(
            name=name,
            defaults={'description': desc}
        )
        if created:
            created_count += 1
            print(f"  [+] Created permission: {name}")
        else:
            existing_count += 1
            if perm_obj.description != desc:
                perm_obj.description = desc
                perm_obj.save(update_fields=['description'])
            print(f"  [=] Permission exists: {name}")

    print(f"Finished. {created_count} created, {existing_count} existing. Template-based role seeding was not used.")

if __name__ == '__main__':
    main()
