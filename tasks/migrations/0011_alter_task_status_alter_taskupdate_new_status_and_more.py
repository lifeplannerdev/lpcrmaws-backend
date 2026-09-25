from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0010_alter_task_company'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('IN_PROGRESS', 'In Progress'),
                    ('PENDING_APPROVAL', 'Pending Approval'),
                    ('COMPLETED', 'Completed'),
                    ('CANCELLED', 'Cancelled'),
                    ('OVERDUE', 'Overdue'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='taskupdate',
            name='new_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('IN_PROGRESS', 'In Progress'),
                    ('PENDING_APPROVAL', 'Pending Approval'),
                    ('COMPLETED', 'Completed'),
                    ('CANCELLED', 'Cancelled'),
                    ('OVERDUE', 'Overdue'),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='taskupdate',
            name='previous_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('IN_PROGRESS', 'In Progress'),
                    ('PENDING_APPROVAL', 'Pending Approval'),
                    ('COMPLETED', 'Completed'),
                    ('CANCELLED', 'Cancelled'),
                    ('OVERDUE', 'Overdue'),
                ],
                max_length=20,
            ),
        ),
    ]
