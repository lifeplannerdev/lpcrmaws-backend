from trainers.models import Student
s = Student.objects.filter(name__icontains='AKASH S NAIR').first()
if s and hasattr(s, 'fee_account'):
    print('Status:', s.fee_account.status)
    print('Overdue Amount:', s.fee_account.overdue_amount)
    print('Is Overdue:', s.fee_account.is_overdue)
else:
    print('Student or fee account not found')
