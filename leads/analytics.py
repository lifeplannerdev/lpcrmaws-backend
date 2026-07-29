from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.models import User
from leads.models import Lead, FollowUp, LeadConversionDetail
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

class UserPerformanceAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Allow passing user_id, or default to all active users if admin
        user_id = request.query_params.get('user_id')
        timeframe = request.query_params.get('timeframe', 'month') # day, week, month

        now = timezone.now()
        if timeframe == 'day':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == 'week':
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        else: # month
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Build query for users
        users = User.objects.filter(is_active=True)
        if user_id:
            users = users.filter(id=user_id)

        # Analytics
        data = []
        for user in users:
            # 1. Leads assigned within timeframe
            leads_assigned = Lead.objects.filter(
                assigned_to=user,
                created_at__gte=start_date
            ).count()

            # 2. Leads converted within timeframe
            leads_converted = LeadConversionDetail.objects.filter(
                updated_by=user,
                created_at__gte=start_date
            ).count()

            # 3. FollowUps completed (Touched)
            followups_completed = FollowUp.objects.filter(
                assigned_to=user,
                updated_at__gte=start_date,
                status__in=['contacted', 'not_interested']
            ).count()

            # 4. Overdue followups
            overdue_followups = FollowUp.objects.filter(
                assigned_to=user,
                status='pending',
                follow_up_date__lt=now.date()
            ).count()

            # 5. Current Pipeline (Leads assigned to user grouped by status)
            pipeline = list(Lead.objects.filter(
                assigned_to=user
            ).values('status').annotate(count=Count('id')))

            data.append({
                'user_id': user.id,
                'username': user.username,
                'full_name': user.get_full_name(),
                'metrics': {
                    'leads_assigned': leads_assigned,
                    'leads_converted': leads_converted,
                    'followups_completed': followups_completed,
                    'overdue_followups': overdue_followups,
                },
                'pipeline': pipeline
            })

        return Response(data)
