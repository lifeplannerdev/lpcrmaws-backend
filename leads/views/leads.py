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
from accounts.permissions import has_dynamic_permission
from accounts.filters import CompanyFilterBackend
from utils.pusher import pusher_client, trigger_pusher
from utils import notify_lead_assigned
from leads.email_utils import send_conversion_email
from leads.models import (
    Lead, ProcessingUpdate, RemarkHistory, 
    LeadAssignment, FollowUp, LeadConversionDetail, WebhookLog,
    LeadDocument
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
    LeadDocumentSerializer,
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

class LeadListView(generics.ListAPIView):
    serializer_class = LeadListSerializer
    permission_classes = [CanAccessLeads]
    pagination_class = LeadPagination

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
        CompanyFilterBackend,
    ]
    filterset_fields = {
        'priority':          ['exact'],
        'source':            ['exact'],
        'processing_status': ['exact'],
        'assigned_to':       ['exact', 'isnull'],
        'sub_assigned_to':   ['exact'],
        'campaign_name':     ['exact', 'icontains'],
        'adset_name':        ['exact', 'icontains'],
        'ad_name':           ['exact', 'icontains'],
        'created_at':        ['date', 'gte', 'lte'],
    }
    search_fields   = ['name', 'phone', 'email', 'program', 'campaign_name']
    ordering_fields = ['created_at', 'priority', 'updated_at']
    ordering        = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        base_qs = Lead.objects.select_related(
            'assigned_to', 'assigned_by',
            'sub_assigned_to', 'sub_assigned_by',
        )

        if (user.db_roles.filter(name__in=FULL_ACCESS_ROLES + ['SENIOR ADM', 'SENIOR_ADM', 'ADM_MANAGER']).exists() or 
            has_dynamic_permission(user, 'leads:read_any') or 
            has_dynamic_permission(user, 'leads:read_tenant') or
            has_dynamic_permission(user, 'staff_analysis:admin')) :
            perm_qs = base_qs.all()
        else:
            perm_qs = base_qs.filter(
                models.Q(assigned_to=user) |
                models.Q(sub_assigned_to=user)
            )
        
        from django.utils import timezone
        if self.request.query_params.get('daily_agenda') == 'true':
            agenda_date_str = self.request.query_params.get('agenda_date')
            if agenda_date_str:
                from datetime import datetime
                try:
                    target_date = datetime.strptime(agenda_date_str, '%Y-%m-%d').date()
                except ValueError:
                    target_date = timezone.localtime(timezone.now()).date()
            else:
                target_date = timezone.localtime(timezone.now()).date()
            
            from django.db.models import Exists, OuterRef, Q
            return perm_qs.filter(
                models.Q(created_at__date=target_date) |
                models.Q(followups__follow_up_date=target_date, followups__status='pending')
            ).annotate(
                has_follow_up_today=Exists(
                    FollowUp.objects.filter(
                        lead=OuterRef('pk'),
                        follow_up_date=target_date,
                        status='pending'
                    )
                )
            ).distinct()

        # Employee Status filter (Active staff / Inactive staff / Unassigned)
        emp_status = self.request.query_params.get('employee_status')
        if emp_status == 'active':
            perm_qs = perm_qs.filter(assigned_to__isnull=False, assigned_to__is_active=True)
        elif emp_status == 'inactive':
            perm_qs = perm_qs.filter(assigned_to__isnull=False, assigned_to__is_active=False)
        elif emp_status == 'unassigned':
            perm_qs = perm_qs.filter(assigned_to__isnull=True)
        elif emp_status == 'inactive_or_unassigned':
            perm_qs = perm_qs.filter(models.Q(assigned_to__is_active=False) | models.Q(assigned_to__isnull=True))

        # Status filter (handles both modern and legacy statuses like NOT_INTERESTED / CNR with spacing/underscore tolerance)
        status_param = self.request.query_params.get('status') or self.request.query_params.get('status__iexact')
        if status_param and status_param != 'all':
            s_clean = status_param.strip().upper().replace(' ', '_')
            if s_clean in ['NOT_INTERESTED', 'NOTINTERESTED']:
                perm_qs = perm_qs.filter(
                    models.Q(status__iexact='NOT_INTERESTED') |
                    models.Q(status__iexact='not interested') |
                    models.Q(status__iexact='not_interested') |
                    models.Q(status__iexact='NOT INTERESTED')
                )
            elif s_clean in ['CNR', 'COULD_NOT_REACH', 'COULDNOTREACH']:
                perm_qs = perm_qs.filter(
                    models.Q(status__iexact='CNR') |
                    models.Q(status__iexact='could not reach') |
                    models.Q(status__iexact='could_not_reach') |
                    models.Q(status__iexact='COULD NOT REACH')
                )
            elif s_clean in ['REGISTERED']:
                perm_qs = perm_qs.filter(
                    models.Q(status__iexact='REGISTERED') |
                    models.Q(status__iexact='registered')
                )
            else:
                perm_qs = perm_qs.filter(
                    models.Q(status__iexact=status_param) |
                    models.Q(status__iexact=s_clean)
                )

        # Active pipeline only (strictly exclude closed, converted, registered, lost, and legacy statuses like not_interested, cnr)
        if self.request.query_params.get('active_pipeline_only') == 'true' or self.request.query_params.get('exclude_closed_converted') == 'true':
            perm_qs = perm_qs.exclude(
                status__in=[
                    'CLOSED', 'CONVERTED', 'REGISTERED', 'LOST', 'NOT_INTERESTED', 'CNR',
                    'closed', 'converted', 'registered', 'lost', 'not_interested', 'not interested', 'cnr', 'could not reach'
                ]
            )

        # Overdue filter
        if self.request.query_params.get('overdue') == 'true':
            today = timezone.localtime(timezone.now()).date()
            perm_qs = perm_qs.filter(followups__follow_up_date__lt=today, followups__status='pending')

        # Has pending follow-up filter
        if self.request.query_params.get('has_pending_followup') == 'true':
            perm_qs = perm_qs.filter(followups__status='pending')

        return perm_qs.distinct()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        from datetime import datetime
        agenda_date_str = request.query_params.get('agenda_date')
        if agenda_date_str:
            try:
                target_date = datetime.strptime(agenda_date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = timezone.localtime(timezone.now()).date()
        else:
            target_date = timezone.localtime(timezone.now()).date()
        date_pattern1 = target_date.strftime('%d/%m/%Y')
        date_pattern2 = target_date.strftime('%Y-%m-%d')

        stats = queryset.aggregate(
            new=Count('id', filter=DQ(status__iexact='ENQUIRY')),
            qualified=Count('id', filter=DQ(status__iexact='QUALIFIED')),
            converted=Count('id', filter=DQ(status__iexact='CONVERTED')),
            total_assigned=Count('id', filter=DQ(assigned_to=request.user)),
            total_sub_assigned=Count('id', filter=DQ(sub_assigned_to=request.user)),
            attended=Count('id', filter=DQ(remarks__icontains=date_pattern1) | DQ(remarks__icontains=date_pattern2)),
        )

        return self.get_paginated_response({
            'leads': serializer.data,
            'stats': stats,
        })

class LeadCreateView(generics.CreateAPIView):
    queryset = Lead.objects.all()
    serializer_class = LeadCreateSerializer
    permission_classes = [CanAccessLeads]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save(created_by=request.user, company=request.user.company)

        ActivityLog.objects.create(
            user=request.user,
            action='LEAD_CREATED',
            entity_type='Lead',
            entity_id=lead.id,
            entity_name=lead.name,
            description=f'Lead "{lead.name}" was created by {request.user.get_full_name() or request.user.username}',
            metadata={'phone': lead.phone, 'source': lead.source}
        )

        if getattr(lead, 'processing_status', None) and lead.processing_status != 'PENDING':
            ProcessingUpdate.objects.create(
                lead=lead,
                status=lead.processing_status,
                changed_by=request.user,
                notes='Initial status on lead creation'
            )

        if lead.assigned_to and lead.assigned_to != request.user:
            notify_lead_assigned(
                assignee=lead.assigned_to,
                assigned_by=request.user,
                lead=lead,
                assignment_type='PRIMARY',
            )

        return Response({
            'message': 'Lead created successfully',
            'lead_id': lead.id
        }, status=status.HTTP_201_CREATED)

class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeadDetailSerializer
    permission_classes = [CanAccessLeads]

    def get_queryset(self):
        user = self.request.user
        base_qs = Lead.objects.select_related(
            'assigned_to', 'assigned_by',
            'sub_assigned_to', 'sub_assigned_by',
        )
        from accounts.permissions import has_dynamic_permission
        if (user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() or 
            has_dynamic_permission(user, 'leads:read_any') or 
            has_dynamic_permission(user, 'leads:read_tenant')):
            return base_qs.all()
        return base_qs.filter(
            models.Q(assigned_to=user) |
            models.Q(sub_assigned_to=user)
        )

    def update(self, request, *args, **kwargs):
        partial  = kwargs.pop('partial', False)
        lead     = self.get_object()
        old_processing_status = lead.processing_status
        old_status            = lead.status

        serializer = self.get_serializer(lead, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated_lead = serializer.save()

        if old_processing_status != updated_lead.processing_status:
            ProcessingUpdate.objects.create(
                lead=updated_lead,
                status=updated_lead.processing_status,
                changed_by=request.user,
                notes='Status updated via API'
            )

        if old_status != updated_lead.status:
            ActivityLog.objects.create(
                user=request.user,
                action='LEAD_STATUS_CHANGED',
                entity_type='Lead',
                entity_id=updated_lead.id,
                entity_name=updated_lead.name,
                description=f'Lead "{updated_lead.name}" status changed from {old_status} → {updated_lead.status}',
                metadata={
                    'old_status': old_status,
                    'new_status': updated_lead.status,
                }
            )

        if old_status != 'CONVERTED' and updated_lead.status == 'CONVERTED':
            send_conversion_email(updated_lead)

        return Response({
            'message': 'Lead updated successfully',
            'lead': LeadDetailSerializer(updated_lead).data,
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        lead = self.get_object()
        user = request.user

        if (
            not user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() and
            lead.assigned_to != user and
            lead.sub_assigned_to != user
        ):
            return Response(
                {'error': 'You do not have permission to delete this lead'},
                status=status.HTTP_403_FORBIDDEN,
            )

        ActivityLog.objects.create(
            user=request.user,
            action='LEAD_DELETED',
            entity_type='Lead',
            entity_id=lead.id,
            entity_name=lead.name,
            description=f'Lead "{lead.name}" was deleted by {request.user.get_full_name() or request.user.username}',
            metadata={
                'phone':       lead.phone,
                'status':      lead.status,
                'assigned_to': lead.assigned_to.get_full_name() if lead.assigned_to else None,
            }
        )

        self.perform_destroy(lead)
        return Response(
            {'message': 'Lead deleted successfully'},
            status=status.HTTP_204_NO_CONTENT,
        )

class LeadProcessingTimelineView(generics.ListAPIView):
    pagination_class = None
    serializer_class = ProcessingUpdateSerializer
    permission_classes = [CanAccessLeads]

    def get_queryset(self):
        lead_id = self.kwargs.get('lead_id')
        lead    = get_object_or_404(Lead, id=lead_id)
        user    = self.request.user

        if user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists():
            return ProcessingUpdate.objects.filter(lead=lead).select_related('changed_by').order_by('-timestamp')

        if lead.assigned_to != user and lead.sub_assigned_to != user:
            return ProcessingUpdate.objects.none()

        return ProcessingUpdate.objects.filter(lead=lead).select_related('changed_by').order_by('-timestamp')

class UpdateLeadView(APIView):
    permission_classes = [CanAccessLeads]

    def patch(self, request, pk):
        lead = get_object_or_404(Lead, id=pk)

        if (
            lead.assigned_to != request.user
            and lead.sub_assigned_to != request.user
            and not request.user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists()
        ):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN,
            )

        old_status = lead.status

        serializer = LeadUpdateSerializer(
            lead,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        updated_lead = serializer.save()

        if old_status != 'CONVERTED' and updated_lead.status == 'CONVERTED':
            send_conversion_email(updated_lead)

        return Response(serializer.data, status=status.HTTP_200_OK)

class TodayLeadsAPI(APIView):
    permission_classes = [CanAccessLeads]

    def get(self, request):
        today = date.today()
        leads = Lead.objects.filter(
            created_at__date=today
        ).values('id', 'name', 'status', 'assigned_to')
        return Response(list(leads))

class MyTeamLeadsView(generics.ListAPIView):
    serializer_class   = LeadListSerializer
    permission_classes = [CanAccessLeads]
    pagination_class   = LeadPagination

    def get_queryset(self):
        user = self.request.user
        base_qs = Lead.objects.select_related(
            'assigned_to', 'assigned_by',
            'sub_assigned_to', 'sub_assigned_by',
        )
        from accounts.permissions import has_dynamic_permission
        if (user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists() or 
            has_dynamic_permission(user, 'leads:read_any') or 
            has_dynamic_permission(user, 'leads:read_tenant')):
            return base_qs.all().distinct()
            
        return base_qs.filter(
            models.Q(assigned_to=user) |
            models.Q(sub_assigned_to=user)
        ).distinct()

class LeadConversionDetailView(APIView):
 
    def get_permissions(self):
        if self.request.method == 'GET':
            return [CanAccessLeads()]
        return [CanManageConversion()]
 
    def get(self, request, lead_id):
        lead = get_object_or_404(Lead, id=lead_id)
 
        if lead.status != 'CONVERTED':
            return Response(
                {'error': 'This lead is not converted yet.'},
                status=status.HTTP_400_BAD_REQUEST
            )
 
        try:
            detail     = lead.conversion_detail
            serializer = LeadConversionDetailSerializer(detail)
            return Response(serializer.data)
        except LeadConversionDetail.DoesNotExist:
            return Response(
                {'detail': None, 'message': 'No conversion details filled yet.'},
                status=status.HTTP_204_NO_CONTENT
            )
 
    def post(self, request, lead_id):
        lead = get_object_or_404(Lead, id=lead_id)
 
        if lead.status != 'CONVERTED':
            return Response(
                {'error': 'Can only add conversion details to a CONVERTED lead.'},
                status=status.HTTP_400_BAD_REQUEST
            )
 
        if hasattr(lead, 'conversion_detail'):
            return Response(
                {'error': 'Conversion detail already exists. Use PATCH to update.'},
                status=status.HTTP_400_BAD_REQUEST
            )
 
        serializer = LeadConversionDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        detail = serializer.save(lead=lead, updated_by=request.user)
 
        ActivityLog.objects.create(
            user=request.user,
            action='LEAD_UPDATED',
            entity_type='Lead',
            entity_id=lead.id,
            entity_name=lead.name,
            description=f'Conversion details added for "{lead.name}" by {request.user.get_full_name() or request.user.username}',
            metadata={
                'course':         detail.course,
                'payment_status': detail.payment_status,
            }
        )
 
        return Response(
            LeadConversionDetailSerializer(detail).data,
            status=status.HTTP_201_CREATED
        )
 
    def patch(self, request, lead_id):
        lead   = get_object_or_404(Lead, id=lead_id)
        detail = get_object_or_404(LeadConversionDetail, lead=lead)
 
        serializer = LeadConversionDetailSerializer(
            detail, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(updated_by=request.user)
 
        ActivityLog.objects.create(
            user=request.user,
            action='LEAD_UPDATED',
            entity_type='Lead',
            entity_id=lead.id,
            entity_name=lead.name,
            description=f'Conversion details updated for "{lead.name}" by {request.user.get_full_name() or request.user.username}',
            metadata={'payment_status': updated.payment_status}
        )
 
        return Response(LeadConversionDetailSerializer(updated).data)

class WebhookLogListView(generics.ListAPIView):
    """
    Lists all webhook logs (for admin review or lead conversion).
    """
    queryset = WebhookLog.objects.all().order_by('-created_at')
    serializer_class = WebhookLogSerializer
    permission_classes = [CanAccessLeads]  # or more strict permission

    def get_queryset(self):
        qs = super().get_queryset()
        source = self.request.query_params.get('source')
        processed = self.request.query_params.get('processed')
        if source:
            qs = qs.filter(source=source.upper())
        if processed is not None:
            processed_bool = processed.lower() == 'true'
            qs = qs.filter(processed=processed_bool)
        return qs

class ConvertWebhookToLeadAPIView(APIView):
    """
    Converts a Voxbay (or other) WebhookLog entry into a Lead (1-Click Lead Conversion).
    """
    permission_classes = [CanAccessLeads]

    def post(self, request, log_id):
        log = get_object_or_404(WebhookLog, id=log_id)
        if log.processed:
            return Response({'error': 'This webhook log has already been processed.'}, status=status.HTTP_400_BAD_REQUEST)
        
        payload = log.payload or {}
        
        # Extract potential phone number
        phone = payload.get('caller_number') or payload.get('phone') or payload.get('number')
        if not phone:
            return Response({'error': 'No phone number found in payload to convert.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if lead already exists
        if Lead.objects.filter(phone=phone).exists():
            log.processed = True
            log.save()
            return Response({'error': 'Lead with this phone number already exists.'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Create lead
        name = payload.get('name', f"Unknown Caller {phone}")
        source = 'VOXBAY CALL' if log.source == 'VOXBAY' else 'ADS'
        
        lead = Lead.objects.create(
            name=name,
            phone=phone,
            source=source,
            created_by=request.user,
            remarks=f"Auto-created from {log.source} Webhook Log ID: {log.id}",
            assigned_to=request.user,
            assigned_by=request.user,
            assigned_date=timezone.now()
        )
        
        # Mark processed
        log.processed = True
        log.save()
        
        
        return Response({
            'message': 'Lead created successfully.',
            'lead_id': lead.id
        }, status=status.HTTP_201_CREATED)

class ExportLeadsExcelView(LeadListView):
    """
    Exports filtered leads to an Excel file.
    Takes the same query parameters as LeadListView.
    """
    pagination_class = None
    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
        CompanyFilterBackend,
    ]

    def get_queryset(self):
        user = self.request.user
        base_qs = Lead.objects.select_related(
            'assigned_to', 'assigned_by',
            'sub_assigned_to', 'sub_assigned_by',
        )

        from accounts.permissions import has_dynamic_permission
        from leads.permissions import FULL_ACCESS_ROLES
        is_elevated = (
            user.is_superuser or
            user.db_roles.filter(name__in=FULL_ACCESS_ROLES + ['SENIOR ADM', 'SENIOR_ADM', 'ADM_MANAGER', 'CM', 'BDM']).exists() or 
            has_dynamic_permission(user, 'leads:read_any') or 
            has_dynamic_permission(user, 'leads:read_tenant') or
            has_dynamic_permission(user, 'reports:sales_all') or
            has_dynamic_permission(user, 'staff_analysis:admin')
        )
        if is_elevated:
            perm_qs = base_qs.all()
        else:
            perm_qs = base_qs.filter(
                models.Q(assigned_to=user) |
                models.Q(sub_assigned_to=user)
            )
        return perm_qs.distinct()

    def get(self, request, *args, **kwargs):
        import io
        from datetime import datetime as dt_cls
        from django.http import HttpResponse
        from openpyxl.styles import PatternFill, Font, Alignment
        
        # Base queryset
        queryset = self.get_queryset()

        # Date filtering
        date_preset = request.query_params.get('date_preset')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now())
        today = now.date()

        if date_preset == 'today':
            start_dt = timezone.make_aware(dt_cls.combine(today, dt_cls.min.time()), tz)
            queryset = queryset.filter(created_at__gte=start_dt, created_at__lte=now)
        elif date_preset == 'yesterday':
            yesterday = today - timezone.timedelta(days=1)
            start_dt = timezone.make_aware(dt_cls.combine(yesterday, dt_cls.min.time()), tz)
            end_dt = timezone.make_aware(dt_cls.combine(yesterday, dt_cls.max.time()), tz)
            queryset = queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        elif date_preset == 'this_week':
            start_week = today - timezone.timedelta(days=today.weekday())
            start_dt = timezone.make_aware(dt_cls.combine(start_week, dt_cls.min.time()), tz)
            queryset = queryset.filter(created_at__gte=start_dt, created_at__lte=now)
        elif date_preset == 'this_month':
            start_month = today.replace(day=1)
            start_dt = timezone.make_aware(dt_cls.combine(start_month, dt_cls.min.time()), tz)
            queryset = queryset.filter(created_at__gte=start_dt, created_at__lte=now)
        elif date_preset == 'last_month':
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month - timezone.timedelta(days=1)
            first_last_month = last_month_end.replace(day=1)
            start_dt = timezone.make_aware(dt_cls.combine(first_last_month, dt_cls.min.time()), tz)
            end_dt = timezone.make_aware(dt_cls.combine(first_this_month, dt_cls.min.time()), tz)
            queryset = queryset.filter(created_at__gte=start_dt, created_at__lt=end_dt)
        elif date_preset == 'custom' or (start_date and end_date):
            if start_date:
                s_date = dt_cls.strptime(start_date, '%Y-%m-%d').date() if isinstance(start_date, str) else start_date
                start_dt = timezone.make_aware(dt_cls.combine(s_date, dt_cls.min.time()), tz)
                queryset = queryset.filter(created_at__gte=start_dt)
            if end_date:
                e_date = dt_cls.strptime(end_date, '%Y-%m-%d').date() if isinstance(end_date, str) else end_date
                end_dt = timezone.make_aware(dt_cls.combine(e_date, dt_cls.max.time()), tz)
                queryset = queryset.filter(created_at__lte=end_dt)

        # Status filtering (comma-separated or single)
        status_param = request.query_params.get('status')
        if status_param and status_param != 'all':
            statuses = [s.strip().upper() for s in status_param.split(',') if s.strip() and s.strip().upper() != 'ALL']
            if statuses:
                queryset = queryset.filter(status__in=statuses)

        # Source filtering (comma-separated or single)
        source_param = request.query_params.get('source')
        if source_param and source_param != 'all':
            sources = [s.strip() for s in source_param.split(',') if s.strip() and s.strip().lower() != 'all']
            if sources:
                source_q = models.Q()
                for src in sources:
                    if src.lower() == 'voxbay':
                        source_q |= models.Q(source__icontains='voxbay')
                    else:
                        source_q |= models.Q(source__iexact=src)
                queryset = queryset.filter(source_q)

        # Call type filtering
        call_type_param = request.query_params.get('call_type')
        if call_type_param and call_type_param != 'all':
            ct = call_type_param.lower()
            if ct == 'incoming':
                queryset = queryset.filter(
                    models.Q(voxbay_status__icontains='inbound') |
                    models.Q(voxbay_status__icontains='incoming')
                )
            elif ct == 'outgoing':
                queryset = queryset.filter(
                    models.Q(voxbay_status__icontains='outbound') |
                    models.Q(voxbay_status__icontains='outgoing') |
                    models.Q(source__icontains='voxbay')
                )

        # Apply standard filters (search, priority, staff, etc.)
        queryset = self.filter_queryset(queryset).prefetch_related(
            models.Prefetch('followups', queryset=FollowUp.objects.order_by('-created_at')),
            models.Prefetch('remark_history', queryset=RemarkHistory.objects.order_by('-changed_at'))
        )
        
        leads_data = []
        remarks_data = []
        followups_data = []

        for lead in queryset:
            # Main Leads Sheet Data
            latest_fup = lead.followups.first()
            call_type = 'unknown'
            if lead.voxbay_status:
                vs = lead.voxbay_status.lower()
                if 'inbound' in vs or 'incoming' in vs: call_type = 'incoming'
                elif 'outbound' in vs or 'outgoing' in vs: call_type = 'outgoing'
            elif lead.source and 'VOXBAY' in lead.source.upper():
                call_type = 'outgoing'
                
            leads_data.append({
                'ID': lead.id,
                'Name': lead.name,
                'Phone': lead.phone,
                'Email': lead.email,
                'Status': lead.status,
                'Call Type': call_type,
                'Latest Remarks': lead.remarks,
                'Latest Followup Date': latest_fup.follow_up_date.strftime('%Y-%m-%d') if latest_fup and latest_fup.follow_up_date else None,
                'Latest Followup Status': latest_fup.status if latest_fup else None,
                'Source': lead.source,
                'Assigned To': lead.assigned_to.get_full_name() if lead.assigned_to else None,
                'Created At': lead.created_at.replace(tzinfo=None) if lead.created_at else None,
            })
            
            # Remarks History Data
            for rm in lead.remark_history.all():
                remarks_data.append({
                    'Lead ID': lead.id,
                    'Lead Name': lead.name,
                    'Previous Remarks': rm.previous_remarks,
                    'New Remarks': rm.new_remarks,
                    'Changed By': rm.changed_by.get_full_name() if rm.changed_by else 'System',
                    'Changed At': rm.changed_at.replace(tzinfo=None) if rm.changed_at else None,
                })
                
            # Followups History Data
            for fup in lead.followups.all():
                followups_data.append({
                    'Lead ID': lead.id,
                    'Lead Name': lead.name,
                    'Follow-up Date': fup.follow_up_date.strftime('%Y-%m-%d') if fup.follow_up_date else None,
                    'Type': fup.followup_type,
                    'Status': fup.status,
                    'Notes': fup.notes,
                    'Assigned To': fup.assigned_to.get_full_name() if fup.assigned_to else None,
                    'Created At': fup.created_at.replace(tzinfo=None) if fup.created_at else None,
                })
                
        leads_cols = ['ID', 'Name', 'Phone', 'Email', 'Status', 'Call Type', 'Latest Remarks', 'Latest Followup Date', 'Latest Followup Status', 'Source', 'Assigned To', 'Created At']
        remarks_cols = ['Lead ID', 'Lead Name', 'Previous Remarks', 'New Remarks', 'Changed By', 'Changed At']
        fups_cols = ['Lead ID', 'Lead Name', 'Follow-up Date', 'Type', 'Status', 'Notes', 'Assigned To', 'Created At']

        df_leads = pd.DataFrame(leads_data) if leads_data else pd.DataFrame(columns=leads_cols)
        df_remarks = pd.DataFrame(remarks_data) if remarks_data else pd.DataFrame(columns=remarks_cols)
        df_fups = pd.DataFrame(followups_data) if followups_data else pd.DataFrame(columns=fups_cols)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_leads.to_excel(writer, sheet_name='Leads Overview', index=False)
            df_remarks.to_excel(writer, sheet_name='Remarks History', index=False)
            df_fups.to_excel(writer, sheet_name='Follow-ups History', index=False)
            
            workbook = writer.book
            
            # ── Format Leads Sheet ──
            if 'Leads Overview' in workbook.sheetnames:
                ws_leads = workbook['Leads Overview']
                
                status_colors = {
                    'ENQUIRY': 'DBEAFE', 'JOB_ENQUIRY': 'E0E7FF', 'B2B': 'EDE9FE',
                    'COLD': 'E0F2FE', 'WARM': 'FEF08A', 'HOT': 'FFEDD5', 'CLOSED': 'FFE4E6',
                    'CONVERTED': 'D1FAE5', 'CONTACTED': 'FEF3C7',
                    'QUALIFIED': 'F3E8FF', 'NOT_INTERESTED': 'FEE2E2', 'CNR': 'F3F4F6', 'REGISTERED': 'DCFCE7',
                }
                fup_status_colors = {'contacted': 'D1FAE5', 'pending': 'FEF3C7', 'not_interested': 'FEE2E2', 'rescheduled': 'DBEAFE'}
                
                header_font = Font(bold=True, color='FFFFFF')
                header_fill = PatternFill(start_color='4F46E5', end_color='4F46E5', fill_type='solid')
                
                for cell in ws_leads[1]:
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    
                status_col_idx = df_leads.columns.get_loc('Status') + 1 if 'Status' in df_leads.columns else None
                fup_col_idx = df_leads.columns.get_loc('Latest Followup Status') + 1 if 'Latest Followup Status' in df_leads.columns else None
                
                for row_idx, row in enumerate(ws_leads.iter_rows(min_row=2), start=2):
                    if status_col_idx:
                        cell = row[status_col_idx - 1]
                        if cell.value in status_colors:
                            cell.fill = PatternFill(start_color=status_colors[cell.value], end_color=status_colors[cell.value], fill_type='solid')
                    if fup_col_idx:
                        cell = row[fup_col_idx - 1]
                        if cell.value in fup_status_colors:
                            cell.fill = PatternFill(start_color=fup_status_colors[cell.value], end_color=fup_status_colors[cell.value], fill_type='solid')
                            
                # Legend
                ws_leads.append([])
                ws_leads.append(['COLOR LEGEND - LEAD STATUS'])
                for status, hex_code in status_colors.items():
                    ws_leads.append([status])
                    ws_leads.cell(row=ws_leads.max_row, column=1).fill = PatternFill(start_color=hex_code, end_color=hex_code, fill_type='solid')
                    
            for sheet_name in ['Remarks History', 'Follow-ups History']:
                if sheet_name in workbook.sheetnames:
                    ws = workbook[sheet_name]
                    for cell in ws[1]:
                        cell.font = Font(bold=True)
                        cell.fill = PatternFill(start_color='E5E7EB', end_color='E5E7EB', fill_type='solid')

        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="leads_export.xlsx"'
        return response

class UnifiedTimelineAPIView(APIView):
    """
    Returns a chronologically sorted timeline of all events related to a lead.
    """
    permission_classes = [CanAccessLeads]

    def get(self, request, pk):
        lead = get_object_or_404(Lead, id=pk)
        
        events = []
        
        # 1. Processing Updates
        for pu in lead.processing_updates.all():
            events.append({
                'type': 'processing_update',
                'status': pu.status,
                'notes': pu.notes,
                'user': pu.changed_by.get_full_name() if pu.changed_by else 'System',
                'timestamp': pu.timestamp
            })
            
        # 2. Remark History
        for rm in lead.remark_history.all():
            events.append({
                'type': 'remark_history',
                'old_remarks': rm.previous_remarks,
                'new_remarks': rm.new_remarks,
                'user': rm.changed_by.get_full_name() if rm.changed_by else 'System',
                'timestamp': rm.changed_at
            })
            
        # 3. Assignments
        for la in lead.assignment_history.all():
            events.append({
                'type': 'assignment',
                'assigned_to': la.assigned_to.get_full_name() if la.assigned_to else None,
                'assigned_by': la.assigned_by.get_full_name() if la.assigned_by else None,
                'assignment_type': la.assignment_type,
                'notes': la.notes,
                'timestamp': la.timestamp
            })
            
        # 4. Follow Ups
        for fu in lead.followups.all():
            events.append({
                'type': 'followup_scheduled',
                'followup_type': fu.followup_type,
                'status': fu.status,
                'notes': fu.notes,
                'user': fu.assigned_to.get_full_name() if fu.assigned_to else 'System',
                'timestamp': fu.created_at
            })
            for fhist in fu.history.all():
                events.append({
                    'type': 'followup_status_change',
                    'old_status': fhist.old_status,
                    'new_status': fhist.new_status,
                    'notes': fhist.notes,
                    'user': fhist.changed_by.get_full_name() if fhist.changed_by else 'System',
                    'timestamp': fhist.changed_at
                })

        # 5. Voxbay Call Logs
        try:
            from telephony.models import VoxbayCallLog
            call_logs = VoxbayCallLog.objects.filter(
                models.Q(lead=lead) | (models.Q(caller_number=lead.phone) if lead.phone else models.Q(pk=-1))
            ).distinct()
            for log in call_logs:
                events.append({
                    'type': 'voxbay_call',
                    'call_type': log.call_type or 'call',
                    'call_status': log.call_status or 'UNKNOWN',
                    'duration': log.duration or 0,
                    'recording_url': log.recording_url or '',
                    'user': log.agent_name or 'System',
                    'caller_number': log.caller_number or lead.phone,
                    'timestamp': log.created_at
                })
        except Exception:
            pass

        # Sort all events by timestamp descending
        events.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return Response({'timeline': events}, status=status.HTTP_200_OK)

class LeadDocumentListCreateView(APIView):
    permission_classes = [CanAccessLeads]
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request, pk):
        lead = get_object_or_404(Lead, id=pk)
        docs = lead.documents.all()
        serializer = LeadDocumentSerializer(docs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        lead = get_object_or_404(Lead, id=pk)
        
        if (
            lead.assigned_to != request.user
            and lead.sub_assigned_to != request.user
            and not request.user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists()
        ):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = LeadDocumentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(lead=lead, uploaded_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LeadCommandCentreStatsView(APIView):
    permission_classes = [CanAccessLeads]

    def get(self, request):
        user = request.user
        base_qs = Lead.objects.all()

        if not (user.db_roles.filter(name__in=FULL_ACCESS_ROLES + ['SENIOR ADM', 'SENIOR_ADM', 'ADM_MANAGER']).exists() or 
                has_dynamic_permission(user, 'leads:read_any') or 
                has_dynamic_permission(user, 'leads:read_tenant') or
                has_dynamic_permission(user, 'staff_analysis:admin')):
            base_qs = base_qs.filter(
                models.Q(assigned_to=user) | models.Q(sub_assigned_to=user)
            )

        company_param = request.query_params.get('company')
        if company_param:
            base_qs = base_qs.filter(company__iexact=company_param)

        CLOSED_CONVERTED_STATUSES = [
            'CLOSED', 'CONVERTED', 'REGISTERED', 'LOST', 'NOT_INTERESTED', 'CNR',
            'closed', 'converted', 'registered', 'lost', 'not_interested', 'not interested', 'cnr', 'could not reach'
        ]

        stats = base_qs.aggregate(
            total=Count('id'),
            active_staff_leads=Count('id', filter=DQ(assigned_to__isnull=False, assigned_to__is_active=True)),
            inactive_staff_leads=Count('id', filter=DQ(assigned_to__isnull=False, assigned_to__is_active=False)),
            unassigned_leads=Count('id', filter=DQ(assigned_to__isnull=True)),
            active_pipeline_leads=Count(
                'id',
                filter=DQ(assigned_to__isnull=False, assigned_to__is_active=True) & ~DQ(status__in=CLOSED_CONVERTED_STATUSES)
            ),
            closed_leads=Count('id', filter=DQ(status__in=['CLOSED', 'closed'])),
            converted_leads=Count('id', filter=DQ(status__in=['CONVERTED', 'converted', 'REGISTERED', 'registered'])),
        )

        return Response(stats, status=status.HTTP_200_OK)

