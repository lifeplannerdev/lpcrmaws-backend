import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

import re

# We will just replace the entire FeeAnalyticsOverviewAPIView class
# We'll use regex to find it and replace it.

pattern = r"class FeeAnalyticsOverviewAPIView\(APIView\):.*?class FeeStudent360APIView"
replacement = """class FeeAnalyticsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewAnalytics]

    def get(self, request):
        from decimal import Decimal
        company = request.GET.get('company')
        qs = StudentFeeAccount.objects.select_related('student', 'student__branch', 'student__academic_batch')
        if company:
            qs = qs.filter(company=company)
        
        branch_id = request.GET.get('branch')
        batch_id = request.GET.get('batch')
        if branch_id:
            qs = qs.filter(student__branch_id=branch_id)
        if batch_id:
            qs = qs.filter(student__academic_batch_id=batch_id)

        data = []
        for acc in qs:
            overdue = acc.overdue_amount or Decimal('0.00')
            t_due = acc.total_due or Decimal('0.00')
            t_paid = acc.total_paid or Decimal('0.00')
            
            branch_name = acc.student.branch.name if hasattr(acc.student, 'branch') and acc.student.branch else ''
            batch_name = acc.student.academic_batch.name if hasattr(acc.student, 'academic_batch') and acc.student.academic_batch else ''

            data.append({
                'id': acc.student_id,
                'student_name': acc.student.name,
                'branch_name': branch_name,
                'batch_name': batch_name,
                'plan_name': acc.plan_name or '',
                'total_due': t_due,
                'total_paid': t_paid,
                'overdue_amount': overdue,
                'status': acc.status or '',
                'is_on_track': overdue <= 0
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

class FeeStudent360APIView"""

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)
print("Safely patched FeeAnalyticsOverviewAPIView!")
