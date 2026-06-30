import os

file_path = "b:/lp alternative/lpcrmbackend-main/accounts/permission_templates.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Update ADMIN
old_admin = """'students:read_tenant', 'students:edit_any', 'fees:read_tenant', 'fees:manage', 'fees:restructure',"""
new_admin = """'students:read_tenant', 'students:edit_any', 'fees:read_tenant', 'fees:manage', 'fees:restructure', 'fees:analytics',"""

# Update CEO
old_ceo = """'students:read_tenant', 'students:edit_any', 'fees:read_tenant', 'fees:manage', 'fees:view_reports',"""
new_ceo = """'students:read_tenant', 'students:edit_any', 'fees:read_tenant', 'fees:manage', 'fees:view_reports', 'fees:analytics',"""

if old_admin in content:
    content = content.replace(old_admin, new_admin)
if old_ceo in content:
    content = content.replace(old_ceo, new_ceo)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched permissions successfully!")
