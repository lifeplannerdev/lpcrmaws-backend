import os
import django
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lpcrm.settings")
django.setup()

from students.models import Grade, Campus, AcademicPackage, AcademicBatch, GradeBatch, Student, StudentBatchHistory
from django.contrib.auth import get_user_model

User = get_user_model()

def run_test():
    # Setup data
    user, _ = User.objects.get_or_create(username='admin', is_superuser=True)
    
    grade_a1, _ = Grade.objects.get_or_create(code='A1', defaults={'name': 'A1', 'order': 1})
    grade_a2, _ = Grade.objects.get_or_create(code='A2', defaults={'name': 'A2', 'order': 2})
    
    campus, _ = Campus.objects.get_or_create(code='C1', defaults={'name': 'Main Campus'})
    
    package, _ = AcademicPackage.objects.get_or_create(name='P1', starting_grade=grade_a1, ending_grade=grade_a2)
    
    batch, _ = AcademicBatch.objects.get_or_create(name='B1', campus=campus, package=package)
    batch2, _ = AcademicBatch.objects.get_or_create(name='B2', campus=campus, package=package)
    
    gb_a1, _ = GradeBatch.objects.get_or_create(academic_batch=batch, grade=grade_a1)
    gb_a2, _ = GradeBatch.objects.get_or_create(academic_batch=batch, grade=grade_a2)
    
    gb2_a2, _ = GradeBatch.objects.get_or_create(academic_batch=batch2, grade=grade_a2)
    
    # Create student
    student, _ = Student.objects.get_or_create(
        name='Test Student',
        campus=campus,
        academic_package=package,
        batch=batch,
        grade_batch=gb_a1,
    )
    
    # create history record
    StudentBatchHistory.objects.filter(student=student).delete()
    StudentBatchHistory.objects.create(
        student=student,
        batch=batch,
        grade_batch=gb_a1,
        action='enrolled',
        from_date=timezone.now().date()
    )

    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=user)

    # Test promote
    res = client.post(f'/api/students/students/{student.id}/promote/')
    print("Promote Response:", res.status_code, res.json())
    assert res.status_code == 200, "Promote failed"

    student.refresh_from_db()
    assert student.grade_batch == gb_a2, "Student not promoted"

    hist = StudentBatchHistory.objects.filter(student=student).order_by('-created_at')
    assert hist.count() == 2, f"Expected 2 history records, got {hist.count()}"
    
    # Verify the previous record was closed
    enrolled_hist = hist.last()
    assert enrolled_hist.to_date == timezone.now().date(), "Previous history not closed correctly"
    
    # Verify the new record
    promoted_hist = hist.first()
    print("Promoted hist action:", promoted_hist.action)
    for h in hist:
        print("Hist:", h.action, h.from_date, h.to_date)
    assert promoted_hist.action == 'promoted'
    assert promoted_hist.to_date is None

    # Test demote
    res = client.post(f'/api/students/students/{student.id}/demote/', {
        'academic_batch_id': batch2.id,
        'grade_batch_id': gb2_a2.id,
        'reason': 'Testing demote'
    }, format='json')
    print("Demote Response:", res.status_code, res.json())
    assert res.status_code == 200, "Demote failed"

    student.refresh_from_db()
    assert student.batch == batch2
    assert student.grade_batch == gb2_a2
    
    hist = StudentBatchHistory.objects.filter(student=student).order_by('-created_at')
    assert hist.count() == 3, f"Expected 3 history records, got {hist.count()}"
    
    # Verify the previous record was closed
    prev_promoted_hist = hist[1]
    assert prev_promoted_hist.to_date == timezone.now().date(), "Promoted history not closed correctly"

    # Verify the new demote record
    demoted_hist = hist.first()
    assert demoted_hist.action == 'demoted'
    assert demoted_hist.to_date is None

    print("All tests passed!")

if __name__ == '__main__':
    run_test()
