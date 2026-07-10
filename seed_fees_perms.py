import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from accounts.models import AppPermission

permissions = [
    {"name": "fees_grid:view", "description": "Can view the dynamic fees grid / spreadsheet UI"},
    {"name": "fees:export", "description": "Can export fee data to Excel"},
]

for p in permissions:
    perm, created = AppPermission.objects.get_or_create(
        name=p['name'],
        defaults={'description': p['description']}
    )
    if created:
        print(f"Created permission: {p['name']}")
    else:
        print(f"Permission already exists: {p['name']}")

print("Seeding complete.")
