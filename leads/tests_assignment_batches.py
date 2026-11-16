from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from leads.models import FollowUp, Lead, LeadAssignment, LeadAssignmentBatch
from accounts.models import Role

User = get_user_model()


class LeadAssignmentBatchTests(APITestCase):
    def setUp(self):
        exec_role, _ = Role.objects.get_or_create(name='ADM_EXEC')
        self.admin = User.objects.create_user(
            username='admin_batch',
            password='pass12345',
            first_name='Admin',
            last_name='User',
            company='LP',
            is_superuser=True,
            permissions=['leads:read_any', 'leads:read_tenant', 'leads:edit_tenant', 'leads:assign'],
        )
        self.staff_a = User.objects.create_user(
            username='anjali_sales',
            password='pass12345',
            first_name='Anjali',
            last_name='Nair',
            company='LP',
            permissions=['leads:read_own', 'leads:edit_own'],
        )
        self.staff_a.db_roles.add(exec_role)
        self.staff_b = User.objects.create_user(
            username='rahul_sales',
            password='pass12345',
            first_name='Rahul',
            last_name='Menon',
            company='LP',
            permissions=['leads:read_own', 'leads:edit_own'],
        )
        self.staff_b.db_roles.add(exec_role)
        self.flag_admin = User.objects.create_user(
            username='flag_mgr',
            password='pass12345',
            first_name='Flag',
            last_name='Manager',
            company='FLAG',
            permissions=['leads:read_tenant', 'leads:edit_tenant', 'leads:assign'],
        )

        self.leads = []
        for idx in range(1, 7):
            self.leads.append(
                Lead.objects.create(
                    name=f'Lead {idx}',
                    phone=f'987654321{idx}',
                    company='LP',
                    status='ENQUIRY',
                    priority='MEDIUM',
                    assigned_to=self.staff_b if idx <= 3 else None,
                )
            )

    def test_two_bulk_assigns_to_same_staff_create_distinct_batches(self):
        self.client.force_authenticate(user=self.admin)

        res1 = self.client.post(
            '/api/leads/bulk-assign/',
            {
                'lead_ids': [self.leads[0].id, self.leads[1].id, self.leads[2].id],
                'assigned_to_id': self.staff_a.id,
                'batch_label': 'Batch 1 - From Rahul',
                'followup_strategy': 'specific_date',
                'followup_date': str(date.today() + timedelta(days=1)),
                'notes': 'Call urgently',
            },
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertIn('assignment_batch', res1.data)
        batch1_id = res1.data['assignment_batch']['id']
        self.assertEqual(res1.data['assignment_batch']['title'], 'Batch 1 - From Rahul')

        res2 = self.client.post(
            '/api/leads/bulk-assign/',
            {
                'lead_ids': [self.leads[3].id, self.leads[4].id],
                'assigned_to_id': self.staff_a.id,
                'followup_strategy': 'keep',
                'notes': 'Second lot',
            },
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        batch2_id = res2.data['assignment_batch']['id']
        self.assertNotEqual(batch1_id, batch2_id)
        self.assertTrue(res2.data['assignment_batch']['title'])

        # Staff A sees 2 distinct batches
        self.client.force_authenticate(user=self.staff_a)
        list_res = self.client.get('/api/leads/assignment-batches/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        batches = list_res.data['results'] if 'results' in list_res.data else list_res.data
        self.assertEqual(len(batches), 2)

        b1 = next(b for b in batches if b['id'] == batch1_id)
        b2 = next(b for b in batches if b['id'] == batch2_id)
        self.assertEqual(b1['total_assigned_count'], 3)
        self.assertEqual(b1['active_count'], 3)
        self.assertEqual(b2['total_assigned_count'], 2)
        self.assertEqual(b2['active_count'], 2)

        # Fetch leads inside Batch 1 and verify follow-up date annotation
        b1_leads_res = self.client.get(f'/api/leads/assignment-batches/{batch1_id}/leads/')
        self.assertEqual(b1_leads_res.status_code, status.HTTP_200_OK)
        b1_leads = b1_leads_res.data['results'] if 'results' in b1_leads_res.data else b1_leads_res.data
        self.assertEqual(len(b1_leads), 3)
        self.assertEqual(b1_leads[0]['next_follow_up_date'], str(date.today() + timedelta(days=1)))

    def test_reassigned_out_leads_move_out_of_active_batch_and_appear_when_toggled(self):
        self.client.force_authenticate(user=self.admin)
        res1 = self.client.post(
            '/api/leads/bulk-assign/',
            {
                'lead_ids': [self.leads[0].id, self.leads[1].id, self.leads[2].id],
                'assigned_to_id': self.staff_a.id,
                'batch_label': 'Initial Lot',
            },
            format='json',
        )
        batch1_id = res1.data['assignment_batch']['id']

        # Reassign lead[0] to staff_b via single assign
        single_res = self.client.post(
            '/api/leads/assign/',
            {
                'lead_id': self.leads[0].id,
                'assigned_to_id': self.staff_b.id,
                'notes': 'Transferred out',
            },
            format='json',
        )
        self.assertEqual(single_res.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.staff_a)
        batches_res = self.client.get('/api/leads/assignment-batches/')
        batches = batches_res.data['results'] if 'results' in batches_res.data else batches_res.data
        b1 = next(b for b in batches if b['id'] == batch1_id)
        self.assertEqual(b1['total_assigned_count'], 3)
        self.assertEqual(b1['active_count'], 2)
        self.assertEqual(b1['reassigned_out_count'], 1)

        active_leads_res = self.client.get(f'/api/leads/assignment-batches/{batch1_id}/leads/')
        active_leads = active_leads_res.data['results'] if 'results' in active_leads_res.data else active_leads_res.data
        self.assertEqual(len(active_leads), 2)
        self.assertNotIn(self.leads[0].id, [l['id'] for l in active_leads])

        all_leads_res = self.client.get(f'/api/leads/assignment-batches/{batch1_id}/leads/?include_reassigned_out=true')
        all_leads = all_leads_res.data['results'] if 'results' in all_leads_res.data else all_leads_res.data
        self.assertEqual(len(all_leads), 3)
        moved_row = next(l for l in all_leads if l['id'] == self.leads[0].id)
        self.assertTrue(moved_row['is_reassigned_out'])

    def test_rbac_isolation_for_batches(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            '/api/leads/bulk-assign/',
            {
                'lead_ids': [self.leads[0].id],
                'assigned_to_id': self.staff_a.id,
                'batch_label': 'Private to Anjali',
            },
            format='json',
        )
        batch_id = res.data['assignment_batch']['id']

        # Staff B cannot see Staff A's batch or its leads
        self.client.force_authenticate(user=self.staff_b)
        list_b = self.client.get('/api/leads/assignment-batches/')
        batches_b = list_b.data['results'] if 'results' in list_b.data else list_b.data
        self.assertFalse(any(b['id'] == batch_id for b in batches_b))

        detail_b = self.client.get(f'/api/leads/assignment-batches/{batch_id}/leads/')
        self.assertIn(detail_b.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

        # Cross-company manager without staff:access_flag cannot see LP batches
        self.client.force_authenticate(user=self.flag_admin)
        list_flag = self.client.get('/api/leads/assignment-batches/')
        batches_flag = list_flag.data['results'] if 'results' in list_flag.data else list_flag.data
        self.assertEqual(len(batches_flag), 0)
