import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from hr.serializers import AssetSerializer

data = {
    "name": "COMAPANY SIM AIRTEL TEST",
    "category": 1,  # Need valid category ID for SIM, let's omit or mock
    "serial_number": "7736274522",
    "assigned_to": 1,
    "assigned_location": 1,
    "company": "LP"
}

# Let's get real IDs
from hr.models import AssetCategory, Location, Branch
from django.contrib.auth import get_user_model
User = get_user_model()
cat = AssetCategory.objects.first()
user = User.objects.first()
loc = Location.objects.first()

if cat and user and loc:
    data['category'] = cat.id
    data['assigned_to'] = user.id
    data['assigned_location'] = loc.id
    data['branch'] = loc.branch.id if loc.branch else None

    serializer = AssetSerializer(data=data)
    if serializer.is_valid():
        try:
            asset = serializer.save()
            print("Saved successfully. Serializer data:")
            print(serializer.data)
        except Exception as e:
            import traceback
            print("Crash during save/serialize:")
            traceback.print_exc()
    else:
        print("Invalid data:", serializer.errors)
else:
    print("Could not find needed DB objects")
