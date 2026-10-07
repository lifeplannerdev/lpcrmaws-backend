with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

new_mixin = '''class MailPermissionMixin:
    """Ensure user has mail:use or mail:manage permission."""
    def check_permissions(self, request):
        if getattr(self, 'action', None) == 'download':
            return
        super().check_permissions(request)
        if not request.user or not request.user.is_authenticated:
            from rest_framework.exceptions import NotAuthenticated
            raise NotAuthenticated("Authentication credentials were not provided.")
        if not (has_dynamic_permission(request.user, 'mail:use') or has_dynamic_permission(request.user, 'mail:manage')):
            raise PermissionDenied("You do not have permission to access mail features.")'''

import re
views = re.sub(
    r'class MailPermissionMixin:.*?raise PermissionDenied\(\"You do not have permission to access mail features\.\"\)',
    new_mixin,
    views,
    flags=re.DOTALL
)

views = views.replace("@action(detail=True, methods=['get'], permission_classes=[])", "@action(detail=True, methods=['get'], permission_classes=[], authentication_classes=[])")

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
