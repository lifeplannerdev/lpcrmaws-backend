import os
import django
import json
from django.core.serializers.json import DjangoJSONEncoder

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from students.models import (Student, Grade, Campus, AcademicPackage, AttendancePolicy, 
                             AcademicBatch, AttendanceSession, AttendanceRecord, 
                             StudentBatchHistory, GradeExamRecord, PromotionEvent, DemotionEvent)
from fees.models import StudentFeeAccount, FeeInstallment, FeePayment, FeeAdjustment
from django.forms.models import model_to_dict

def dump_data():
    data = {}
    
    # 1. Students (FLAG company)
    students = Student.objects.filter(company='FLAG')
    data['students'] = list(students.values())
    student_ids = [s['id'] for s in data['students']]
    
    # 2. Batches related to FLAG students + other metadata
    batches = AcademicBatch.objects.all()
    data['academic_batches'] = list(batches.values())
    
    data['grades'] = list(Grade.objects.all().values())
    data['campuses'] = list(Campus.objects.all().values())
    data['academic_packages'] = list(AcademicPackage.objects.all().values())
    data['attendance_policies'] = list(AttendancePolicy.objects.all().values())
    
    # 3. Attendance
    sessions = AttendanceSession.objects.filter(batch__in=[b['id'] for b in data['academic_batches']])
    data['attendance_sessions'] = list(sessions.values())
    
    attendance_records = AttendanceRecord.objects.filter(student_id__in=student_ids)
    data['attendance_records'] = list(attendance_records.values())
    
    # 4. History / Exams / Promotions / Demotions
    data['batch_history'] = list(StudentBatchHistory.objects.filter(student_id__in=student_ids).values())
    data['grade_exam_records'] = list(GradeExamRecord.objects.filter(student_id__in=student_ids).values())
    data['promotion_events'] = list(PromotionEvent.objects.filter(batch__in=[b['id'] for b in data['academic_batches']]).values())
    data['demotion_events'] = list(DemotionEvent.objects.filter(student_id__in=student_ids).values())
    
    # 5. Fees for FLAG students
    fee_accounts = StudentFeeAccount.objects.filter(company='FLAG')
    data['fee_accounts'] = list(fee_accounts.values())
    account_ids = [a['id'] for a in data['fee_accounts']]
    
    data['fee_installments'] = list(FeeInstallment.objects.filter(account_id__in=account_ids).values())
    data['fee_payments'] = list(FeePayment.objects.filter(account_id__in=account_ids).values())
    data['fee_adjustments'] = list(FeeAdjustment.objects.filter(account_id__in=account_ids).values())
    
    with open('flag_data_backup.json', 'w') as f:
        json.dump(data, f, cls=DjangoJSONEncoder, indent=2)
    print(f"Data exported successfully. Total FLAG students: {len(data['students'])}")

if __name__ == '__main__':
    dump_data()
