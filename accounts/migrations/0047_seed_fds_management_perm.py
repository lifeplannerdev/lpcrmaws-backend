from django.db import migrations


def seed_fds_management_permission(apps, schema_editor):
    """
    Registers the fds:management permission in the system so it appears
    in the Role Management page for manual assignment.
    No roles are auto-assigned — administrators tick it manually.
    """
    AppPermission = apps.get_model('accounts', 'AppPermission')

    AppPermission.objects.get_or_create(
        name='fds:management',
        defaults={
            'description': (
                'Read-only management view of FDS — full cross-branch visibility '
                'across Kochi and Kottayam with analytics dashboard. '
                'Assign manually to management roles via Role Management page.'
            )
        }
    )


def remove_fds_management_permission(apps, schema_editor):
    apps.get_model('accounts', 'AppPermission').objects.filter(
        name='fds:management'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0046_seed_fds_roles'),
    ]

    operations = [
        migrations.RunPython(
            seed_fds_management_permission,
            remove_fds_management_permission,
        ),
    ]
