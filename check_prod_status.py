import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from notifications.models import DevicePushToken, Notification
from django.contrib.auth import get_user_model
from tasks.models import Task

User = get_user_model()

print("=" * 60)
print("PRODUCTION SERVER DIAGNOSTIC REPORT")
print("=" * 60)
print(f"Total Users: {User.objects.count()}")
print("Users:")
for u in User.objects.filter(is_active=True).order_by('id')[:10]:
    roles = list(u.db_roles.values_list('name', flat=True)) if hasattr(u, 'db_roles') else []
    print(f"  - [{u.id}] {u.username} (Roles: {roles})")

print(f"\nRegistered Device Push Tokens: {DevicePushToken.objects.count()}")
for t in DevicePushToken.objects.all():
    print(f"  - User: {t.user.username} | Platform: {t.platform} | Device: {t.device_name} | Active: {t.is_active} | Token: {t.token[:30]}...")

print(f"\nTotal Notifications in DB: {Notification.objects.count()}")
for n in Notification.objects.order_by('-created_at')[:5]:
    print(f"  - [{n.type}] To: {n.user.username} | Message: {n.message[:40]}... | By: {n.by}")

print(f"\nTotal Tasks in DB: {Task.objects.count()}")
for t in Task.objects.order_by('-created_at')[:3]:
    assignee = t.assigned_to.username if t.assigned_to else 'None'
    assigner = t.assigned_by.username if t.assigned_by else 'None'
    print(f"  - Task #{t.id}: \"{t.title}\" | Assignee: {assignee} | Assigner: {assigner} | Status: {t.status}")
print("=" * 60)
