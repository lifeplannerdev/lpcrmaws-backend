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

def notify_task_submitted_for_approval(task, submitted_by, notes=""):
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    User = get_user_model()
    by_name = submitted_by.get_full_name() or submitted_by.username
    message = f"Task \"{task.title}\" marked as complete by {by_name} and is waiting for Managing Director approval."

    target_users = set()
    if task.assigned_by_id and task.assigned_by_id != submitted_by.id:
        target_users.add(task.assigned_by_id)

    md_users = User.objects.filter(
        Q(db_roles__name__in=['MANAGING_DIRECTOR', 'managing_director', 'MD', 'Managing Director']) |
        Q(role__iexact='MANAGING_DIRECTOR') |
        Q(is_superuser=True)
    ).values_list('id', flat=True)
    for u_id in md_users:
        if u_id != submitted_by.id:
            target_users.add(u_id)

    for uid in target_users:
        save_notification.delay(
            user_id=uid,
            type='task',
            message=message,
            by=by_name,
            related_id=task.id,
            title="Task Completion Needs Approval"
        )
        trigger_pusher.delay(
            channel=f"private-user-{uid}",
            event="task.status_updated",
            data={
                "task_id":         task.id,
                "title":           task.title,
                "old_status":      task.status,
                "new_status":      'PENDING_APPROVAL',
                "updated_by_id":   submitted_by.id,
                "updated_by_name": by_name,
                "notes":           notes or "",
                "message":         message,
            }
        )

def notify_task_approval_decision(task, decided_by, approved, notes="", new_deadline=None):
    by_name = decided_by.get_full_name() or decided_by.username
    if approved:
        message = f"Task \"{task.title}\" completion was approved by {by_name}."
        title = "Task Approved"
        new_status = 'COMPLETED'
    else:
        dl_text = f" New deadline: {new_deadline}." if new_deadline else ""
        reason = f" Reason: {notes}." if notes else ""
        message = f"Task \"{task.title}\" completion was rejected by {by_name}. Task remains in progress.{reason}{dl_text}"
        title = "Task Completion Rejected"
        new_status = 'IN_PROGRESS'

    target_user_id = task.assigned_to_id
    if target_user_id:
        save_notification.delay(
            user_id=target_user_id,
            type='task',
            message=message,
            by=by_name,
            related_id=task.id,
            title=title
        )
        trigger_pusher.delay(
            channel=f"private-user-{target_user_id}",
            event="task.status_updated",
            data={
                "task_id":         task.id,
                "title":           task.title,
                "new_status":      new_status,
                "updated_by_id":   decided_by.id,
                "updated_by_name": by_name,
                "notes":           notes or "",
                "message":         message,
                "new_deadline":    str(new_deadline) if new_deadline else None,
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


# ── Reminder helpers ──────────────────────────────────

def notify_reminder_assigned(reminder, assigned_by):
    by_name = assigned_by.get_full_name() or assigned_by.username
    message = f"New reminder assigned to you: \"{reminder.title}\" (Due: {reminder.deadline or reminder.reminder_date}) by {by_name}"

    save_notification.delay(
        user_id=reminder.user.id,
        type='reminder',
        message=message,
        by=by_name,
        related_id=reminder.id,
        title="New Reminder Assigned"
    )

    trigger_pusher.delay(
        channel=f"private-user-{reminder.user.id}",
        event="reminder.assigned",
        data={
            "reminder_id": reminder.id,
            "title": reminder.title,
            "priority": reminder.priority,
            "reminder_date": str(reminder.reminder_date),
            "deadline": str(reminder.deadline) if reminder.deadline else None,
            "assigned_by_id": assigned_by.id,
            "assigned_by_name": by_name,
            "message": message,
        }
    )

def notify_reminder_submitted(reminder, submitted_by):
    from accounts.models import User
    by_name = submitted_by.get_full_name() or submitted_by.username
    message = f"Reminder work submitted for verification: \"{reminder.title}\" by {by_name}"

    # Notify all reminder admins or the creator
    recipients = set()
    if reminder.created_by and reminder.created_by.id != submitted_by.id:
        recipients.add(reminder.created_by.id)

    admin_ids = list(User.objects.filter(
        db_roles__permissions__name='processing:reminders_admin',
        is_active=True
    ).values_list('id', flat=True))
    for aid in admin_ids:
        if aid != submitted_by.id:
            recipients.add(aid)

    for uid in recipients:
        save_notification.delay(
            user_id=uid,
            type='reminder',
            message=message,
            by=by_name,
            related_id=reminder.id,
            title="Reminder Submitted For Approval"
        )
        trigger_pusher.delay(
            channel=f"private-user-{uid}",
            event="reminder.status_updated",
            data={
                "reminder_id": reminder.id,
                "title": reminder.title,
                "status": "PENDING_APPROVAL",
                "submitted_by_name": by_name,
                "message": message,
            }
        )

def notify_reminder_approved(reminder, approved_by):
    by_name = approved_by.get_full_name() or approved_by.username
    message = f"Reminder approved and completed: \"{reminder.title}\" by {by_name}"

    save_notification.delay(
        user_id=reminder.user.id,
        type='reminder',
        message=message,
        by=by_name,
        related_id=reminder.id,
        title="Reminder Approved"
    )

    trigger_pusher.delay(
        channel=f"private-user-{reminder.user.id}",
        event="reminder.status_updated",
        data={
            "reminder_id": reminder.id,
            "title": reminder.title,
            "status": "COMPLETED",
            "approved_by_name": by_name,
            "message": message,
        }
    )

def notify_reminder_rejected(reminder, rejected_by, reason):
    by_name = rejected_by.get_full_name() or rejected_by.username
    message = f"Reminder returned to In Progress by {by_name}. Revision needed: {reason}"

    save_notification.delay(
        user_id=reminder.user.id,
        type='reminder',
        message=message,
        by=by_name,
        related_id=reminder.id,
        title="Reminder Needs Revision"
    )

    trigger_pusher.delay(
        channel=f"private-user-{reminder.user.id}",
        event="reminder.status_updated",
        data={
            "reminder_id": reminder.id,
            "title": reminder.title,
            "status": "IN_PROGRESS",
            "rejection_reason": reason,
            "rejected_by_name": by_name,
            "message": message,
        }
    )

def notify_reminder_comment(reminder, author, notes):
    by_name = author.get_full_name() or author.username
    message = f"New remark on reminder \"{reminder.title}\" from {by_name}: {notes[:80]}"

    # Send to the other party (assignee or creator)
    target_ids = set()
    if reminder.user.id != author.id:
        target_ids.add(reminder.user.id)
    if reminder.created_by.id != author.id:
        target_ids.add(reminder.created_by.id)

    for uid in target_ids:
        save_notification.delay(
            user_id=uid,
            type='reminder',
            message=message,
            by=by_name,
            related_id=reminder.id,
            title="Reminder Update"
        )
        trigger_pusher.delay(
            channel=f"private-user-{uid}",
            event="reminder.remark_added",
            data={
                "reminder_id": reminder.id,
                "title": reminder.title,
                "author_name": by_name,
                "notes": notes,
                "message": message,
            }
        )