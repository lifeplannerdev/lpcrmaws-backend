import pandas as pd
import math
from datetime import date, timedelta, datetime
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
        filters_applied = request.data.get('filters', {})
        strategy       = request.data.get('followup_strategy', 'keep')
        fu_type        = request.data.get('followup_type', 'call')
        fu_priority    = request.data.get('followup_priority', 'medium')
        fu_date        = request.data.get('followup_date')
        stagger_days   = int(request.data.get('stagger_days', 10))

        if not assigned_to_id:
            return Response(
                {'error': 'assigned_to_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        base_qs = Lead.objects.all()
        if not (user.db_roles.filter(name__in=FULL_ACCESS_ROLES + ['SENIOR ADM', 'SENIOR_ADM', 'ADM_MANAGER']).exists() or 
                has_dynamic_permission(user, 'leads:read_any') or 
                has_dynamic_permission(user, 'leads:read_tenant') or
                has_dynamic_permission(user, 'staff_analysis:admin')):
            base_qs = base_qs.filter(
                models.Q(assigned_to=user) | models.Q(sub_assigned_to=user)
            )

        if lead_ids == 'all_matching' or (isinstance(lead_ids, list) and len(lead_ids) == 0 and filters_applied):
            target_qs = base_qs
            emp_status = filters_applied.get('employee_status')
            if emp_status == 'active':
                target_qs = target_qs.filter(assigned_to__isnull=False, assigned_to__is_active=True)
            elif emp_status == 'inactive':
                target_qs = target_qs.filter(assigned_to__isnull=False, assigned_to__is_active=False)
            elif emp_status == 'unassigned':
                target_qs = target_qs.filter(assigned_to__isnull=True)
            elif emp_status == 'inactive_or_unassigned':
                target_qs = target_qs.filter(models.Q(assigned_to__is_active=False) | models.Q(assigned_to__isnull=True))

            if filters_applied.get('active_pipeline_only') or filters_applied.get('exclude_closed_converted'):
                target_qs = target_qs.exclude(
                    status__in=[
                        'CLOSED', 'CONVERTED', 'REGISTERED', 'LOST', 'NOT_INTERESTED', 'CNR',
                        'closed', 'converted', 'registered', 'lost', 'not_interested', 'not interested', 'cnr', 'could not reach'
                    ]
                )

            if filters_applied.get('assigned_to') and filters_applied.get('assigned_to') != 'all':
                target_qs = target_qs.filter(assigned_to_id=filters_applied['assigned_to'])

            if filters_applied.get('status') and filters_applied.get('status') != 'all':
                st = filters_applied['status']
                st_clean = st.strip().upper().replace(' ', '_')
                if st_clean in ['NOT_INTERESTED', 'NOTINTERESTED']:
                    target_qs = target_qs.filter(
                        models.Q(status__iexact='NOT_INTERESTED') |
                        models.Q(status__iexact='not interested') |
                        models.Q(status__iexact='not_interested') |
                        models.Q(status__iexact='NOT INTERESTED')
                    )
                elif st_clean in ['CNR', 'COULD_NOT_REACH', 'COULDNOTREACH']:
                    target_qs = target_qs.filter(
                        models.Q(status__iexact='CNR') |
                        models.Q(status__iexact='could not reach') |
                        models.Q(status__iexact='could_not_reach') |
                        models.Q(status__iexact='COULD NOT REACH')
                    )
                else:
                    target_qs = target_qs.filter(
                        models.Q(status__iexact=st) | models.Q(status__iexact=st_clean)
                    )

            if filters_applied.get('priority') and filters_applied.get('priority') != 'all':
                target_qs = target_qs.filter(priority__iexact=filters_applied['priority'])

            if filters_applied.get('source') and filters_applied.get('source') != 'all':
                target_qs = target_qs.filter(source=filters_applied['source'])

            if filters_applied.get('company'):
                target_qs = target_qs.filter(company__iexact=filters_applied['company'])

            if filters_applied.get('created_at__gte'):
                target_qs = target_qs.filter(created_at__date__gte=filters_applied['created_at__gte'])

            if filters_applied.get('created_at__lte'):
                target_qs = target_qs.filter(created_at__date__lte=filters_applied['created_at__lte'])

            lead_ids = list(target_qs.values_list('id', flat=True))
        elif not lead_ids or not isinstance(lead_ids, list):
            return Response(
                {'error': 'lead_ids must be a non-empty list or all_matching'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success_count = 0
        failed_leads  = []
        assigned_summary = {}

        try:
            assignee = User.objects.get(id=assigned_to_id)
        except User.DoesNotExist:
            return Response({'error': 'Assignee user not found.'}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localtime(timezone.now()).date()

        for idx, lead_id in enumerate(lead_ids):
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
                    assignment_type = serializer.validated_data.get('assignment_type', 'PRIMARY')

                    current_notes = notes
                    if assignment_type == 'PRIMARY' and lead.assigned_to:
                        old_name = lead.assigned_to.get_full_name() or lead.assigned_to.username
                        current_notes = f"{current_notes} [Transferred from {old_name}]".strip()
                    elif assignment_type == 'SUB' and lead.sub_assigned_to:
                        old_name = lead.sub_assigned_to.get_full_name() or lead.sub_assigned_to.username
                        current_notes = f"{current_notes} [Transferred from {old_name}]".strip()

                    # Always make the new assignee PRIMARY when transferred from command centre
                    lead.assigned_to       = assignee
                    lead.assigned_by       = user
                    lead.assigned_date     = timezone.now()
                    lead.sub_assigned_to   = None
                    lead.sub_assigned_by   = None
                    lead.sub_assigned_date = None
                    lead.save()

                    LeadAssignment.objects.create(
                        lead=lead,
                        assigned_to=assignee,
                        assigned_by=user,
                        assignment_type='PRIMARY',
                        notes=current_notes,
                    )
                    success_count += 1

                    # ── Follow-up scheduling strategy
                    if strategy == 'keep':
                        FollowUp.objects.filter(lead=lead, status='pending').update(assigned_to=assignee)
                    elif strategy == 'none':
                        FollowUp.objects.filter(lead=lead, status='pending').update(
                            status='not_interested',
                            notes='Resolved upon transfer (no follow-up)'
                        )
                    elif strategy == 'overdue':
                        FollowUp.objects.filter(lead=lead, status='pending').update(status='not_interested')
                        yesterday = today - timedelta(days=1)
                        FollowUp.objects.create(
                            lead=lead,
                            phone_number=lead.phone or '',
                            name=lead.name,
                            follow_up_date=yesterday,
                            followup_type=fu_type,
                            priority=fu_priority,
                            status='pending',
                            assigned_to=assignee,
                            notes='Priority queue transfer follow-up'
                        )
                    elif strategy == 'specific_date':
                        FollowUp.objects.filter(lead=lead, status='pending').update(status='not_interested')
                        target_d = datetime.strptime(fu_date, '%Y-%m-%d').date() if fu_date else today
                        FollowUp.objects.create(
                            lead=lead,
                            phone_number=lead.phone or '',
                            name=lead.name,
                            follow_up_date=target_d,
                            followup_type=fu_type,
                            priority=fu_priority,
                            status='pending',
                            assigned_to=assignee,
                            notes='Scheduled transfer follow-up'
                        )
                    elif strategy == 'stagger':
                        FollowUp.objects.filter(lead=lead, status='pending').update(status='not_interested')
                        offset = 1 + (idx % max(1, stagger_days))
                        target_d = today + timedelta(days=offset)
                        FollowUp.objects.create(
                            lead=lead,
                            phone_number=lead.phone or '',
                            name=lead.name,
                            follow_up_date=target_d,
                            followup_type=fu_type,
                            priority=fu_priority,
                            status='pending',
                            assigned_to=assignee,
                            notes=f'Staggered transfer follow-up (day +{offset})'
                        )

                    if assignee == user:
                        continue

                    uid = assignee.id
                    if uid not in assigned_summary:
                        assigned_summary[uid] = {
                            'user':  assignee,
                            'leads': [],
                            'type':  'PRIMARY',
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

        # 🔔 One grouped Pusher notification per assignee
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


class BulkLeadCloseView(APIView):
    permission_classes = [CanAssignLeads]

    def post(self, request):
        user              = request.user
        lead_ids          = request.data.get('lead_ids')
        reason            = request.data.get('reason', 'Closed via Lead Command Centre')
        remarks           = request.data.get('remarks', '')
        resolve_followups = request.data.get('resolve_followups', True)
        filters_applied   = request.data.get('filters', {})

        base_qs = Lead.objects.all()
        if not (user.db_roles.filter(name__in=FULL_ACCESS_ROLES + ['SENIOR ADM', 'SENIOR_ADM', 'ADM_MANAGER']).exists() or 
                has_dynamic_permission(user, 'leads:read_any') or 
                has_dynamic_permission(user, 'leads:read_tenant') or
                has_dynamic_permission(user, 'staff_analysis:admin')):
            base_qs = base_qs.filter(
                models.Q(assigned_to=user) | models.Q(sub_assigned_to=user)
            )

        if lead_ids == 'all_matching' or (isinstance(lead_ids, list) and len(lead_ids) == 0 and filters_applied):
            target_qs = base_qs
            emp_status = filters_applied.get('employee_status')
            if emp_status == 'active':
                target_qs = target_qs.filter(assigned_to__isnull=False, assigned_to__is_active=True)
            elif emp_status == 'inactive':
                target_qs = target_qs.filter(assigned_to__isnull=False, assigned_to__is_active=False)
            elif emp_status == 'unassigned':
                target_qs = target_qs.filter(assigned_to__isnull=True)
            elif emp_status == 'inactive_or_unassigned':
                target_qs = target_qs.filter(models.Q(assigned_to__is_active=False) | models.Q(assigned_to__isnull=True))

            if filters_applied.get('active_pipeline_only') or filters_applied.get('exclude_closed_converted'):
                target_qs = target_qs.exclude(
                    status__in=[
                        'CLOSED', 'CONVERTED', 'REGISTERED', 'LOST', 'NOT_INTERESTED', 'CNR',
                        'closed', 'converted', 'registered', 'lost', 'not_interested', 'not interested', 'cnr', 'could not reach'
                    ]
                )

            if filters_applied.get('assigned_to') and filters_applied.get('assigned_to') != 'all':
                target_qs = target_qs.filter(assigned_to_id=filters_applied['assigned_to'])

            if filters_applied.get('status') and filters_applied.get('status') != 'all':
                st = filters_applied['status']
                st_clean = st.strip().upper().replace(' ', '_')
                if st_clean in ['NOT_INTERESTED', 'NOTINTERESTED']:
                    target_qs = target_qs.filter(
                        models.Q(status__iexact='NOT_INTERESTED') |
                        models.Q(status__iexact='not interested') |
                        models.Q(status__iexact='not_interested') |
                        models.Q(status__iexact='NOT INTERESTED')
                    )
                elif st_clean in ['CNR', 'COULD_NOT_REACH', 'COULDNOTREACH']:
                    target_qs = target_qs.filter(
                        models.Q(status__iexact='CNR') |
                        models.Q(status__iexact='could not reach') |
                        models.Q(status__iexact='could_not_reach') |
                        models.Q(status__iexact='COULD NOT REACH')
                    )
                else:
                    target_qs = target_qs.filter(
                        models.Q(status__iexact=st) | models.Q(status__iexact=st_clean)
                    )

            if filters_applied.get('priority') and filters_applied.get('priority') != 'all':
                target_qs = target_qs.filter(priority__iexact=filters_applied['priority'])

            if filters_applied.get('source') and filters_applied.get('source') != 'all':
                target_qs = target_qs.filter(source=filters_applied['source'])

            if filters_applied.get('company'):
                target_qs = target_qs.filter(company__iexact=filters_applied['company'])

            if filters_applied.get('created_at__gte'):
                target_qs = target_qs.filter(created_at__date__gte=filters_applied['created_at__gte'])

            if filters_applied.get('created_at__lte'):
                target_qs = target_qs.filter(created_at__date__lte=filters_applied['created_at__lte'])

        elif isinstance(lead_ids, list) and len(lead_ids) > 0:
            target_qs = base_qs.filter(id__in=lead_ids)
        else:
            return Response({'error': 'No leads specified to close.'}, status=status.HTTP_400_BAD_REQUEST)

        # Exclude leads that are already closed
        leads_to_close = target_qs.exclude(status__in=['CLOSED', 'closed'])
        count = leads_to_close.count()

        if count == 0:
            return Response({'message': 'No open leads to close matching the selection.', 'closed_count': 0}, status=status.HTTP_200_OK)

        lead_ids_list = list(leads_to_close.values_list('id', flat=True))

        with transaction.atomic():
            Lead.objects.filter(id__in=lead_ids_list).update(status='CLOSED')

            if resolve_followups:
                FollowUp.objects.filter(lead_id__in=lead_ids_list, status='pending').update(
                    status='not_interested',
                    notes=f"Closed via Command Centre: {reason}. {remarks}".strip()
                )

            ActivityLog.objects.create(
                user=user,
                action='LEAD_BULK_CLOSED',
                entity_type='Lead',
                entity_name=f"{count} Leads",
                description=f"{count} leads were bulk-closed by {user.get_full_name() or user.username}. Reason: {reason}",
                metadata={'lead_count': count, 'reason': reason, 'remarks': remarks}
            )

        return Response({
            'message': f"Successfully closed {count} lead{'s' if count > 1 else ''}.",
            'closed_count': count,
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
        from leads.permissions import LEAD_ACCESS_ROLES
        
        # Include LEAD_ACCESS_ROLES plus any explicitly assigned roles like FLAG COORDINATOR
        ASSIGNABLE_ROLES = list(set(LEAD_ACCESS_ROLES + ['FLAG COORDINATOR']))
        
        team_filter = request.query_params.get('team', 'Sales')
        qs = User.objects.filter(
            db_roles__name__in=ASSIGNABLE_ROLES,
            is_active=True,
        )
        if team_filter and team_filter.lower() != 'all':
            qs = qs.filter(team__iexact=team_filter)

        users = qs.annotate(
            role=models.F('db_roles__name')
        ).values(
            'id', 'username', 'email', 'role', 'first_name', 'last_name', 'team'
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

