import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_class = "class CanViewAnalytics(BasePermission):"
new_class = "from rest_framework.permissions import BasePermission\nclass CanViewAnalytics(BasePermission):"

if old_class in content:
    content = content.replace(old_class, new_class)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("BasePermission fixed!")
else:
    print("Could not find class CanViewAnalytics")
