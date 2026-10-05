with open('mailcenter/services.py', 'r', encoding='utf-8') as f:
    services = f.read()

services = services.replace("max_results=25", "max_results=100")

with open('mailcenter/services.py', 'w', encoding='utf-8') as f:
    f.write(services)

with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

views = views.replace(
    "qs = EmailMessage.objects.all().select_related('account', 'template', 'created_by', 'student').prefetch_related('attachments')",
    "qs = EmailMessage.objects.all().select_related('account', 'template', 'created_by', 'student').prefetch_related('attachments').order_by('-effective_time')"
)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
