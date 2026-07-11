import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/urls.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_1 = "path('analytics/overview/'"
new_1 = "path('fees/analytics/overview/'"

old_2 = "path('analytics/student/"
new_2 = "path('fees/analytics/student/"

content = content.replace(old_1, new_1)
content = content.replace(old_2, new_2)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Backend URLs patched!")
