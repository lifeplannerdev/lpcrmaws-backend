from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Count, Q, Prefetch, Case, When, Value, CharField
from rest_framework.views import APIView
from rest_framework import generics, filters
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from accounts.permissions import has_dynamic_permission
from leads.models import Lead, FollowUp
from leads.permissions import FULL_ACCESS_ROLES


def _get_date_range(request):
    preset = request.query_params.get('date_preset', 'all_time')
    today = timezone.now().date()
    if preset == 'today':
        return today, today
    elif preset == 'yesterday':
        y = today - timedelta(days=1)
        return y, y
    elif preset == 'custom':
        start = request.query_params.get('start_date')
        end = request.query_params.get('end_date')
        if start and end:
            try:
                from datetime import date as dt_date
                return dt_date.fromisoformat(start), dt_date.fromisoformat(end)
            except ValueError:
                pass
        return None, None
    else:
        return None, None


class StaffAnalysisAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_admin = (
            user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists()
            or has_dynamic_permission(user, 'leads:read_tenant')
            or has_dynamic_permission(user, 'leads:read_any')
            or has_dynamic_permission(user, 'staff_analysis:admin')
        )
        if not is_admin:
            return Response({'detail': 'Permission denied.'}, status=403)

        start_date, end_date = _get_date_range(request)
        status_filter = request.query_params.get('status', '')
        source_filter = request.query_params.get('source', '')
        call_type_filter = request.query_params.get('call_type', '')

        employees_qs = User.objects.filter(is_active=True).prefetch_related('db_roles')

        # Base queryset with filters
        lead_base = Lead.objects.all()
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(',') if s.strip()]
            if statuses:
                lead_base = lead_base.filter(status__in=statuses)
        if source_filter:
            sources = [s.strip() for s in source_filter.split(',') if s.strip()]
            if sources:
                lead_base = lead_base.filter(source__in=sources)
        if call_type_filter:
            ctypes = [c.strip().lower() for c in call_type_filter.split(',') if c.strip()]
            if 'incoming' in ctypes and 'outgoing' not in ctypes:
                lead_base = lead_base.filter(Q(voxbay_status__icontains='inbound') | Q(voxbay_status__icontains='incoming'))
            elif 'outgoing' in ctypes and 'incoming' not in ctypes:
                lead_base = lead_base.filter(Q(voxbay_status__icontains='outbound') | Q(voxbay_status__icontains='outgoing') | Q(source='VOXBAY CALL'))

        # Filter base for followups
        fu_qs = FollowUp.objects.all()
        if start_date and end_date:
            fu_qs = fu_qs.filter(follow_up_date__gte=start_date, follow_up_date__lte=end_date)

        results = []
        today = timezone.now().date()

        for emp in employees_qs:
            if start_date and end_date:
                fresh_count = lead_base.filter(
                    Q(assigned_to=emp) | Q(sub_assigned_to=emp),
                    created_at__date__gte=start_date,
                    created_at__date__lte=end_date
                ).distinct().count()

                followup_count = lead_base.filter(
                    Q(assigned_to=emp) | Q(sub_assigned_to=emp) | Q(followups__assigned_to=emp),
                    followups__follow_up_date__gte=start_date,
                    followups__follow_up_date__lte=end_date
                ).exclude(
                    created_at__date__gte=start_date,
                    created_at__date__lte=end_date
                ).distinct().count()

                total_leads = fresh_count + followup_count
            else:
                total_leads = lead_base.filter(Q(assigned_to=emp) | Q(sub_assigned_to=emp)).distinct().count()
                fresh_count = total_leads
                followup_count = 0
            
            emp_followups = fu_qs.filter(assigned_to=emp)
            total_fups = emp_followups.count()
            contacted_fups = emp_followups.filter(status='contacted').count()
            pending_fups = emp_followups.filter(status='pending').count()
            overdue_fups = emp_followups.filter(status='pending', follow_up_date__lt=today).count()
            deficit = contacted_fups - total_fups

            results.append({
                'employee': {
                    'id': emp.id,
                    'username': emp.username,
                    'full_name': emp.get_full_name() or emp.username,
                    'email': emp.email,
                    'roles': list(emp.db_roles.values_list('name', flat=True)),
                },
                'summary': {
                    'total_leads': total_leads,
                    'fresh_leads': fresh_count,
                    'followup_leads': followup_count,
                    'followups_total': total_fups,
                    'followups_contacted': contacted_fups,
                    'followups_pending': pending_fups,
                    'followups_overdue': overdue_fups,
                    'followup_deficit': deficit,
                }
            })

        grand_total_leads = sum(r['summary']['total_leads'] for r in results)
        grand_fresh_leads = sum(r['summary']['fresh_leads'] for r in results)
        grand_followup_leads = sum(r['summary']['followup_leads'] for r in results)
        grand_fu_total = sum(r['summary']['followups_total'] for r in results)
        grand_fu_contacted = sum(r['summary']['followups_contacted'] for r in results)
        grand_fu_pending = sum(r['summary']['followups_pending'] for r in results)
        grand_fu_overdue = sum(r['summary']['followups_overdue'] for r in results)

        return Response({
            'grand_summary': {
                'total_leads': grand_total_leads,
                'fresh_leads': grand_fresh_leads,
                'followup_leads': grand_followup_leads,
                'followups_total': grand_fu_total,
                'followups_contacted': grand_fu_contacted,
                'followups_pending': grand_fu_pending,
                'followups_overdue': grand_fu_overdue,
                'completion_rate': round((grand_fu_contacted / grand_fu_total * 100) if grand_fu_total else 0, 1),
            },
            'employees': results,
        })


class StaffAnalysisPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class StaffAnalysisLeadsAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StaffAnalysisPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'phone', 'email', 'remarks']

    def get_queryset(self):
        user = self.request.user
        is_admin = (
            user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists()
            or has_dynamic_permission(user, 'leads:read_tenant')
            or has_dynamic_permission(user, 'leads:read_any')
            or has_dynamic_permission(user, 'staff_analysis:admin')
        )
        if not is_admin:
            return Lead.objects.none()

        start_date, end_date = _get_date_range(self.request)
        employee_id = self.request.query_params.get('employee_id')
        category_filter = self.request.query_params.get('category', '').lower()
        status_filter = self.request.query_params.get('status', '')
        source_filter = self.request.query_params.get('source', '')
        call_type_filter = self.request.query_params.get('call_type', '')

        lead_qs = Lead.objects.select_related(
            'assigned_to', 'sub_assigned_to'
        ).prefetch_related(
            Prefetch('followups', queryset=FollowUp.objects.order_by('-follow_up_date', '-created_at'))
        )

        if employee_id:
            lead_qs = lead_qs.filter(
                Q(assigned_to_id=employee_id) |
                Q(sub_assigned_to_id=employee_id) |
                Q(followups__assigned_to_id=employee_id)
            )

        if start_date and end_date:
            if category_filter == 'fresh':
                lead_qs = lead_qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
            elif category_filter == 'followup':
                lead_qs = lead_qs.filter(
                    followups__follow_up_date__gte=start_date,
                    followups__follow_up_date__lte=end_date
                ).exclude(created_at__date__gte=start_date, created_at__date__lte=end_date)
            else:
                lead_qs = lead_qs.filter(
                    Q(created_at__date__gte=start_date, created_at__date__lte=end_date) |
                    Q(followups__follow_up_date__gte=start_date, followups__follow_up_date__lte=end_date)
                )
            
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(',') if s.strip()]
            if statuses:
                lead_qs = lead_qs.filter(status__in=statuses)
                
        if source_filter:
            sources = [s.strip() for s in source_filter.split(',') if s.strip()]
            if sources:
                lead_qs = lead_qs.filter(source__in=sources)
                
        if call_type_filter:
            ctypes = [c.strip().lower() for c in call_type_filter.split(',') if c.strip()]
            if 'incoming' in ctypes and 'outgoing' not in ctypes:
                lead_qs = lead_qs.filter(Q(voxbay_status__icontains='inbound') | Q(voxbay_status__icontains='incoming'))
            elif 'outgoing' in ctypes and 'incoming' not in ctypes:
                lead_qs = lead_qs.filter(Q(voxbay_status__icontains='outbound') | Q(voxbay_status__icontains='outgoing') | Q(source='VOXBAY CALL'))

        return lead_qs.distinct().order_by('-created_at')

    def list(self, request, *args, **kwargs):
        start_date, end_date = _get_date_range(self.request)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        def _serialize(lead):
            # Dynamic call_type inference for JSON
            ctype = 'unknown'
            if lead.voxbay_status:
                vs = lead.voxbay_status.lower()
                if 'inbound' in vs or 'incoming' in vs: ctype = 'incoming'
                elif 'outbound' in vs or 'outgoing' in vs: ctype = 'outgoing'
            elif lead.source == 'VOXBAY CALL':
                ctype = 'outgoing'
                
            # Determine Lead Tag (Fresh vs Follow-up)
            is_fresh = False
            if start_date and end_date:
                is_fresh = (lead.created_at.date() >= start_date and lead.created_at.date() <= end_date)
            else:
                is_fresh = (lead.followups.count() <= 1)
                
            lead_tag = 'FRESH' if is_fresh else 'FOLLOWUP'
            lead_tag_display = 'Fresh Lead' if is_fresh else 'Follow-up Lead'

            # Get the follow-up for this lead in the selected date range, or the latest
            if start_date and end_date:
                period_fup = None
                for f in lead.followups.all():
                    if f.follow_up_date and start_date <= f.follow_up_date <= end_date:
                        period_fup = f
                        break
                latest_fup = period_fup or lead.followups.first()
            else:
                latest_fup = lead.followups.first()

            latest_fup_data = None
            if latest_fup:
                latest_fup_data = {
                    'id': latest_fup.id,
                    'follow_up_date': latest_fup.follow_up_date.isoformat() if latest_fup.follow_up_date else None,
                    'status': latest_fup.status,
                    'notes': latest_fup.notes,
                    'is_overdue': latest_fup.is_overdue,
                }
                
            return {
                'id': lead.id,
                'name': lead.name,
                'phone': lead.phone,
                'email': lead.email,
                'status': lead.status,
                'source': lead.source,
                'remarks': lead.remarks,
                'program': lead.program,
                'location': lead.location,
                'priority': lead.priority,
                'created_at': lead.created_at.isoformat() if lead.created_at else None,
                'call_type': ctype,
                'lead_tag': lead_tag,
                'lead_tag_display': lead_tag_display,
                'latest_followup': latest_fup_data,
                'assigned_to_name': lead.assigned_to.get_full_name() if lead.assigned_to else (lead.sub_assigned_to.get_full_name() if lead.sub_assigned_to else ''),
                'followups': [
                    {
                        'id': f.id,
                        'follow_up_date': f.follow_up_date.isoformat() if f.follow_up_date else None,
                        'status': f.status,
                        'notes': f.notes,
                        'is_overdue': f.is_overdue,
                    } for f in lead.followups.all()
                ]
            }

        if page is not None:
            data = [_serialize(lead) for lead in page]
            return self.get_paginated_response(data)

        data = [_serialize(lead) for lead in queryset]
        return Response(data)

