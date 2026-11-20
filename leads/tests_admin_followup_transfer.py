from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from leads.assignment_utils import resolve_counselor_from_context
from leads.models import FollowUp, Lead

User = get_user_model()


class AdminFollowUpTransferTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='pass',
        )
        self.navya = User.objects.create_user(
            username='navya',
            email='navya@example.com',
            password='pass',
            first_name='Navya',
            last_name='Rajgopal',
        )

    def test_alerts_never_show_admin_followups(self):
        lead = Lead.objects.create(
            name='Voxbay Missed Call - 919048147006',
            phone='919048147006',
            assigned_to=self.admin,
        )
        FollowUp.objects.create(
            lead=lead,
            phone_number='919048147006',
            name=lead.name,
            follow_up_date=timezone.now().date(),
            followup_type='call',
            status='pending',
            assigned_to=self.admin,
            notes='Unanswered call',
        )

        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/followups/alerts/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['counts']['total_active'], 0)

        list_res = self.client.get('/api/followups/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        items = list_res.data['results'] if isinstance(list_res.data, dict) else list_res.data
        self.assertEqual(len(items), 0)

    def test_counselor_followup_update_transfers_lead_and_followup_from_admin(self):
        lead = Lead.objects.create(
            name='Voxbay Missed Call - 919048147006',
            phone='919048147006',
            assigned_to=self.admin,
        )
        fu = FollowUp.objects.create(
            lead=lead,
            phone_number='919048147006',
            name=lead.name,
            follow_up_date=timezone.now().date(),
            followup_type='call',
            status='pending',
            assigned_to=self.admin,
            notes='Call UUID: abc-123',
        )

        self.client.force_authenticate(user=self.navya)
        res = self.client.post(
            '/api/followups/',
            {
                'lead': lead.id,
                'phone_number': '919048147006',
                'follow_up_date': str(timezone.now().date()),
                'followup_type': 'call',
                'status': 'pending',
                'notes': '[18/11/2026 10:11] Navya Rajgopal: Akhila from TVM',
                'call_uuid': 'abc-123',
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        fu.refresh_from_db()
        lead.refresh_from_db()
        self.assertEqual(fu.assigned_to, self.navya)
        self.assertEqual(lead.assigned_to, self.navya)

    def test_resolve_counselor_from_remark_notes(self):
        resolved = resolve_counselor_from_context(
            notes='[18/11/2026 10:11] Navya Rajgopal: Akhila from TVM 29Yrs Old Btech'
        )
        self.assertEqual(resolved, self.navya)

    def test_alerts_only_include_followups_within_two_days(self):
        today = timezone.localtime(timezone.now()).date()
        lead = Lead.objects.create(
            name='Rajitha',
            phone='919744644950',
            assigned_to=self.navya,
        )
        due_today = FollowUp.objects.create(
            lead=lead,
            phone_number='919744644950',
            name='Due Today',
            follow_up_date=today,
            followup_type='call',
            status='pending',
            assigned_to=self.navya,
        )
        due_two_days = FollowUp.objects.create(
            lead=lead,
            phone_number='919744644950',
            name='Due In Two Days',
            follow_up_date=today + timezone.timedelta(days=2),
            followup_type='call',
            status='pending',
            assigned_to=self.navya,
        )
        FollowUp.objects.create(
            lead=lead,
            phone_number='919744644950',
            name='Far Future',
            follow_up_date=today + timezone.timedelta(days=50),
            followup_type='call',
            status='pending',
            assigned_to=self.navya,
        )

        self.client.force_authenticate(user=self.navya)
        res = self.client.get('/api/followups/alerts/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['counts']['total_active'], 2)
        self.assertEqual(res.data['counts']['today'], 1)
        self.assertEqual(res.data['counts']['upcoming'], 1)
        self.assertEqual([r['id'] for r in res.data['today']], [due_today.id])
        self.assertEqual([r['id'] for r in res.data['upcoming']], [due_two_days.id])
