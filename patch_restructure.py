import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_logic = """            installment_payloads = data.get('installments') or []
            if installment_payloads:
                account.installments.all().delete()
                for idx, item in enumerate(installment_payloads, start=1):
                    FeeInstallment.objects.create(
                        account=account,
                        sequence_number=idx,
                        label=item.get('label') or f'Installment {idx}',
                        due_date=item['due_date'],
                        scheduled_amount=item['scheduled_amount'],
                        paid_amount=Decimal('0'),
                        balance_amount=item['scheduled_amount'],
                        status='PENDING',
                        notes=item.get('notes', ''),
                    )"""

new_logic = """            installment_payloads = data.get('installments') or []
            if installment_payloads:
                account.installments.all().delete()
                for idx, item in enumerate(installment_payloads, start=1):
                    FeeInstallment.objects.create(
                        account=account,
                        sequence_number=idx,
                        label=item.get('label') or f'Installment {idx}',
                        due_date=item['due_date'],
                        scheduled_amount=item['scheduled_amount'],
                        paid_amount=Decimal('0'),
                        balance_amount=item['scheduled_amount'],
                        status='PENDING',
                        notes=item.get('notes', ''),
                    )
                
                from django.db.models import Sum
                total_paid = account.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
                remaining = total_paid
                
                for inst in account.installments.all().order_by('sequence_number'):
                    if remaining > 0:
                        if remaining >= inst.scheduled_amount:
                            inst.paid_amount = inst.scheduled_amount
                            inst.balance_amount = Decimal('0')
                            inst.status = 'PAID'
                            remaining -= inst.scheduled_amount
                        else:
                            inst.paid_amount = remaining
                            inst.balance_amount = inst.scheduled_amount - remaining
                            inst.status = 'PARTIAL'
                            remaining = Decimal('0')
                        inst.save(update_fields=['paid_amount', 'balance_amount', 'status'])"""

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fee Restructure API View successfully patched!")
else:
    print("Failed to find old logic to replace.")
