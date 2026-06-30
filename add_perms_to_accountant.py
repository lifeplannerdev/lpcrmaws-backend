import os
import django
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission, Role

def run():
    # Make sure all fees permissions exist
    fee_perms = [
        {'name': 'fees:manage', 'description': 'Can fully manage fees (create, edit, delete)'},
        {'name': 'fees:read_tenant', 'description': 'Can view all fees in the tenant/company'},
        {'name': 'fees:restructure', 'description': 'Can restructure fees'},
        {'name': 'fees:partial_payment', 'description': 'Can accept partial payments'},
        {'name': 'fees:issue_notice', 'description': 'Can issue fee notices'},
        {'name': 'fees:view_reports', 'description': 'Can view fee reports'},
        {'name': 'fees:read_own', 'description': 'Can read own fees'},
    ]
    
    for p in fee_perms:
        AppPermission.objects.get_or_create(name=p['name'], defaults={'description': p['description']})

    # Add to ACCOUNTANT roles across all tenants
    accountant_roles = Role.objects.filter(name='ACCOUNTANT')
    perms_to_add = AppPermission.objects.filter(name__in=['fees:manage', 'fees:read_tenant', 'fees:restructure', 'fees:partial_payment', 'fees:view_reports'])
    
    count = 0
    for role in accountant_roles:
        role.permissions.add(*perms_to_add)
        count += 1
        
    print(f"Added fees permissions to {count} ACCOUNTANT roles.")

if __name__ == '__main__':
    run()
