import json
from hr.views import BranchViewSet
from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()
req = factory.get("/api/branches/?company=LP")
view = BranchViewSet()
view.request = view.initialize_request(req)
qs = view.get_queryset()
print("QUERYSET:", qs)
print("SQL:", str(qs.query))
