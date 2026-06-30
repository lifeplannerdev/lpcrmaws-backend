import os

file_path = "b:/lp alternative/lpcrmbackend-main/trainers/views.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_logic = """        serializer = AttendanceSerializer(data=request.data)
        if serializer.is_valid():
            approval_status = 'APPROVED'
            try:
                if student.fee_attendance_policy == 'STRICT' and student.fee_account and student.fee_account.is_overdue:
                    approval_status = 'PENDING_FEE_APPROVAL'
            except Exception:
                pass

            serializer.save(trainer=trainer, approval_status=approval_status)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)"""

new_logic = """        from fees.models import FeePolicy
        policy = FeePolicy.objects.filter(company=trainer.company).first()
        
        has_fee_account = hasattr(student, 'fee_account') and student.fee_account is not None
        
        if policy and policy.block_without_fee_account and not has_fee_account:
            return Response(
                {"detail": "Attendance blocked: Student has no fee structure assigned."},
                status=403
            )

        serializer = AttendanceSerializer(data=request.data)
        if serializer.is_valid():
            approval_status = 'APPROVED'
            
            if policy and policy.pending_if_overdue:
                # If marked PRESENT, check for overdue fees
                if serializer.validated_data.get('status', 'PRESENT') == 'PRESENT':
                    if has_fee_account and getattr(student.fee_account, 'is_overdue', False):
                        approval_status = 'PENDING_FEE_APPROVAL'

            serializer.save(trainer=trainer, approval_status=approval_status)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)"""

content = content.replace(old_logic, new_logic)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched trainers/views.py")
