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
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        call_uuid = data.get('call_uuid') or data.get('callUuid')
        lead_id = data.get('lead')
        user_notes = data.get('notes') or ''
        duration = data.get('duration')
        recording_url = data.get('recording_url')
        
        # 1. Check if a FollowUp already exists for this call_uuid or recent call by this user
        existing_followup = None
        if call_uuid and lead_id:
            existing_followup = FollowUp.objects.filter(lead_id=lead_id, notes__contains=str(call_uuid)).first()
        elif call_uuid:
            existing_followup = FollowUp.objects.filter(notes__contains=str(call_uuid)).first()
            
        if not existing_followup and lead_id and request.user and request.user.is_authenticated:
            # Check if there is a recent FollowUp created for this lead by this user in the last 15 minutes
            recent_cutoff = timezone.now() - timezone.timedelta(minutes=15)
            existing_followup = FollowUp.objects.filter(
                lead_id=lead_id,
                assigned_to=request.user,
                followup_type='call',
                created_at__gte=recent_cutoff
            ).first()

        if existing_followup:
            # Update existing follow-up without disturbing user remarks or CDR details
            existing_notes = (existing_followup.notes or '').strip()
            user_notes_clean = user_notes.strip()
            
            merged_notes = existing_notes
            if user_notes_clean:
                if user_notes_clean not in existing_notes:
                    if existing_notes:
                        merged_notes = f"{user_notes_clean}\n\n{existing_notes}"
                    else:
                        merged_notes = user_notes_clean
            
            if call_uuid and str(call_uuid) not in merged_notes:
                merged_notes = f"{merged_notes}\nCall UUID: {call_uuid}" if merged_notes else f"Call UUID: {call_uuid}"
                
            if recording_url and str(recording_url) not in merged_notes:
                merged_notes = f"{merged_notes}\nRecording: {recording_url}" if merged_notes else f"Recording: {recording_url}"

            if duration and f"Duration: {duration}s" not in merged_notes:
                if "Duration:" in merged_notes:
                    import re
                    merged_notes = re.sub(r'Duration:\s*[^\n]+', f'Duration: {duration}s', merged_notes)
                else:
                    merged_notes = f"{merged_notes}\nDuration: {duration}s"

            existing_followup.notes = merged_notes
            if data.get('follow_up_date'):
                existing_followup.follow_up_date = data.get('follow_up_date')
            if data.get('follow_up_time') is not None:
                existing_followup.follow_up_time = data.get('follow_up_time') or None
            if data.get('status'):
                existing_followup.status = data.get('status')
            if data.get('priority'):
                existing_followup.priority = data.get('priority')
            if data.get('name') and not existing_followup.name:
                existing_followup.name = data.get('name')
                
            existing_followup.save()
            serializer = FollowUpSerializer(existing_followup)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # 2. If no existing follow-up, create new unified record
        final_notes = user_notes.strip()
        if duration and f"Duration: {duration}s" not in final_notes:
            final_notes = f"{final_notes}\nDuration: {duration}s" if final_notes else f"Duration: {duration}s"
        if recording_url and str(recording_url) not in final_notes:
            final_notes = f"{final_notes}\nRecording: {recording_url}" if final_notes else f"Recording: {recording_url}"
        if call_uuid and str(call_uuid) not in final_notes:
            final_notes = f"{final_notes}\nCall UUID: {call_uuid}" if final_notes else f"Call UUID: {call_uuid}"
            
        data['notes'] = final_notes
        serializer = FollowUpSerializer(data=data)
        if serializer.is_valid():
            serializer.save(assigned_to=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

