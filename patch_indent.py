
with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

views = views.replace(
    '                qs = EmailMessage',
    '        qs = EmailMessage'
)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)

