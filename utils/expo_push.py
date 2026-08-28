# utils/expo_push.py
import requests
import json
from typing import List, Union
from celery import shared_task

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

@shared_task
def send_expo_push_notification(user_ids: Union[int, List[int]], title: str, body: str, data: dict = None, sound: str = "default"):
    """
    Sends native system push notifications to one or multiple users via Expo Push Service.
    Wakes devices, rings sound, shows on lock screen / notification tray even when app is closed.
    """
    try:
        from notifications.models import DevicePushToken
        
        if isinstance(user_ids, int):
            user_ids = [user_ids]
            
        device_tokens = list(
            DevicePushToken.objects.filter(
                user_id__in=user_ids, 
                is_active=True
            ).values_list('token', flat=True)
        )
        
        if not device_tokens:
            return
            
        messages = []
        for token in set(device_tokens):
            if not token or not isinstance(token, str):
                continue
            # Basic validation for Expo push tokens
            if not (token.startswith('ExponentPushToken[') or token.startswith('ExpoPushToken[')):
                continue
                
            messages.append({
                "to": token,
                "sound": sound,
                "title": title,
                "body": body,
                "data": data or {},
                "priority": "high",
                "channelId": "default",
                "_displayInForeground": True,
            })
            
        if not messages:
            return

        headers = {
            "Accept": "application/json",
            "Accept-encoding": "gzip, deflate",
            "Content-Type": "application/json",
        }
        
        # Expo accepts batch payloads up to 100 messages
        chunk_size = 100
        for i in range(0, len(messages), chunk_size):
            chunk = messages[i:i + chunk_size]
            response = requests.post(
                EXPO_PUSH_URL,
                data=json.dumps(chunk),
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                res_data = response.json().get('data', [])
                for idx, ticket in enumerate(res_data):
                    if ticket.get('status') == 'error':
                        details = ticket.get('details', {})
                        error_code = details.get('error')
                        if error_code == 'DeviceNotRegistered':
                            bad_token = chunk[idx]['to']
                            DevicePushToken.objects.filter(token=bad_token).delete()
            else:
                print(f"[Expo Push] API returned status {response.status_code}: {response.text}")
                
    except Exception as e:
        print(f"[Expo Push] Error sending notification: {e}")
