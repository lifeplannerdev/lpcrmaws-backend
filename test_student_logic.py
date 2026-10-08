import os
import django
import sys

sys.path.append(r"B:\LP WORKSPACE\lp_crm\lpcrmbackend-main")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from students.models import Campus, Grade, AcademicPackage, AcademicBatch, GradeBatch, Student, ExamRecord
from accounts.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from students.views import StudentViewSet

def run():
    # Setup test data
    campus, _ = Campus.objects.get_or_create(code='TEST', defaults={'name': 'Test Campus'})
    g1, _ = Grade.objects.get_or_create(code='A1', defaults={'name': 'A1', 'order': 1})
    g2, _ = Grade.objects.get_or_create(code='A2', defaults={'name': 'A2', 'order': 2})
    pkg, _ = AcademicPackage.objects.get_or_create(name='Test Pkg', starting_grade=g1, ending_grade=g2)
    trainer, _ = User.objects.get_or_create(username='trainer', defaults={'is_active': True})
    
    batch, _ = AcademicBatch.objects.get_or_create(name='Test Batch', campus=campus, package=pkg, trainer=trainer)
    gb1, _ = GradeBatch.objects.get_or_create(academic_batch=batch, grade=g1)
    gb2, _ = GradeBatch.objects.get_or_create(academic_batch=batch, grade=g2)

    student, _ = Student.objects.get_or_create(
        name='Test Student', 
        defaults={'batch': batch, 'grade_batch': gb1}
    )
    student.batch = batch
    student.grade_batch = gb1
    student.save()
    student.batch = batch
    student.grade_batch = gb1
    student.save()
    
    # Assert inheritance
    assert student.campus == campus
    assert student.academic_package == pkg
    assert student.trainer == trainer

    factory = APIRequestFactory()
    view = StudentViewSet.as_view({'post': 'promote'})
    
    user, _ = User.objects.get_or_create(username='admin', is_superuser=True)
    
    # Test promote without passing exam -> should fail
    request = factory.post('/promote/')
    force_authenticate(request, user=user)
    response = view(request, pk=student.pk)
    assert response.status_code == 400
    assert 'must pass an exam' in response.data['error']
    print("Promote without exam correctly failed.")

    # Create failing exam
    ExamRecord.objects.create(student=student, grade_batch=gb1, exam_type='model', max_marks=100, achieved_marks=40, result='fail')
    
    # Test promote with failing exam -> should fail
    response = view(request, pk=student.pk)
    assert response.status_code == 400
    print("Promote with failing exam correctly failed.")

    # Create passing exam
    ExamRecord.objects.create(student=student, grade_batch=gb1, exam_type='grade', max_marks=100, achieved_marks=80, result='pass')
    
    # Test promote with passing exam -> should succeed
    response = view(request, pk=student.pk)
    assert response.status_code == 200
    print("Promote with passing exam succeeded:", response.data)
    
    student.refresh_from_db()
    assert student.grade_batch == gb2
    print("Student successfully promoted to:", student.grade_batch.grade.code)

    # Test demote without failing exam in gb2 -> should fail
    view_demote = StudentViewSet.as_view({'post': 'demote'})
    request = factory.post('/demote/', {'academic_batch_id': batch.id, 'grade_batch_id': gb1.id, 'reason': 'test'})
    force_authenticate(request, user=user)
    response = view_demote(request, pk=student.pk)
    assert response.status_code == 400
    assert 'must have a failed exam' in response.data['error']
    print("Demote without failed exam correctly failed.")
    
    # Create failing exam in gb2
    ExamRecord.objects.create(student=student, grade_batch=gb2, exam_type='model', max_marks=100, achieved_marks=30, result='fail')
    
    # Test demote with failing exam in gb2 -> should succeed
    response = view_demote(request, pk=student.pk)
    assert response.status_code == 200
    print("Demote with failing exam succeeded:", response.data)
    student.refresh_from_db()
    assert student.grade_batch == gb1
    print("Student successfully demoted to:", student.grade_batch.grade.code)
    print("All tests passed.")

if __name__ == '__main__':
    run()
