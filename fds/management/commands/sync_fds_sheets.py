import os
import gspread
from django.core.management.base import BaseCommand
from django.conf import settings
from fds.models import FdsStudent, FdsFeeStructure, FdsFeesCollection, FdsEnquiry, FdsTrial

class Command(BaseCommand):
    help = 'Syncs FDS data to Google Sheets (Registration, Fees, Enquiry, Trial)'

    def handle(self, *args, **options):
        # 1. Authenticate with Google Sheets
        self.stdout.write("Authenticating with Google Sheets...")
        try:
            # We assume a service account JSON is provided in settings or env
            # e.g., GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE')
            cred_file = getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS_FILE', None)
            if not cred_file or not os.path.exists(cred_file):
                self.stderr.write(f"Credentials file not found: {cred_file}")
                self.stderr.write("Please set GOOGLE_SHEETS_CREDENTIALS_FILE in settings.")
                return

            gc = gspread.service_account(filename=cred_file)
            self.stdout.write(self.style.SUCCESS("Successfully authenticated."))
        except Exception as e:
            self.stderr.write(f"Authentication failed: {e}")
            return

        # 2. Sync Registration & Fees Sheet
        # Sheet: FDS KTM-2026-JOINING DETAILS & ACCOUNTS -FEES STRUCTURE _ FEES COLLECTIONS -REGULAR BATCH
        sheet1_name = "FDS KTM-2026-JOINING DETAILS & ACCOUNTS -FEES STRUCTURE _ FEES COLLECTIONS -REGULAR BATCH"
        try:
            sh1 = gc.open(sheet1_name)
            self.sync_registration_details(sh1)
            self.sync_fee_structure(sh1)
            self.sync_fees_collection(sh1)
            self.stdout.write(self.style.SUCCESS(f"Successfully synced {sheet1_name}"))
        except Exception as e:
            self.stderr.write(f"Failed to sync {sheet1_name}: {e}")

        # 3. Sync Enquiry & Trial Sheet
        # Sheet: FDS KTM-ENQUIRY_ TRIAL-2026
        sheet2_name = "FDS KTM-ENQUIRY_ TRIAL-2026"
        try:
            sh2 = gc.open(sheet2_name)
            self.sync_enquiries(sh2)
            self.sync_trials(sh2)
            self.stdout.write(self.style.SUCCESS(f"Successfully synced {sheet2_name}"))
        except Exception as e:
            self.stderr.write(f"Failed to sync {sheet2_name}: {e}")

    def sync_registration_details(self, sh):
        self.stdout.write("  Syncing REGISTRATION DETAILS...")
        worksheet = sh.worksheet("REGISTRATION DETAILS")
        
        # Columns: 'Student ID', 'Name ', 'Joining Date', 'Age &Gender', 'Parent Name ', 'Contact No.', 
        # 'Emergency contact NO.', 'Batch/Time', 'Medical Condition', 'Media Consent', 'Pickup Person 1 NO.', 
        # 'Can Leave alone', 'Admission Fee Paid Date'
        
        students = FdsStudent.objects.all().order_by('joining_date', 'name')
        
        rows = []
        for s in students:
            age_gender = ""
            if s.age is not None:
                age_gender = str(s.age)
            if s.gender:
                if age_gender:
                    age_gender += f" / {s.get_gender_display()}"
                else:
                    age_gender = s.get_gender_display()
            
            batch_time = ""
            if s.batch:
                batch_time = f"{s.batch.name} - {s.batch.time_display}"

            rows.append([
                s.student_id,
                s.name,
                str(s.joining_date) if s.joining_date else "",
                age_gender,
                s.parent_name or "",
                s.contact_no or "",
                s.emergency_contact_no or "",
                batch_time,
                s.medical_condition or "",
                "Yes" if s.media_consent else "No",
                s.pickup_person_1_no or "",
                "Yes" if s.can_leave_alone else "No",
                str(s.admission_fee_paid_date) if s.admission_fee_paid_date else ""
            ])
            
        self._update_worksheet(worksheet, rows, start_row=2)

    def sync_fee_structure(self, sh):
        self.stdout.write("  Syncing FEES STRUCTURE...")
        worksheet = sh.worksheet("FEES STRUCTURE")
        
        # Columns: 'CATEGORY', 'DETAILS', ' AMOUNT (RUPEES)', 'NOTES /OFFER'
        structures = FdsFeeStructure.objects.all().order_by('category')
        
        rows = []
        for f in structures:
            rows.append([
                f.get_category_display(),
                f.details or "",
                float(f.amount),
                f.notes or ""
            ])
            
        self._update_worksheet(worksheet, rows, start_row=2)

    def sync_fees_collection(self, sh):
        self.stdout.write("  Syncing FEES COLLECTION...")
        worksheet = sh.worksheet("FEES COLLECTION")
        
        # Columns: 'Student ID', 'Pay Date', 'Student name', "What's app No.", 'Joined Date', 'Batch/Time', 
        # 'Fees Type', 'Month', 'Paid Amount', 'Total Fees', 'Balance', 'Mode Of Pay', 'PDF LINK', 'Status/Remarks'
        
        # KEY REQUIREMENT: Group all fees per student
        collections = FdsFeesCollection.objects.all().order_by('student__name', 'pay_date')
        
        rows = []
        for c in collections:
            student_id = c.student.student_id if c.student else ""
            student_name = c.student.name if c.student else (c.wedding_group.event_name if c.wedding_group else "")
            whatsapp = c.student.whatsapp_no if c.student else ""
            joined_date = str(c.student.joining_date) if (c.student and c.student.joining_date) else ""
            
            batch_time = ""
            if c.student and c.student.batch:
                batch_time = f"{c.student.batch.name} - {c.student.batch.time_display}"
            elif c.wedding_group and c.wedding_group.batch:
                batch_time = f"{c.wedding_group.batch.name} - {c.wedding_group.batch.time_display}"
                
            fee_type = c.fees_type.get_category_display() if c.fees_type else ""
            month = c.get_fee_month_display() if c.fee_month else ""
            if c.fee_year:
                month += f" {c.fee_year}"
                
            status_remarks = c.get_status_display()
            if c.remarks:
                status_remarks += f" - {c.remarks}"
                
            rows.append([
                student_id,
                str(c.pay_date) if c.pay_date else "",
                student_name,
                whatsapp or "",
                joined_date,
                batch_time,
                fee_type,
                month,
                float(c.paid_amount),
                float(c.total_fees),
                float(c.balance),
                c.get_mode_of_pay_display(),
                c.pdf_link or "",
                status_remarks
            ])
            
        self._update_worksheet(worksheet, rows, start_row=2)

    def sync_enquiries(self, sh):
        self.stdout.write("  Syncing ENQUIRY...")
        worksheet = sh.worksheet("ENQUIRY")
        
        # Columns: 'Enquiry ID', 'Date', 'Name', 'Location', 'Age', 'Source', 'Phone', 
        # "What's App no.", 'Preffered Timing', 'Status', 'Follow Up1', 'Follow Up 2', 
        # 'Joined Or Not', 'Remarks / Concerns'
        
        enquiries = FdsEnquiry.objects.all().order_by('-date')
        
        rows = []
        for e in enquiries:
            rows.append([
                e.enquiry_id,
                str(e.date) if e.date else "",
                e.name,
                e.location or "",
                str(e.age) if e.age else "",
                e.get_source_display(),
                e.phone or "",
                e.whatsapp_no or "",
                e.preferred_timing or "",
                e.get_status_display(),
                str(e.follow_up_1) if e.follow_up_1 else "",
                str(e.follow_up_2) if e.follow_up_2 else "",
                "Yes" if e.joined else "No",
                e.remarks or ""
            ])
            
        self._update_worksheet(worksheet, rows, start_row=2)

    def sync_trials(self, sh):
        self.stdout.write("  Syncing TRIAL...")
        worksheet = sh.worksheet("TRIAL")
        
        # Columns: 'TRIAL ID', 'DATE', 'TIME', 'NAME', 'AGE', 'PHONE', 'LOCATION', 
        # 'FEE QUOTED', 'FEEDBACK', 'TRAINER RATING(IN 5⭐)', 'STATUS', 'CONVERTED', 
        # 'JOIN DATE', 'FOLLOW UP DATE', 'REMARKS'
        
        trials = FdsTrial.objects.all().order_by('-date')
        
        rows = []
        for t in trials:
            rows.append([
                t.trial_id,
                str(t.date) if t.date else "",
                str(t.time) if t.time else "",
                t.name,
                str(t.age) if t.age else "",
                t.phone or "",
                t.location or "",
                float(t.fee_quoted),
                t.feedback or "",
                str(t.trainer_rating) if t.trainer_rating else "",
                t.get_status_display(),
                "Yes" if t.converted else "No",
                str(t.join_date) if t.join_date else "",
                str(t.follow_up_date) if t.follow_up_date else "",
                t.remarks or ""
            ])
            
        self._update_worksheet(worksheet, rows, start_row=2)
        
    def _update_worksheet(self, worksheet, data_rows, start_row=2):
        """
        Helper method to clear data from start_row onwards and write fresh data.
        """
        # We need to find the total rows currently in the sheet to clear them
        # Alternatively, we can just update range.
        # But if the new data is smaller, the old data at the bottom remains.
        # So it's best to clear the range from start_row to bottom.
        
        # Get all values to know how many rows exist
        all_values = worksheet.get_all_values()
        num_rows = len(all_values)
        num_cols = len(all_values[0]) if num_rows > 0 else len(data_rows[0]) if data_rows else 15
        
        # Note: gspread uses 1-based indexing
        # If there are rows to clear (after headers)
        if num_rows >= start_row:
            # We clear A2:Z1000 dynamically based on num_rows and num_cols
            # Let's get the max column letter
            col_letter = chr(64 + num_cols) if num_cols <= 26 else 'Z' # simple approx for <=26 cols
            range_to_clear = f"A{start_row}:{col_letter}{num_rows}"
            worksheet.batch_clear([range_to_clear])
            
        # Write new data
        if data_rows:
            col_letter = chr(64 + len(data_rows[0])) if len(data_rows[0]) <= 26 else 'Z'
            end_row = start_row + len(data_rows) - 1
            range_to_update = f"A{start_row}:{col_letter}{end_row}"
            worksheet.update(range_name=range_to_update, values=data_rows)
