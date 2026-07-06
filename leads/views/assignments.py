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

class LeadAssignView(APIView):
    permission_classes = [CanAssignLeads]

    def post(self, request):
        serializer = LeadAssignSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        lead            = serializer.validated_data['lead']
        assignee        = serializer.validated_data['assignee']
        assignment_type = serializer.validated_data['assignment_type']
        notes           = serializer.validated_data.get('notes', '')

        if assignment_type == 'PRIMARY':
            lead.assigned_to       = assignee
            lead.assigned_by       = request.user
            lead.assigned_date     = timezone.now()
            lead.sub_assigned_to   = None
            lead.sub_assigned_by   = None
            lead.sub_assigned_date = None

        elif assignment_type == 'SUB':
            lead.sub_assigned_to   = assignee
            lead.sub_assigned_by   = request.user
            lead.sub_assigned_date = timezone.now()

        lead.save()

        LeadAssignment.objects.create(
            lead=lead,
            assigned_to=assignee,
            assigned_by=request.user,
            assignment_type=assignment_type,
            notes=notes,
        )

        if assignee != request.user:
            notify_lead_assigned(
                assignee=assignee,
                assigned_by=request.user,
                lead=lead,
                assignment_type=assignment_type,
            )

        return Response({
            'message': 'Lead assigned successfully',
            'lead': LeadDetailSerializer(lead).data,
        }, status=status.HTTP_200_OK)

class BulkLeadAssignView(APIView):
    permission_classes = [CanAssignLeads]

    def post(self, request):
        lead_ids       = request.data.get('lead_ids', [])
        assigned_to_id = request.data.get('assigned_to_id')
        notes          = request.data.get('notes', '')

        if not lead_ids or not isinstance(lead_ids, list):
            return Response(
                {'error': 'lead_ids must be a non-empty list'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not assigned_to_id:
            return Response(
                {'error': 'assigned_to_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user          = request.user
        success_count = 0
        failed_leads  = []
        assigned_summary = {}

        for lead_id in lead_ids:
            try:
                serializer = LeadAssignSerializer(
                    data={
                        'lead_id':        lead_id,
                        'assigned_to_id': assigned_to_id,
                        'notes':          notes,
                    },
                    context={'request': request},
                )

                if serializer.is_valid():
                    lead            = serializer.validated_data['lead']
                    assignee        = serializer.validated_data['assignee']
                    assignment_type = serializer.validated_data['assignment_type']

                    if assignment_type == 'PRIMARY':
                        lead.assigned_to       = assignee
                        lead.assigned_by       = user
                        lead.assigned_date     = timezone.now()
                        lead.sub_assigned_to   = None
                        lead.sub_assigned_by   = None
                        lead.sub_assigned_date = None
                    elif assignment_type == 'SUB':
                        lead.sub_assigned_to   = assignee
                        lead.sub_assigned_by   = user
                        lead.sub_assigned_date = timezone.now()

                    lead.save()

                    LeadAssignment.objects.create(
                        lead=lead,
                        assigned_to=assignee,
                        assigned_by=user,
                        assignment_type=assignment_type,
                        notes=notes,
                    )
                    success_count += 1

                    if assignee == user:
                        continue

                    uid = assignee.id
                    if uid not in assigned_summary:
                        assigned_summary[uid] = {
                            'user':  assignee,
                            'leads': [],
                            'type':  assignment_type,
                        }
                    assigned_summary[uid]['leads'].append({
                        'lead_id':   lead.id,
                        'lead_name': lead.name,
                        'priority':  lead.priority,
                    })

                else:
                    failed_leads.append({'lead_id': lead_id, 'errors': serializer.errors})

            except Exception as e:
                failed_leads.append({'lead_id': lead_id, 'error': str(e)})

        # 🔔 One grouped Pusher notification per assignee (self-assignments already excluded above)
        for uid, summary in assigned_summary.items():
            count = len(summary['leads'])
            trigger_pusher(
                channel=f'private-user-{uid}',
                event='lead.assigned',
                data={
                    'bulk':             True,
                    'count':            count,
                    'leads':            summary['leads'],
                    'assignment_type':  summary['type'],
                    'assigned_by_id':   user.id,
                    'assigned_by_name': user.get_full_name() or user.username,
                    'message': (
                        f"{count} lead{'s' if count > 1 else ''} assigned to you "
                        f"by {user.get_full_name() or user.username}"
                    ),
                }
            )

        return Response({
            'message':       f'Successfully assigned {success_count} leads',
            'success_count': success_count,
            'failed_count':  len(failed_leads),
            'failed_leads':  failed_leads,
        }, status=status.HTTP_200_OK)

class LeadAssignmentHistoryView(generics.ListAPIView):
    pagination_class   = None
    serializer_class   = LeadAssignmentSerializer
    permission_classes = [CanAccessLeads]

    def get_queryset(self):
        lead_id = self.kwargs.get('lead_id')
        lead    = get_object_or_404(Lead, id=lead_id)
        user    = self.request.user

        if user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists():
            return LeadAssignment.objects.filter(lead=lead).select_related('assigned_to', 'assigned_by').order_by('-timestamp')

        if lead.assigned_to != user and lead.sub_assigned_to != user:
            return LeadAssignment.objects.none()

        return LeadAssignment.objects.filter(lead=lead).select_related('assigned_to', 'assigned_by').order_by('-timestamp')

class AvailableUsersForAssignmentView(APIView):
    permission_classes = [CanAssignLeads]

    def get(self, request):
        ASSIGNABLE_ROLES = [
            'OPS', 'ADM_MANAGER', 'ADM_EXEC',
            'CM', 'BDM', 'FOE', 'ADM_COUNSELLOR',
            'FLAG COORDINATOR'
        ]
        users = User.objects.filter(
            db_roles__name__in=ASSIGNABLE_ROLES,
            is_active=True,
        ).annotate(
            role=models.F('db_roles__name')
        ).values(
            'id', 'username', 'email', 'role', 'first_name', 'last_name'
        ).order_by('role', 'first_name', 'last_name')

        return Response(list(users), status=status.HTTP_200_OK)

class UnassignLeadView(APIView):
    permission_classes = [CanAssignLeads]

    def post(self, request):
        lead_id       = request.data.get('lead_id')
        unassign_type = request.data.get('unassign_type', 'SUB')

        if not lead_id:
            return Response(
                {'error': 'lead_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return Response(
                {'error': 'Lead not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user

        if user.db_roles.filter(name='ADM_EXEC').exists():
            return Response(
                {'error': 'Admission Executives cannot unassign leads'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists():
            if unassign_type == 'PRIMARY':
                lead.assigned_to       = None
                lead.assigned_by       = None
                lead.assigned_date     = None
                lead.sub_assigned_to   = None
                lead.sub_assigned_by   = None
                lead.sub_assigned_date = None
            elif unassign_type == 'SUB':
                lead.sub_assigned_to   = None
                lead.sub_assigned_by   = None
                lead.sub_assigned_date = None

        elif user.db_roles.filter(name='ADM_MANAGER').exists():
            if lead.assigned_to != user:
                return Response(
                    {'error': 'You can only unassign leads assigned to you'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            lead.sub_assigned_to   = None
            lead.sub_assigned_by   = None
            lead.sub_assigned_date = None

        else:
            return Response(
                {'error': 'You do not have permission to unassign leads'},
                status=status.HTTP_403_FORBIDDEN,
            )

        lead.save()

        return Response({
            'message': 'Lead unassigned successfully',
            'lead':    LeadDetailSerializer(lead).data,
        }, status=status.HTTP_200_OK)

