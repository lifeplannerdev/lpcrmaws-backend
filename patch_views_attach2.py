with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

views = views.replace(
    "res = client.get_attachment(attachment.message.gmail_message_id, attachment.gmail_attachment_id)\n                data = base64.urlsafe_b64decode(res['data'])",
    "data = client.get_attachment(attachment.message.gmail_message_id, attachment.gmail_attachment_id)"
)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
