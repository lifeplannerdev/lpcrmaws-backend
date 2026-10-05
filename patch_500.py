with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

import_statement = "from django.db.models.functions import Coalesce\n"

if 'Coalesce' not in views:
    views = views.replace("from django.db.models import Q", "from django.db.models import Q\n" + import_statement)

replacement = '''        qs = EmailMessage.objects.all().select_related('account', 'template', 'created_by', 'student').prefetch_related('attachments').annotate(
            sort_time=Coalesce('sent_at', 'created_at')
        ).order_by('-sort_time')'''

views = views.replace(
    "qs = EmailMessage.objects.all().select_related('account', 'template', 'created_by', 'student').prefetch_related('attachments').order_by('-effective_time')",
    replacement
)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
