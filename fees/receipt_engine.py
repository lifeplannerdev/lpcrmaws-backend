import hashlib
import hmac
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone


TWO_PLACES = Decimal('0.01')

DEFAULT_DISPLAY_OPTIONS = {
    'show_ledger_summary': True,
    'show_installment_schedule': False,
    'show_tax_breakdown': True,
    'show_bank_details': True,
    'show_signature_and_stamp': True,
    'show_qr_verification': True,
    'show_amount_in_words': True,
    'show_sac_column': True,
    'show_discount_line': True,
    'show_watermark': True,
    'show_student_academic_info': True,
    'show_terms': True,
}


def to_decimal(value, default=Decimal('0.00')) -> Decimal:
    if value is None or value == '':
        return default
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    try:
        cleaned = str(value).replace(',', '').replace('₹', '').strip()
        if not cleaned:
            return default
        return Decimal(cleaned).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return default


_ONES = [
    '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
    'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
    'Seventeen', 'Eighteen', 'Nineteen'
]

_TENS = [
    '', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'
]


def _two_digit_words(n: int) -> str:
    if n <= 0:
        return ''
    if n < 20:
        return _ONES[n]
    tens_word = _TENS[n // 10]
    ones_word = _ONES[n % 10]
    return f"{tens_word}-{ones_word}" if ones_word else tens_word


def _three_digit_words(n: int) -> str:
    if n <= 0:
        return ''
    hundreds = n // 100
    remainder = n % 100
    parts = []
    if hundreds > 0:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if remainder > 0:
        parts.append(_two_digit_words(remainder))
    return ' '.join(parts)


def _indian_integer_to_words(n: int) -> str:
    if n == 0:
        return 'Zero'
    if n < 0:
        return f"Minus {_indian_integer_to_words(abs(n))}"

    parts = []
    crores = n // 10_000_000
    remainder = n % 10_000_000

    if crores > 0:
        if crores >= 100:
            parts.append(f"{_indian_integer_to_words(crores)} Crore")
        else:
            parts.append(f"{_two_digit_words(crores)} Crore")

    lakhs = remainder // 100_000
    remainder = remainder % 100_000
    if lakhs > 0:
        parts.append(f"{_two_digit_words(lakhs)} Lakh")

    thousands = remainder // 1_000
    remainder = remainder % 1_000
    if thousands > 0:
        parts.append(f"{_two_digit_words(thousands)} Thousand")

    if remainder > 0:
        parts.append(_three_digit_words(remainder))

    return ' '.join(parts)


def amount_to_words(amount) -> str:
    """
    Convert a numeric amount to Indian Currency words.
    Examples:
      38000 -> "Rupees Thirty-Eight Thousand Only"
      106200 -> "Rupees One Lakh Six Thousand Two Hundred Only"
      1250.50 -> "Rupees One Thousand Two Hundred Fifty and Fifty Paise Only"
    """
    dec = to_decimal(amount, Decimal('0.00'))
    is_negative = dec < 0
    dec = abs(dec)

    rupees = int(dec)
    paise = int(((dec - Decimal(rupees)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if paise >= 100:
        rupees += 1
        paise -= 100

    prefix = "Minus " if is_negative else ""
    rupee_words = _indian_integer_to_words(rupees)

    if paise > 0:
        paise_words = _two_digit_words(paise)
        return f"{prefix}Rupees {rupee_words} and {paise_words} Paise Only"
    return f"{prefix}Rupees {rupee_words} Only"


def get_indian_financial_year(dt=None) -> str:
    """
    Return the Indian Financial Year string (April 1 to March 31), e.g., '2026-27'.
    """
    if dt is None:
        dt = timezone.localdate()
    else:
        if isinstance(dt, str):
            from django.utils.dateparse import parse_date, parse_datetime
            parsed_dt = parse_datetime(dt)
            if parsed_dt is not None:
                dt = parsed_dt
            else:
                parsed_d = parse_date(dt)
                dt = parsed_d if parsed_d is not None else timezone.localdate()
        if hasattr(dt, 'date'):
            if timezone.is_aware(dt):
                dt = timezone.localtime(dt).date()
            else:
                dt = dt.date()

    year = dt.year
    if dt.month >= 4:
        return f"{year}-{str(year + 1)[-2:]}"
    return f"{year - 1}-{str(year)[-2:]}"


def normalize_line_items(line_items, default_sac='999293', fallback_title='Course Tuition Fee', fallback_amount=Decimal('0.00'), fallback_period=''):
    """
    Validate and normalize itemized receipt rows.
    Guarantees each item has:
      title, description, sac_code, period, quantity, unit_price, discount, amount
    """
    normalized = []
    if isinstance(line_items, list) and len(line_items) > 0:
        for idx, raw in enumerate(line_items, start=1):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get('title') or raw.get('particulars') or f'Item #{idx}').strip()
            description = str(raw.get('description') or '').strip()
            sac_code = str(raw.get('sac_code') if raw.get('sac_code') is not None else default_sac).strip()
            period = str(raw.get('period') or raw.get('installment') or '').strip()

            qty = to_decimal(raw.get('quantity', 1), Decimal('1.00'))
            if qty <= 0:
                qty = Decimal('1.00')

            has_explicit_unit = raw.get('unit_price') not in (None, '')
            raw_amount = to_decimal(raw.get('amount'), Decimal('0.00'))
            unit_price = to_decimal(raw.get('unit_price'), raw_amount) if has_explicit_unit else raw_amount
            line_discount = max(Decimal('0.00'), to_decimal(raw.get('discount'), Decimal('0.00')))

            if has_explicit_unit:
                computed_amount = max(
                    Decimal('0.00'),
                    (qty * unit_price - line_discount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                )
            else:
                computed_amount = max(Decimal('0.00'), (raw_amount - line_discount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))

            normalized.append({
                'sl_no': idx,
                'title': title,
                'description': description,
                'sac_code': sac_code,
                'period': period,
                'quantity': str(qty),
                'unit_price': str(unit_price),
                'discount': str(line_discount),
                'amount': str(computed_amount),
            })

    if not normalized:
        amt = max(Decimal('0.00'), to_decimal(fallback_amount, Decimal('0.00')))
        normalized.append({
            'sl_no': 1,
            'title': fallback_title or 'Course Fee',
            'description': '',
            'sac_code': default_sac or '999293',
            'period': fallback_period or '',
            'quantity': '1.00',
            'unit_price': str(amt),
            'discount': '0.00',
            'amount': str(amt),
        })

    return normalized


def calculate_receipt_financials(
    *,
    line_items=None,
    subtotal_amount=None,
    discount_amount=Decimal('0.00'),
    tax_mode='NONE',
    supply_type='INTRA_STATE',
    gst_rate=Decimal('18.00'),
    cgst_rate=None,
    sgst_rate=None,
    igst_rate=None,
    default_sac='999293',
    fallback_title='Course Fee',
    fallback_period='',
):
    """
    Deterministic, ACID-grade financial & GST calculation engine.
    Supports:
      - NONE: No tax; total = max(0, subtotal - discount)
      - INCLUSIVE: Back-calculates base taxable amount and CGST/SGST or IGST from net inclusive total
                   with zero paisa drift (taxable + cgst + sgst == total).
      - EXCLUSIVE: Adds CGST/SGST or IGST on top of net taxable amount.
    """
    fallback_amt = to_decimal(subtotal_amount, Decimal('0.00'))
    items = normalize_line_items(
        line_items,
        default_sac=default_sac,
        fallback_title=fallback_title,
        fallback_amount=fallback_amt,
        fallback_period=fallback_period,
    )

    items_sum = sum((to_decimal(i['amount']) for i in items), Decimal('0.00'))
    if line_items and len(line_items) > 0:
        subtotal = items_sum
    elif subtotal_amount is not None and subtotal_amount != '':
        subtotal = max(Decimal('0.00'), to_decimal(subtotal_amount))
        items[0]['unit_price'] = str(subtotal)
        items[0]['amount'] = str(subtotal)
    else:
        subtotal = items_sum

    discount = max(Decimal('0.00'), to_decimal(discount_amount, Decimal('0.00')))
    if discount > subtotal:
        discount = subtotal

    net_after_discount = (subtotal - discount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    tax_mode = (tax_mode or 'NONE').upper()
    if tax_mode not in ('NONE', 'INCLUSIVE', 'EXCLUSIVE'):
        tax_mode = 'NONE'

    supply_type = (supply_type or 'INTRA_STATE').upper()
    if supply_type not in ('INTRA_STATE', 'INTER_STATE'):
        supply_type = 'INTRA_STATE'

    # Determine effective total GST rate (all rates clamped >= 0.00)
    if supply_type == 'INTER_STATE':
        raw_igst = to_decimal(igst_rate, to_decimal(gst_rate, Decimal('18.00')))
        effective_rate = max(Decimal('0.00'), raw_igst)
    else:
        if cgst_rate not in (None, '') or sgst_rate not in (None, ''):
            c_r = max(Decimal('0.00'), to_decimal(cgst_rate, Decimal('9.00')))
            s_r = max(Decimal('0.00'), to_decimal(sgst_rate, Decimal('9.00')))
            effective_rate = c_r + s_r
        else:
            effective_rate = max(Decimal('0.00'), to_decimal(gst_rate, Decimal('18.00')))

    if tax_mode == 'NONE' or effective_rate == Decimal('0.00'):
        taxable_amount = net_after_discount
        out_cgst_rate = Decimal('0.00')
        out_sgst_rate = Decimal('0.00')
        out_igst_rate = Decimal('0.00')
        out_cgst_amount = Decimal('0.00')
        out_sgst_amount = Decimal('0.00')
        out_igst_amount = Decimal('0.00')
        total_tax_amount = Decimal('0.00')
        total_amount = net_after_discount

    elif tax_mode == 'INCLUSIVE':
        total_amount = net_after_discount
        divisor = Decimal('1.00') + (effective_rate / Decimal('100.00'))
        taxable_amount = (total_amount / divisor).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total_tax_amount = (total_amount - taxable_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if supply_type == 'INTER_STATE':
            out_igst_rate = effective_rate
            out_igst_amount = total_tax_amount
            out_cgst_rate = Decimal('0.00')
            out_sgst_rate = Decimal('0.00')
            out_cgst_amount = Decimal('0.00')
            out_sgst_amount = Decimal('0.00')
        else:
            raw_c = to_decimal(cgst_rate, (effective_rate / Decimal('2')).quantize(TWO_PLACES))
            out_cgst_rate = min(effective_rate, max(Decimal('0.00'), raw_c))
            out_sgst_rate = max(Decimal('0.00'), (effective_rate - out_cgst_rate).quantize(TWO_PLACES))
            if effective_rate > 0:
                out_cgst_amount = (total_tax_amount * (out_cgst_rate / effective_rate)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                out_cgst_amount = Decimal('0.00')
            out_sgst_amount = (total_tax_amount - out_cgst_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            out_igst_rate = Decimal('0.00')
            out_igst_amount = Decimal('0.00')

    else:  # EXCLUSIVE
        taxable_amount = net_after_discount
        if supply_type == 'INTER_STATE':
            out_igst_rate = effective_rate
            out_igst_amount = (taxable_amount * out_igst_rate / Decimal('100.00')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            out_cgst_rate = Decimal('0.00')
            out_sgst_rate = Decimal('0.00')
            out_cgst_amount = Decimal('0.00')
            out_sgst_amount = Decimal('0.00')
            total_tax_amount = out_igst_amount
        else:
            raw_c = to_decimal(cgst_rate, (effective_rate / Decimal('2')).quantize(TWO_PLACES))
            out_cgst_rate = min(effective_rate, max(Decimal('0.00'), raw_c))
            out_sgst_rate = max(Decimal('0.00'), (effective_rate - out_cgst_rate).quantize(TWO_PLACES))
            out_cgst_amount = (taxable_amount * out_cgst_rate / Decimal('100.00')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            out_sgst_amount = (taxable_amount * out_sgst_rate / Decimal('100.00')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            out_igst_rate = Decimal('0.00')
            out_igst_amount = Decimal('0.00')
            total_tax_amount = (out_cgst_amount + out_sgst_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        total_amount = (taxable_amount + total_tax_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    words = amount_to_words(total_amount)

    return {
        'line_items': items,
        'subtotal_amount': subtotal,
        'discount_amount': discount,
        'taxable_amount': taxable_amount,
        'tax_mode': tax_mode,
        'supply_type': supply_type,
        'cgst_rate': out_cgst_rate,
        'cgst_amount': out_cgst_amount,
        'sgst_rate': out_sgst_rate,
        'sgst_amount': out_sgst_amount,
        'igst_rate': out_igst_rate,
        'igst_amount': out_igst_amount,
        'total_tax_amount': total_tax_amount,
        'total_amount': total_amount,
        'amount_in_words': words,
    }


def generate_verification_token() -> str:
    return uuid.uuid4().hex


def _normalize_issue_date_iso(dt) -> str:
    if not dt:
        return ''
    if isinstance(dt, str):
        from django.utils.dateparse import parse_date, parse_datetime
        parsed_dt = parse_datetime(dt)
        if parsed_dt is not None:
            dt = parsed_dt
        else:
            parsed_d = parse_date(dt)
            if parsed_d is not None:
                return parsed_d.isoformat()
            return dt[:10]
    if hasattr(dt, 'date'):
        if timezone.is_aware(dt):
            dt = timezone.localtime(dt).date()
        else:
            dt = dt.date()
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)[:10]


def compute_receipt_signature(
    receipt_or_number,
    total_amount=None,
    recipient_name: str = '',
    status: str = 'ISSUED',
    verification_token: str = '',
    *,
    document_type: str = 'RECEIPT',
    issue_date=None,
    subtotal_amount=None,
    discount_amount=Decimal('0.00'),
    total_tax_amount=Decimal('0.00'),
) -> str:
    if hasattr(receipt_or_number, 'receipt_number') or isinstance(receipt_or_number, dict):
        r = receipt_or_number
        get_val = (lambda k, d=None: r.get(k, d)) if isinstance(r, dict) else (lambda k, d=None: getattr(r, k, d))
        r_num = get_val('receipt_number', '')
        doc_type = get_val('document_type', 'RECEIPT')
        iss_date = get_val('issue_date', None)
        rec_name = get_val('recipient_name', '')
        sub_amt = get_val('subtotal_amount', Decimal('0.00'))
        disc_amt = get_val('discount_amount', Decimal('0.00'))
        tax_amt = get_val('total_tax_amount', Decimal('0.00'))
        tot_amt = get_val('total_amount', Decimal('0.00'))
        st = get_val('status', 'ISSUED')
        v_token = get_val('verification_token', '')
    else:
        r_num = receipt_or_number
        doc_type = document_type
        iss_date = issue_date
        rec_name = recipient_name
        sub_amt = subtotal_amount if subtotal_amount is not None else total_amount
        disc_amt = discount_amount
        tax_amt = total_tax_amount
        tot_amt = total_amount
        st = status
        v_token = verification_token

    issue_date_str = _normalize_issue_date_iso(iss_date)
    sub_dec = to_decimal(sub_amt, Decimal('0.00'))
    disc_dec = to_decimal(disc_amt, Decimal('0.00'))
    tax_dec = to_decimal(tax_amt, Decimal('0.00'))
    tot_dec = to_decimal(tot_amt, Decimal('0.00'))

    canonical = (
        f"{(r_num or '').strip()}|"
        f"{(doc_type or '').strip()}|"
        f"{issue_date_str}|"
        f"{(rec_name or '').strip()}|"
        f"{sub_dec:.2f}|"
        f"{disc_dec:.2f}|"
        f"{tax_dec:.2f}|"
        f"{tot_dec:.2f}|"
        f"{(st or '').strip()}|"
        f"{(v_token or '').strip()}"
    )
    secret = (getattr(settings, 'SECRET_KEY', None) or 'flag-receipt-default-secret').encode('utf-8')
    return hmac.new(secret, canonical.encode('utf-8'), hashlib.sha256).hexdigest()


def verify_receipt_signature(receipt) -> bool:
    if not receipt.signature_hash or not receipt.verification_token:
        return False
    expected = compute_receipt_signature(receipt)
    return hmac.compare_digest(receipt.signature_hash, expected)


def build_issuer_snapshot(settings_obj=None, company='FLAG') -> dict:
    if not settings_obj:
        return {
            'company': company,
            'organization_name': 'FLAG German Language Academy' if company == 'FLAG' else f'{company} Academy',
            'subtitle': 'Foreign Language Academy for Global Careers',
            'address': 'Kochi | Kottayam | Kerala, India',
            'phone': '+91 98460 00000',
            'email': 'accounts@flagacademy.in',
            'website': 'www.flagacademy.in',
            'gstin': '',
            'pan_number': '',
            'place_of_supply': 'Kerala (32)',
            'sac_code': '999293',
            'logo_url': '',
            'signature_image': '',
            'stamp_image': '',
            'watermark_text': 'FLAG GERMAN ACADEMY',
            'authorized_signatory_name': 'Authorized Signatory',
            'authorized_signatory_designation': 'Accounts & Finance Department',
            'bank_name': '',
            'account_name': '',
            'account_number': '',
            'ifsc_code': '',
            'upi_id': '',
            'footer_note': 'Thank you for choosing FLAG German Academy.',
            'brand_color': '#312e81',
        }

    return {
        'company': settings_obj.company,
        'campus_id': settings_obj.campus_id,
        'campus_name': settings_obj.campus.name if settings_obj.campus else '',
        'organization_name': settings_obj.organization_name,
        'subtitle': settings_obj.subtitle,
        'address': settings_obj.address,
        'phone': settings_obj.phone,
        'email': settings_obj.email,
        'website': settings_obj.website,
        'gstin': settings_obj.gstin,
        'pan_number': settings_obj.pan_number,
        'place_of_supply': settings_obj.place_of_supply,
        'sac_code': settings_obj.sac_code,
        'logo_url': settings_obj.logo_url,
        'signature_image': settings_obj.signature_image,
        'stamp_image': settings_obj.stamp_image,
        'watermark_text': settings_obj.watermark_text,
        'authorized_signatory_name': settings_obj.authorized_signatory_name,
        'authorized_signatory_designation': settings_obj.authorized_signatory_designation,
        'bank_name': settings_obj.bank_name,
        'account_name': settings_obj.account_name,
        'account_number': settings_obj.account_number,
        'ifsc_code': settings_obj.ifsc_code,
        'upi_id': settings_obj.upi_id,
        'footer_note': settings_obj.footer_note,
        'brand_color': settings_obj.brand_color,
    }


def extract_student_metadata(student) -> dict:
    if not student:
        return {}
    campus_name = ''
    if hasattr(student, 'campus') and student.campus:
        campus_name = student.campus.name
    elif hasattr(student, 'branch') and student.branch:
        campus_name = student.branch.name

    batch_name = ''
    mode_of_study = ''
    if hasattr(student, 'batch') and student.batch:
        batch_name = getattr(student.batch, 'name', '') or str(student.batch)
        if hasattr(student.batch, 'get_mode_display'):
            mode_of_study = student.batch.get_mode_display()
        elif hasattr(student.batch, 'mode'):
            mode_of_study = str(student.batch.mode).title()

    if not mode_of_study and hasattr(student, 'mode_of_study') and student.mode_of_study:
        mode_of_study = student.get_mode_of_study_display() if hasattr(student, 'get_mode_of_study_display') else str(student.mode_of_study)

    package_name = ''
    if hasattr(student, 'academic_package') and student.academic_package:
        package_name = student.academic_package.name

    grade_level = ''
    if hasattr(student, 'current_grade') and student.current_grade:
        grade_level = student.current_grade.code

    phone = getattr(student, 'phone', '') or getattr(student, 'mobile_number', '') or ''
    email = getattr(student, 'email', '') or ''
    parent_name = getattr(student, 'parent_name', '') or ''
    enrollment_code = f"FLAG-STU-{student.id:04d}"

    return {
        'recipient_name': student.name,
        'recipient_phone': phone,
        'recipient_email': email,
        'parent_or_sponsor_name': parent_name,
        'student_enrollment_code': enrollment_code,
        'course_or_package_name': package_name,
        'batch_name': batch_name,
        'campus_name': campus_name,
        'grade_level': grade_level,
        'mode_of_study': mode_of_study or 'Offline',
    }


def extract_account_ledger_snapshot(account, payment=None) -> dict:
    if not account:
        amt = to_decimal(getattr(payment, 'amount', Decimal('0.00'))) if payment else Decimal('0.00')
        return {
            'ledger_total_fee': amt,
            'ledger_discount': Decimal('0.00'),
            'ledger_previously_paid': Decimal('0.00'),
            'ledger_current_paid': amt,
            'ledger_total_paid': amt,
            'ledger_balance_due': Decimal('0.00'),
            'ledger_next_due_date': None,
            'installment_schedule_snapshot': [],
        }

    total_fee = to_decimal(account.total_due, Decimal('0.00'))
    adj_discount = account.adjustments.filter(
        adjustment_type__in=['DISCOUNT', 'CONCESSION', 'WAIVER']
    ).aggregate(s=Sum('amount_delta')).get('s') or Decimal('0.00')
    adj_discount = abs(to_decimal(adj_discount, Decimal('0.00')))
    attr_discount = abs(to_decimal(getattr(account, 'discount', Decimal('0.00')), Decimal('0.00')))
    discount = max(adj_discount, attr_discount)

    if payment is not None:
        curr_paid = to_decimal(getattr(payment, 'amount', Decimal('0.00')), Decimal('0.00'))
        if getattr(payment, 'pk', None):
            db_prev_paid = account.payments.filter(
                Q(payment_date__lt=payment.payment_date) |
                Q(payment_date=payment.payment_date, pk__lt=payment.pk)
            ).aggregate(s=Sum('amount')).get('s') or Decimal('0.00')
            db_prev_paid = max(Decimal('0.00'), to_decimal(db_prev_paid, Decimal('0.00')))
            db_tot_paid = db_prev_paid + curr_paid
            acc_tot_paid = to_decimal(account.total_paid, Decimal('0.00'))
            has_later_payment = account.payments.filter(
                Q(payment_date__gt=payment.payment_date) |
                Q(payment_date=payment.payment_date, pk__gt=payment.pk)
            ).exists()
            if not has_later_payment and acc_tot_paid > db_tot_paid:
                tot_paid = acc_tot_paid
                prev_paid = max(Decimal('0.00'), tot_paid - curr_paid)
            else:
                prev_paid = db_prev_paid
                tot_paid = db_tot_paid
        else:
            tot_paid = to_decimal(account.total_paid, Decimal('0.00'))
            prev_paid = max(Decimal('0.00'), tot_paid - curr_paid)
        bal_due = max(Decimal('0.00'), total_fee - discount - tot_paid)
    else:
        prev_paid = to_decimal(account.total_paid, Decimal('0.00'))
        curr_paid = Decimal('0.00')
        tot_paid = prev_paid
        bal_due = max(Decimal('0.00'), total_fee - discount - tot_paid)

    schedule = []
    for inst in account.installments.all().order_by('sequence_number'):
        schedule.append({
            'sequence_number': inst.sequence_number,
            'label': inst.label or f"Installment #{inst.sequence_number}",
            'due_date': inst.due_date.isoformat() if inst.due_date else '',
            'scheduled_amount': str(to_decimal(inst.scheduled_amount)),
            'paid_amount': str(to_decimal(inst.paid_amount)),
            'balance_amount': str(to_decimal(inst.balance_amount)),
            'status': inst.status,
        })

    return {
        'ledger_total_fee': total_fee,
        'ledger_discount': discount,
        'ledger_previously_paid': prev_paid,
        'ledger_current_paid': curr_paid,
        'ledger_total_paid': tot_paid,
        'ledger_balance_due': bal_due,
        'ledger_next_due_date': account.next_due_date,
        'installment_schedule_snapshot': schedule,
    }


def get_or_create_receipt_settings(company='FLAG', campus=None):
    from django.db import IntegrityError, transaction
    from .models import ReceiptSettings

    company = (company or 'FLAG').upper()
    if campus is not None:
        settings_obj = ReceiptSettings.objects.filter(company=company, campus=campus).first()
        if settings_obj:
            return settings_obj
    settings_obj = ReceiptSettings.objects.filter(company=company, campus__isnull=True).first()
    if not settings_obj:
        org_name = 'FLAG German Language Academy' if company == 'FLAG' else f'{company} Academy'
        try:
            with transaction.atomic():
                settings_obj = ReceiptSettings.objects.create(
                    company=company,
                    campus=None,
                    organization_name=org_name,
                    receipt_prefix=company,
                    default_display_options=dict(DEFAULT_DISPLAY_OPTIONS),
                )
        except IntegrityError:
            settings_obj = (
                ReceiptSettings.objects.filter(company=company, campus__isnull=True).first()
                or ReceiptSettings.objects.first()
            )
    return settings_obj


def allocate_receipt_number(company='FLAG', campus=None, issue_date=None):
    """
    Atomically allocate the next sequential Financial Year receipt number
    (e.g., FLAG/2026-27/0001) using row-level locking on ReceiptSettings,
    tracking and resetting sequences per Financial Year (fy).
    """
    from django.db import IntegrityError, transaction
    from django.db.models import Max
    from .models import FeeReceipt, ReceiptSettings

    if hasattr(company, 'year') or (isinstance(company, str) and len(company) >= 8 and company[:4].isdigit()):
        issue_date = company
        company = 'FLAG'

    company = (company or 'FLAG').upper()
    fy = get_indian_financial_year(issue_date or timezone.now())

    with transaction.atomic():
        locked = None
        if campus is not None:
            locked = ReceiptSettings.objects.select_for_update().filter(company=company, campus=campus).first()
        if not locked:
            locked = ReceiptSettings.objects.select_for_update().filter(company=company, campus__isnull=True).first()
        if not locked:
            org_name = 'FLAG German Language Academy' if company == 'FLAG' else f'{company} Academy'
            try:
                with transaction.atomic():
                    created = ReceiptSettings.objects.create(
                        company=company,
                        campus=None,
                        organization_name=org_name,
                        receipt_prefix=company,
                        default_display_options=dict(DEFAULT_DISPLAY_OPTIONS),
                    )
                locked = ReceiptSettings.objects.select_for_update().get(pk=created.pk)
            except IntegrityError:
                locked = ReceiptSettings.objects.select_for_update().filter(company=company, campus__isnull=True).first()
                if not locked:
                    locked = ReceiptSettings.objects.select_for_update().get(id=1)

        raw_prefix = (locked.receipt_prefix or company).strip().rstrip('/')

        # Avoid duplicating FY if the user already included it in receipt_prefix
        if fy in raw_prefix:
            prefix_with_fy = raw_prefix
        else:
            prefix_with_fy = f"{raw_prefix}/{fy}"

        opts = dict(locked.default_display_options or {})
        fy_sequences = dict(opts.get('fy_sequences') or {})
        active_fy = opts.get('active_fy')

        db_max_seq = (
            FeeReceipt.objects.filter(
                Q(company=company, financial_year=fy) | Q(receipt_number__startswith=f"{prefix_with_fy}/")
            ).aggregate(m=Max('sequence_number')).get('m') or 0
        )
        parsed_max_seq = 0
        prefix_len = len(prefix_with_fy) + 1
        for r_num in FeeReceipt.objects.filter(receipt_number__startswith=f"{prefix_with_fy}/").values_list('receipt_number', flat=True):
            suffix = (r_num or '')[prefix_len:].strip()
            if suffix.isdigit():
                parsed_max_seq = max(parsed_max_seq, int(suffix))
        max_existing_seq = max(db_max_seq, parsed_max_seq)

        if fy in fy_sequences:
            tracked_seq = max(1, int(fy_sequences[fy]))
            if active_fy == fy and (locked.next_sequence_number or 1) > tracked_seq:
                seq = max(locked.next_sequence_number or 1, max_existing_seq + 1)
            else:
                seq = max(tracked_seq, max_existing_seq + 1)
        else:
            has_other_fy_receipts = (
                bool(fy_sequences)
                or (active_fy is not None and active_fy != fy)
                or FeeReceipt.objects.filter(company=company).exclude(financial_year=fy).exists()
            )
            if has_other_fy_receipts:
                seq = max(1, max_existing_seq + 1)
            else:
                seq = max(1, locked.next_sequence_number or 1, max_existing_seq + 1)

        while True:
            candidate = f"{prefix_with_fy}/{seq:04d}"
            if not FeeReceipt.objects.filter(receipt_number=candidate).exists():
                break
            seq += 1

        fy_sequences[fy] = seq + 1
        opts['fy_sequences'] = fy_sequences
        opts['active_fy'] = fy
        locked.default_display_options = opts
        locked.next_sequence_number = seq + 1
        locked.save(update_fields=['next_sequence_number', 'default_display_options', 'updated_at'])
        return candidate, fy, seq, locked

