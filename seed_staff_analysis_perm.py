import os
import sys
import django

os.chdir('/home/lpcrm/lpcrmaws-backend')
sys.path.insert(0, '/home/lpcrm/lpcrmaws-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission, Role

# Create permission
perm, created = AppPermission.objects.get_or_create(
    name='staff_analysis:admin',
    defaults={'description': 'Full access to the Staff Analysis page — view all employee leads, followups and performance metrics.'}
)
if created:
    print(f'[+] Created permission: staff_analysis:admin')
else:
    print(f'[~] Permission already exists: staff_analysis:admin')

# Assign to ADMIN and CEO roles
for role_name in ['ADMIN', 'CEO']:
    try:
        role = Role.objects.get(name=role_name)
        role.permissions.add(perm)
        print(f'[+] Assigned staff_analysis:admin to role: {role_name}')
    except Role.DoesNotExist:
        print(f'[!] Role not found: {role_name}')

print('Done.')
