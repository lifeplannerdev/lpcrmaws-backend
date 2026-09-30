from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0042_alter_followup_status_alter_lead_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lead',
            name='source',
            field=models.CharField(
                blank=True,
                choices=[
                    ('WHATSAPP', 'WhatsApp'),
                    ('INSTAGRAM', 'Instagram'),
                    ('WEBSITE', 'Website'),
                    ('WALK_IN', 'Walk-in'),
                    ('AUTOMATION', 'Automation'),
                    ('OTHER', 'Other'),
                    ('ADS', 'Ads'),
                    ('VOXBAY CALL', 'Voxbay'),
                    ('VOXBAY-EDITORIAL', 'Voxbay-Editorial'),
                    ('IN HOUSE SOCIAL MEDIA', 'In House Social Media'),
                    ('BULK DATA', 'Bulk data'),
                ],
                max_length=50,
                null=True,
            ),
        ),
    ]
