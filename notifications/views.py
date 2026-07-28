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
        data = [{
            'id': n.id,
            'type': n.type,
            'message': n.message,
            'by': n.by,
            'is_read': n.is_read,
            'related_id': n.related_id,
            'time': n.created_at.isoformat(),
        } for n in notifs]
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