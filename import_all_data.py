import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrmbackend.settings')
django.setup()

from hr.models import Asset, AssetCategory, Location
from django.contrib.auth import get_user_model

User = get_user_model()

def import_excel_data():
    file_path = r'b:\lp alternative\updated assets list kochi.xlsx'
    print("Reading Excel file for Space Inventory...")
    df = pd.read_excel(file_path, sheet_name='Sheet1')
    
    # Locations are columns from index 2 to 10
    location_names = df.columns[2:11]
    print(f"Found locations: {list(location_names)}")
    
    for loc_name in location_names:
        Location.objects.get_or_create(name=loc_name, company='LP')

    assets_created = 0
    for index, row in df.iterrows():
        particular = str(row['PARTICULARS']).strip()
        if pd.isna(particular) or particular == 'nan' or particular == 'None':
            continue
            
        category, _ = AssetCategory.objects.get_or_create(name=particular)
        
        for loc_name in location_names:
            count = row[loc_name]
            if pd.notna(count) and count > 0:
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
    print(f"Created {assets_created} assets from Excel file.")

def import_phone_data():
    print("\nReading Phone Details from Image Data...")
    phone_data = [
        {"name": "ASWATHY KRISHNA", "phone": "MOTO", "phone_no": "8129410107", "imei": "353418205981993", "sim2": ""},
        {"name": "BIJI SOBIN", "phone": "SAMSUNG", "phone_no": "8089040107", "imei": "352968446427173", "sim2": "8593020107"},
        {"name": "TONY", "phone": "REALME", "phone_no": "8593050107", "imei": "862145079170890", "sim2": "9072222933"},
        {"name": "REVANTH", "phone": "POCO", "phone_no": "8594060107", "imei": "862560062411822", "sim2": "8089095055"},
        {"name": "MELBIN", "phone": "SAMSUNG", "phone_no": "8089010107", "imei": "352968446445027", "sim2": "9072222911"},
        {"name": "LIMSITHA", "phone": "VIVO", "phone_no": "9633320107", "imei": "869907079068702", "sim2": "9745400107"},
        {"name": "MANGULLA", "phone": "REDMI", "phone_no": "8589040107", "imei": "864503054929557", "sim2": ""},
        {"name": "SREETHU", "phone": "MOTO", "phone_no": "8089030107", "imei": "864503054374358", "sim2": ""},
        {"name": "JITHIN", "phone": "REDMI", "phone_no": "8086610107", "imei": "354016331703239", "sim2": ""},
        {"name": "REENU", "phone": "REDMI", "phone_no": "8593030107", "imei": "863799043714966", "sim2": ""},
        {"name": "NAVYA", "phone": "SAMSUNG", "phone_no": "8943510107", "imei": "353704476427174", "sim2": ""},
    ]

    category, _ = AssetCategory.objects.get_or_create(name='Mobiles')
    
    assets_created = 0
    for row in phone_data:
        first_name = row['name'].split()[0]
        user = User.objects.filter(first_name__icontains=first_name).first()
        
        asset = Asset.objects.create(
            name=f"Mobile - {row['phone']} ({row['name']})",
            category=category,
            serial_number=row['imei'],
            primary_phone_number=row['phone_no'],
            secondary_phone_number=row['sim2'],
            status='ASSIGNED' if user else 'AVAILABLE',
            assigned_to=user,
            company='LP'
        )
        print(f"Created Phone Asset: {asset.name} (Assigned to: {user.username if user else 'None'})")
        assets_created += 1

    print(f"Created {assets_created} phone assets.")

if __name__ == '__main__':
    print("Starting Asset Import Process...")
    import_excel_data()
    import_phone_data()
    print("Done!")
