from django.db import migrations


def seed_reminder_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    
    AppPermission.objects.get_or_create(
        name='processing:reminders_admin',
        defaults={
            'description': 'Full admin access to all employee reminders, approvals, updates, and checklist management'
        }
    )
    
    AppPermission.objects.get_or_create(
        name='processing:reminders_users',
        defaults={
            'description': 'Employee access to create personal reminders, checklists, mark complete for approval, and post updates'
        }
    )


def rollback_reminder_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(name__in=[
        'processing:reminders_admin',
        'processing:reminders_users'
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('reminders', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_reminder_permissions, rollback_reminder_permissions),
    ]
