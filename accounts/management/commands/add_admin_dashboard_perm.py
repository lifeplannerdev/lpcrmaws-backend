"""
Django Management Command: add_admin_dashboard_perm
Usage: python manage.py add_admin_dashboard_perm

Registers 'admin:dashboard' permission independently in AppPermission and assigns
it to ADMIN, CEO, and managing_director roles without touching any template or wiping existing permissions.
"""
from django.core.management.base import BaseCommand
from accounts.models import AppPermission, Role

PERMISSION_NAME = "admin:dashboard"
PERMISSION_DESCRIPTION = "Full administrative access to CRM overview dashboard, metrics, analytics, and operational aggregations"
ADMIN_ROLES_TO_ASSIGN = ["ADMIN", "CEO", "managing_director"]

class Command(BaseCommand):
    help = "Independently registers admin:dashboard permission and assigns to administrative roles without using templates."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=" * 65))
        self.stdout.write(self.style.NOTICE("Registering 'admin:dashboard' independently..."))
        self.stdout.write(self.style.NOTICE("=" * 65))

        # 1. Register permission
        perm_obj, created = AppPermission.objects.get_or_create(
            name=PERMISSION_NAME,
            defaults={"description": PERMISSION_DESCRIPTION}
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f" [CREATED] Permission '{PERMISSION_NAME}' (ID: {perm_obj.id})"))
        else:
            if not perm_obj.description or perm_obj.description != PERMISSION_DESCRIPTION:
                perm_obj.description = PERMISSION_DESCRIPTION
                perm_obj.save(update_fields=['description'])
                self.stdout.write(self.style.SUCCESS(f" [UPDATED] Permission '{PERMISSION_NAME}' description updated."))
            else:
                self.stdout.write(self.style.WARNING(f" [EXISTS]  Permission '{PERMISSION_NAME}' already exists (ID: {perm_obj.id})."))

        # 2. Assign to administrative roles
        assigned_count = 0
        for role_name in ADMIN_ROLES_TO_ASSIGN:
            role = Role.objects.filter(name=role_name).first()
            if role:
                if not role.permissions.filter(id=perm_obj.id).exists():
                    role.permissions.add(perm_obj)
                    assigned_count += 1
                    self.stdout.write(self.style.SUCCESS(f" [+] Assigned to role '{role_name}'"))
                else:
                    self.stdout.write(self.style.WARNING(f" [=] Role '{role_name}' already possesses '{PERMISSION_NAME}'"))
            else:
                self.stdout.write(self.style.WARNING(f" [!] Role '{role_name}' not found in database (skipped)"))

        self.stdout.write(self.style.NOTICE("-" * 65))
        self.stdout.write(self.style.SUCCESS(f"Successfully processed '{PERMISSION_NAME}'. Assigned to {assigned_count} roles."))
        self.stdout.write(self.style.NOTICE("Template usage: NONE. Existing permissions preserved."))
        self.stdout.write(self.style.NOTICE("=" * 65))
