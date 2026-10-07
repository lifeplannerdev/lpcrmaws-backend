import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission, Role

def seed():
    perm, created = AppPermission.objects.get_or_create(
        name='reports:approval',
        defaults={'description': 'Approve or reject staff daily reports and agendas'}
    )
    if created:
        print("Created permission: reports:approval")
    else:
        print("Permission reports:approval already exists")
    
    admin_role = Role.objects.filter(name='ADMIN').first()
    if admin_role:
        admin_role.permissions.add(perm)
        print("Added reports:approval to ADMIN role.")

if __name__ == '__main__':
    seed()
