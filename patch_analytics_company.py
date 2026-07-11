import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace FeeAnalyticsOverviewAPIView company filtering
old_overview = """    def get(self, request):
        company = request.GET.get('company') or 'LP'
        qs = StudentFeeAccount.objects.select_related('student', 'student__branch', 'student__academic_batch').filter(company=company)"""

new_overview = """    def get(self, request):
        company = request.GET.get('company')
        qs = StudentFeeAccount.objects.select_related('student', 'student__branch', 'student__academic_batch')
        if company:
            qs = qs.filter(company=company)"""

if old_overview in content:
    content = content.replace(old_overview, new_overview)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Backend patched for company filter!")
