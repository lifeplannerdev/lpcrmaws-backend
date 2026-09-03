from django.db import migrations

def seed_reports_kochi_perm(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.get_or_create(
        name='reports:kochi',
        defaults={'description': 'View staff reports for staff with location assigned KOCHI'}
    )

def remove_reports_kochi_perm(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(name='reports:kochi').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0043_alter_user_company'),
    ]

    operations = [
        migrations.RunPython(seed_reports_kochi_perm, remove_reports_kochi_perm),
    ]
