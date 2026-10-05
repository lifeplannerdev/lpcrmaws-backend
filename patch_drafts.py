import re

# 1. Patch services.py
with open('mailcenter/services.py', 'r', encoding='utf-8') as f:
    services = f.read()

sync_draft_code = '''
def sync_draft_to_gmail(message):
    if message.state != EmailMessage.STATE_DRAFT or not message.account:
        return
    final_html = _compose_final_html(message)
    final_text = html_to_text(final_html)
    from email.utils import formataddr
    from_header = formataddr((message.account.display_name or '', message.account.email))
    thread_id, in_reply_to, references = _threading_for(message)
    raw = build_mime(
        from_header, message.to, message.cc, message.bcc, message.subject or '(no subject)',
        final_html, final_text, _attachment_payloads(message), in_reply_to, references,
    )
    from .gmail_client import GmailClient
    client = GmailClient(message.account)
    if message.gmail_draft_id:
        try:
            res = client.update_draft(message.gmail_draft_id, raw, thread_id)
            message.gmail_message_id = res.get('message', {}).get('id')
            message.save(update_fields=['gmail_message_id'])
            return
        except Exception:
            pass
    res = client.create_draft(raw, thread_id)
    message.gmail_draft_id = res.get('id')
    message.gmail_message_id = res.get('message', {}).get('id')
    message.save(update_fields=['gmail_draft_id', 'gmail_message_id'])

'''
services = services.replace('def send_draft(', sync_draft_code + 'def send_draft(')

delete_draft_code = '''        client = GmailClient(account)
        if message.gmail_draft_id:
            try:
                client.delete_draft(message.gmail_draft_id)
            except Exception:
                pass
        try:'''
services = services.replace('''        client = GmailClient(account)
        try:''', delete_draft_code)

with open('mailcenter/services.py', 'w', encoding='utf-8') as f:
    f.write(services)

# 2. Patch views.py
with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

views = views.replace('from .services import send_draft, sync_student, get_gmail_attachment', 'from .services import send_draft, sync_student, get_gmail_attachment, sync_draft_to_gmail')

create_code = '''    def perform_create(self, serializer):
        msg = serializer.save(created_by=self.request.user)
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Failed to sync draft to gmail: %s', e)'''
views = views.replace('''    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)''', create_code)

update_code = '''    def perform_update(self, serializer):
        message = self.get_object()
        if message.state != EmailMessage.STATE_DRAFT:
            raise PermissionDenied("Only drafts can be edited.")
        msg = serializer.save()
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Failed to sync draft to gmail: %s', e)'''
views = views.replace('''    def perform_update(self, serializer):
        # Ensure only drafts can be updated
        message = self.get_object()
        if message.state != EmailMessage.STATE_DRAFT:
            raise PermissionDenied("Only drafts can be edited.")
        serializer.save()''', update_code)

destroy_code = '''    def perform_destroy(self, instance):
        if instance.state == EmailMessage.STATE_DRAFT and instance.gmail_draft_id and instance.account:
            from .gmail_client import GmailClient
            try:
                client = GmailClient(instance.account)
                client.delete_draft(instance.gmail_draft_id)
            except Exception:
                pass
        instance.delete()'''
views = views.replace('''    @action(detail=True, methods=['post'])''', destroy_code + '\n\n    @action(detail=True, methods=[\'post\'])')

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
