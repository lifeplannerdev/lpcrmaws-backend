from fees.models import StudentFeeAccount
acc = StudentFeeAccount.objects.first()
print(f"Company: '{acc.company}'")
print(f"Count: {StudentFeeAccount.objects.count()}")
