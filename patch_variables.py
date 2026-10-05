
import re

with open('mailcenter/variables.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''
    ctx = {
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
    
    if hasattr(student, 'dynamic_data') and student.dynamic_data:
        for k, v in student.dynamic_data.items():
            clean_k = re.sub(r'[^a-zA-Z0-9_]', '_', k.lower().strip())
            if clean_k not in ctx:
                ctx[clean_k] = str(v) if v is not None else ''
                
    return ctx
'''

content = re.sub(r'    return \{\s*\'student_name\': name,.*?\}', replacement, content, flags=re.DOTALL)

with open('mailcenter/variables.py', 'w', encoding='utf-8') as f:
    f.write(content)

