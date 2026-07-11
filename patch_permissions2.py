import os

file_path = "b:/lp alternative/lpcrmbackend-main/fees/views.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_perm = """class CanViewAnalytics(BasePermission):
    def has_permission(self, request, view):
        return has_dynamic_permission(request.user, 'fees:analytics')"""

new_perm = """class CanViewAnalytics(BasePermission):
    def has_permission(self, request, view):
        return has_dynamic_permission(request.user, 'fees:analytics') or has_dynamic_permission(request.user, 'fees:manage') or has_dynamic_permission(request.user, 'fees:view_reports')"""

if old_perm in content:
    content = content.replace(old_perm, new_perm)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched CanViewAnalytics!")
