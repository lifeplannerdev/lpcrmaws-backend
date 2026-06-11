import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from fees.models import FeePlanTemplate

def run():
    templates = [
        {
            'company': 'FLAG',
            'code': 'FLAG-A1B2-ONETIME',
            'name': 'A1-B2 Course Work - One time payment',
            'course_label': 'A1-B2',
            'plan_type': 'PACKAGE',
            'total_amount': 106200.00,
            'registration_amount': 0.00,
            'notes': 'Special offer - One time payment'
        },
        {
            'company': 'FLAG',
            'code': 'FLAG-A1B2-3INST',
            'name': 'A1-B2 Course Work - 3 Installments',
            'course_label': 'A1-B2',
            'plan_type': 'INSTALLMENT',
            'total_amount': 114000.00,
            'registration_amount': 0.00,
            'installment_count': 3,
            'installment_amount': 38000.00,
            'duration_months': 3,
            'due_day': 10,
            'notes': '38,000 x 3 installments (1st 3 months payment - before 10th of every month)'
        },
        {
            'company': 'FLAG',
            'code': 'FLAG-A1B2-MONTHLY',
            'name': 'A1-B2 Course Work - Monthly Installment',
            'course_label': 'A1-B2',
            'plan_type': 'MONTHLY',
            'total_amount': 115000.00, # 20000 + 10 * 9500
            'registration_amount': 20000.00,
            'monthly_amount': 9500.00,
            'duration_months': 11,
            'notes': 'On Registration - 20,000 Only & 2nd month - 11th month - 9500/ month (10 months)'
        },
        {
            'company': 'FLAG',
            'code': 'FLAG-A1-LEVEL',
            'name': 'A1 Level Fee',
            'course_label': 'A1',
            'plan_type': 'ONE_TIME',
            'total_amount': 21240.00,
            'registration_amount': 0.00,
            'notes': 'Level Based Fees'
        },
        {
            'company': 'FLAG',
            'code': 'FLAG-A2-LEVEL',
            'name': 'A2 Level Fee',
            'course_label': 'A2',
            'plan_type': 'ONE_TIME',
            'total_amount': 21240.00,
            'registration_amount': 0.00,
            'notes': 'Level Based Fees'
        },
        {
            'company': 'FLAG',
            'code': 'FLAG-B1-LEVEL',
            'name': 'B1 Level Fee',
            'course_label': 'B1',
            'plan_type': 'ONE_TIME',
            'total_amount': 29500.00,
            'registration_amount': 0.00,
            'notes': 'Level Based Fees'
        },
        {
            'company': 'FLAG',
            'code': 'FLAG-B2-LEVEL',
            'name': 'B2 Level Fee',
            'course_label': 'B2',
            'plan_type': 'ONE_TIME',
            'total_amount': 47200.00,
            'registration_amount': 0.00,
            'notes': 'Level Based Fees'
        }
    ]

    created_count = 0
    updated_count = 0

    for item in templates:
        obj, created = FeePlanTemplate.objects.update_or_create(
            code=item['code'],
            defaults=item
        )
        if created:
            created_count += 1
            print(f"Created template: {obj.name} (Code: {obj.code})")
        else:
            updated_count += 1
            print(f"Updated template: {obj.name} (Code: {obj.code})")

    print(f"\nDone! Created {created_count}, Updated {updated_count} fee templates.")

if __name__ == '__main__':
    run()
