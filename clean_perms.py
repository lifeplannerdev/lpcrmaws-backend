import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lpcrm.settings")
django.setup()

from accounts.models import AppPermission
from accounts.permission_templates import ROLE_PERMISSIONS

active_perms = set()
for perms in ROLE_PERMISSIONS.values():
    active_perms.update(perms)

prefixes = ["students:", "fees:", "attendance:", "processing_students:"]

deleted = 0
for p in AppPermission.objects.all():
    if any(p.name.startswith(prefix) for prefix in prefixes):
        if p.name not in active_perms:
            print(f"Deleting unused permission: {p.name}")
            p.delete()
            deleted += 1

print(f"Deleted {deleted} unused permissions.")
