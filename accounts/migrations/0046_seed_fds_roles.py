from django.db import migrations

def seed_fds_roles(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    AppPermission = apps.get_model('accounts', 'AppPermission')

    # Ensure required permissions exist
    permissions_map = {
        'fds:admin': 'Full administrative access to FDS module',
        'fds:admin_own': 'Access and manage own FDS records',
        'fds:view': 'View-only access to FDS records',
        'fds_fees:view': 'Access to FDS fees and payments',
        'dashboard:read': 'Access dashboard metrics',
        'tasks:read_own': 'Read own assigned tasks',
        'reports:read_own': 'Read and submit own reports',
    }
    
    perm_objs = {}
    for code, desc in permissions_map.items():
        obj, _ = AppPermission.objects.get_or_create(name=code, defaults={'description': desc})
        perm_objs[code] = obj

    roles_to_seed = {
        'FDS_COORDINATOR': {
            'description': 'FILMAATIC Dance Studio Coordinator',
            'perms': ['dashboard:read', 'tasks:read_own', 'reports:read_own', 'fds:admin', 'fds:view', 'fds_fees:view']
        },
        'FDS COORDINATOR': {
            'description': 'FILMAATIC Dance Studio Coordinator',
            'perms': ['dashboard:read', 'tasks:read_own', 'reports:read_own', 'fds:admin', 'fds:view', 'fds_fees:view']
        },
        'FDS_TRAINER': {
            'description': 'FILMAATIC Dance Studio Trainer',
            'perms': ['dashboard:read', 'tasks:read_own', 'reports:read_own', 'fds:view', 'fds:admin_own']
        },
        'FDS TRAINER': {
            'description': 'FILMAATIC Dance Studio Trainer',
            'perms': ['dashboard:read', 'tasks:read_own', 'reports:read_own', 'fds:view', 'fds:admin_own']
        },
    }

    for role_name, data in roles_to_seed.items():
        role, _ = Role.objects.get_or_create(
            name=role_name,
            defaults={'description': data['description']}
        )
        for p_code in data['perms']:
            if p_code in perm_objs:
                role.permissions.add(perm_objs[p_code])

def remove_fds_roles(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.filter(name__in=['FDS_COORDINATOR', 'FDS COORDINATOR', 'FDS_TRAINER', 'FDS TRAINER']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0045_seed_reports_sales_all_perm'),
    ]

    operations = [
        migrations.RunPython(seed_fds_roles, remove_fds_roles),
    ]
