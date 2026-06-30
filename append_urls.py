import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/urls.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

import_statement = "from .views import FeeAnalyticsOverviewAPIView, FeeStudent360APIView"
if import_statement not in content:
    content = content.replace("from .views import (", "from .views import (\n    FeeAnalyticsOverviewAPIView,\n    FeeStudent360APIView,")

new_urls = """
    path('analytics/overview/', FeeAnalyticsOverviewAPIView.as_view(), name='fee-analytics-overview'),
    path('analytics/student/<int:student_id>/', FeeStudent360APIView.as_view(), name='fee-student-360'),
]"""

content = content.replace("]", new_urls)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Appended URLs to fees/urls.py")
