# Generated manually for a clean academic dataset.  The hosted database was
# verified empty before this change; abort rather than guessing at a historic
# placement in any other environment.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def seed_levels_and_require_empty_academic_data(apps, schema_editor):
    CourseLevel = apps.get_model('trainers', 'CourseLevel')
    AcademicBatch = apps.get_model('trainers', 'AcademicBatch')
    Student = apps.get_model('trainers', 'Student')
    Attendance = apps.get_model('trainers', 'Attendance')
    ExamResult = apps.get_model('trainers', 'ExamResult')

    for order, name in enumerate(('A1', 'A2', 'B1', 'B2'), start=1):
        level, _ = CourseLevel.objects.get_or_create(name=name, defaults={'order': order})
        if level.order != order:
            level.order = order
            level.save(update_fields=['order'])

    if any((
        AcademicBatch.objects.exists(),
        Student.objects.exists(),
        Attendance.objects.exists(),
        ExamResult.objects.exists(),
    )):
        raise RuntimeError(
            'Academic progression migration requires an empty academic dataset. '
            'Do not infer historic placements; clean or migrate that data explicitly first.'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('trainers', '0021_courselevel_attendance_academic_batch_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AcademicPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=80, unique=True)),
                ('name', models.CharField(max_length=150)),
                ('is_active', models.BooleanField(default=True)),
                ('maximum_level', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='packages_ending_here', to='trainers.courselevel')),
                ('minimum_level', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='packages_starting_here', to='trainers.courselevel')),
            ],
            options={'ordering': ['minimum_level__order', 'maximum_level__order', 'name']},
        ),
        migrations.AddField(
            model_name='academicbatch',
            name='branch',
            field=models.ForeignKey(blank=True, help_text='The branch running this academic batch', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='academic_batches', to='trainers.branch'),
        ),
        migrations.AddField(
            model_name='academicbatch',
            name='starting_level',
            field=models.ForeignKey(blank=True, help_text='The grade at which this batch begins', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='starting_academic_batches', to='trainers.courselevel'),
        ),
        migrations.RunPython(seed_levels_and_require_empty_academic_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='academicbatch',
            name='branch',
            field=models.ForeignKey(help_text='The branch running this academic batch', on_delete=django.db.models.deletion.PROTECT, related_name='academic_batches', to='trainers.branch'),
        ),
        migrations.AlterField(
            model_name='academicbatch',
            name='starting_level',
            field=models.ForeignKey(help_text='The grade at which this batch begins', on_delete=django.db.models.deletion.PROTECT, related_name='starting_academic_batches', to='trainers.courselevel'),
        ),
        migrations.AddConstraint(
            model_name='academicbatch',
            constraint=models.UniqueConstraint(fields=('branch', 'name', 'academic_year'), name='unique_academic_batch_name_per_branch_year'),
        ),
        migrations.AlterField(
            model_name='student',
            name='status',
            field=models.CharField(choices=[('PENDING_ENROLLMENT', 'Pending Enrollment'), ('PENDING_BATCH_ASSIGNMENT', 'Pending Batch Assignment'), ('ACTIVE', 'Active'), ('EXAM_PREPARATION', 'Exam Preparation'), ('PAUSED', 'Paused'), ('AWAITING_REPEAT_TRANSFER', 'Awaiting Repeat Transfer'), ('AWAITING_PACKAGE_UPGRADE', 'Awaiting Package Upgrade'), ('COMPLETED', 'Completed'), ('DROPPED', 'Dropped')], default='PENDING_ENROLLMENT', max_length=30),
        ),
        migrations.AlterField(
            model_name='studenttimeline',
            name='event_type',
            field=models.CharField(choices=[('BATCH_ASSIGNMENT', 'Batch Assignment'), ('PROMOTE', 'Promote'), ('FALLBACK', 'Fallback'), ('REPEAT_TRANSFER', 'Repeat Transfer'), ('PACKAGE_UPGRADE', 'Package Upgrade'), ('PACKAGE_COMPLETE', 'Package Complete'), ('EXAM_FINALIZED', 'Exam Finalized'), ('STATUS_CHANGE', 'Status Change'), ('NOTE', 'Note')], max_length=50),
        ),
        migrations.CreateModel(
            name='StudentPackageEnrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('REPLACED', 'Replaced')], default='ACTIVE', max_length=20)),
                ('started_on', models.DateField(default=django.utils.timezone.localdate)),
                ('ended_on', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='student_enrollments', to='trainers.academicpackage')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='package_enrollments', to='trainers.student')),
            ],
            options={'ordering': ['-started_on', '-id']},
        ),
        migrations.AddConstraint(
            model_name='studentpackageenrollment',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'ACTIVE')), fields=('student',), name='one_active_academic_package_per_student'),
        ),
        migrations.CreateModel(
            name='StudentAcademicPlacement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('CLOSED', 'Closed')], default='ACTIVE', max_length=20)),
                ('entry_reason', models.CharField(choices=[('INITIAL', 'Initial Enrollment'), ('PROMOTION', 'Promotion'), ('REPEAT', 'Repeat Transfer'), ('PACKAGE_UPGRADE', 'Package Upgrade')], max_length=30)),
                ('exit_reason', models.CharField(blank=True, choices=[('PROMOTION', 'Promoted'), ('FAILED', 'Failed'), ('PACKAGE_COMPLETE', 'Package Complete'), ('B2_COMPLETE', 'B2 Complete')], max_length=30)),
                ('entered_on', models.DateField(default=django.utils.timezone.localdate)),
                ('exited_on', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('academic_batch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='placements', to='trainers.academicbatch')),
                ('level', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='placements', to='trainers.courselevel')),
                ('package_enrollment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='placements', to='trainers.studentpackageenrollment')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='academic_placements', to='trainers.student')),
            ],
            options={
                'ordering': ['-entered_on', '-id'],
                'indexes': [models.Index(fields=['academic_batch', 'level', 'status'], name='trainers_st_academi_d4d647_idx'), models.Index(fields=['student', 'status'], name='trainers_st_student_d46255_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='studentacademicplacement',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'ACTIVE')), fields=('student',), name='one_active_academic_placement_per_student'),
        ),
        migrations.AddField(
            model_name='attendance',
            name='placement',
            field=models.ForeignKey(blank=True, help_text='Immutable academic placement active when attendance was marked', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='attendance_records', to='trainers.studentacademicplacement'),
        ),
        migrations.AddField(
            model_name='examresult',
            name='placement',
            field=models.ForeignKey(blank=True, help_text='The student placement for which this exam was taken', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='exam_results', to='trainers.studentacademicplacement'),
        ),
        migrations.AddField(
            model_name='examresult',
            name='outcome',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('PASS', 'Pass'), ('FAIL', 'Fail')], default='PENDING', max_length=10),
        ),
        migrations.AddField(
            model_name='examresult',
            name='processed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='examresult',
            name='processed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_exam_results', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterUniqueTogether(name='attendance', unique_together=set()),
        migrations.AlterUniqueTogether(name='examresult', unique_together={('placement', 'exam_type')}),
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(fields=['placement', 'date'], name='trainers_at_placeme_1da730_idx'),
        ),
        migrations.AddConstraint(
            model_name='attendance',
            constraint=models.UniqueConstraint(fields=('date', 'placement'), name='unique_attendance_per_placement_date'),
        ),
        migrations.AlterField(
            model_name='attendance',
            name='placement',
            field=models.ForeignKey(help_text='Immutable academic placement active when attendance was marked', on_delete=django.db.models.deletion.PROTECT, related_name='attendance_records', to='trainers.studentacademicplacement'),
        ),
        migrations.AlterField(
            model_name='examresult',
            name='placement',
            field=models.ForeignKey(help_text='The student placement for which this exam was taken', on_delete=django.db.models.deletion.PROTECT, related_name='exam_results', to='trainers.studentacademicplacement'),
        ),
    ]
