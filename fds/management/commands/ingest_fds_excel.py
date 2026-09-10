import os
import re
from datetime import datetime, date, time
import openpyxl
from django.core.management.base import BaseCommand
from django.conf import settings
from fds.models import (
    FdsFeeStructure, FdsBatch, FdsEnquiry, FdsTrial,
    FdsStudent, FdsFeesCollection, FdsLeadSourcing
)

def clean_str(val):
    if val is None:
        return ''
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()

def parse_date(val):
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def parse_time(val):
    if not val:
        return None, ''
    if isinstance(val, time):
        return val, val.strftime('%H:%M')
    if isinstance(val, datetime):
        return val.time(), val.strftime('%H:%M')
    return None, str(val).strip()

class Command(BaseCommand):
    help = '1-Way Ingestion: Mirror Google Sheets / Excel files into FDS CRM without data loss'

    def add_arguments(self, parser):
        parser.add_argument('--workbook1', type=str, help='Path to Enquiry & Trial workbook')
        parser.add_argument('--workbook2', type=str, help='Path to Registration & Accounts workbook')

    def handle(self, *args, **options):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        
        # Workbook 1: ENQUIRY, TRIAL, LEAD SOURCING
        wb1_path = options.get('workbook1') or os.path.join(base_dir, 'FDS KTM-ENQUIRY_ TRIAL-2026 (1).xlsx')
        if not os.path.exists(wb1_path):
            wb1_path = os.path.join(os.path.dirname(base_dir), 'FDS KTM-ENQUIRY_ TRIAL-2026 (1).xlsx')
            
        # Workbook 2: REGISTRATION DETAILS, FEES STRUCTURE, FEES COLLECTION 2026
        wb2_path = options.get('workbook2') or os.path.join(base_dir, 'FDS KTM-2026-JOINING DETAILS & ACCOUNTS -FEES STRUCTURE _ FEES COLLECTIONS -REGULAR BATCH (1).xlsx')
        if not os.path.exists(wb2_path):
            wb2_path = os.path.join(os.path.dirname(base_dir), 'FDS KTM-2026-JOINING DETAILS & ACCOUNTS -FEES STRUCTURE _ FEES COLLECTIONS -REGULAR BATCH (1).xlsx')

        self.stdout.write(f"Workbook 1 path: {wb1_path}")
        self.stdout.write(f"Workbook 2 path: {wb2_path}")

        # ── 1. INGEST FEES STRUCTURE ──────────────────────────────────
        if os.path.exists(wb2_path):
            wb2 = openpyxl.load_workbook(wb2_path, data_only=False)
            if 'FEES STRUCTURE' in wb2.sheetnames:
                ws = wb2['FEES STRUCTURE']
                fs_count = 0
                for r in range(2, ws.max_row + 1):
                    cat = clean_str(ws.cell(r, 1).value)
                    if not cat:
                        continue
                    details = clean_str(ws.cell(r, 2).value)
                    amt_val = ws.cell(r, 3).value
                    amt_text = clean_str(amt_val)
                    notes = clean_str(ws.cell(r, 4).value)
                    
                    amount = 0.0
                    try:
                        clean_num = re.sub(r'[^\d.]', '', amt_text.split('\n')[0].replace(',', ''))
                        amount = float(clean_num) if clean_num else 0.0
                    except Exception:
                        amount = 0.0
                        
                    FdsFeeStructure.objects.update_or_create(
                        category=cat,
                        defaults={
                            'category_name': cat,
                            'details': details,
                            'amount': amount,
                            'amount_text': amt_text,
                            'notes': notes,
                            'is_active': True
                        }
                    )
                    fs_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [Sheet 5] Imported {fs_count} Fee Structures."))

            # ── 2. INGEST REGISTRATION DETAILS ─────────────────────────
            if 'REGISTRATION DETAILS' in wb2.sheetnames:
                ws = wb2['REGISTRATION DETAILS']
                reg_count = 0
                for r in range(2, ws.max_row + 1):
                    stu_id = clean_str(ws.cell(r, 1).value)
                    name = clean_str(ws.cell(r, 2).value)
                    if not stu_id or not name:
                        continue
                    
                    joining_date = parse_date(ws.cell(r, 3).value) or date.today()
                    age_gender = clean_str(ws.cell(r, 4).value)
                    parent_name = clean_str(ws.cell(r, 5).value)
                    contact_no = clean_str(ws.cell(r, 6).value)
                    emergency_contact = clean_str(ws.cell(r, 7).value)
                    batch_time = clean_str(ws.cell(r, 8).value)
                    medical = clean_str(ws.cell(r, 9).value) or 'NO'
                    pickup_no = clean_str(ws.cell(r, 10).value)
                    can_leave = clean_str(ws.cell(r, 11).value) or 'NO'
                    fee_paid_date = parse_date(ws.cell(r, 12).value)
                    
                    FdsStudent.objects.update_or_create(
                        student_id=stu_id,
                        defaults={
                            'name': name,
                            'joining_date': joining_date,
                            'age_gender': age_gender,
                            'parent_name': parent_name,
                            'contact_no': contact_no,
                            'emergency_contact_no': emergency_contact,
                            'batch_time_text': batch_time,
                            'medical_condition': medical,
                            'pickup_person_1_no': pickup_no,
                            'can_leave_alone': can_leave,
                            'fee_paid_date': fee_paid_date,
                            'admission_fee_paid_date': fee_paid_date,
                            'is_active': True,
                        }
                    )
                    reg_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [Sheet 4] Imported {reg_count} Students / Registration Details."))

            # ── 3. INGEST FEES COLLECTION 2026 (Monthly Ledger) ────────
            if 'FEES COLLECTION 2026' in wb2.sheetnames:
                ws = wb2['FEES COLLECTION 2026']
                col_count = 0
                curr_stu = {}
                for r in range(2, ws.max_row + 1):
                    stu_id = clean_str(ws.cell(r, 1).value)
                    if stu_id:
                        curr_stu = {
                            'student_id': stu_id,
                            'name': clean_str(ws.cell(r, 2).value),
                            'joined_date': parse_date(ws.cell(r, 3).value),
                            'batch_time': clean_str(ws.cell(r, 4).value),
                            'fees_type': clean_str(ws.cell(r, 5).value) or 'MONTHLY',
                        }
                    month = clean_str(ws.cell(r, 6).value)
                    amt_text = clean_str(ws.cell(r, 7).value)
                    mode = clean_str(ws.cell(r, 8).value) or 'ONLINE'
                    txn_id = clean_str(ws.cell(r, 9).value)
                    status_remarks = clean_str(ws.cell(r, 10).value)
                    
                    if month and curr_stu.get('student_id'):
                        paid_amount = 0.0
                        try:
                            clean_num = re.sub(r'[^\d.]', '', amt_text.replace(',', ''))
                            paid_amount = float(clean_num) if clean_num else 0.0
                        except Exception:
                            paid_amount = 0.0
                            
                        student_obj = FdsStudent.objects.filter(student_id=curr_stu['student_id']).first()
                        month_clean = month.split()[0].upper()
                        payment_id = f"PAY-{curr_stu['student_id']}-{month_clean[:3]}-2026"
                        
                        FdsFeesCollection.objects.update_or_create(
                            payment_id=payment_id,
                            defaults={
                                'student': student_obj,
                                'student_id_code': curr_stu['student_id'],
                                'student_name_text': curr_stu.get('name', ''),
                                'batch_time_text': curr_stu.get('batch_time', ''),
                                'fees_type_text': curr_stu.get('fees_type', 'MONTHLY'),
                                'month_name': month,
                                'paid_amount_text': amt_text,
                                'paid_amount': paid_amount,
                                'mode_of_pay': mode,
                                'transaction_id': txn_id,
                                'status_remarks': status_remarks,
                                'fee_year': 2026,
                                'pay_date': curr_stu.get('joined_date') or date(2026, 9, 1),
                                'status': 'PAID' if paid_amount > 0 else 'PENDING',
                            }
                        )
                        col_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [Sheet 6] Imported {col_count} Fee Collection / Monthly Ledger rows."))

        # ── INGEST WORKBOOK 1: ENQUIRY, TRIAL, LEAD SOURCING ──────────
        if os.path.exists(wb1_path):
            wb1 = openpyxl.load_workbook(wb1_path, data_only=False)
            
            # ── 4. INGEST ENQUIRY ─────────────────────────────────────
            if 'ENQUIRY' in wb1.sheetnames:
                ws = wb1['ENQUIRY']
                enq_count = 0
                for r in range(2, ws.max_row + 1):
                    enq_id = clean_str(ws.cell(r, 1).value)
                    date_val = parse_date(ws.cell(r, 2).value) or date.today()
                    name = clean_str(ws.cell(r, 3).value)
                    if not enq_id and not name:
                        continue
                    
                    parent = clean_str(ws.cell(r, 4).value)
                    location = clean_str(ws.cell(r, 5).value)
                    age = clean_str(ws.cell(r, 6).value)
                    source = clean_str(ws.cell(r, 7).value) or 'WALK_IN'
                    whatsapp = clean_str(ws.cell(r, 8).value)
                    prev_exp = clean_str(ws.cell(r, 9).value)
                    timing = clean_str(ws.cell(r, 10).value)
                    status_val = clean_str(ws.cell(r, 11).value) or 'interested'
                    fu1 = parse_date(ws.cell(r, 12).value)
                    fu2 = parse_date(ws.cell(r, 13).value)
                    joined_st = clean_str(ws.cell(r, 14).value)
                    remarks = clean_str(ws.cell(r, 15).value)
                    
                    if not enq_id:
                        enq_id = f'ENQ{r:03d}'
                        
                    FdsEnquiry.objects.update_or_create(
                        enquiry_id=enq_id,
                        defaults={
                            'date': date_val,
                            'name': name or f'Enquiry {enq_id}',
                            'parent_name': parent,
                            'location': location,
                            'age': age,
                            'source': source,
                            'whatsapp_no': whatsapp,
                            'phone': whatsapp,
                            'previous_exp': prev_exp,
                            'preferred_timing': timing,
                            'status': status_val,
                            'follow_up_1': fu1,
                            'follow_up_2': fu2,
                            'joined': joined_st.lower() in ['joined', 'yes', 'true'],
                            'joined_status': joined_st,
                            'remarks': remarks,
                        }
                    )
                    enq_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [Sheet 1] Imported {enq_count} Enquiries."))

            # ── 5. INGEST TRIAL ───────────────────────────────────────
            if 'TRIAL' in wb1.sheetnames:
                ws = wb1['TRIAL']
                trl_count = 0
                for r in range(2, ws.max_row + 1):
                    trl_id = clean_str(ws.cell(r, 1).value)
                    date_val = parse_date(ws.cell(r, 2).value) or date.today()
                    t_obj, t_txt = parse_time(ws.cell(r, 3).value)
                    name = clean_str(ws.cell(r, 4).value)
                    if not trl_id and not name:
                        continue
                    
                    age = clean_str(ws.cell(r, 5).value)
                    phone = clean_str(ws.cell(r, 6).value)
                    location = clean_str(ws.cell(r, 7).value)
                    fee_quoted = clean_str(ws.cell(r, 8).value)
                    feedback = clean_str(ws.cell(r, 9).value)
                    rating = clean_str(ws.cell(r, 10).value)
                    status_val = clean_str(ws.cell(r, 11).value) or 'WILL INFORM'
                    follow_up = parse_date(ws.cell(r, 12).value)
                    converted_st = clean_str(ws.cell(r, 13).value)
                    join_date = parse_date(ws.cell(r, 14).value)
                    fee_st = clean_str(ws.cell(r, 15).value) or 'PENDING'
                    remarks = clean_str(ws.cell(r, 16).value)
                    
                    if not trl_id:
                        trl_id = f'TRL{r:03d}'
                        
                    FdsTrial.objects.update_or_create(
                        trial_id=trl_id,
                        defaults={
                            'date': date_val,
                            'time': t_obj,
                            'time_text': t_txt,
                            'name': name or f'Trial {trl_id}',
                            'age': age,
                            'phone': phone,
                            'location': location,
                            'fee_quoted': fee_quoted,
                            'feedback': feedback,
                            'trainer_rating': rating,
                            'status': status_val,
                            'follow_up_date': follow_up,
                            'converted': 'join' in converted_st.lower() or converted_st.lower() in ['yes', 'true'],
                            'converted_text': converted_st,
                            'join_date': join_date,
                            'fee_status': fee_st,
                            'remarks': remarks,
                        }
                    )
                    trl_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [Sheet 2] Imported {trl_count} Trials."))

            # ── 6. INGEST LEAD SOURCING ───────────────────────────────
            if 'LEAD SOURCING' in wb1.sheetnames:
                ws = wb1['LEAD SOURCING']
                curr_cat = None
                ls_count = 0
                for r in range(1, ws.max_row + 1):
                    c1 = clean_str(ws.cell(r, 1).value)
                    c2 = clean_str(ws.cell(r, 2).value)
                    c3 = clean_str(ws.cell(r, 3).value)
                    c4 = clean_str(ws.cell(r, 4).value)
                    if not c1 and not c2:
                        continue
                    
                    low = c1.lower()
                    if 'prominent colleges' in low:
                        curr_cat = 'COLLEGES'
                        continue
                    elif 'prominent schools' in low:
                        curr_cat = 'SCHOOLS'
                        continue
                    elif 'social clubs' in low or 'recreation' in low:
                        curr_cat = 'CLUBS'
                        continue
                    elif 'resident welfare' in low:
                        curr_cat = 'RESIDENTS'
                        continue
                    elif 'villa' in low:
                        curr_cat = 'VILLAS'
                        continue
                    elif 'residency / builder' in low:
                        curr_cat = 'BUILDERS'
                        continue
                    
                    if any(h in low for h in ['institution name', 'school name', 'organization', 'association', 'villa project', 'residency / builder']):
                        continue
                        
                    if curr_cat and c1:
                        FdsLeadSourcing.objects.update_or_create(
                            category=curr_cat,
                            name=c1,
                            defaults={
                                'location': c2,
                                'phone': c3,
                                'email_website': c4 if curr_cat != 'RESIDENTS' else '',
                                'extra_info': c4 if curr_cat in ['RESIDENTS', 'SCHOOLS'] else '',
                            }
                        )
                        ls_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [Sheet 3] Imported {ls_count} Lead Sourcing directory entries."))

        self.stdout.write(self.style.SUCCESS("All 6 sheets mirrored into CRM successfully!"))
