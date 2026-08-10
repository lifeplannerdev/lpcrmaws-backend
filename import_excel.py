import os
import django
import sys
import pandas as pd
import math

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from programs.models import Program, ProgramCountry, ProgramUniversity, ProgramIntake

def is_nan(val):
    if isinstance(val, float) and math.isnan(val):
        return True
    if pd.isna(val):
        return True
    if str(val).strip() == "" or str(val).strip().lower() == "nan":
        return True
    return False

def clean_str(val):
    if is_nan(val):
        return ""
    return str(val).strip()

def run_import():
    file_path = r'b:\LP WORKSPACE\lp_crm\ALL PROGRAMS- FEES STRUCTURE.xlsx'
    print(f"Reading {file_path}...")
    df = pd.read_excel(file_path, header=None)
    
    current_headers = {}
    fee_headers = []
    
    current_program = None
    
    for index, row in df.iterrows():
        col0 = clean_str(row[0])
        col1 = clean_str(row[1])
        
        # Check for header row
        if col0.upper() == "SL NO.":
            current_headers = {}
            fee_headers = []
            for c_idx, val in enumerate(row):
                val_str = clean_str(val).upper()
                if not val_str:
                    continue
                if val_str == "SL NO.": current_headers['sl_no'] = c_idx
                elif val_str == "PROGRAM": current_headers['program'] = c_idx
                elif val_str == "COUNTRY": current_headers['country'] = c_idx
                elif val_str == "QUALIFICATION": current_headers['qualification'] = c_idx
                elif val_str == "COURSE DURATION": current_headers['duration'] = c_idx
                elif val_str == "UNIVERSITY" or val_str == "COLLEGE": current_headers['university'] = c_idx
                elif val_str == "INTAKE": current_headers['intake'] = c_idx
                else:
                    fee_headers.append((c_idx, clean_str(val)))
            continue
        
        # If no headers yet, skip
        if not current_headers:
            continue
            
        # Check if this is a Program row: col0 is digit AND col2 (country) is NOT empty
        col_country_idx = current_headers.get('country')
        if col0.isdigit() and col_country_idx is not None and not is_nan(row[col_country_idx]):
            # It's a program row!
            title = clean_str(row[current_headers.get('program')]) if 'program' in current_headers else ""
            country_str = clean_str(row[current_headers.get('country')]) if 'country' in current_headers else ""
            qual = clean_str(row[current_headers.get('qualification')]) if 'qualification' in current_headers else ""
            dur = clean_str(row[current_headers.get('duration')]) if 'duration' in current_headers else ""
            uni_str = clean_str(row[current_headers.get('university')]) if 'university' in current_headers else ""
            intake_str = clean_str(row[current_headers.get('intake')]) if 'intake' in current_headers else ""
            
            # Create categorical models
            country_obj, _ = ProgramCountry.objects.get_or_create(name=country_str) if country_str else (None, False)
            uni_obj, _ = ProgramUniversity.objects.get_or_create(name=uni_str) if uni_str else (None, False)
            intake_obj, _ = ProgramIntake.objects.get_or_create(name=intake_str) if intake_str else (None, False)
            
            fees = []
            for c_idx, fee_name in fee_headers:
                fee_val = clean_str(row[c_idx])
                if fee_val:
                    fees.append({"name": fee_name, "amount": fee_val})
            
            current_program = Program.objects.create(
                title=title,
                country=country_obj,
                qualification=qual,
                course_duration=dur,
                university=uni_obj,
                intake=intake_obj,
                fees_structure=fees,
                services=[]
            )
            print(f"Created Program: {title}")
            continue
            
        # Check if this is a Service row: col0 is digit AND col2 (country) is empty, OR col0 is a string (e.g. "Document German translation...")
        if current_program:
            # If it explicitly says "OUR SERVICES", skip
            if "OUR SERVICES" in col0.upper() or "OUR SERVICES" in col1.upper():
                continue
            
            # A numbered service
            if col0.isdigit() and col1:
                current_program.services.append(col1)
                current_program.save()
                continue
                
            # An unnumbered service string in col0
            if col0 and not col0.isdigit() and not is_nan(row[0]) and "LP SERVICE CHARGE" not in col0.upper():
                if len(col0) > 10: # Just to ensure it's a real sentence
                    current_program.services.append(col0)
                    current_program.save()
            
            # Check for LP SERVICE CHARGE in any cell
            for cell in row:
                cell_str = clean_str(cell)
                if "LP SERVICE CHARGE" in cell_str.upper():
                    # Add as a fee
                    current_program.fees_structure.append({"name": "LP Service Charge", "amount": cell_str})
                    current_program.save()
                    break

    print("Import complete!")
    print(f"Total Programs: {Program.objects.count()}")
    print(f"Total Countries: {ProgramCountry.objects.count()}")

if __name__ == "__main__":
    run_import()
