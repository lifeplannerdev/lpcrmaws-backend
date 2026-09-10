import os
import re
from datetime import datetime, date, time
import gspread
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from fds.models import (
    FdsStudent, FdsFeeStructure, FdsFeesCollection,
    FdsEnquiry, FdsTrial, FdsLeadSourcing
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
    help = '1-Way Sync: Google Sheets (Master) ➔ CRM (Mirror) for all 6 sheets'

    def handle(self, *args, **options):
        self.stdout.write("Checking Google Sheets credentials...")
        cred_file = getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS_FILE', None)
        
        if cred_file and os.path.exists(cred_file):
            try:
                gc = gspread.service_account(filename=cred_file)
                self.stdout.write(self.style.SUCCESS("Authenticated with Google Sheets API."))
                self.sync_from_google_drive(gc)
                return
            except Exception as e:
                self.stderr.write(f"Google Sheets API sync failed: {e}. Falling back to local workbook mirror.")
        else:
            self.stdout.write("GOOGLE_SHEETS_CREDENTIALS_FILE not set or not found. Using local master Excel workbooks.")
            
        # Run local ingestion
        call_command('ingest_fds_excel')

    def sync_from_google_drive(self, gc):
        # Sheet 1: Registration, Fees Structure, Fees Collection
        sheet1_title = "FDS KTM-2026-JOINING DETAILS & ACCOUNTS -FEES STRUCTURE _ FEES COLLECTIONS -REGULAR BATCH"
        try:
            sh1 = gc.open(sheet1_title)
            self.sync_registration_sheet(sh1)
            self.sync_fee_structure_sheet(sh1)
            self.sync_fees_collection_sheet(sh1)
        except Exception as e:
            self.stderr.write(f"Error reading {sheet1_title}: {e}")

        # Sheet 2: Enquiry, Trial, Lead Sourcing
        sheet2_title = "FDS KTM-ENQUIRY_ TRIAL-2026"
        try:
            sh2 = gc.open(sheet2_title)
            self.sync_enquiry_sheet(sh2)
            self.sync_trial_sheet(sh2)
            self.sync_lead_sourcing_sheet(sh2)
        except Exception as e:
            self.stderr.write(f"Error reading {sheet2_title}: {e}")

    def sync_fee_structure_sheet(self, sh):
        ws = sh.worksheet("FEES STRUCTURE")
        rows = ws.get_all_values()
        count = 0
        for row in rows[1:]:
            cat = clean_str(row[0]) if len(row) > 0 else ''
            if not cat: continue
            details = clean_str(row[1]) if len(row) > 1 else ''
            amt_text = clean_str(row[2]) if len(row) > 2 else ''
            notes = clean_str(row[3]) if len(row) > 3 else ''
            
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
                    'is_active': True,
                }
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"  Synced {count} Fee Structure rows."))

    def sync_registration_sheet(self, sh):
        ws = sh.worksheet("REGISTRATION DETAILS")
        rows = ws.get_all_values()
        count = 0
        for row in rows[1:]:
            stu_id = clean_str(row[0]) if len(row) > 0 else ''
            name = clean_str(row[1]) if len(row) > 1 else ''
            if not stu_id or not name: continue
            
            joining_date = parse_date(row[2]) if len(row) > 2 else date.today()
            age_gender = clean_str(row[3]) if len(row) > 3 else ''
            parent_name = clean_str(row[4]) if len(row) > 4 else ''
            contact_no = clean_str(row[5]) if len(row) > 5 else ''
            emergency_contact = clean_str(row[6]) if len(row) > 6 else ''
            batch_time = clean_str(row[7]) if len(row) > 7 else ''
            medical = clean_str(row[8]) if len(row) > 8 else 'NO'
            pickup_no = clean_str(row[9]) if len(row) > 9 else ''
            can_leave = clean_str(row[10]) if len(row) > 10 else 'NO'
            fee_paid_date = parse_date(row[11]) if len(row) > 11 else None

            FdsStudent.objects.update_or_create(
                student_id=stu_id,
                defaults={
                    'name': name,
                    'joining_date': joining_date or date.today(),
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
            count += 1
        self.stdout.write(self.style.SUCCESS(f"  Synced {count} Student registration rows."))

    def sync_fees_collection_sheet(self, sh):
        ws = sh.worksheet("FEES COLLECTION 2026")
        rows = ws.get_all_values()
        count = 0
        curr_stu = {}
        for row in rows[1:]:
            stu_id = clean_str(row[0]) if len(row) > 0 else ''
            if stu_id:
                curr_stu = {
                    'student_id': stu_id,
                    'name': clean_str(row[1]) if len(row) > 1 else '',
                    'joined_date': parse_date(row[2]) if len(row) > 2 else None,
                    'batch_time': clean_str(row[3]) if len(row) > 3 else '',
                    'fees_type': clean_str(row[4]) if len(row) > 4 else 'MONTHLY',
                }
            month = clean_str(row[5]) if len(row) > 5 else ''
            amt_text = clean_str(row[6]) if len(row) > 6 else ''
            mode = clean_str(row[7]) if len(row) > 7 else 'ONLINE'
            txn_id = clean_str(row[8]) if len(row) > 8 else ''
            status_remarks = clean_str(row[9]) if len(row) > 9 else ''

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
                count += 1
        self.stdout.write(self.style.SUCCESS(f"  Synced {count} Monthly Fee Collection rows."))

    def sync_enquiry_sheet(self, sh):
        ws = sh.worksheet("ENQUIRY")
        rows = ws.get_all_values()
        count = 0
        for r, row in enumerate(rows[1:], start=2):
            enq_id = clean_str(row[0]) if len(row) > 0 else ''
            date_val = parse_date(row[1]) if len(row) > 1 else date.today()
            name = clean_str(row[2]) if len(row) > 2 else ''
            if not enq_id and not name: continue
            
            parent = clean_str(row[3]) if len(row) > 3 else ''
            location = clean_str(row[4]) if len(row) > 4 else ''
            age = clean_str(row[5]) if len(row) > 5 else ''
            source = clean_str(row[6]) if len(row) > 6 else 'WALK_IN'
            whatsapp = clean_str(row[7]) if len(row) > 7 else ''
            prev_exp = clean_str(row[8]) if len(row) > 8 else ''
            timing = clean_str(row[9]) if len(row) > 9 else ''
            status_val = clean_str(row[10]) if len(row) > 10 else 'interested'
            fu1 = parse_date(row[11]) if len(row) > 11 else None
            fu2 = parse_date(row[12]) if len(row) > 12 else None
            joined_st = clean_str(row[13]) if len(row) > 13 else ''
            remarks = clean_str(row[14]) if len(row) > 14 else ''
            
            if not enq_id: enq_id = f'ENQ{r:03d}'
            
            FdsEnquiry.objects.update_or_create(
                enquiry_id=enq_id,
                defaults={
                    'date': date_val or date.today(),
                    'name': name or f'Enquiry {enq_id}',
                    'parent_name': parent,
                    'location': location,
                    'age': age,
                    'source': source or 'WALK_IN',
                    'whatsapp_no': whatsapp,
                    'phone': whatsapp,
                    'previous_exp': prev_exp,
                    'preferred_timing': timing,
                    'status': status_val or 'interested',
                    'follow_up_1': fu1,
                    'follow_up_2': fu2,
                    'joined': 'join' in joined_st.lower() or joined_st.lower() in ['yes', 'true'],
                    'joined_status': joined_st,
                    'remarks': remarks,
                }
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"  Synced {count} Enquiry rows."))

    def sync_trial_sheet(self, sh):
        ws = sh.worksheet("TRIAL")
        rows = ws.get_all_values()
        count = 0
        for r, row in enumerate(rows[1:], start=2):
            trl_id = clean_str(row[0]) if len(row) > 0 else ''
            date_val = parse_date(row[1]) if len(row) > 1 else date.today()
            t_obj, t_txt = parse_time(row[2]) if len(row) > 2 else (None, '')
            name = clean_str(row[3]) if len(row) > 3 else ''
            if not trl_id and not name: continue
            
            age = clean_str(row[4]) if len(row) > 4 else ''
            phone = clean_str(row[5]) if len(row) > 5 else ''
            location = clean_str(row[6]) if len(row) > 6 else ''
            fee_quoted = clean_str(row[7]) if len(row) > 7 else ''
            feedback = clean_str(row[8]) if len(row) > 8 else ''
            rating = clean_str(row[9]) if len(row) > 9 else ''
            status_val = clean_str(row[10]) if len(row) > 10 else 'WILL INFORM'
            follow_up = parse_date(row[11]) if len(row) > 11 else None
            converted_st = clean_str(row[12]) if len(row) > 12 else ''
            join_date = parse_date(row[13]) if len(row) > 13 else None
            fee_st = clean_str(row[14]) if len(row) > 14 else 'PENDING'
            remarks = clean_str(row[15]) if len(row) > 15 else ''
            
            if not trl_id: trl_id = f'TRL{r:03d}'
            
            FdsTrial.objects.update_or_create(
                trial_id=trl_id,
                defaults={
                    'date': date_val or date.today(),
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
            count += 1
        self.stdout.write(self.style.SUCCESS(f"  Synced {count} Trial rows."))

    def sync_lead_sourcing_sheet(self, sh):
        ws = sh.worksheet("LEAD SOURCING")
        rows = ws.get_all_values()
        count = 0
        curr_cat = None
        for row in rows:
            c1 = clean_str(row[0]) if len(row) > 0 else ''
            c2 = clean_str(row[1]) if len(row) > 1 else ''
            c3 = clean_str(row[2]) if len(row) > 2 else ''
            c4 = clean_str(row[3]) if len(row) > 3 else ''
            if not c1 and not c2: continue
            
            low = c1.lower()
            if 'prominent colleges' in low: curr_cat = 'COLLEGES'; continue
            elif 'prominent schools' in low: curr_cat = 'SCHOOLS'; continue
            elif 'social clubs' in low or 'recreation' in low: curr_cat = 'CLUBS'; continue
            elif 'resident welfare' in low: curr_cat = 'RESIDENTS'; continue
            elif 'villa' in low: curr_cat = 'VILLAS'; continue
            elif 'residency / builder' in low: curr_cat = 'BUILDERS'; continue
            
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
                count += 1
        self.stdout.write(self.style.SUCCESS(f"  Synced {count} Lead Sourcing directory rows."))
