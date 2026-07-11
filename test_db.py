import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from fees.models import StudentFeeAccount

qs = StudentFeeAccount.objects.all()
print("Total StudentFeeAccount in DB:", qs.count())
for acc in qs:
    print(acc.id, acc.company, acc.student.name, acc.plan_name)
