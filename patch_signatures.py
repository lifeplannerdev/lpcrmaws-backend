with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

fetch_code = '''    @action(detail=True, methods=['post'])
    def fetch_signatures(self, request, pk=None):
        account = self.get_object()
        from .gmail_client import GmailClient
        try:
            client = GmailClient(account)
            aliases = client.send_as_list()
            imported = 0
            for alias in aliases:
                if alias.get('signature'):
                    from .models import EmailSignature
                    sig, created = EmailSignature.objects.get_or_create(
                        name=f"Gmail: {alias['email']}",
                        owner=request.user,
                        defaults={'body_html': alias['signature']}
                    )
                    if not created and sig.body_html != alias['signature']:
                        sig.body_html = alias['signature']
                        sig.save(update_fields=['body_html'])
                    imported += 1
            return Response({'imported': imported, 'message': f'Synced {imported} signatures.'})
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

'''

views = views.replace('    def perform_create(self, serializer):\n        serializer.save(connected_by=self.request.user)', '    def perform_create(self, serializer):\n        serializer.save(connected_by=self.request.user)\n\n' + fetch_code)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
