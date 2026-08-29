# utils/pusher.py
import pusher
import threading
from django.conf import settings

def get_pusher_client():
    try:
        return pusher.Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET,
            cluster=settings.PUSHER_CLUSTER,
            ssl=True
        )
    except Exception as e:
        print(f"[Pusher] Init failed: {e}")
        return None

pusher_client = get_pusher_client()

def _trigger_pusher_sync(channel: str, event: str, data: dict):
    if not pusher_client:
        return
    try:
        pusher_client.trigger(channel, event, data)
    except Exception as e:
        print(f"[Pusher] Trigger error: {e}")

class AsyncPusherTask:
    def __call__(self, *args, **kwargs):
        return _trigger_pusher_sync(*args, **kwargs)
        
    def delay(self, *args, **kwargs):
        t = threading.Thread(target=_trigger_pusher_sync, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t

trigger_pusher = AsyncPusherTask()

def _save_notification_sync(user_id, type, message, by=None, related_id=None, title=None):
    """Save notification to DB and automatically dispatch Expo Push notification to phone"""
    try:
        from notifications.models import Notification
        from django.contrib.auth import get_user_model
        from utils.expo_push import send_expo_push_notification
        User = get_user_model()
        user = User.objects.filter(id=user_id).first()
        if not user:
            return
        Notification.objects.create(user=user, type=type, message=message, by=by, related_id=related_id)
        
        push_title = title or f"LP CRM · {type.capitalize()}"
        send_expo_push_notification.delay(
            user_ids=user_id,
            title=push_title,
            body=message,
            data={"type": type, "id": related_id}
        )
    except Exception as e:
        print(f"[Notification] Save failed: {e}")

class AsyncSaveNotificationTask:
    def __call__(self, *args, **kwargs):
        return _save_notification_sync(*args, **kwargs)
        
    def delay(self, *args, **kwargs):
        t = threading.Thread(target=_save_notification_sync, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t

save_notification = AsyncSaveNotificationTask()



# ── Task helpers ──────────────────────────────────────

def notify_task_assigned(task, assigned_by):
    by_name = assigned_by.get_full_name() or assigned_by.username
    message = f"New task assigned to you: \"{task.title}\" by {by_name}"

    save_notification.delay(
        user_id=task.assigned_to.id,
        type='task',
        message=message,
        by=by_name,
        related_id=task.id,
        title="New Task Assigned"
    )

    trigger_pusher.delay(
        channel=f"private-user-{task.assigned_to.id}",
        event="task.assigned",
        data={
            "task_id":          task.id,
            "title":            task.title,
            "priority":         task.priority,
            "deadline":         str(task.deadline),
            "assigned_by_id":   assigned_by.id,
            "assigned_by_name": by_name,
            "message":          message,
        }
    )

def notify_task_status_updated(task, updated_by, old_status, new_status, notes):
    by_name = updated_by.get_full_name() or updated_by.username
    message = f"\"{task.title}\" marked as {new_status} by {by_name}"

    save_notification.delay(
        user_id=task.assigned_by.id,
        type='task',
        message=message,
        by=by_name,
        related_id=task.id,
        title="Task Status Updated"
    )

    trigger_pusher.delay(
        channel=f"private-user-{task.assigned_by.id}",
        event="task.status_updated",
        data={
            "task_id":         task.id,
            "title":           task.title,
            "old_status":      old_status,
            "new_status":      new_status,
            "updated_by_id":   updated_by.id,
            "updated_by_name": by_name,
            "notes":           notes or "",
            "message":         message,
        }
    )

def notify_task_remark(task, update):
    by_name = update.updated_by.get_full_name() or update.updated_by.username
    message = f"New remark on \"{task.title}\" by {by_name}"
    
    # Notify the person who needs attention
    target_user_id = task.requires_attention_from_id
    if not target_user_id:
        return
        
    save_notification.delay(
        user_id=target_user_id,
        type='task',
        message=message,
        by=by_name,
        related_id=task.id,
        title="Task Remark Added"
    )

    trigger_pusher.delay(
        channel=f"private-user-{target_user_id}",
        event="task.remark_added",
        data={
            "task_id":         task.id,
            "title":           task.title,
            "updated_by_id":   update.updated_by.id,
            "updated_by_name": by_name,
            "notes":           update.notes or "",
            "message":         message,
        }
    )

# ── Lead helpers ──────────────────────────────────────

def notify_lead_assigned(assignee, assigned_by, lead, assignment_type):
    by_name = assigned_by.get_full_name() or assigned_by.username
    message = (
        f"{'Lead' if assignment_type == 'PRIMARY' else 'Sub-lead'} "
        f"assigned to you: {lead.name} by {by_name}"
    )

    save_notification.delay(
        user_id=assignee.id,
        type='lead',
        message=message,
        by=by_name,
        related_id=lead.id,
        title="New Lead Assigned"
    )

    trigger_pusher.delay(
        channel=f"private-user-{assignee.id}",
        event="lead.assigned",
        data={
            "lead_id":          lead.id,
            "lead_name":        lead.name,
            "lead_phone":       lead.phone,
            "priority":         lead.priority,
            "status":           lead.status,
            "assignment_type":  assignment_type,
            "assigned_by_id":   assigned_by.id,
            "assigned_by_name": by_name,
            "message":          message,
        }
    )

def notify_lead_created(lead_data):
    trigger_pusher.delay(
        channel="private-leads-updates",
        event="lead.created",
        data={"lead": lead_data}
    )

def notify_lead_updated(lead_data):
    trigger_pusher.delay(
        channel="private-leads-updates",
        event="lead.updated",
        data={"lead": lead_data}
    )

def notify_lead_deleted(lead_id):
    trigger_pusher.delay(
        channel="private-leads-updates",
        event="lead.deleted",
        data={"lead_id": lead_id}
    )

# ── Penalty helpers ───────────────────────────────────

def notify_penalty_issued(penalty):
    if not penalty.user_id:
        return
    message = f"Penalty of ₹{penalty.amount} issued for: {penalty.act}"
    save_notification.delay(
        user_id=penalty.user_id,
        type='penalty',
        message=message,
        by="Management",
        related_id=penalty.id,
        title="Penalty Issued"
    )
    trigger_pusher.delay(
        channel=f"private-user-{penalty.user_id}",
        event="penalty.issued",
        data={
            "penalty_id": penalty.id,
            "amount": str(penalty.amount),
            "act": penalty.act,
            "message": message
        }
    )

# ── Chat helpers ──────────────────────────────────────

def notify_new_message(conversation_id, message_data):
    payload = dict(message_data)
    payload["conversation_id"] = conversation_id

    trigger_pusher.delay(
        channel=f"private-chat-{conversation_id}",
        event="new-message",
        data=payload
    )
    
    try:
        from chats.models import Conversation
        from utils.expo_push import send_expo_push_notification
        conversation = Conversation.objects.get(id=conversation_id)
        sender_id = message_data.get('sender', {}).get('id') if isinstance(message_data.get('sender'), dict) else message_data.get('sender_id')
        sender_name = message_data.get('sender', {}).get('username') if isinstance(message_data.get('sender'), dict) else (message_data.get('sender_name') or 'Someone')
        msg_text = message_data.get('text') or 'Sent an attachment'

        recipient_ids = [u.id for u in conversation.participants.all() if u.id != sender_id]

        for user_id in recipient_ids:
            trigger_pusher.delay(
                channel=f"private-user-{user_id}",
                event="chat.new_message",
                data=payload
            )

        if recipient_ids:
            chat_title = conversation.name if conversation.type == 'GROUP' else sender_name
            send_expo_push_notification.delay(
                user_ids=recipient_ids,
                title=f"Message from {chat_title}",
                body=msg_text,
                data={"type": "chat", "id": conversation_id}
            )
    except Exception as e:
        print(f"[Pusher] Error notifying participants: {e}")

def notify_message_deleted(conversation_id, message_id):
    trigger_pusher.delay(
        channel=f"private-chat-{conversation_id}",
        event="message-deleted",
        data={"message_id": message_id, "conversation_id": conversation_id}
    )

def notify_messages_delivered(conversation_id, user_id, message_ids):
    trigger_pusher.delay(
        channel=f"private-chat-{conversation_id}",
        event="messages-delivered",
        data={"conversation_id": conversation_id, "user_id": user_id, "message_ids": message_ids}
    )

def notify_messages_read(conversation_id, user_id, message_ids):
    trigger_pusher.delay(
        channel=f"private-chat-{conversation_id}",
        event="messages-read",
        data={"conversation_id": conversation_id, "user_id": user_id, "message_ids": message_ids}
    )

def notify_new_conversation(user_id, conversation_id, conversation_type, name=None):
    message = (
        f"Added to group: \"{name}\"" if conversation_type == 'GROUP'
        else "New direct message conversation"
    )

    save_notification.delay(
        user_id=user_id,
        type='chat',
        message=message,
        related_id=conversation_id,
        title="New Conversation"
    )

    data = {"conversation_id": conversation_id, "type": conversation_type}
    if name:
        data["name"] = name
    trigger_pusher.delay(
        channel=f"private-user-{user_id}",
        event="new-conversation",
        data=data
    )