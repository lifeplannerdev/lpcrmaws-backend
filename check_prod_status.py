import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from notifications.models import DevicePushToken, Notification
from django.contrib.auth import get_user_model
from tasks.models import Task
from utils.pusher import notify_task_assigned
from utils.expo_push import send_expo_push_notification

User = get_user_model()

print("=" * 60)
print("PRODUCTION SERVER DIAGNOSTIC REPORT")
print("=" * 60)
print(f"Total Users: {User.objects.count()}")

print(f"\nRegistered Device Push Tokens: {DevicePushToken.objects.count()}")
for t in DevicePushToken.objects.all():
    print(f"  - User: {t.user.username} (ID: {t.user.id}) | Platform: {t.platform} | Device: {t.device_name} | Active: {t.is_active} | Token: {t.token}")

print(f"\nTotal Tasks in DB: {Task.objects.count()}")
latest_task = Task.objects.order_by('-created_at').first()
if latest_task:
    assignee = latest_task.assigned_to.username if latest_task.assigned_to else 'None'
    assigner = latest_task.assigned_by.username if latest_task.assigned_by else 'None'
    print(f"  - Latest Task #{latest_task.id}: \"{latest_task.title}\" | Assignee: {assignee} | Assigner: {assigner} | Status: {latest_task.status}")

# Send a real live test notification to all registered tokens
print("\n" + "=" * 60)
print("🚀 SENDING LIVE PUSH NOTIFICATION TEST FROM PRODUCTION EC2...")
print("=" * 60)

for t in DevicePushToken.objects.filter(is_active=True):
    print(f"[*] Sending alert to {t.user.username} ({t.device_name})...")
    send_expo_push_notification(
        user_ids=t.user_id,
        title="🔔 Life Planner CRM · Task Update",
        body=f"Hello {t.user.username}! Real push notification is 100% active from AWS Production Server! 🚀",
        data={"type": "task", "id": latest_task.id if latest_task else 1}
    )
print("[+] Dispatched! Check your Android phone screen / status bar!")
