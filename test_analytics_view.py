import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()
user = User.objects.first()

client = APIClient()
client.force_authenticate(user=user)

response = client.get('/api/fees/analytics/overview/')

print("Status code:", response.status_code)
if response.status_code == 200:
    print("Response Data:", response.data)
else:
    print("Error content:", response.content)
