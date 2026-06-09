from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import Role, AppPermission
from accounts.permission_templates import ROLE_PERMISSIONS
from accounts.services import PermissionService

User = get_user_model()



class Command(BaseCommand):
    help = 'Seeds the database with dynamic roles and permissions'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting DB role/permission seeding...")

        # 1. Strip superuser and ADMIN bypasses from everyone
        self.stdout.write("Revoking admin bypasses from existing users...")
        User.objects.filter(is_superuser=True).update(is_superuser=False)
        
        # 2. Create the exact one superuser 'admin' / 'admin'
        admin_user, created = User.objects.get_or_create(username='admin')
        if created:
            admin_user.set_password('admin')
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.role = 'ADMIN'
        admin_user.save()
        if created:
            self.stdout.write(self.style.SUCCESS("Created admin user (admin/admin)"))
        else:
            self.stdout.write(self.style.SUCCESS("Updated admin user to be superuser"))

        # 3. Create or Update Roles and their explicit permissions
        for role_name, backend_perms in ROLE_PERMISSIONS.items():
            role_obj, _ = Role.objects.get_or_create(name=role_name)
            
            # ROLE_PERMISSIONS already contains full resource:action strings
            
            all_perms = set(backend_perms)
            
            # Ensure basic permissions are present
            all_perms.update(["profile:read", "profile:edit_own", "dashboard:read"])
            
            role_obj.permissions.clear()
            for perm_name in all_perms:
                if perm_name == "*":
                    continue # handled by superuser flag
                perm_obj, _ = AppPermission.objects.get_or_create(name=perm_name)
                role_obj.permissions.add(perm_obj)
                
            self.stdout.write(f"Seeded role {role_name} with {len(all_perms)} permissions")



        self.stdout.write(self.style.SUCCESS('Successfully seeded roles and permissions'))
