from django.db import migrations


def seed_fee_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')

    perms = [
        (
            'fees:accounts',
            'Full authority to access, generate receipts, and manage settings across ALL companies (FLAG, FDS, LP)'
        ),
        (
            'fees:fds',
            'Access, generate receipts, and manage settings for FDS (Filmaatic Dance Studio)'
        ),
        (
            'fees:flag',
            'Access, generate receipts, and manage settings for FLAG (German Language Academy)'
        ),
        (
            'fees:lp',
            'Access, generate receipts, and manage settings for LP (Life Planner Universal)'
        ),
        (
            'fds_fees:manage',
            'Manage FDS fees, collections, and receipt settings'
        ),
        (
            'processing_students:manage_fees',
            'Manage LP processing student fee payments and receipts'
        ),
    ]

    for name, desc in perms:
        AppPermission.objects.get_or_create(
            name=name,
            defaults={'description': desc}
        )


def rollback_fee_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(name__in=[
        'fees:accounts',
        'fees:fds',
        'fees:flag',
        'fees:lp',
        'fds_fees:manage',
        'processing_students:manage_fees',
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fees', '0003_feereceipt_fds_account_feereceipt_fds_payment_and_more'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_fee_permissions, rollback_fee_permissions),
    ]
