from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.permission_templates import get_permissions_for_role
from trainers.models import Branch, Trainer, Student


User = get_user_model()


class StudentAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='KTM', location='Kottayam')

        self.trainer_user = User.objects.create_user(
            username='trainer1',
            password='pass12345',
            role='TRAINER',
            company='FLAG',
            permissions=get_permissions_for_role('TRAINER'),
        )
        self.trainer = self.trainer_user.trainer_profile
        self.trainer.branch = self.branch
        self.trainer.save(update_fields=['branch'])

        self.other_trainer_user = User.objects.create_user(
            username='trainer2',
            password='pass12345',
            role='TRAINER',
            company='FLAG',
            permissions=get_permissions_for_role('TRAINER'),
        )
        self.other_trainer = self.other_trainer_user.trainer_profile
        self.other_trainer.branch = self.branch
        self.other_trainer.save(update_fields=['branch'])

        self.viewer_user = User.objects.create_user(
            username='viewer',
            password='pass12345',
            role='HR',
            company='FLAG',
            permissions=['view_students'],
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
