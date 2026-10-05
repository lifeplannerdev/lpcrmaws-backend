with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

sync_all_code = '''    @action(detail=False, methods=['post'])
    def sync_all(self, request):
        from .tasks import sync_emails_for_all_students_task
        try:
            sync_emails_for_all_students_task.delay()
            return Response({"detail": "Sync process started in the background."})
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
'''

views = views.replace("    @action(detail=False, methods=['post'])\n    def sync(self, request):", sync_all_code + "\n    @action(detail=False, methods=['post'])\n    def sync(self, request):")

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
