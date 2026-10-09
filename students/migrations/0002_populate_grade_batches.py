from django.db import migrations

def populate_all_grade_batches(apps, schema_editor):
    AcademicBatch = apps.get_model('students', 'AcademicBatch')
    Grade = apps.get_model('students', 'Grade')
    GradeBatch = apps.get_model('students', 'GradeBatch')

    for batch in AcademicBatch.objects.all():
        if batch.package and batch.package.starting_grade and batch.package.ending_grade:
            start_order = batch.package.starting_grade.order
            end_order = batch.package.ending_grade.order
            grades = Grade.objects.filter(order__gte=start_order, order__lte=end_order)
            for g in grades:
                GradeBatch.objects.get_or_create(academic_batch=batch, grade=g)

def reverse_noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populate_all_grade_batches, reverse_noop),
    ]
