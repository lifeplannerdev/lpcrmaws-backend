from rest_framework.test import APIRequestFactory, force_authenticate
from hr.views import BranchViewSet
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if not user:
    user = User.objects.first()

factory = APIRequestFactory()
request = factory.get("/api/branches/?company=LP")
force_authenticate(request, user=user)

view = BranchViewSet.as_view({"get": "list"})
response = view(request)
print("Status Code:", response.status_code)
print("Data:", response.data)
