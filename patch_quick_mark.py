import os

file_path = "b:/lp alternative/lpcrmbackend-main/trainers/views.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_logic_outer = """        saved = []
        errors = []

        for r in records:"""

new_logic_outer = """        saved = []
        errors = []
        
        from fees.models import FeePolicy
        company = getattr(request.user, 'company', 'LP')
        policy = FeePolicy.objects.filter(company=company).first()

        for r in records:"""

content = content.replace(old_logic_outer, new_logic_outer)

old_logic_inner = """                approval_status = 'APPROVED'
                try:
                    if student.fee_attendance_policy == 'STRICT' and student.fee_account and student.fee_account.is_overdue:
                        approval_status = 'PENDING_FEE_APPROVAL'
                except Exception:
                    pass"""

new_logic_inner = """                has_fee_account = hasattr(student, 'fee_account') and student.fee_account is not None
                
                if policy and policy.block_without_fee_account and not has_fee_account:
                    errors.append({
                        'student_id': r.get('student'),
                        'error': 'Attendance blocked: Student has no fee structure assigned.'
                    })
                    continue

                approval_status = 'APPROVED'
                if policy and policy.pending_if_overdue:
                    if r.get('status', 'PRESENT') == 'PRESENT':
                        if has_fee_account and getattr(student.fee_account, 'is_overdue', False):
                            approval_status = 'PENDING_FEE_APPROVAL'"""

content = content.replace(old_logic_inner, new_logic_inner)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched QuickMarkAttendanceAPIView in trainers/views.py")
