import os

file_path = "b:/lp alternative/lpcrm-frontend-main/src/Pages/FeesAnalyticsWorkspace.jsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("'/api/analytics/overview/", "'/api/fees/analytics/overview/")
content = content.replace("`/api/analytics/overview/", "`/api/fees/analytics/overview/")

content = content.replace("'/api/analytics/student/", "'/api/fees/analytics/student/")
content = content.replace("`/api/analytics/student/", "`/api/fees/analytics/student/")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Frontend URLs patched!")
