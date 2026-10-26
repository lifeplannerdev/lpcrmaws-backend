from django.core.management.base import BaseCommand
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


class Command(BaseCommand):
    help = 'Loads granular company-scoped fee permissions into the AppPermission database table without template-based role seeding.'

    def handle(self, *args, **options):
        self.stdout.write("Loading multi-company fee permissions to DB...")
        created_count = 0
        existing_count = 0

        for name, desc in FEE_PERMISSIONS:
            perm_obj, created = AppPermission.objects.get_or_create(
                name=name,
                defaults={'description': desc}
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [+] Created permission: {name}"))
            else:
                existing_count += 1
                if perm_obj.description != desc:
                    perm_obj.description = desc
                    perm_obj.save(update_fields=['description'])
                self.stdout.write(f"  [=] Permission exists: {name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully loaded fee permissions ({created_count} created, {existing_count} existing). "
                f"No role templates modified."
            )
        )
