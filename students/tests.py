from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from students.models import AcademicBatch, AcademicPackage, Campus, Grade, Student, StudentBatchHistory

User = get_user_model()


class StudentBatchEndDateSerializerTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='flag_admin_test',
            password='pass12345',
            company='FLAG',
            permissions=['flag:admin'],
        )
        self.campus = Campus.objects.create(name='FLAG Kochi', code='FLG-KOC-T', city='Kochi')
        self.grade_a1, _ = Grade.objects.get_or_create(code='A1', defaults={'name': 'A1', 'order': 1})
        self.package = AcademicPackage.objects.create(
            name='A1 Package',
            starting_grade=self.grade_a1,
            ending_grade=self.grade_a1,
        )
        self.batch = AcademicBatch.objects.create(
            name='CHN 1',
            campus=self.campus,
            package=self.package,
            start_date=date(2026, 4, 22),
            end_date=date(2026, 12, 15),
        )
        self.student = Student.objects.create(
            name='Abhiya Kuriakose',
            phone='9447104279',
            campus=self.campus,
            academic_package=self.package,
            batch=self.batch,
            joined_date=date(2026, 4, 22),
        )

    def test_student_and_batch_endpoints_include_end_date(self):
        self.client.force_authenticate(user=self.admin)

        batch_res = self.client.get('/api/students/batches/')
        self.assertEqual(batch_res.status_code, status.HTTP_200_OK)
        batches = batch_res.data['results'] if 'results' in batch_res.data else batch_res.data
        self.assertEqual(batches[0]['end_date'], '2026-12-15')

        stu_list_res = self.client.get('/api/students/students/')
        self.assertEqual(stu_list_res.status_code, status.HTTP_200_OK)
        students = stu_list_res.data['results'] if 'results' in stu_list_res.data else stu_list_res.data
        self.assertEqual(students[0]['batch_end_date'], '2026-12-15')
        self.assertIsNone(students[0]['end_date'])
        self.assertEqual(students[0]['effective_end_date'], '2026-12-15')

        stu_detail_res = self.client.get(f'/api/students/students/{self.student.id}/')
        self.assertEqual(stu_detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stu_detail_res.data['batch_end_date'], '2026-12-15')
        self.assertIsNone(stu_detail_res.data['end_date'])
        self.assertEqual(stu_detail_res.data['effective_end_date'], '2026-12-15')

    def test_per_student_end_date_overrides_effective_end_date_and_clears_back_to_batch(self):
        self.client.force_authenticate(user=self.admin)

        patch_res = self.client.patch(
            f'/api/students/students/{self.student.id}/',
            {'end_date': '2026-11-30'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['end_date'], '2026-11-30')
        self.assertEqual(patch_res.data['batch_end_date'], '2026-12-15')
        self.assertEqual(patch_res.data['effective_end_date'], '2026-11-30')

        clear_res = self.client.patch(
            f'/api/students/students/{self.student.id}/',
            {'end_date': None},
            format='json',
        )
        self.assertEqual(clear_res.status_code, status.HTTP_200_OK)
        self.assertIsNone(clear_res.data['end_date'])
        self.assertEqual(clear_res.data['effective_end_date'], '2026-12-15')

    def test_marking_exited_requires_end_date(self):
        self.client.force_authenticate(user=self.admin)

        patch_res = self.client.patch(
            f'/api/students/students/{self.student.id}/',
            {'status': 'exited'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_date', patch_res.data)

        create_res = self.client.post(
            '/api/students/students/',
            {
                'name': 'Exited Student',
                'campus': self.campus.id,
                'academic_package': self.package.id,
                'status': 'exited',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_date', create_res.data)

    def test_marking_exited_with_end_date_persists_and_logs_history(self):
        self.client.force_authenticate(user=self.admin)
        StudentBatchHistory.objects.create(
            student=self.student,
            batch=self.batch,
            action='enrolled',
            from_date=date(2026, 4, 22),
        )

        patch_res = self.client.patch(
            f'/api/students/students/{self.student.id}/',
            {'status': 'exited', 'end_date': '2026-11-20'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['status'], 'exited')
        self.assertEqual(patch_res.data['end_date'], '2026-11-20')

        enrolled_hist = StudentBatchHistory.objects.get(student=self.student, action='enrolled')
        self.assertEqual(enrolled_hist.to_date, date(2026, 11, 20))

        exited_hist = StudentBatchHistory.objects.get(student=self.student, action='exited')
        self.assertEqual(exited_hist.from_date, date(2026, 11, 20))
        self.assertEqual(exited_hist.to_date, date(2026, 11, 20))

    def test_marking_unassigned_student_exited_with_end_date_succeeds(self):
        self.client.force_authenticate(user=self.admin)
        unassigned = Student.objects.create(
            name='Unassigned Student',
            campus=self.campus,
            academic_package=self.package,
            batch=None,
            joined_date=date(2026, 6, 8),
        )

        patch_res = self.client.patch(
            f'/api/students/students/{unassigned.id}/',
            {'status': 'exited', 'end_date': '2026-11-20'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['status'], 'exited')
        self.assertEqual(patch_res.data['end_date'], '2026-11-20')

    def test_unrelated_patch_on_legacy_exited_student_without_end_date_succeeds(self):
        self.client.force_authenticate(user=self.admin)
        legacy = Student.objects.create(
            name='Legacy Exited',
            campus=self.campus,
            academic_package=self.package,
            status='exited',
            end_date=None,
        )

        patch_res = self.client.patch(
            f'/api/students/students/{legacy.id}/',
            {'phone': '9999999999'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['phone'], '9999999999')
