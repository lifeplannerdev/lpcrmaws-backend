from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from students.models import AcademicBatch, AcademicPackage, Campus, Grade, Student

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

        stu_detail_res = self.client.get(f'/api/students/students/{self.student.id}/')
        self.assertEqual(stu_detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stu_detail_res.data['batch_end_date'], '2026-12-15')
