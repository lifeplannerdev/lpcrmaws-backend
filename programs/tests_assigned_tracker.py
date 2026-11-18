from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import AppPermission, Role
from programs.models import (
    AssignedProgram,
    AssignedProgramChangeLog,
    AssignedStudentRecord,
    AssignedStudentChangeLog,
)

User = get_user_model()


class AssignedProgramsStudentsTrackerTests(APITestCase):
    def setUp(self):
        doc_role, _ = Role.objects.get_or_create(name='DOCUMENTATION')
        ops_role, _ = Role.objects.get_or_create(name='OPERATION')

        self.manager = User.objects.create_user(
            username='proc_manager',
            password='pass12345',
            first_name='Anju',
            last_name='Thomas',
            company='LP',
            permissions=['processing:prog_stud_manage'],
        )
        self.doc_user = User.objects.create_user(
            username='dona_doc',
            password='pass12345',
            first_name='Dona',
            last_name='Jose',
            company='LP',
            permissions=['processing:prog_stud_assigned'],
        )
        self.doc_user.db_roles.add(doc_role)

        self.ops_user = User.objects.create_user(
            username='navya_ops',
            password='pass12345',
            first_name='Navya',
            last_name='Rajgopal',
            company='LP',
            permissions=['processing:prog_stud_assigned'],
        )
        self.ops_user.db_roles.add(ops_role)

        self.other_user = User.objects.create_user(
            username='sales_user',
            password='pass12345',
            first_name='Sales',
            last_name='Rep',
            company='LP',
            permissions=['leads:read_own'],
        )

    def test_permissions_seeded_in_app_permission(self):
        self.assertTrue(AppPermission.objects.filter(name='processing:prog_stud_manage').exists())
        self.assertTrue(AppPermission.objects.filter(name='processing:prog_stud_assigned').exists())

    def test_unauthorized_user_cannot_access_endpoints(self):
        self.client.force_authenticate(user=self.other_user)
        self.assertEqual(self.client.get('/api/assigned-programs/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/assigned-students-db/').status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_crud_assign_and_assigned_user_sees_only_own_with_timeline_no_delete(self):
        self.client.force_authenticate(user=self.manager)

        # Manager creates 2 Assigned Programs: 1 for Dona (DOCUMENTATION), 1 for Navya (OPERATION)
        p1_res = self.client.post(
            '/api/assigned-programs/',
            {
                'sl_no': 1,
                'project': 'AUSBILDUNG',
                'country': 'GERMANY',
                'assignment': 'GIVEN',
                'completed': 'DONE',
                'presentation': '-',
                'training_to_team': 'Done by Navya',
                'assigned_to': self.doc_user.id,
            },
            format='json',
        )
        self.assertEqual(p1_res.status_code, status.HTTP_201_CREATED)
        p1_id = p1_res.data['id']

        p2_res = self.client.post(
            '/api/assigned-programs/',
            {
                'sl_no': 2,
                'project': 'ITALIAN PUBLIC UNIVERSITIES- FREE EDUCATION',
                'country': 'ITALY',
                'assignment': 'GIVEN',
                'completed': 'DONE',
                'presentation': 'DONE',
                'training_to_team': 'pending',
                'assigned_to': self.ops_user.id,
            },
            format='json',
        )
        self.assertEqual(p2_res.status_code, status.HTTP_201_CREATED)
        p2_id = p2_res.data['id']

        # Manager creates 2 Assigned Students
        s1_res = self.client.post(
            '/api/assigned-students-db/',
            {
                'sl_no': 1,
                'name': 'Joshua Shaji',
                'age': '21',
                'phone': '6282693592',
                'email_address': '',
                'place': '',
                'qualification': 'Bcom',
                'preferred_country': 'Ireland',
                'preferred_program': 'finance and accounting',
                'intake': '',
                'aps_status': '',
                'ielts_status': '',
                'german_status': '',
                'assigned_to': self.doc_user.id,
            },
            format='json',
        )
        self.assertEqual(s1_res.status_code, status.HTTP_201_CREATED)
        s1_id = s1_res.data['id']

        s2_res = self.client.post(
            '/api/assigned-students-db/',
            {
                'sl_no': 2,
                'name': 'jerry paul',
                'age': '24',
                'phone': '9539185565',
                'place': 'kottayam',
                'qualification': 'BTech in Artificial Intelligence',
                'preferred_country': 'Ireland',
                'preferred_program': 'AI',
                'assigned_to': self.ops_user.id,
            },
            format='json',
        )
        self.assertEqual(s2_res.status_code, status.HTTP_201_CREATED)
        s2_id = s2_res.data['id']

        # Dona (assigned) sees ONLY her own program & student
        self.client.force_authenticate(user=self.doc_user)
        dona_progs = self.client.get('/api/assigned-programs/').data
        prog_rows = dona_progs['results'] if 'results' in dona_progs else dona_progs
        self.assertEqual([r['id'] for r in prog_rows], [p1_id])

        dona_students = self.client.get('/api/assigned-students-db/').data
        stu_rows = dona_students['results'] if 'results' in dona_students else dona_students
        self.assertEqual([r['id'] for r in stu_rows], [s1_id])

        # Dona cannot view Navya's program or student timeline
        self.assertEqual(self.client.get(f'/api/assigned-programs/{p2_id}/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f'/api/assigned-students-db/{s2_id}/timeline/').status_code, status.HTTP_404_NOT_FOUND)

        # Dona cannot create, delete, bulk-assign, bulk-import, or reassign assigned_to
        self.assertEqual(
            self.client.post('/api/assigned-students-db/', {'name': 'Hack'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(f'/api/assigned-students-db/{s1_id}/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post('/api/assigned-students-db/bulk-assign/', {'ids': [s1_id], 'assigned_to': self.ops_user.id}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(
                f'/api/assigned-students-db/{s1_id}/',
                {'assigned_to': self.ops_user.id, 'aps_status': 'Submitted'},
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Dona CAN full-edit all data fields on her assigned student & program, and changes log to timeline
        patch_s1 = self.client.patch(
            f'/api/assigned-students-db/{s1_id}/',
            {'email_address': 'joshua@example.com', 'aps_status': 'Done', 'ielts_status': '6.5'},
            format='json',
        )
        self.assertEqual(patch_s1.status_code, status.HTTP_200_OK)

        # No-op PATCH should NOT create duplicate timeline entries
        self.client.patch(
            f'/api/assigned-students-db/{s1_id}/',
            {'aps_status': 'Done'},
            format='json',
        )

        tl_res = self.client.get(f'/api/assigned-students-db/{s1_id}/timeline/')
        self.assertEqual(tl_res.status_code, status.HTTP_200_OK)
        fields_logged = [entry['field_name'] for entry in tl_res.data]
        self.assertIn('aps_status', fields_logged)
        self.assertIn('ielts_status', fields_logged)
        self.assertIn('email_address', fields_logged)
        self.assertEqual(fields_logged.count('aps_status'), 1)

        # Program edit & timeline
        patch_p1 = self.client.patch(
            f'/api/assigned-programs/{p1_id}/',
            {'presentation': 'DONE'},
            format='json',
        )
        self.assertEqual(patch_p1.status_code, status.HTTP_200_OK)
        ptl_res = self.client.get(f'/api/assigned-programs/{p1_id}/timeline/')
        self.assertEqual(ptl_res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(e['field_name'] == 'presentation' and e['new_value'] == 'DONE' for e in ptl_res.data))

    def test_manager_bulk_import_and_bulk_assign_and_delete(self):
        self.client.force_authenticate(user=self.manager)
        imp_res = self.client.post(
            '/api/assigned-students-db/bulk-import/',
            {
                'default_assigned_to': self.doc_user.id,
                'rows': [
                    {
                        'sl_no': 1,
                        'name': 'Bulk Student 1',
                        'age': '22',
                        'phone': '9000011111',
                        'preferred_country': 'Germany',
                        'preferred_program': 'Ausbildung',
                    },
                    {
                        'sl_no': 2,
                        'name': 'Bulk Student 2',
                        'age': '23',
                        'phone': '9000022222',
                        'preferred_country': 'Poland',
                        'preferred_program': 'UITM',
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(imp_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(imp_res.data['created_count'], 2)

        created_ids = [r['id'] for r in imp_res.data['rows']]
        bulk_assign = self.client.post(
            '/api/assigned-students-db/bulk-assign/',
            {'ids': created_ids, 'assigned_to': self.ops_user.id},
            format='json',
        )
        self.assertEqual(bulk_assign.status_code, status.HTTP_200_OK)
        self.assertEqual(bulk_assign.data['updated_count'], 2)

        # Verify timeline recorded assignment change
        tl = self.client.get(f'/api/assigned-students-db/{created_ids[0]}/timeline/').data
        self.assertTrue(any(e['action'] == 'ASSIGNED' for e in tl))

        # Manager can delete
        del_res = self.client.delete(f'/api/assigned-students-db/{created_ids[0]}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

    def test_auto_sl_no_and_resequence_on_delete(self):
        self.client.force_authenticate(user=self.manager)
        created_ids = []
        for idx in range(5):
            res = self.client.post(
                '/api/assigned-students-db/',
                {'name': f'Student {idx + 1}'},
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            self.assertEqual(res.data['sl_no'], idx + 1)
            created_ids.append(res.data['id'])

        # Delete the 3rd row (sl_no=3)
        del_res = self.client.delete(f'/api/assigned-students-db/{created_ids[2]}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

        list_data = self.client.get('/api/assigned-students-db/').data
        remaining = list_data['results'] if isinstance(list_data, dict) else list_data
        self.assertEqual([r['sl_no'] for r in remaining], [1, 2, 3, 4])
        self.assertEqual([r['name'] for r in remaining], ['Student 1', 'Student 2', 'Student 4', 'Student 5'])
