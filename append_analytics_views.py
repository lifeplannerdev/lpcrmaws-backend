import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"

analytics_views = """
class CanViewAnalytics(BasePermission):
    def has_permission(self, request, view):
        return has_dynamic_permission(request.user, 'fees:analytics')

class FeeAnalyticsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewAnalytics]

    def get(self, request):
        company = request.GET.get('company') or 'LP'
        qs = StudentFeeAccount.objects.select_related('student', 'student__branch', 'student__academic_batch').filter(company=company)
        
        branch_id = request.GET.get('branch')
        batch_id = request.GET.get('batch')
        if branch_id:
            qs = qs.filter(student__branch_id=branch_id)
        if batch_id:
            qs = qs.filter(student__academic_batch_id=batch_id)

        data = []
        for acc in qs:
            data.append({
                'id': acc.student_id,
                'student_name': acc.student.name,
                'branch_name': acc.student.branch.name if acc.student.branch else '',
                'batch_name': acc.student.academic_batch.name if acc.student.academic_batch else '',
                'plan_name': acc.plan_name,
                'total_due': acc.total_due,
                'total_paid': acc.total_paid,
                'overdue_amount': acc.overdue_amount,
                'status': acc.status,
                'is_on_track': acc.overdue_amount <= 0
            })
            
        summary = {
            'total_students': len(data),
            'on_track': sum(1 for d in data if d['is_on_track']),
            'off_track': sum(1 for d in data if not d['is_on_track']),
            'total_overdue': sum(d['overdue_amount'] for d in data)
        }
        
        return Response({
            'summary': summary,
            'students': data
        })

class FeeStudent360APIView(APIView):
    permission_classes = [IsAuthenticated, CanViewAnalytics]

    def get(self, request, student_id):
        from students.models import Student
        from trainers.models import Attendance
        
        student = get_object_or_404(Student, id=student_id)
        account = StudentFeeAccount.objects.filter(student=student).first()
        
        attendance_qs = Attendance.objects.filter(student=student).order_by('-date')
        
        payload = {
            'student_info': {
                'id': student.id,
                'name': student.name,
                'email': student.email,
                'phone': student.phone,
                'branch': student.branch.name if student.branch else None,
                'batch': student.academic_batch.name if student.academic_batch else None,
            },
            'fee_account': None,
            'attendance_summary': {
                'total': attendance_qs.count(),
                'present': attendance_qs.filter(status='PRESENT').count(),
                'absent': attendance_qs.filter(status='ABSENT').count()
            },
            'recent_attendance': [
                {'date': a.date, 'status': a.status, 'approval_status': a.approval_status}
                for a in attendance_qs[:10]
            ]
        }
        
        if account:
            payload['fee_account'] = {
                'id': account.id,
                'plan_name': account.plan_name,
                'plan_type': account.plan_type,
                'status': account.status,
                'total_due': account.total_due,
                'total_paid': account.total_paid,
                'balance_due': account.balance_due,
                'overdue_amount': account.overdue_amount,
                'installments': [
                    {
                        'sequence': i.sequence_number,
                        'due_date': i.due_date,
                        'scheduled_amount': i.scheduled_amount,
                        'paid_amount': i.paid_amount,
                        'status': i.status
                    } for i in account.installments.all().order_by('sequence_number')
                ],
                'payments': [
                    {
                        'date': p.payment_date,
                        'amount': p.amount,
                        'method': p.payment_method,
                        'receipt': p.receipt_number
                    } for p in account.payments.all().order_by('-payment_date')
                ]
            }
            
        return Response(payload)
"""

with open(file_path, "a", encoding="utf-8") as f:
    f.write(analytics_views)

print("Appended analytics views to fees/views.py")
