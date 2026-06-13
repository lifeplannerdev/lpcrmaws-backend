import pandas as pd
import json

excel_file = r'b:\lp alternative\updated assets list kochi.xlsx'
df = pd.read_excel(excel_file, sheet_name='Sheet1')
location_names = list(df.columns[2:11])

space_assets = []
for index, row in df.iterrows():
    particular = str(row['PARTICULARS']).strip()
    if pd.isna(row['PARTICULARS']) or particular in ['nan', 'None']:
        continue
    for loc_name in location_names:
        count = row[loc_name]
        if pd.notna(count) and type(count) in [int, float] and count > 0:
            for i in range(int(count)):
                space_assets.append({
                    "name": f"{particular} - {loc_name} #{i+1}",
                    "category": particular,
                    "location": loc_name
                })

details_file = r'b:\lp alternative\details.xlsx'
df2 = pd.read_excel(details_file, sheet_name='Sheet1', skiprows=1).head(11)

phone_assets = []
for index, row in df2.iterrows():
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
    phone_assets.append({
        "name": f"{phone_model} Mobile ({name})",
        "category": "Mobiles",
        "imei": imei,
        "phone_no": phone_no,
        "sim2": sim2,
        "first_name": first_name
    })

script_content = f"""import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from hr.models import Asset, AssetCategory, Location
from django.contrib.auth import get_user_model

User = get_user_model()

location_names = {json.dumps(location_names)}
space_assets = {json.dumps(space_assets)}
phone_assets = {json.dumps(phone_assets)}

for loc_name in location_names:
    Location.objects.get_or_create(name=loc_name, company='LP')

assets_created = 0
for asset_data in space_assets:
    category, _ = AssetCategory.objects.get_or_create(name=asset_data['category'])
    location = Location.objects.get(name=asset_data['location'])
    Asset.objects.create(
        name=asset_data['name'],
        category=category,
        status='AVAILABLE',
        assigned_location=location,
        company='LP'
    )
    assets_created += 1

print(f"Created {{assets_created}} space inventory assets.")

category, _ = AssetCategory.objects.get_or_create(name='Mobiles')
phones_created = 0
for asset_data in phone_assets:
    user = User.objects.filter(first_name__icontains=asset_data['first_name']).first()
    Asset.objects.create(
        name=asset_data['name'],
        category=category,
        serial_number=asset_data['imei'],
        primary_phone_number=asset_data['phone_no'],
        secondary_phone_number=asset_data['sim2'],
        status='ASSIGNED' if user else 'AVAILABLE',
        assigned_to=user,
        company='LP'
    )
    phones_created += 1

print(f"Created {{phones_created}} phone assets.")
print("All data imported successfully!")
"""

with open(r'b:\lp alternative\lpcrmbackend-main\prod_import_assets.py', 'w') as f:
    f.write(script_content)
print("Generated prod_import_assets.py")
