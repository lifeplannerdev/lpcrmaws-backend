
with open('mailcenter/services.py', 'r', encoding='utf-8') as f:
    services = f.read()

apply_vars_code = '''def apply_variables(message, user=None):
    from .variables import build_context, render_string
    if not message.student:
        return
    ctx = build_context(message.student, user or message.created_by)
    changed = False
    
    if message.subject:
        s, _, _ = render_string(message.subject, ctx, html=False)
        if s != message.subject:
            message.subject = s
            changed = True
            
    if message.body_html:
        b, _, _ = render_string(message.body_html, ctx, html=True)
        if b != message.body_html:
            message.body_html = b
            changed = True
            
    if message.signature_html:
        s, _, _ = render_string(message.signature_html, ctx, html=True)
        if s != message.signature_html:
            message.signature_html = s
            changed = True
            
    if changed:
        message.save(update_fields=['subject', 'body_html', 'signature_html'])

'''

services = services.replace('def sync_draft_to_gmail(message):', apply_vars_code + 'def sync_draft_to_gmail(message):')

services = services.replace('''def sync_draft_to_gmail(message):
    if message.state != EmailMessage.STATE_DRAFT or not message.account:
        return''', '''def sync_draft_to_gmail(message):
    if message.state != EmailMessage.STATE_DRAFT or not message.account:
        return
    apply_variables(message)''')

services = services.replace('''    def _release(error):
        EmailMessage.objects.filter(pk=message_id).update(state=EmailMessage.STATE_DRAFT, error=str(error)[:490])

    try:''', '''    def _release(error):
        EmailMessage.objects.filter(pk=message_id).update(state=EmailMessage.STATE_DRAFT, error=str(error)[:490])

    try:
        apply_variables(message, user)''')

with open('mailcenter/services.py', 'w', encoding='utf-8') as f:
    f.write(services)

