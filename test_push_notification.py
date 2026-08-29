import os
import sys
import django
import json
import requests

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from notifications.models import DevicePushToken, Notification
from django.contrib.auth import get_user_model
from utils.expo_push import EXPO_PUSH_URL

User = get_user_model()

def test_send_push(username=None, title="Life Planner CRM Test Alert", body="Real Android Push Notification test successful!", data=None):
    print("=" * 60)
    print("[PUSH TEST] LIFE PLANNER CRM - REAL PUSH NOTIFICATION TESTER")
    print("=" * 60)
    
    tokens_query = DevicePushToken.objects.filter(is_active=True)
    if username:
        user = User.objects.filter(username=username).first()
        if not user:
            print(f"[-] User '{username}' not found.")
            return False
        tokens_query = tokens_query.filter(user=user)
        print(f"[*] Target User: {username} (ID: {user.id})")
    else:
        print("[*] Target: All registered active devices")

    tokens = list(tokens_query)
    print(f"[*] Found {len(tokens)} active registered device token(s):")
    for t in tokens:
        print(f"  - User: {t.user.username} | Platform: {t.platform} | Device: {t.device_name} | Token: {t.token[:25]}...")

    if not tokens:
        print("\n[*] Notice: 0 tokens in local DB (Phone registered with live production API).")
        print("[*] Using active device token: ExponentPushToken[Wsns9uN1-LQ6BY_Hm8rmm8]")
        tokens = [type('TokenObj', (object,), {
            'token': 'ExponentPushToken[Wsns9uN1-LQ6BY_Hm8rmm8]',
            'user': type('UserObj', (object,), {'username': 'Phone Device'})(),
            'platform': 'android',
            'device_name': 'Connected Android Device'
        })()]

    messages = []
    for t in tokens:
        messages.append({
            "to": t.token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {"type": "test", "message": "Test notification payload"},
            "priority": "high",
            "channelId": "default",
            "_displayInForeground": True,
        })

    headers = {
        "Accept": "application/json",
        "Accept-encoding": "gzip, deflate",
        "Content-Type": "application/json",
    }

    print(f"\n[*] Dispatching {len(messages)} notification(s) to Expo Push Server...")
    try:
        response = requests.post(EXPO_PUSH_URL, json=messages, headers=headers, timeout=10)
        print(f"[*] Expo API Response Status: {response.status_code}")
        res_data = response.json()
        print(f"[*] Response Payload: {json.dumps(res_data, indent=2)}")

        for idx, ticket in enumerate(res_data.get('data', [])):
            status = ticket.get('status')
            if status == 'ok':
                print(f"[+] Notification #{idx+1} successfully accepted by Expo! (Receipt ID: {ticket.get('id')})")
                print("    Check your Android phone screen / status bar!")
            else:
                print(f"[-] Notification #{idx+1} failed: {ticket.get('message')} - {ticket.get('details')}")
        return True
    except Exception as e:
        print(f"[-] Error sending push notification: {e}")
        return False

if __name__ == "__main__":
    target_user = sys.argv[1] if len(sys.argv) > 1 else None
    test_send_push(username=target_user)

