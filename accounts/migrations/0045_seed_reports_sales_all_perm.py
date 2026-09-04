from django.db import migrations

def seed_reports_sales_all_perm(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.get_or_create(
        name='reports:sales_all',
        defaults={'description': 'View sales staff reports (ADM_COUNSELLOR, ADM_MANAGER, BMCO, FLAG COORDINATOR)'}
    )

def remove_reports_sales_all_perm(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(name='reports:sales_all').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0044_seed_reports_kochi_perm'),
    ]

    operations = [
        migrations.RunPython(seed_reports_sales_all_perm, remove_reports_sales_all_perm),
    ]
