from trainers.models import Student
s = Student.objects.filter(name__icontains='AKASH S NAIR').first()
if s and hasattr(s, 'fee_account'):
    for inst in s.fee_account.installments.all():
        print(f"Inst {inst.sequence_number}: {inst.label} | Status: {inst.status} | Due: {inst.due_date} | Amt: {inst.scheduled_amount} | Bal: {inst.balance_amount}")
