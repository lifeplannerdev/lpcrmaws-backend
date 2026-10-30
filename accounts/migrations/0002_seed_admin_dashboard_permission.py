# Generated manually for independent admin:dashboard permission seeding
from django.db import migrations

def seed_admin_dashboard_permission(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    Role = apps.get_model('accounts', 'Role')

    perm_obj, _ = AppPermission.objects.get_or_create(
        name='admin:dashboard',
        defaults={
            'description': 'Full administrative access to CRM overview dashboard, metrics, analytics, and operational aggregations'
        }
    )

    admin_roles = ['ADMIN', 'CEO', 'managing_director']
    for role_name in admin_roles:
        role = Role.objects.filter(name=role_name).first()
        if role and not role.permissions.filter(id=perm_obj.id).exists():
            role.permissions.add(perm_obj)

def rollback_admin_dashboard_permission(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(name='admin:dashboard').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_admin_dashboard_permission, rollback_admin_dashboard_permission),
    ]
