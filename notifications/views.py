# notifications/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Notification

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifs = Notification.objects.filter(user=request.user)
        
        from reports.models import DailyReport
        from django.db.models import Q

        data = []
        for n in notifs:
            rel_id = n.related_id
            if not rel_id and (n.type == 'report' or 'report' in (n.message or '').lower()):
                if n.by:
                    first = n.by.split()[0] if n.by else ''
                    rep = DailyReport.objects.filter(
                        Q(name__icontains=first) | Q(user__first_name__icontains=first) | Q(user__username__icontains=first)
                    ).order_by('-created_at').first()
                    if rep:
                        rel_id = rep.id
                if not rel_id:
                    rep = DailyReport.objects.filter(user=request.user).order_by('-created_at').first()
                    if rep:
                        rel_id = rep.id

            data.append({
                'id': n.id,
                'type': n.type,
                'message': n.message,
                'by': n.by,
                'is_read': n.is_read,
                'related_id': rel_id,
                'time': n.created_at.isoformat(),
            })
        return Response(data)

class MarkNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'ok'})

class ClearNotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        Notification.objects.filter(user=request.user).delete()
        return Response({'status': 'ok'})