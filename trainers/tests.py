from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.permission_templates import get_permissions_for_role
from fees.models import FeePlanTemplate
from trainers.models import Branch, Trainer, Student


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
            'batch': 'B1',
            'branch': self.branch.id,
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

