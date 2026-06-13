from django.test import Client
c = Client()
res = c.get("/api/branches/?company=LP", follow=True)
print(res.status_code)
print(res.content)
