from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import AppPermission, Role
from .models import Reminder, ReminderUpdate

User = get_user_model()


class RemindersAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create permissions
        self.perm_admin, _ = AppPermission.objects.get_or_create(
            name='processing:reminders_admin',
            defaults={'description': 'Admin reminders'}
        )
        self.perm_user, _ = AppPermission.objects.get_or_create(
            name='processing:reminders_users',
            defaults={'description': 'User reminders'}
        )

        # Create roles
        self.role_admin = Role.objects.create(name='REMINDERS_ADMIN')
        self.role_admin.permissions.add(self.perm_admin)

        self.role_user = Role.objects.create(name='REMINDERS_USER')
        self.role_user.permissions.add(self.perm_user)

        # Create users
        self.admin_user = User.objects.create_user(
            username='admin_reminders',
            email='admin@example.com',
            password='password123',
            first_name='Admin',
            last_name='Boss'
        )
        self.admin_user.db_roles.add(self.role_admin)

        self.employee1 = User.objects.create_user(
            username='emp_john',
            email='john@example.com',
            password='password123',
            first_name='John',
            last_name='Doe'
        )
        self.employee1.db_roles.add(self.role_user)

        self.employee2 = User.objects.create_user(
            username='emp_jane',
            email='jane@example.com',
            password='password123',
            first_name='Jane',
            last_name='Smith'
        )
        self.employee2.db_roles.add(self.role_user)

        self.no_perm_user = User.objects.create_user(
            username='no_perm',
            email='noperm@example.com',
            password='password123'
        )

    def test_unauthorized_user_blocked(self):
        self.client.force_authenticate(user=self.no_perm_user)
        response = self.client.get('/api/reminders/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_can_create_backdated_reminder_with_checklist(self):
        self.client.force_authenticate(user=self.employee1)
        past_date = (timezone.now() - timedelta(days=5)).date().isoformat()
        future_deadline = (timezone.now() + timedelta(days=3)).date().isoformat()

        payload = {
            "title": "Verify Student Certificates",
            "description": "Double check attested transcripts",
            "reminder_date": past_date,
            "deadline": future_deadline,
            "priority": "HIGH",
            "category": "Processing",
            "checklist": [
                {"id": 1, "text": "Collect degree certificate", "completed": False},
                {"id": 2, "text": "Verify with university portal", "completed": False}
            ]
        }

        response = self.client.post('/api/reminders/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user'], self.employee1.id)
        self.assertEqual(response.data['status'], 'PENDING')
        self.assertTrue(response.data['is_backdated'])

    def test_employee_submit_completion_requires_remarks_and_sets_pending_approval(self):
        self.client.force_authenticate(user=self.employee1)
        reminder = Reminder.objects.create(
            user=self.employee1,
            created_by=self.employee1,
            title="Complete Visa Filing",
            reminder_date=timezone.now().date(),
            status='IN_PROGRESS'
        )

        # Attempt submit without remarks -> should fail 400
        fail_res = self.client.post(f'/api/reminders/{reminder.id}/submit-completion/', {}, format='json')
        self.assertEqual(fail_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mandatory", fail_res.data['detail'].lower())

        # Submit with remarks -> should transition to PENDING_APPROVAL
        success_res = self.client.post(f'/api/reminders/{reminder.id}/submit-completion/', {
            "completion_remarks": "All documents uploaded to embassy portal with ref #9821."
        }, format='json')
        self.assertEqual(success_res.status_code, status.HTTP_200_OK)
        self.assertEqual(success_res.data['status'], 'PENDING_APPROVAL')

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, 'PENDING_APPROVAL')
        self.assertEqual(reminder.completion_remarks, "All documents uploaded to embassy portal with ref #9821.")

    def test_admin_submit_completion_auto_completes(self):
        self.client.force_authenticate(user=self.admin_user)
        reminder = Reminder.objects.create(
            user=self.admin_user,
            created_by=self.admin_user,
            title="Executive Review",
            reminder_date=timezone.now().date(),
            status='IN_PROGRESS'
        )

        # Admin completes own reminder -> directly COMPLETED
        res = self.client.post(f'/api/reminders/{reminder.id}/submit-completion/', {
            "completion_remarks": "Reviewed and closed directly by admin."
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'COMPLETED')

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, 'COMPLETED')
        self.assertIsNotNone(reminder.completed_at)
        self.assertEqual(reminder.approved_by, self.admin_user)

    def test_admin_approval_and_rejection_workflow(self):
        # Create reminder for employee in PENDING_APPROVAL
        reminder = Reminder.objects.create(
            user=self.employee1,
            created_by=self.employee1,
            title="Police Clearance Document",
            reminder_date=timezone.now().date(),
            status='PENDING_APPROVAL',
            completion_remarks="Obtained certificate from passport office."
        )

        # Employee cannot call approve endpoint (admin only)
        self.client.force_authenticate(user=self.employee1)
        res_emp_approve = self.client.post(f'/api/reminders/{reminder.id}/approve/', {})
        self.assertEqual(res_emp_approve.status_code, status.HTTP_403_FORBIDDEN)

        # Admin rejects with feedback
        self.client.force_authenticate(user=self.admin_user)
        res_reject = self.client.post(f'/api/reminders/{reminder.id}/reject/', {
            "reason": "The stamp is faded. Please request a clearer scan.",
            "new_deadline": (timezone.now() + timedelta(days=2)).date().isoformat()
        }, format='json')
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)
        self.assertEqual(res_reject.data['status'], 'IN_PROGRESS')

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, 'IN_PROGRESS')
        self.assertIn("stamp is faded", reminder.rejection_reason)

        # Employee resubmits
        self.client.force_authenticate(user=self.employee1)
        res_resubmit = self.client.post(f'/api/reminders/{reminder.id}/submit-completion/', {
            "completion_remarks": "Uploaded high resolution 600dpi scan with distinct seal."
        }, format='json')
        self.assertEqual(res_resubmit.data['status'], 'PENDING_APPROVAL')

        # Admin approves
        self.client.force_authenticate(user=self.admin_user)
        res_approve = self.client.post(f'/api/reminders/{reminder.id}/approve/', {
            "notes": "Verified. Perfectly clear."
        }, format='json')
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        self.assertEqual(res_approve.data['status'], 'COMPLETED')

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, 'COMPLETED')
        self.assertEqual(reminder.approved_by, self.admin_user)

    def test_two_way_updates_thread(self):
        reminder = Reminder.objects.create(
            user=self.employee1,
            created_by=self.employee1,
            title="Finance clearance",
            reminder_date=timezone.now().date(),
            status='IN_PROGRESS'
        )

        # Admin posts an update/query on employee's reminder
        self.client.force_authenticate(user=self.admin_user)
        res_admin_update = self.client.post(f'/api/reminders/{reminder.id}/updates/', {
            "notes": "Did the student submit fee receipt #104?"
        }, format='json')
        self.assertEqual(res_admin_update.status_code, status.HTTP_201_CREATED)

        # Employee replies back
        self.client.force_authenticate(user=self.employee1)
        res_emp_update = self.client.post(f'/api/reminders/{reminder.id}/updates/', {
            "notes": "Yes, received receipt #104 and filed under finance drive."
        }, format='json')
        self.assertEqual(res_emp_update.status_code, status.HTTP_201_CREATED)

        # Fetch updates
        res_list = self.client.get(f'/api/reminders/{reminder.id}/updates/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        updates_data = res_list.data.get('results', res_list.data) if isinstance(res_list.data, dict) else res_list.data
        self.assertEqual(len(updates_data), 2)

    def test_employee_cannot_see_other_employees_reminders(self):
        rem1 = Reminder.objects.create(
            user=self.employee1,
            created_by=self.employee1,
            title="John Private Reminder",
            reminder_date=timezone.now().date()
        )
        rem2 = Reminder.objects.create(
            user=self.employee2,
            created_by=self.employee2,
            title="Jane Private Reminder",
            reminder_date=timezone.now().date()
        )

        self.client.force_authenticate(user=self.employee1)
        res = self.client.get('/api/reminders/')
        data = res.data if isinstance(res.data, list) else res.data.get('results', [])
        titles = [r['title'] for r in data]
        self.assertIn("John Private Reminder", titles)
        self.assertNotIn("Jane Private Reminder", titles)

        # Admin sees both
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get('/api/reminders/')
        data_admin = res_admin.data if isinstance(res_admin.data, list) else res_admin.data.get('results', [])
        admin_titles = [r['title'] for r in data_admin]
        self.assertIn("John Private Reminder", admin_titles)
        self.assertIn("Jane Private Reminder", admin_titles)
