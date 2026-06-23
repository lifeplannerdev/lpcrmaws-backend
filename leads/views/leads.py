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
        'status':            ['exact', 'iexact'],
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
    ordering_fields = ['created_at', 'priority']
    ordering        = ['-created_at']

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
            perm_qs = base_qs.all()
        else:
            perm_qs = base_qs.filter(
                models.Q(assigned_to=user) |
                models.Q(sub_assigned_to=user)
            )
        
        from django.utils import timezone
        if self.request.query_params.get('daily_agenda') == 'true':
            today = timezone.localtime(timezone.now()).date()
            
            from django.db.models import Exists, OuterRef, Q
            return perm_qs.filter(
                models.Q(created_at__date=today) |
                models.Q(followups__follow_up_date=today, followups__status='pending')
            ).annotate(
                has_follow_up_today=Exists(
                    FollowUp.objects.filter(
                        lead=OuterRef('pk'),
                        follow_up_date=today,
                        status='pending'
                    )
                )
            ).distinct()

        return perm_qs.distinct()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        stats = queryset.aggregate(
            new=Count('id', filter=DQ(status__iexact='ENQUIRY')),
            qualified=Count('id', filter=DQ(status__iexact='QUALIFIED')),
            converted=Count('id', filter=DQ(status__iexact='CONVERTED')),
            total_assigned=Count('id', filter=DQ(assigned_to=request.user)),
            total_sub_assigned=Count('id', filter=DQ(sub_assigned_to=request.user)),
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

    def get(self, request, *args, **kwargs):
        import io
        from django.http import HttpResponse
        
        queryset = self.filter_queryset(self.get_queryset())
        
        data = list(queryset.values(
            'id', 'name', 'phone', 'email', 'status', 'source', 
            'campaign_name', 'adset_name', 'ad_name', 'created_at', 'remarks'
        ))
        
        df = pd.DataFrame(data)
        if not df.empty:
            # Remove timezone for Excel export
            df['created_at'] = df['created_at'].dt.tz_localize(None)
            
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Leads', index=False)
            
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

