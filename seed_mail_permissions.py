import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission

def seed_mail_permissions():
    print("Seeding mail permissions (database only)...")
    
    mail_use, created = AppPermission.objects.get_or_create(
        name='mail:use',
        defaults={'description': 'Can send and view emails in the Mail Control Center'}
    )
    if created:
        print("Created permission: mail:use")
    else:
        print("Permission already exists: mail:use")
        
    mail_manage, created = AppPermission.objects.get_or_create(
        name='mail:manage',
        defaults={'description': 'Can connect Gmail accounts and manage shared templates/signatures'}
    )
    if created:
        print("Created permission: mail:manage")
    else:
        print("Permission already exists: mail:manage")
        
    print("Mail permissions seeded successfully. Please assign them in the Role Management UI.")

if __name__ == '__main__':
    seed_mail_permissions()
