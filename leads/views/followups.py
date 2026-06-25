import pandas as pd
import math
from datetime import date
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Count, Q as DQ
from django.shortcuts import get_object_or_404
from rest_framework import generics, filters, status
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from accounts.models import User, ActivityLog
from accounts.filters import CompanyFilterBackend
from utils.pusher import pusher_client, trigger_pusher
from utils import notify_lead_assigned
from leads.email_utils import send_conversion_email
from leads.models import (
    Lead, ProcessingUpdate, RemarkHistory, 
    LeadAssignment, FollowUp, LeadConversionDetail, WebhookLog
)
from leads.permissions import (
    CanAccessLeads, CanAssignLeads, CanViewAllLeads,
    CanModifyAllLeads, FULL_ACCESS_ROLES, MANAGER_ROLES,
    EXECUTIVE_ROLES, CanManageConversion,
)
from leads.serializers import (
    LeadListSerializer, LeadDetailSerializer, LeadCreateSerializer,
    ProcessingUpdateSerializer, LeadAssignSerializer,
    LeadAssignmentSerializer, LeadUpdateSerializer,
    BulkLeadCreateSerializer, FollowUpSerializer,
    LeadConversionDetailSerializer, WebhookLogSerializer,
)

# ── Helpers
def clean_value(val):
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

# ── Pagination
class LeadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class FollowUpListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        from accounts.permissions import has_dynamic_permission
        if (user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() or 
            has_dynamic_permission(user, 'leads:read_any') or 
            has_dynamic_permission(user, 'leads:read_tenant')):
            queryset = FollowUp.objects.all()
        else:
            queryset = FollowUp.objects.filter(assigned_to=user)

        # rest of your filters stay exactly the same ...
        lead_id       = request.query_params.get('lead')
        processing_student_id = request.query_params.get('processing_student')
        date          = request.query_params.get('date')
        start_date    = request.query_params.get('start_date')
        end_date      = request.query_params.get('end_date')
        status        = request.query_params.get('status')
        overdue       = request.query_params.get('overdue')
        followup_type = request.query_params.get('followup_type')
        priority      = request.query_params.get('priority')
        search        = request.query_params.get('search')

        if lead_id:
            queryset = queryset.filter(lead_id=lead_id)
        if processing_student_id:
            queryset = queryset.filter(processing_student_id=processing_student_id)
        if date:
            queryset = queryset.filter(follow_up_date=date)
        if start_date and end_date:
            queryset = queryset.filter(follow_up_date__range=[start_date, end_date])
        if status:
            queryset = queryset.filter(status=status)
        if overdue == 'true':
            queryset = queryset.filter(
                follow_up_date__lt=timezone.now().date(),
                status='pending'
            )
        if followup_type:
            queryset = queryset.filter(followup_type=followup_type)
        if priority:
            queryset = queryset.filter(priority=priority)
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(phone_number__icontains=search)
            )

        queryset = queryset.order_by('follow_up_date', 'follow_up_time')
        serializer = FollowUpSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = FollowUpSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(assigned_to=request.user)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

class FollowUpDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        from accounts.permissions import has_dynamic_permission
        if (user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() or 
            has_dynamic_permission(user, 'leads:read_any') or 
            has_dynamic_permission(user, 'leads:read_tenant')):
            return get_object_or_404(FollowUp, pk=pk)
        return get_object_or_404(FollowUp, pk=pk, assigned_to=user)

    def get(self, request, pk):
        followup = self.get_object(pk, request.user)
        serializer = FollowUpSerializer(followup)
        return Response(serializer.data)

    def put(self, request, pk):
        followup = self.get_object(pk, request.user)
        serializer = FollowUpSerializer(followup, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        followup = self.get_object(pk, request.user)
        followup.delete()
        return Response({"message": "Deleted successfully"}, status=204)

class TodayFollowUpsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()

        from accounts.permissions import has_dynamic_permission
        if (request.user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() or 
            has_dynamic_permission(request.user, 'leads:read_any') or 
            has_dynamic_permission(request.user, 'leads:read_tenant')):
            queryset = FollowUp.objects.filter(follow_up_date=today)
        else:
            queryset = FollowUp.objects.filter(
                assigned_to=request.user,
                follow_up_date=today
            )

        serializer = FollowUpSerializer(queryset, many=True)
        return Response(serializer.data)

class OverdueFollowUpsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()

        from accounts.permissions import has_dynamic_permission
        if (request.user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() or 
            has_dynamic_permission(request.user, 'leads:read_any') or 
            has_dynamic_permission(request.user, 'leads:read_tenant')):
            queryset = FollowUp.objects.filter(
                follow_up_date__lt=today,
                status='pending'
            )
        else:
            queryset = FollowUp.objects.filter(
                assigned_to=request.user,
                follow_up_date__lt=today,
                status='pending'
            )

        serializer = FollowUpSerializer(queryset, many=True)
        return Response(serializer.data)

