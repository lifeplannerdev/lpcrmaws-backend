with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

import re

new_download = '''    @action(detail=True, methods=['get'], permission_classes=[])
    def download(self, request, pk=None):
        token = request.GET.get('token')
        if not token:
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            from django.http import HttpResponse
            return HttpResponse('Unauthorized', status=401)
            
        from rest_framework_simplejwt.tokens import AccessToken
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.get(id=user_id)
        except Exception:
            from django.http import HttpResponse
            return HttpResponse('Unauthorized', status=401)
            
        from accounts.permissions import has_dynamic_permission
        if not (has_dynamic_permission(user, 'mail:use') or has_dynamic_permission(user, 'mail:manage')):
            from django.http import HttpResponse
            return HttpResponse('Forbidden', status=403)
            
        attachment = self.get_object()
        
        from django.http import HttpResponse, HttpResponseRedirect
        if attachment.gmail_attachment_id and not attachment.file:
            # Proxy from Gmail API
            from .gmail_client import GmailClient
            import base64
            try:
                client = GmailClient(attachment.message.account)
                res = client.get_attachment(attachment.message.gmail_message_id, attachment.gmail_attachment_id)
                data = base64.urlsafe_b64decode(res['data'])
                response = HttpResponse(data, content_type=attachment.content_type or 'application/octet-stream')
                response['Content-Disposition'] = f'inline; filename="{attachment.filename}"'
                return response
            except Exception as e:
                return HttpResponse(f"Failed to fetch attachment: {str(e)}", status=400)
                
        if attachment.file:
            return HttpResponseRedirect(attachment.file.url)
        elif attachment.student_document and attachment.student_document.document:
            return HttpResponseRedirect(attachment.student_document.document.url)
            
        return HttpResponse("Attachment file not found", status=404)
'''

# Find the download method block and replace it
views = re.sub(
    r'    @action\(detail=True, methods=\[\'get\'\]\)\n    def download\(self, request, pk=None\):.*?return Response\(\{"detail": "Attachment file not found"\}, status=status\.HTTP_404_NOT_FOUND\)',
    new_download.strip('\n'),
    views,
    flags=re.DOTALL
)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
