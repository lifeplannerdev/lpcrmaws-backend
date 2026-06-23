import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lpcrm.settings")
django.setup()

from accounts.models import User
from accounts.serializers import StaffUpdateSerializer

user = User.objects.first()
data = {
    "first_name": "Test",
    "last_name": "User",
    "voxbay_extension": "999",
    "voxbay_number": "888"
}

serializer = StaffUpdateSerializer(user, data=data, partial=True)
if serializer.is_valid():
    print("VALID!")
    print(serializer.validated_data)
else:
    print("INVALID!")
    print(serializer.errors)
