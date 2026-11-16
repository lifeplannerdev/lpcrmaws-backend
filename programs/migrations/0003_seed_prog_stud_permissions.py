from django.db import migrations


def seed_prog_stud_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')

    AppPermission.objects.get_or_create(
        name='processing:prog_stud_manage',
        defaults={
            'description': 'Manage Assigned Programs & Assigned Students Database (create, import, edit, assign to documentation/operation staff, delete, view all timelines)'
        },
    )

    AppPermission.objects.get_or_create(
        name='processing:prog_stud_assigned',
        defaults={
            'description': 'View and update only Assigned Programs and Assigned Students rows assigned to oneself (no delete/reassign)'
        },
    )


def rollback_prog_stud_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(
        name__in=[
            'processing:prog_stud_manage',
            'processing:prog_stud_assigned',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0002_assignedprogram_assignedprogramchangelog_and_more'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_prog_stud_permissions, rollback_prog_stud_permissions),
    ]
