import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from hr.models import Asset, AssetCategory, Location
from django.contrib.auth import get_user_model

User = get_user_model()

def import_space_inventory():
    file_path = r'b:\lp alternative\updated assets list kochi.xlsx'
    print(f"Reading {file_path}...")
    df = pd.read_excel(file_path, sheet_name='Sheet1')
    
    location_names = df.columns[2:11]
    
    for loc_name in location_names:
        Location.objects.get_or_create(name=loc_name, company='LP')

    assets_created = 0
    for index, row in df.iterrows():
        particular = str(row['PARTICULARS']).strip()
        if pd.isna(row['PARTICULARS']) or particular in ['nan', 'None']:
            continue
            
        category, _ = AssetCategory.objects.get_or_create(name=particular)
        
        for loc_name in location_names:
            count = row[loc_name]
            if pd.notna(count) and type(count) in [int, float] and count > 0:
                location = Location.objects.get(name=loc_name)
                for i in range(int(count)):
                    Asset.objects.create(
                        name=f"{particular} - {loc_name} #{i+1}",
                        category=category,
                        status='AVAILABLE',
                        assigned_location=location,
                        company='LP'
                    )
                    assets_created += 1
    print(f"--> Created {assets_created} assets for space inventory.")

def import_phone_details():
    file_path = r'b:\lp alternative\details.xlsx'
    print(f"\nReading {file_path} for phone details...")
    
    df = pd.read_excel(file_path, sheet_name='Sheet1', skiprows=1)
    df_phones = df.head(11)
    
    category, _ = AssetCategory.objects.get_or_create(name='Mobiles')
    
    assets_created = 0
    for index, row in df_phones.iterrows():
        name = str(row['NAME']).strip()
        if name == 'nan': continue
            
        phone_model = str(row['PHONE ']).strip() if 'PHONE ' in row else str(row.iloc[2]).strip()
        phone_no = str(row['PHONE NO:']).strip() if pd.notna(row['PHONE NO:']) else ''
        if phone_no.endswith('.0'): phone_no = phone_no[:-2]
        
        imei_raw = str(row['IMEI NUMBER']).strip()
        imei = imei_raw.replace('"', '').replace("'", "")
        if imei == 'nan': imei = ''
        
        sim2_val = row['2ND SIM '] if '2ND SIM ' in row else row.iloc[5]
        sim2 = str(int(sim2_val)) if pd.notna(sim2_val) and type(sim2_val) in [float, int] else str(sim2_val).strip() if pd.notna(sim2_val) else ''
        if sim2 == 'nan': sim2 = ''
        if sim2.endswith('.0'): sim2 = sim2[:-2]
        
        first_name = name.split()[0]
        user = User.objects.filter(first_name__icontains=first_name).first()
        
        asset = Asset.objects.create(
            name=f"{phone_model} Mobile ({name})",
            category=category,
            serial_number=imei,
            primary_phone_number=phone_no,
            secondary_phone_number=sim2,
            status='ASSIGNED' if user else 'AVAILABLE',
            assigned_to=user,
            company='LP'
        )
        print(f"Created: {asset.name} (Assigned to: {user.username if user else 'Unassigned'})")
        assets_created += 1

    print(f"--> Created {assets_created} phone assets.")

if __name__ == '__main__':
    print("Starting import process...")
    import_space_inventory()
    import_phone_details()
    print("\nAll data imported successfully!")
