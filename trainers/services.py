from decimal import Decimal
from django.db import transaction
from django.db.models import Sum


HEAD_TO_PREFIX = {
    'PROCESSING': 'processing_fee',
    'ADMISSION': 'fee_admission',
    'LANGUAGE': 'fee_language',
    'VISA': 'fee_visa',
    'MINISTRY': 'fee_ministry',
}


def recalculate_processing_student_fees(student):
    """
    Recalculates and synchronizes fee heads and statuses on a ProcessingStudent
    from their transactional ProcessingFeePayment history.

    Preserves historical opening balances for fee heads that have no payment rows.
    """
    from .models import ProcessingStudent, ProcessingFeePayment

    if isinstance(student, (int, str)):
        student = ProcessingStudent.objects.filter(pk=student).first()
    if not student:
        return None

    payments = ProcessingFeePayment.objects.filter(student=student)
    update_fields = []

    for head, prefix in HEAD_TO_PREFIX.items():
        head_payments = payments.filter(fee_head=head)
        if head_payments.exists():
            paid_sum = head_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            amount_due = getattr(student, f'{prefix}_amount', None) or Decimal('0.00')

            setattr(student, f'{prefix}_paid', paid_sum)
            update_fields.append(f'{prefix}_paid')

            if paid_sum >= amount_due and amount_due > 0:
                new_status = 'PAID'
            elif paid_sum > 0:
                new_status = 'PARTIAL'
            elif amount_due > 0:
                new_status = 'PENDING'
            else:
                new_status = getattr(student, f'{prefix}_status', 'PENDING') or 'PENDING'

            setattr(student, f'{prefix}_status', new_status)
            update_fields.append(f'{prefix}_status')

    # Handle REGISTRATION fee head payments
    reg_payments = payments.filter(fee_head='REGISTRATION')
    if reg_payments.exists():
        reg_paid = reg_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if reg_paid > 0 and getattr(student, 'registration_fee_status', 'Pending') == 'Pending':
            student.registration_fee_status = 'Paid with gst'
            update_fields.append('registration_fee_status')

    if update_fields:
        student.save(update_fields=list(set(update_fields)))

    return student
