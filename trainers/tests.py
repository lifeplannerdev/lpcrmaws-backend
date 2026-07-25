from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.permission_templates import get_permissions_for_role
from fees.models import FeePlanTemplate
from trainers.models import (
    AcademicBatch, AcademicPackage, Attendance, Branch, CourseLevel, ExamResult,
    Student, StudentAcademicPlacement, Trainer,
)
from trainers.academic_services import create_initial_academic_enrollment


User = get_user_model()


class StudentAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='KTM', location='Kottayam')

        self.trainer_user = User.objects.create_user(
            username='trainer1',
            password='pass12345',
            company='FLAG',
            permissions=get_permissions_for_role('TRAINER'),
        )
        self.trainer = Trainer.objects.create(user=self.trainer_user, branch=self.branch)

        self.other_trainer_user = User.objects.create_user(
            username='trainer2',
            password='pass12345',
            company='FLAG',
            permissions=get_permissions_for_role('TRAINER'),
        )
        self.other_trainer = Trainer.objects.create(user=self.other_trainer_user, branch=self.branch)

        self.viewer_user = User.objects.create_user(
            username='viewer',
            password='pass12345',
            company='FLAG',
            permissions=['students:read_tenant'],
        )

        self.own_student = Student.objects.create(
            name='Own Student',
            batch='A1',
            branch=self.branch,
            trainer=self.trainer,
            status='ACTIVE',
            admission_date=date(2026, 1, 1),
            company='FLAG',
        )
        self.other_student = Student.objects.create(
            name='Other Student',
            batch='A1',
            branch=self.branch,
            trainer=self.other_trainer,
            status='ACTIVE',
            admission_date=date(2026, 1, 1),
            company='FLAG',
        )

    def test_trainer_only_sees_own_students(self):
        self.client.force_authenticate(user=self.trainer_user)
        response = self.client.get(reverse('student-list-create'))
        self.assertEqual(response.status_code, 200)
        names = [item['name'] for item in response.data['results']]
        self.assertIn('Own Student', names)
        self.assertNotIn('Other Student', names)

    def test_user_without_mark_attendance_cannot_quick_mark(self):
        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.post(
            reverse('attendance-quick-mark'),
            {'date': '2026-06-04', 'records': [{'student': self.own_student.id, 'status': 'PRESENT'}]},
            format='json',
        )
        self.assertEqual(response.status_code, 403)


class StudentEnrollmentFeeSyncTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='FLAG Branch', location='Kochi')
        self.a1 = CourseLevel.objects.get(name='A1')
        self.a2 = CourseLevel.objects.get(name='A2')
        self.b2 = CourseLevel.objects.get(name='B2')
        self.academic_batch = AcademicBatch.objects.create(
            name='FLAGCHN-01-2026',
            academic_year='2026',
            branch=self.branch,
            starting_level=self.a1,
        )
        self.academic_package = AcademicPackage.objects.create(
            code='A1-B2',
            name='A1 to B2',
            minimum_level=self.a1,
            maximum_level=self.b2,
        )
        self.template = FeePlanTemplate.objects.create(
            company='FLAG',
            code='FLAG-B1',
            name='FLAG B1 Level',
            course_label='B1',
            plan_type='PACKAGE',
            total_amount='29500.00',
            registration_amount='0.00',
            due_day=10,
        )
        self.enroller = User.objects.create_user(
            username='enroller',
            password='pass12345',
            company='FLAG',
            permissions=['students:edit_any', 'students:read_tenant', 'fees:read_tenant'],
        )
        self.trainer = Trainer.objects.create(user=self.enroller, branch=self.branch)

    def _student_payload(self, fee_template=None):
        payload = {
            'name': 'Enrollment Student',
            'branch': self.branch.id,
            'academic_batch': self.academic_batch.id,
            'academic_package': self.academic_package.id,
            'trainer': self.trainer.id,
            'status': 'ACTIVE',
            'admission_date': '2026-01-01',
            'company': 'FLAG',
        }
        if fee_template:
            payload['fee_template'] = fee_template.id
        return payload

    def test_student_creation_with_fee_template_creates_fee_account(self):
        self.client.force_authenticate(user=self.enroller)
        response = self.client.post(
            reverse('student-list-create'),
            self._student_payload(self.template),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['fee_setup_status'], 'ACTIVE')
        self.assertIsNotNone(response.data['fee_summary'])
        student = Student.objects.get(name='Enrollment Student')
        self.assertTrue(hasattr(student, 'fee_account'))
        self.assertEqual(student.fee_account.plan_code, self.template.code)
        self.assertEqual(student.fee_account.plan_name, self.template.name)
        self.assertEqual(student.current_level, self.a1)
        self.assertEqual(student.academic_batch, self.academic_batch)
        self.assertEqual(student.academic_placements.filter(status='ACTIVE').count(), 1)

    def test_student_creation_without_fee_template_stays_pending(self):
        self.client.force_authenticate(user=self.enroller)
        response = self.client.post(
            reverse('student-list-create'),
            self._student_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['fee_setup_status'], 'PENDING_FEE_SETUP')
        self.assertIsNone(response.data['fee_summary'])


class AcademicProgressionTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='KTM', location='Kottayam')
        self.a1 = CourseLevel.objects.get(name='A1')
        self.a2 = CourseLevel.objects.get(name='A2')
        self.b2 = CourseLevel.objects.get(name='B2')
        self.manager = User.objects.create_user(
            username='academic-manager',
            password='pass12345',
            company='FLAG',
            permissions=['students:edit_any', 'students:read_tenant', 'attendance:mark'],
        )
        self.trainer = Trainer.objects.create(user=self.manager, branch=self.branch)
        self.a1_batch = AcademicBatch.objects.create(
            name='FLAGKTM-01-2026',
            academic_year='2026',
            branch=self.branch,
            starting_level=self.a1,
        )
        self.repeat_a1_batch = AcademicBatch.objects.create(
            name='FLAGKTM-02-2026',
            academic_year='2026',
            branch=self.branch,
            starting_level=self.a1,
        )
        self.full_package = AcademicPackage.objects.create(
            code='A1-B2',
            name='A1 to B2',
            minimum_level=self.a1,
            maximum_level=self.b2,
        )
        self.a1_only_package = AcademicPackage.objects.create(
            code='A1-ONLY',
            name='A1 only',
            minimum_level=self.a1,
            maximum_level=self.a1,
        )
        self.client.force_authenticate(user=self.manager)

    def _student(self, name='Academic Student', package=None):
        student = Student.objects.create(
            name=name,
            branch=self.branch,
            trainer=self.trainer,
            admission_date=date(2026, 1, 1),
            company='FLAG',
        )
        create_initial_academic_enrollment(
            student,
            package or self.full_package,
            self.a1_batch,
            actor=self.manager,
            effective_date=date(2026, 1, 1),
        )
        return student

    def _final_result(self, placement, outcome):
        return ExamResult.objects.create(
            student=placement.student,
            placement=placement,
            academic_batch=placement.academic_batch,
            exam_type='FINAL',
            outcome=outcome,
        )

    def test_pass_promotes_in_same_batch_and_history_keeps_attendance_separate_by_grade(self):
        student = self._student()
        a1_placement = student.academic_placements.get(status='ACTIVE')
        Attendance.objects.create(
            date=date(2026, 1, 2), trainer=self.trainer, student=student,
            placement=a1_placement, status='PRESENT',
        )
        self._final_result(a1_placement, 'PASS')

        response = self.client.post(
            reverse('academic-batch-level-finalize', args=[self.a1_batch.id, self.a1.id]),
            {'effective_date': '2026-02-01'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        repeated_finalize = self.client.post(
            reverse('academic-batch-level-finalize', args=[self.a1_batch.id, self.a1.id]),
            {'effective_date': '2026-02-01'}, format='json',
        )
        self.assertEqual(repeated_finalize.status_code, 200)
        self.assertTrue(repeated_finalize.data['already_finalized'])

        student.refresh_from_db()
        a2_placement = student.academic_placements.get(status='ACTIVE')
        self.assertEqual(a2_placement.academic_batch_id, self.a1_batch.id)
        self.assertEqual(a2_placement.level_id, self.a2.id)
        Attendance.objects.create(
            date=date(2026, 2, 2), trainer=self.trainer, student=student,
            placement=a2_placement, status='PRESENT',
        )

        history = self.client.get(reverse('student-academic-history', args=[student.id]))
        self.assertEqual(history.status_code, 200)
        placements = history.data['placements']
        self.assertEqual(len(placements), 2)
        by_level = {placement['level_name']: placement for placement in placements}
        self.assertEqual(by_level['A1']['academic_batch'], self.a1_batch.id)
        self.assertEqual(by_level['A2']['academic_batch'], self.a1_batch.id)
        self.assertEqual(len(by_level['A1']['attendance_records']), 1)
        self.assertEqual(len(by_level['A2']['attendance_records']), 1)

    def test_b2_pass_completes_student(self):
        b2_batch = AcademicBatch.objects.create(
            name='FLAGKTM-B2-2026',
            academic_year='2026',
            branch=self.branch,
            starting_level=self.b2,
        )
        student = Student.objects.create(
            name='B2 Student',
            branch=self.branch,
            trainer=self.trainer,
            admission_date=date(2026, 1, 1),
            company='FLAG',
        )
        create_initial_academic_enrollment(
            student,
            self.full_package,
            b2_batch,
            actor=self.manager,
            effective_date=date(2026, 1, 1),
        )
        placement = student.academic_placements.get(status='ACTIVE')
        self._final_result(placement, 'PASS')

        response = self.client.post(
            reverse('academic-batch-level-finalize', args=[b2_batch.id, self.b2.id]),
            {'effective_date': '2026-02-01'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.status, 'COMPLETED')
        self.assertFalse(student.academic_placements.filter(status='ACTIVE').exists())

    def test_failed_student_requires_different_same_grade_batch_before_repeat(self):
        student = self._student()
        placement = student.academic_placements.get(status='ACTIVE')
        self._final_result(placement, 'FAIL')
        response = self.client.post(
            reverse('academic-batch-level-finalize', args=[self.a1_batch.id, self.a1.id]),
            {'effective_date': '2026-02-01'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.status, 'AWAITING_REPEAT_TRANSFER')
        self.assertFalse(student.academic_placements.filter(status='ACTIVE').exists())

        invalid = self.client.post(
            reverse('student-repeat-transfer', args=[student.id]),
            {'academic_batch_id': self.a1_batch.id, 'effective_date': '2026-02-02'}, format='json',
        )
        self.assertEqual(invalid.status_code, 400)
        response = self.client.post(
            reverse('student-repeat-transfer', args=[student.id]),
            {'academic_batch_id': self.repeat_a1_batch.id, 'effective_date': '2026-02-02'}, format='json',
        )
        self.assertEqual(response.status_code, 201)
        student.refresh_from_db()
        repeat_placement = student.academic_placements.get(status='ACTIVE')
        self.assertEqual(repeat_placement.academic_batch_id, self.repeat_a1_batch.id)
        self.assertEqual(repeat_placement.level_id, self.a1.id)

    def test_package_ceiling_requires_upgrade_then_resumes_in_same_batch(self):
        student = self._student(package=self.a1_only_package)
        placement = student.academic_placements.get(status='ACTIVE')
        self._final_result(placement, 'PASS')
        response = self.client.post(
            reverse('academic-batch-level-finalize', args=[self.a1_batch.id, self.a1.id]),
            {'effective_date': '2026-02-01'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.status, 'AWAITING_PACKAGE_UPGRADE')

        response = self.client.post(
            reverse('student-academic-package-upgrade', args=[student.id]),
            {'academic_package_id': self.full_package.id, 'effective_date': '2026-02-02'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        resumed = student.academic_placements.get(status='ACTIVE')
        self.assertEqual(resumed.academic_batch_id, self.a1_batch.id)
        self.assertEqual(resumed.level_id, self.a2.id)

    def test_attendance_api_resolves_current_placement_and_grade_report_is_segregated(self):
        student = self._student()
        response = self.client.post(
            reverse('attendance-list-create'),
            {'student': student.id, 'date': '2026-01-02', 'status': 'PRESENT'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['placement'], student.academic_placements.get(status='ACTIVE').id)

        report = self.client.get(reverse('attendance-report'), {'group_by': 'grade'})
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['results'][0]['total'], 1)

