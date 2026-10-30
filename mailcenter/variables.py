"""Template variable catalogue and rendering across Students, Staff, Tasks, Penalties, Reports, and Leads."""
import re
from decimal import Decimal

from django.utils import timezone
from django.utils.html import escape

VARIABLE_PATTERN = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')

# (key, label, example, group) - exposed to the UI so staff/MD can insert variables with one click
VARIABLES_WITH_GROUP = [
    # Student / Admissions
    ('student_name', 'Student full name', 'Anna George', 'Student & Admissions'),
    ('student_first_name', 'Student first name', 'Anna', 'Student & Admissions'),
    ('student_email', 'Student email', 'anna@example.com', 'Student & Admissions'),
    ('mobile_number', 'Mobile number', '+91 90000 00000', 'Student & Admissions'),
    ('whatsapp_number', 'WhatsApp number', '+91 90000 00000', 'Student & Admissions'),
    ('university', 'University', 'University of Bonn', 'Student & Admissions'),
    ('program', 'Program applied', 'MSc Computer Science', 'Student & Admissions'),
    ('intake', 'Intake', 'Winter 2026', 'Student & Admissions'),
    ('category', 'Student category', 'GCC Students', 'Student & Admissions'),
    ('registration_date', 'Registration date', '12 Jan 2026', 'Student & Admissions'),
    ('file_status', 'Student file status', 'Active', 'Student & Admissions'),
    ('registration_fee_status', 'Registration fee status', 'Paid with gst', 'Student & Admissions'),
    ('enrollment_status', 'Enrollment process status', 'Shared', 'Student & Admissions'),
    ('documents_status', 'Application documents status', 'Collected', 'Student & Admissions'),
    ('application_status', 'Application status', 'Submitted', 'Student & Admissions'),
    ('offer_letter_status', 'Offer letter status', 'Received', 'Student & Admissions'),
    ('visa_documentation', 'Visa documentation status', 'In Process', 'Student & Admissions'),
    ('visa_appointment_date', 'Visa appointment date', '20 Mar 2026', 'Student & Admissions'),
    ('visa_result', 'Visa result', 'Granted', 'Student & Admissions'),
    ('processing_fee_amount', 'Processing fee amount', '25000.00', 'Student & Admissions'),
    ('processing_fee_paid', 'Processing fee paid', '10000.00', 'Student & Admissions'),
    ('processing_fee_balance', 'Processing fee balance', '15000.00', 'Student & Admissions'),
    ('assigned_staff', 'Assigned staff member', 'Rahul K', 'Student & Admissions'),

    # Staff & Executive
    ('employee_name', 'Employee / Advisor full name', 'Rahul Nair', 'Staff & Executive'),
    ('employee_email', 'Employee / Advisor email', 'rahul@lifeplanneruniversal.com', 'Staff & Executive'),
    ('employee_role', 'Employee role', 'ADM_COUNSELLOR', 'Staff & Executive'),
    ('advisor_name', 'Advisor full name', 'Rahul Nair', 'Staff & Executive'),

    # Tasks
    ('task_title', 'Task title', 'Q4 Admissions Audit', 'Tasks'),
    ('task_deadline', 'Task deadline', '30 Oct 2026', 'Tasks'),
    ('task_status', 'Task status', 'IN_PROGRESS', 'Tasks'),
    ('task_priority', 'Task priority', 'HIGH', 'Tasks'),

    # Penalties & HR
    ('penalty_act', 'Penalty reason / act', 'Late Report Submission', 'Penalties & HR'),
    ('penalty_amount', 'Penalty amount (INR)', '500', 'Penalties & HR'),
    ('penalty_date', 'Penalty date', '30 Oct 2026', 'Penalties & HR'),
    ('penalty_month', 'Penalty month', 'October 2026', 'Penalties & HR'),

    # Reports
    ('report_date', 'Daily report date', '30 Oct 2026', 'Reports'),
    ('report_status', 'Daily report status', 'Pending Review', 'Reports'),

    # Leads & Sales Analysis
    ('lead_name', 'Lead full name', 'Arjun Menon', 'Leads & Sales'),
    ('lead_phone', 'Lead phone number', '+91 98765 43210', 'Leads & Sales'),
    ('lead_email', 'Lead email address', 'arjun@example.com', 'Leads & Sales'),
    ('lead_status', 'Lead pipeline status', 'Hot', 'Leads & Sales'),
    ('lead_program', 'Lead interested program', 'German A1-B2', 'Leads & Sales'),
    ('lead_source', 'Lead source', 'Instagram', 'Leads & Sales'),

    # General / Sender
    ('staff_name', 'Your name (sender)', 'Managing Director', 'General'),
    ('staff_phone', 'Your phone', '+91 90000 00000', 'General'),
    ('today', "Today's date", '30 Oct 2026', 'General'),
]

VARIABLES = [(v[0], v[1], v[2]) for v in VARIABLES_WITH_GROUP]
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


def build_context(student=None, user=None, recipient_staff=None, lead=None, custom_variables=None):
    staff_name = ''
    staff_phone = ''
    if user is not None and getattr(user, 'is_authenticated', False):
        staff_name = user.get_full_name() or user.username
        staff_phone = user.phone or user.office_phone or ''

    ctx = {
        'staff_name': staff_name,
        'staff_phone': staff_phone,
        'today': _fmt_date(timezone.localdate()),
        'student_name': '',
        'student_first_name': '',
        'student_email': '',
        'mobile_number': '',
        'whatsapp_number': '',
        'university': '',
        'program': '',
        'intake': '',
        'category': '',
        'registration_date': '',
        'file_status': '',
        'registration_fee_status': '',
        'enrollment_status': '',
        'documents_status': '',
        'application_status': '',
        'offer_letter_status': '',
        'visa_documentation': '',
        'visa_appointment_date': '',
        'visa_result': '',
        'processing_fee_amount': '',
        'processing_fee_paid': '',
        'processing_fee_balance': '',
        'assigned_staff': '',
        'employee_name': '',
        'employee_email': '',
        'employee_role': '',
        'advisor_name': '',
        'task_title': '',
        'task_deadline': '',
        'task_status': '',
        'task_priority': '',
        'penalty_act': '',
        'penalty_amount': '',
        'penalty_date': '',
        'penalty_month': '',
        'report_date': '',
        'report_status': '',
        'lead_name': '',
        'lead_phone': '',
        'lead_email': '',
        'lead_status': '',
        'lead_program': '',
        'lead_source': '',
    }

    if student is not None:
        name = (student.name or '').strip()
        balance = None
        if student.processing_fee_amount is not None and student.processing_fee_paid is not None:
            balance = Decimal(student.processing_fee_amount) - Decimal(student.processing_fee_paid)
        assigned = student.assigned_to.get_full_name() if student.assigned_to_id else ''

        ctx.update({
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
        })

        if hasattr(student, 'dynamic_data') and student.dynamic_data:
            for k, v in student.dynamic_data.items():
                clean_k = re.sub(r'[^a-zA-Z0-9_]', '_', k.lower().strip())
                if clean_k not in ctx:
                    ctx[clean_k] = str(v) if v is not None else ''

    if recipient_staff is not None:
        emp_name = recipient_staff.get_full_name() or recipient_staff.username
        roles_str = ''
        if hasattr(recipient_staff, 'db_roles'):
            roles_str = ', '.join(recipient_staff.db_roles.values_list('name', flat=True))
        ctx.update({
            'employee_name': emp_name,
            'advisor_name': emp_name,
            'employee_email': recipient_staff.email or '',
            'employee_role': roles_str,
        })

    if lead is not None:
        lead_advisor = ''
        if getattr(lead, 'assigned_to', None):
            lead_advisor = lead.assigned_to.get_full_name() or lead.assigned_to.username
        ctx.update({
            'lead_name': lead.name or '',
            'lead_phone': lead.phone or '',
            'lead_email': lead.email or '',
            'lead_status': lead.status or '',
            'lead_program': lead.program or '',
            'lead_source': lead.source or '',
            'student_name': ctx['student_name'] or (lead.name or ''),
            'student_first_name': ctx['student_first_name'] or ((lead.name or '').split(' ')[0] if lead.name else ''),
            'student_email': ctx['student_email'] or (lead.email or ''),
            'mobile_number': ctx['mobile_number'] or (lead.phone or ''),
            'program': ctx['program'] or (lead.program or ''),
            'advisor_name': ctx['advisor_name'] or lead_advisor,
            'employee_name': ctx['employee_name'] or lead_advisor,
        })

    if custom_variables and isinstance(custom_variables, dict):
        for k, v in custom_variables.items():
            if v is not None:
                ctx[str(k)] = str(v)

    return ctx


def render_string(text, context, html=False):
    """
    Replace {{variables}}. Returns (rendered, unknown_keys, empty_keys).
    Unknown variables are left in place so they are visible.
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
