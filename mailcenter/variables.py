"""Template variable catalogue and rendering."""
import re
from decimal import Decimal

from django.utils import timezone
from django.utils.html import escape

VARIABLE_PATTERN = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# (key, label, example) - exposed to the UI so staff can insert variables with one click
VARIABLES = [
    ('student_name', 'Student full name', 'Anna George'),
    ('student_first_name', 'Student first name', 'Anna'),
    ('student_email', 'Student email', 'anna@example.com'),
    ('mobile_number', 'Mobile number', '+91 90000 00000'),
    ('whatsapp_number', 'WhatsApp number', '+91 90000 00000'),
    ('university', 'University', 'University of Bonn'),
    ('program', 'Program applied', 'MSc Computer Science'),
    ('intake', 'Intake', 'Winter 2026'),
    ('category', 'Student category', 'GCC Students'),
    ('registration_date', 'Registration date', '12 Jan 2026'),
    ('file_status', 'Student file status', 'Active'),
    ('registration_fee_status', 'Registration fee status', 'Paid with gst'),
    ('enrollment_status', 'Enrollment process status', 'Shared'),
    ('documents_status', 'Application documents status', 'Collected'),
    ('application_status', 'Application status', 'Submitted'),
    ('offer_letter_status', 'Offer letter status', 'Received'),
    ('visa_documentation', 'Visa documentation status', 'In Process'),
    ('visa_appointment_date', 'Visa appointment date', '20 Mar 2026'),
    ('visa_result', 'Visa result', 'Granted'),
    ('processing_fee_amount', 'Processing fee amount', '25000.00'),
    ('processing_fee_paid', 'Processing fee paid', '10000.00'),
    ('processing_fee_balance', 'Processing fee balance', '15000.00'),
    ('assigned_staff', 'Assigned staff member', 'Rahul K'),
    ('staff_name', 'Your name (sender)', 'Priya S'),
    ('staff_phone', 'Your phone', '+91 90000 00000'),
    ('today', "Today's date", '05 Oct 2026'),
]
VARIABLE_KEYS = {v[0] for v in VARIABLES}


def _fmt_date(value):
    if not value:
        return ''
    try:
        return value.strftime('%d %b %Y')
    except AttributeError:
        return str(value)


def _money(value):
    if value is None:
        return ''
    return f"{Decimal(value):.2f}"


def build_context(student, user=None):
    name = (student.name or '').strip()
    balance = None
    if student.processing_fee_amount is not None and student.processing_fee_paid is not None:
        balance = Decimal(student.processing_fee_amount) - Decimal(student.processing_fee_paid)

    staff_name = ''
    staff_phone = ''
    if user is not None and getattr(user, 'is_authenticated', False):
        staff_name = user.get_full_name() or user.username
        staff_phone = user.phone or user.office_phone or ''

    assigned = student.assigned_to.get_full_name() if student.assigned_to_id else ''

    return {
        'student_name': name,
        'student_first_name': name.split(' ')[0] if name else '',
        'student_email': student.email or '',
        'mobile_number': student.mobile_number or '',
        'whatsapp_number': student.whatsapp_number or '',
        'university': student.university or '',
        'program': student.program_applied or '',
        'intake': student.intake or '',
        'category': student.category or '',
        'registration_date': _fmt_date(student.date_of_registration),
        'file_status': student.student_file_status or '',
        'registration_fee_status': student.registration_fee_status or '',
        'enrollment_status': student.enrollment_process_status or '',
        'documents_status': student.application_documents_status or '',
        'application_status': student.application_status or '',
        'offer_letter_status': student.offer_letter_status or '',
        'visa_documentation': student.visa_documentation or '',
        'visa_appointment_date': student.visa_appointment_date or '',
        'visa_result': student.visa_results or '',
        'processing_fee_amount': _money(student.processing_fee_amount),
        'processing_fee_paid': _money(student.processing_fee_paid),
        'processing_fee_balance': _money(balance),
        'assigned_staff': assigned,
        'staff_name': staff_name,
        'staff_phone': staff_phone,
        'today': _fmt_date(timezone.localdate()),
    }


def render_string(text, context, html=False):
    """
    Replace {{variables}}. Returns (rendered, unknown_keys, empty_keys).
    Unknown variables are left in place so they are visible (and block sending).
    Values are HTML-escaped when rendering into an HTML body.
    """
    unknown, empty = [], []

    def _sub(match):
        key = match.group(1)
        if key not in context:
            if key not in unknown:
                unknown.append(key)
            return match.group(0)
        value = context[key]
        if value in (None, ''):
            if key not in empty:
                empty.append(key)
            return ''
        return escape(value) if html else str(value)

    return VARIABLE_PATTERN.sub(_sub, text or ''), unknown, empty


def find_placeholders(*texts):
    """Any leftover {{variable}} markers in the given strings."""
    found = []
    for text in texts:
        for key in VARIABLE_PATTERN.findall(text or ''):
            if key not in found:
                found.append(key)
    return found
