from django.db import migrations

def sync_student_trainers(apps, schema_editor):
    AcademicBatch = apps.get_model('students', 'AcademicBatch')
    Student = apps.get_model('students', 'Student')

    # For each batch, sync all its students to the batch's trainer
    for batch in AcademicBatch.objects.all():
        Student.objects.filter(batch=batch).update(trainer=batch.trainer)

    # For any students not in a batch, unassign trainer
    Student.objects.filter(batch__isnull=True).update(trainer=None)

def reverse_sync(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(sync_student_trainers, reverse_sync),
    ]
