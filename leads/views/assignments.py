import pandas as pd
import math
from datetime import date, timedelta, datetime
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Count, Max, Q as DQ
from django.shortcuts import get_object_or_404
from rest_framework import generics, filters, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from accounts.models import User, ActivityLog
from accounts.filters import CompanyFilterBackend
from accounts.permissions import has_dynamic_permission
from utils.pusher import pusher_client, trigger_pusher
from utils import notify_lead_assigned
from leads.email_utils import send_conversion_email
from leads.models import (
    Lead, ProcessingUpdate, RemarkHistory, 
    LeadAssignment, LeadAssignmentBatch, FollowUp, FollowUpHistory, LeadConversionDetail, WebhookLog
)
from leads.permissions import (
    is_full_access, is_full_access_or_manager,
    CanAccessLeads, CanAssignLeads, CanViewAllLeads,
    CanModifyAllLeads, FULL_ACCESS_ROLES, MANAGER_ROLES,
    EXECUTIVE_ROLES, CanManageConversion,
)
from leads.serializers import (
    LeadListSerializer, LeadDetailSerializer, LeadCreateSerializer,
    ProcessingUpdateSerializer, LeadAssignSerializer,
    LeadAssignmentSerializer, LeadAssignmentBatchSerializer, LeadUpdateSerializer,
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


def _build_batch_title_and_source(batch_label, total_leads, prev_owners, now, actor_name):
    """Build a human-readable batch title and source summary for an assignment lot."""
    owners_list = [o for o in prev_owners if o]
    if len(owners_list) == 1:
        source_summary = f"From {owners_list[0]}"
    elif len(owners_list) > 1:
        preview = ", ".join(owners_list[:2])
        extra = f" +{len(owners_list) - 2} more" if len(owners_list) > 2 else ""
        source_summary = f"From {preview}{extra}"
    else:
        source_summary = f"Assigned by {actor_name}"

    cleaned_label = (batch_label or '').strip()
    if cleaned_label:
        return cleaned_label[:255], source_summary[:255]

    ts_label = timezone.localtime(now).strftime('%d %b, %I:%M %p')
    noun = 'lead' if total_leads == 1 else 'leads'
    auto_title = f"{total_leads} {noun} ({source_summary}) · {ts_label}"
    return auto_title[:255], source_summary[:255]

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

        # Multi-tenant scope check
        if not has_dynamic_permission(request.user, 'staff:access_flag'):
            if lead.company != request.user.company:
                raise PermissionDenied(f"You do not have permission to assign leads for {lead.company}.")
            if assignee.company != request.user.company:
                raise PermissionDenied(f"You do not have permission to assign leads to staff in {assignee.company}.")

        now = timezone.now()
        now_str = timezone.localtime(now).strftime("%d/%m/%Y %H:%M")
        actor_name = request.user.get_full_name() or request.user.username
        assignee_name = assignee.get_full_name() or assignee.username
        prev_remarks = lead.remarks or ''

        if assignment_type == 'PRIMARY':
            old_name = (lead.assigned_to.get_full_name() or lead.assigned_to.username) if lead.assigned_to else 'Unassigned'
            lead.assigned_to       = assignee
            lead.assigned_by       = request.user
            lead.assigned_date     = now
            lead.sub_assigned_to   = None
            lead.sub_assigned_by   = None
            lead.sub_assigned_date = None

        elif assignment_type == 'SUB':
            old_name = (lead.sub_assigned_to.get_full_name() or lead.sub_assigned_to.username) if lead.sub_assigned_to else 'Unassigned'
            lead.sub_assigned_to   = assignee
            lead.sub_assigned_by   = request.user
            lead.sub_assigned_date = now

        transfer_msg = f"[{now_str}] Transferred from {old_name} to {assignee_name} by {actor_name}"
        if notes and notes.strip():
            transfer_msg += f" (Note: {notes.strip()})"
        new_remarks = f"{prev_remarks}\n\n{transfer_msg}".strip() if prev_remarks else transfer_msg
        lead.remarks = new_remarks
        # Single-lead transfers move a lead out of any prior Command Centre batch without creating a noisy 1-lead batch.
        lead.current_assignment_batch = None
        lead.save()

        RemarkHistory.objects.create(
            lead=lead,
            previous_remarks=prev_remarks or None,
            new_remarks=new_remarks,
            changed_by=request.user,
        )

        FollowUp.objects.filter(lead=lead, status='pending').update(assigned_to=assignee)

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
        lead_ids        = request.data.get('lead_ids', [])
        assigned_to_id  = request.data.get('assigned_to_id')
        notes           = request.data.get('notes', '')
        filters_applied = request.data.get('filters', {})
        strategy        = request.data.get('followup_strategy', 'keep')
        fu_type         = request.data.get('followup_type', 'call')
        fu_priority     = request.data.get('followup_priority', 'medium')
        fu_date         = request.data.get('followup_date')
        stagger_days    = int(request.data.get('stagger_days', 10))

        if not assigned_to_id:
            return Response(
                {'error': 'assigned_to_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            assignee = User.objects.get(id=assigned_to_id)
        except (User.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Assignee user not found.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # ── Permissions Check
        is_full_access = is_full_access_or_manager(user)
        is_adm_manager = user.db_roles.filter(name='ADM_MANAGER').exists()
        is_manager = user.db_roles.filter(name__in=MANAGER_ROLES).exists()

        req_assignment_type = request.data.get('assignment_type')
        if is_full_access:
            assignment_type = req_assignment_type if req_assignment_type in ['PRIMARY', 'SUB'] else 'PRIMARY'
        elif is_adm_manager or is_manager:
            assignment_type = 'SUB'
        else:
            assignment_type = 'PRIMARY'

        # Multi-tenant scoping
        if not has_dynamic_permission(user, 'staff:access_flag') and assignee.company != user.company:
            return Response({'error': f"Cannot assign leads to staff in {assignee.company}."}, status=status.HTTP_403_FORBIDDEN)

        base_qs = Lead.objects.all()
        if not has_dynamic_permission(user, 'staff:access_flag'):
            base_qs = base_qs.filter(company=user.company)
        if not is_full_access:
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
                src_val = str(filters_applied['source']).strip()
                src_lower = src_val.lower()
                if src_lower in ['voxbay', 'voxbay call']:
                    target_qs = target_qs.filter(models.Q(source__iexact='VOXBAY CALL') | models.Q(source__iexact='VOXBAY'))
                elif 'voxbay-editorial' in src_lower or 'voxbay_editorial' in src_lower or 'voxbay editorial' in src_lower:
                    target_qs = target_qs.filter(models.Q(source__iexact='VOXBAY-EDITORIAL') | models.Q(source__iexact='VOXBAY_EDITORIAL') | models.Q(source__iexact='VOXBAY EDITORIAL'))
                elif 'in house' in src_lower or 'in_house' in src_lower:
                    target_qs = target_qs.filter(models.Q(source__iexact='IN HOUSE SOCIAL MEDIA') | models.Q(source__iexact='IN_HOUSE_SOCIAL_MEDIA'))
                else:
                    target_qs = target_qs.filter(source__iexact=src_val)

            if filters_applied.get('company'):
                target_qs = target_qs.filter(company__iexact=filters_applied['company'])

            if filters_applied.get('created_at__gte'):
                target_qs = target_qs.filter(created_at__date__gte=filters_applied['created_at__gte'])

            if filters_applied.get('created_at__lte'):
                target_qs = target_qs.filter(created_at__date__lte=filters_applied['created_at__lte'])

            all_lead_ids = list(target_qs.values_list('id', flat=True))
        elif isinstance(lead_ids, list) and len(lead_ids) > 0:
            all_lead_ids = list(base_qs.filter(id__in=lead_ids).values_list('id', flat=True))
        else:
            return Response(
                {'error': 'lead_ids must be a non-empty list or all_matching'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_leads = len(all_lead_ids)
        if total_leads == 0:
            return Response({
                'message':       'No leads matched for transfer',
                'success_count': 0,
                'failed_count':  0,
                'failed_leads':  [],
            }, status=status.HTTP_200_OK)

        now = timezone.now()
        today = timezone.localtime(now).date()
        BATCH_SIZE = 1000
        sample_leads_for_pusher = []
        batch_label = request.data.get('batch_label', '')
        actor_name = user.get_full_name() or user.username

        # Inspect sample source owners for automatic batch title
        sample_owner_qs = Lead.objects.filter(id__in=all_lead_ids[:50]).select_related('assigned_to', 'sub_assigned_to')
        prev_owners = []
        seen_owners = set()
        batch_company = assignee.company or user.company or 'LP'
        for s_lead in sample_owner_qs:
            if s_lead.company:
                batch_company = s_lead.company
            prev_u = s_lead.sub_assigned_to if assignment_type == 'SUB' else s_lead.assigned_to
            o_name = (prev_u.get_full_name() or prev_u.username) if prev_u else 'Unassigned'
            if o_name not in seen_owners:
                seen_owners.add(o_name)
                prev_owners.append(o_name)

        title, source_summary = _build_batch_title_and_source(
            batch_label=batch_label,
            total_leads=total_leads,
            prev_owners=prev_owners,
            now=now,
            actor_name=actor_name,
        )

        req_source_type = request.data.get('source_type')
        batch_source_type = req_source_type if req_source_type in ('COMMAND_CENTRE', 'BULK_REASSIGN') else 'COMMAND_CENTRE'

        with transaction.atomic():
            assignment_batch = LeadAssignmentBatch.objects.create(
                company=batch_company,
                source_type=batch_source_type,
                title=title,
                assigned_to=assignee,
                assigned_by=user,
                assignment_type=assignment_type,
                followup_strategy=strategy,
                notes=notes or '',
                source_summary=source_summary,
                total_leads_count=total_leads,
            )

            for batch_start in range(0, total_leads, BATCH_SIZE):
                batch_ids = all_lead_ids[batch_start:batch_start + BATCH_SIZE]

                # Fetch necessary metadata for assignment notes and follow-ups
                batch_leads = list(
                    Lead.objects.filter(id__in=batch_ids)
                    .select_related('assigned_to', 'sub_assigned_to')
                )

                now_str = timezone.localtime(now).strftime("%d/%m/%Y %H:%M")
                assignee_name = assignee.get_full_name() or assignee.username

                leads_to_update = []
                remark_history_to_create = []
                assignments_to_create = []

                for lead in batch_leads:
                    prev_remarks = lead.remarks or ''
                    current_notes = notes

                    if assignment_type == 'PRIMARY':
                        old_name = (lead.assigned_to.get_full_name() or lead.assigned_to.username) if lead.assigned_to else 'Unassigned'
                        if lead.assigned_to:
                            current_notes = f"{current_notes} [Transferred from {old_name}]".strip()
                    else:
                        old_name = (lead.sub_assigned_to.get_full_name() or lead.sub_assigned_to.username) if lead.sub_assigned_to else 'Unassigned'
                        if lead.sub_assigned_to:
                            current_notes = f"{current_notes} [Transferred from {old_name}]".strip()

                    transfer_msg = f"[{now_str}] Transferred from {old_name} to {assignee_name} by {actor_name}"
                    if notes and notes.strip() and notes.strip() != 'Bulk transfer via Lead Command Centre':
                        transfer_msg += f" (Note: {notes.strip()})"

                    new_remarks = f"{prev_remarks}\n\n{transfer_msg}".strip() if prev_remarks else transfer_msg
                    lead.remarks = new_remarks
                    lead.current_assignment_batch = assignment_batch

                    if assignment_type == 'SUB':
                        lead.sub_assigned_to = assignee
                        lead.sub_assigned_by = user
                        lead.sub_assigned_date = now
                    else:
                        lead.assigned_to = assignee
                        lead.assigned_by = user
                        lead.assigned_date = now
                        lead.sub_assigned_to = None
                        lead.sub_assigned_by = None
                        lead.sub_assigned_date = None

                    leads_to_update.append(lead)

                    remark_history_to_create.append(RemarkHistory(
                        lead_id=lead.id,
                        previous_remarks=prev_remarks or None,
                        new_remarks=new_remarks,
                        changed_by=user,
                    ))

                    assignments_to_create.append(LeadAssignment(
                        batch=assignment_batch,
                        lead_id=lead.id,
                        assigned_to=assignee,
                        assigned_by=user,
                        assignment_type=assignment_type,
                        notes=current_notes,
                    ))

                    if len(sample_leads_for_pusher) < 20:
                        sample_leads_for_pusher.append({
                            'lead_id':   lead.id,
                            'lead_name': lead.name,
                            'priority':  lead.priority,
                        })

                # 1. Bulk update Lead ownership and remarks
                if assignment_type == 'SUB':
                    update_fields = ['sub_assigned_to', 'sub_assigned_by', 'sub_assigned_date', 'remarks', 'current_assignment_batch']
                else:
                    update_fields = [
                        'assigned_to', 'assigned_by', 'assigned_date',
                        'sub_assigned_to', 'sub_assigned_by', 'sub_assigned_date',
                        'remarks', 'current_assignment_batch'
                    ]
                Lead.objects.bulk_update(leads_to_update, update_fields, batch_size=BATCH_SIZE)

                # 2. Bulk create RemarkHistory and LeadAssignment audit entries
                RemarkHistory.objects.bulk_create(remark_history_to_create, batch_size=BATCH_SIZE)
                LeadAssignment.objects.bulk_create(assignments_to_create, batch_size=BATCH_SIZE)

                # 3. Follow-up scheduling strategy
                if strategy == 'keep':
                    FollowUp.objects.filter(lead_id__in=batch_ids, status='pending').update(assigned_to=assignee)
                elif strategy == 'none':
                    FollowUp.objects.filter(lead_id__in=batch_ids, status='pending').update(
                        status='not_interested',
                        notes='Resolved upon transfer (no follow-up)'
                    )
                elif strategy == 'overdue':
                    FollowUp.objects.filter(lead_id__in=batch_ids, status='pending').update(status='not_interested')
                    yesterday = today - timedelta(days=1)
                    fu_to_create = [
                        FollowUp(
                            lead_id=lead.id,
                            phone_number=lead.phone or '',
                            name=lead.name or '',
                            follow_up_date=yesterday,
                            followup_type=fu_type,
                            priority=fu_priority,
                            status='pending',
                            assigned_to=assignee,
                            notes='Priority queue transfer follow-up'
                        )
                        for lead in batch_leads
                    ]
                    FollowUp.objects.bulk_create(fu_to_create, batch_size=BATCH_SIZE)
                elif strategy == 'specific_date':
                    FollowUp.objects.filter(lead_id__in=batch_ids, status='pending').update(status='not_interested')
                    target_d = datetime.strptime(fu_date, '%Y-%m-%d').date() if fu_date else today
                    fu_to_create = [
                        FollowUp(
                            lead_id=lead.id,
                            phone_number=lead.phone or '',
                            name=lead.name or '',
                            follow_up_date=target_d,
                            followup_type=fu_type,
                            priority=fu_priority,
                            status='pending',
                            assigned_to=assignee,
                            notes='Scheduled transfer follow-up'
                        )
                        for lead in batch_leads
                    ]
                    FollowUp.objects.bulk_create(fu_to_create, batch_size=BATCH_SIZE)
                elif strategy == 'stagger':
                    FollowUp.objects.filter(lead_id__in=batch_ids, status='pending').update(status='not_interested')
                    max_stagger = max(1, stagger_days)
                    fu_to_create = []
                    for idx_in_batch, lead in enumerate(batch_leads):
                        global_idx = batch_start + idx_in_batch
                        offset = 1 + (global_idx % max_stagger)
                        target_d = today + timedelta(days=offset)
                        fu_to_create.append(FollowUp(
                            lead_id=lead.id,
                            phone_number=lead.phone or '',
                            name=lead.name or '',
                            follow_up_date=target_d,
                            followup_type=fu_type,
                            priority=fu_priority,
                            status='pending',
                            assigned_to=assignee,
                            notes=f'Staggered transfer follow-up (day +{offset})'
                        ))
                    FollowUp.objects.bulk_create(fu_to_create, batch_size=BATCH_SIZE)

            # Activity Log
            try:
                ActivityLog.objects.create(
                    user=user,
                    action='LEAD_BULK_ASSIGNED',
                    entity_type='Lead',
                    entity_name=f"{total_leads} Leads",
                    details={
                        'assigned_to': assignee.get_full_name() or assignee.username,
                        'strategy':    strategy,
                        'count':       total_leads,
                    }
                )
            except Exception:
                pass

        # 🔔 Grouped Pusher notification with capped payload
        if assignee != user:
            try:
                trigger_pusher(
                    channel=f'private-user-{assignee.id}',
                    event='lead.assigned',
                    data={
                        'bulk':             True,
                        'count':            total_leads,
                        'leads':            sample_leads_for_pusher,
                        'assignment_type':  assignment_type,
                        'assigned_by_id':   user.id,
                        'assigned_by_name': user.get_full_name() or user.username,
                        'message': (
                            f"{total_leads} lead{'s' if total_leads > 1 else ''} assigned to you "
                            f"by {user.get_full_name() or user.username}"
                        ),
                    }
                )
            except Exception:
                pass

        return Response({
            'message':          f'Successfully assigned {total_leads} leads',
            'success_count':    total_leads,
            'failed_count':     0,
            'failed_leads':     [],
            'assignment_batch': LeadAssignmentBatchSerializer(assignment_batch).data,
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
        if not has_dynamic_permission(user, 'staff:access_flag'):
            base_qs = base_qs.filter(company=user.company)

        if not is_full_access_or_manager(user):
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
                src_val = str(filters_applied['source']).strip()
                src_lower = src_val.lower()
                if src_lower in ['voxbay', 'voxbay call']:
                    target_qs = target_qs.filter(models.Q(source__iexact='VOXBAY CALL') | models.Q(source__iexact='VOXBAY'))
                elif 'voxbay-editorial' in src_lower or 'voxbay_editorial' in src_lower or 'voxbay editorial' in src_lower:
                    target_qs = target_qs.filter(models.Q(source__iexact='VOXBAY-EDITORIAL') | models.Q(source__iexact='VOXBAY_EDITORIAL') | models.Q(source__iexact='VOXBAY EDITORIAL'))
                elif 'in house' in src_lower or 'in_house' in src_lower:
                    target_qs = target_qs.filter(models.Q(source__iexact='IN HOUSE SOCIAL MEDIA') | models.Q(source__iexact='IN_HOUSE_SOCIAL_MEDIA'))
                else:
                    target_qs = target_qs.filter(source__iexact=src_val)

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

        if not has_dynamic_permission(user, 'staff:access_flag') and lead.company != user.company:
            return LeadAssignment.objects.none()

        if is_full_access(user):
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

        requested_company = request.query_params.get('company')
        if requested_company:
            if requested_company != request.user.company and not has_dynamic_permission(request.user, 'staff:access_flag'):
                raise PermissionDenied(f"You do not have permission to access {requested_company} staff.")
            qs = qs.filter(company=requested_company)
        else:
            qs = qs.filter(company=request.user.company)

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

        if not has_dynamic_permission(user, 'staff:access_flag') and lead.company != user.company:
            return Response(
                {'error': f"You do not have permission to unassign leads for {lead.company}."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.db_roles.filter(name='ADM_EXEC').exists():
            return Response(
                {'error': 'Admission Executives cannot unassign leads'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if is_full_access(user):
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


class EmployeeFollowUpSummaryView(APIView):
    """
    Returns the latest/furthest scheduled follow-up date and workload summary
    for a specific employee or all employees.
    """
    permission_classes = [CanAccessLeads]

    def get(self, request):
        employee_id = request.query_params.get('employee_id')
        from_date_str = request.query_params.get('from_date')

        target_name = "All Counsellors"
        base_fup_qs = FollowUp.objects.filter(status='pending')
        if not has_dynamic_permission(request.user, 'staff:access_flag'):
            base_fup_qs = base_fup_qs.filter(assigned_to__company=request.user.company)

        if employee_id and employee_id != 'all':
            try:
                target_user = User.objects.get(id=employee_id)
                target_name = target_user.get_full_name() or target_user.username
                base_fup_qs = base_fup_qs.filter(
                    DQ(assigned_to_id=employee_id) | DQ(lead__assigned_to_id=employee_id)
                )
            except (User.DoesNotExist, ValueError):
                return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)

        summary = base_fup_qs.aggregate(
            max_date=Max('follow_up_date'),
            total_pending=Count('id')
        )

        max_date = summary.get('max_date')
        today = timezone.localtime(timezone.now()).date()

        if max_date:
            suggested_next_date = max_date + timedelta(days=1)
            # If furthest date is in the past (overdue), suggest tomorrow
            if suggested_next_date <= today:
                suggested_next_date = today + timedelta(days=1)
        else:
            suggested_next_date = today + timedelta(days=1)

        count_on_from_date = 0
        if from_date_str:
            try:
                from_date_obj = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                count_on_from_date = base_fup_qs.filter(follow_up_date=from_date_obj).count()
            except ValueError:
                pass

        return Response({
            'employee_id': employee_id or 'all',
            'employee_name': target_name,
            'latest_followup_date': max_date.strftime('%Y-%m-%d') if max_date else None,
            'suggested_next_date': suggested_next_date.strftime('%Y-%m-%d'),
            'total_pending_followups': summary.get('total_pending') or 0,
            'count_on_from_date': count_on_from_date,
            'from_date': from_date_str,
        }, status=status.HTTP_200_OK)


class BulkRescheduleFollowUpsView(APIView):
    """
    Bulk reschedules all leads with pending follow-ups from any day (from_date)
    to a target day (to_date), or for a list of lead_ids.
    Zero follow-ups remain pending on from_date.
    """
    permission_classes = [CanAssignLeads]

    def post(self, request):
        user = request.user
        from_date_str = request.data.get('from_date')
        to_date_str = request.data.get('to_date')
        employee_id = request.data.get('employee_id')
        lead_ids = request.data.get('lead_ids', [])
        stagger_days = int(request.data.get('stagger_days', 1) or 1)
        notes = request.data.get('notes', '')

        if not to_date_str:
            return Response({'error': 'Target date (to_date) is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid target date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        from_date = None
        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Invalid source date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check permissions
        is_full_access = is_full_access_or_manager(user)

        # Query pending follow-ups to reschedule
        fup_qs = FollowUp.objects.filter(status='pending')
        if not has_dynamic_permission(user, 'staff:access_flag'):
            fup_qs = fup_qs.filter(assigned_to__company=user.company)

        if not is_full_access:
            fup_qs = fup_qs.filter(DQ(assigned_to=user) | DQ(lead__assigned_to=user))

        # Mode A: Specific Lead IDs provided
        if isinstance(lead_ids, list) and len(lead_ids) > 0 and lead_ids != 'all_matching':
            fup_qs = fup_qs.filter(lead_id__in=lead_ids)
            if from_date:
                fup_qs = fup_qs.filter(follow_up_date=from_date)

        # Mode B: Reschedule by Source Date & Employee
        elif from_date:
            fup_qs = fup_qs.filter(follow_up_date=from_date)
            if employee_id and employee_id != 'all':
                fup_qs = fup_qs.filter(
                    DQ(assigned_to_id=employee_id) | DQ(lead__assigned_to_id=employee_id)
                )
        else:
            return Response({'error': 'Either from_date or a list of lead_ids must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        followups_to_update = list(fup_qs.select_related('lead', 'assigned_to'))
        count = len(followups_to_update)

        # In case specific lead_ids were selected, but some didn't have a pending followup
        created_count = 0
        if isinstance(lead_ids, list) and len(lead_ids) > 0 and lead_ids != 'all_matching':
            covered_lead_ids = set(f.lead_id for f in followups_to_update if f.lead_id)
            missing_lead_ids = [lid for lid in lead_ids if lid not in covered_lead_ids]
            if missing_lead_ids:
                if not has_dynamic_permission(user, 'staff:access_flag'):
                    missing_leads = Lead.objects.filter(id__in=missing_lead_ids, company=user.company).select_related('assigned_to')
                else:
                    missing_leads = Lead.objects.filter(id__in=missing_lead_ids).select_related('assigned_to')
                new_fups = []
                for idx, ld in enumerate(missing_leads):
                    shift = (idx % stagger_days) if stagger_days > 1 else 0
                    scheduled_date = to_date + timedelta(days=shift)
                    assignee = ld.assigned_to or user
                    new_fup = FollowUp(
                        lead=ld,
                        phone_number=ld.phone or '',
                        name=ld.name or 'Lead',
                        follow_up_date=scheduled_date,
                        followup_type='call',
                        priority=ld.priority.lower() if ld.priority else 'medium',
                        status='pending',
                        assigned_to=assignee,
                        notes=f"Follow-up scheduled via Command Centre to {scheduled_date}. {notes}".strip()
                    )
                    new_fups.append(new_fup)
                if new_fups:
                    FollowUp.objects.bulk_create(new_fups)
                    created_count = len(new_fups)

        if count == 0 and created_count == 0:
            return Response({
                'message': 'No pending follow-ups found to reschedule matching the criteria.',
                'rescheduled_count': 0
            }, status=status.HTTP_200_OK)

        now_str = timezone.localtime(timezone.now()).strftime('%d-%b-%Y %I:%M %p')
        operator_name = user.get_full_name() or user.username

        with transaction.atomic():
            history_entries = []
            for idx, fup in enumerate(followups_to_update):
                old_date_str = fup.follow_up_date.strftime('%d-%b-%Y') if fup.follow_up_date else 'Unknown'
                shift = (idx % stagger_days) if stagger_days > 1 else 0
                new_date = to_date + timedelta(days=shift)
                
                fup.follow_up_date = new_date
                audit_note = f"[Rescheduled from {old_date_str} to {new_date.strftime('%d-%b-%Y')} by {operator_name} on {now_str}]"
                if notes:
                    audit_note += f" Reason: {notes}"
                
                fup.notes = f"{fup.notes}\n{audit_note}".strip() if fup.notes else audit_note
                fup.save(update_fields=['follow_up_date', 'notes', 'updated_at'])

                history_entries.append(FollowUpHistory(
                    followup=fup,
                    old_status='pending',
                    new_status='pending',
                    changed_by=user,
                    notes=f"Rescheduled date from {old_date_str} to {new_date.strftime('%d-%b-%Y')}"
                ))

            if history_entries:
                FollowUpHistory.objects.bulk_create(history_entries)

            total_affected = count + created_count
            ActivityLog.objects.create(
                user=user,
                action='FOLLOWUPS_BULK_RESCHEDULED',
                entity_type='FollowUp',
                entity_name=f"{total_affected} Follow-ups",
                description=f"{total_affected} follow-ups were rescheduled to {to_date_str} by {operator_name}.",
                metadata={
                    'rescheduled_count': count,
                    'created_count': created_count,
                    'from_date': from_date_str,
                    'to_date': to_date_str,
                    'employee_id': employee_id,
                    'notes': notes
                }
            )

        return Response({
            'message': f"Successfully rescheduled {count + created_count} follow-up{'s' if (count + created_count) != 1 else ''} to {to_date.strftime('%d-%b-%Y')}.",
            'rescheduled_count': count,
            'created_count': created_count,
            'total_affected': count + created_count,
            'from_date': from_date_str,
            'to_date': to_date_str,
        }, status=status.HTTP_200_OK)


class AssignmentBatchListView(generics.ListAPIView):
    """List assignment batches visible to the current user, with live active/progress counts."""
    permission_classes = [CanAccessLeads]
    serializer_class = LeadAssignmentBatchSerializer
    pagination_class = LeadPagination

    def get_queryset(self):
        user = self.request.user
        today = timezone.localtime(timezone.now()).date()

        qs = LeadAssignmentBatch.objects.select_related('assigned_to', 'assigned_by').filter(
            source_type__in=['COMMAND_CENTRE', 'BULK_REASSIGN'],
            assigned_by__isnull=False,
        )

        if not has_dynamic_permission(user, 'staff:access_flag'):
            if getattr(user, 'company', None):
                qs = qs.filter(company=user.company)

        if not is_full_access(user):
            qs = qs.filter(assigned_to=user)
        else:
            assigned_to_param = self.request.query_params.get('assigned_to')
            if assigned_to_param and assigned_to_param != 'all':
                qs = qs.filter(assigned_to_id=assigned_to_param)
            elif self.request.query_params.get('include_inactive_staff', 'false').lower() != 'true':
                qs = qs.filter(assigned_to__is_active=True)

        company_param = self.request.query_params.get('company')
        if company_param:
            qs = qs.filter(company__iexact=company_param)

        search_param = (self.request.query_params.get('search') or '').strip()
        if search_param:
            qs = qs.filter(
                DQ(title__icontains=search_param) |
                DQ(notes__icontains=search_param) |
                DQ(source_summary__icontains=search_param) |
                DQ(assigned_by__first_name__icontains=search_param) |
                DQ(assigned_by__last_name__icontains=search_param) |
                DQ(assigned_to__first_name__icontains=search_param) |
                DQ(assigned_to__last_name__icontains=search_param)
            )

        qs = qs.annotate(
            active_count=Count('active_leads', distinct=True),
            new_count=Count(
                'active_leads',
                filter=DQ(active_leads__status__in=['ENQUIRY', 'JOB_ENQUIRY', 'B2B']),
                distinct=True,
            ),
            contacted_count=Count(
                'active_leads',
                filter=DQ(active_leads__status__in=['COLD', 'WARM', 'HOT', 'CONTACTED', 'QUALIFIED']),
                distinct=True,
            ),
            converted_count=Count(
                'active_leads',
                filter=DQ(active_leads__status__in=['CONVERTED', 'REGISTERED']),
                distinct=True,
            ),
            overdue_followups_count=Count(
                'active_leads',
                filter=DQ(
                    active_leads__followups__status='pending',
                    active_leads__followups__follow_up_date__lt=today,
                ),
                distinct=True,
            ),
        )

        include_empty = self.request.query_params.get('include_empty', 'true').lower() == 'true'
        if not include_empty:
            qs = qs.filter(active_count__gt=0)

        return qs.order_by('-created_at')


class AssignmentBatchLeadsView(generics.ListAPIView):
    """List leads belonging to a specific assignment batch with full follow-up annotations."""
    permission_classes = [CanAccessLeads]
    serializer_class = LeadListSerializer
    pagination_class = LeadPagination

    def _get_batch(self):
        if not hasattr(self, '_cached_batch'):
            batch = get_object_or_404(LeadAssignmentBatch, pk=self.kwargs['batch_id'])
            user = self.request.user
            if not has_dynamic_permission(user, 'staff:access_flag') and getattr(user, 'company', None):
                if batch.company != user.company:
                    raise PermissionDenied("You do not have permission to view this assignment batch.")
            if not is_full_access(user) and batch.assigned_to_id != user.id:
                raise PermissionDenied("You do not have permission to view another staff member's assignment batch.")
            self._cached_batch = batch
        return self._cached_batch

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['assignment_batch_id'] = self._get_batch().id
        return ctx

    def get_queryset(self):
        batch = self._get_batch()
        include_reassigned = self.request.query_params.get('include_reassigned_out', 'false').lower() == 'true'

        if include_reassigned:
            qs = Lead.objects.filter(assignment_history__batch=batch)
        else:
            qs = Lead.objects.filter(current_assignment_batch=batch)

        status_param = self.request.query_params.get('status')
        if status_param and status_param != 'all':
            qs = qs.filter(status__iexact=status_param)

        priority_param = self.request.query_params.get('priority')
        if priority_param and priority_param != 'all':
            qs = qs.filter(priority__iexact=priority_param)

        search_param = (self.request.query_params.get('search') or '').strip()
        if search_param:
            qs = qs.filter(
                DQ(name__icontains=search_param) |
                DQ(phone__icontains=search_param) |
                DQ(email__icontains=search_param) |
                DQ(remarks__icontains=search_param)
            )

        from django.db.models import Subquery, OuterRef
        next_fu_sub = FollowUp.objects.filter(
            lead=OuterRef('pk'),
            status='pending',
        ).order_by('follow_up_date', 'follow_up_time').values('follow_up_date')[:1]

        last_fu_sub = FollowUp.objects.filter(
            lead=OuterRef('pk'),
            status__in=['contacted', 'completed'],
        ).order_by('-follow_up_date', '-follow_up_time').values('follow_up_date')[:1]

        return (
            qs.select_related('assigned_to', 'assigned_by', 'sub_assigned_to', 'sub_assigned_by')
            .distinct()
            .annotate(
                next_follow_up_date=Subquery(next_fu_sub),
                last_follow_up_date=Subquery(last_fu_sub),
            )
            .order_by('-priority', '-assigned_date', '-created_at')
        )


