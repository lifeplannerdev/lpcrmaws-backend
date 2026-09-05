from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Count, Q, Prefetch
from rest_framework.views import APIView
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
        employee_id = request.query_params.get('employee_id', 'all')
        status_filter = request.query_params.get('status', '')
        source_filter = request.query_params.get('source', '')

        employees_qs = User.objects.filter(is_active=True).prefetch_related('db_roles')
        if employee_id and employee_id != 'all':
            try:
                employees_qs = employees_qs.filter(id=int(employee_id))
            except ValueError:
                pass

        lead_base = Lead.objects.select_related(
            'assigned_to', 'sub_assigned_to', 'assigned_by'
        ).prefetch_related(
            Prefetch('followups', queryset=FollowUp.objects.order_by('-follow_up_date', '-created_at'))
        )
        if start_date and end_date:
            lead_base = lead_base.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(',') if s.strip()]
            if statuses:
                lead_base = lead_base.filter(status__in=statuses)
        if source_filter:
            sources = [s.strip() for s in source_filter.split(',') if s.strip()]
            if sources:
                lead_base = lead_base.filter(source__in=sources)

        fu_base = FollowUp.objects.select_related('lead', 'assigned_to')
        if start_date and end_date:
            fu_base = fu_base.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

        results = []
        for emp in employees_qs:
            emp_leads = lead_base.filter(Q(assigned_to=emp) | Q(sub_assigned_to=emp)).distinct()
            leads_data = []
            for lead in emp_leads:
                fups = list(lead.followups.all())
                leads_data.append({
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
                    'updated_at': lead.updated_at.isoformat() if lead.updated_at else None,
                    'assigned_to': emp.get_full_name() or emp.username,
                    'call_type': _infer_call_type(lead),
                    'followups': [_serialize_followup(f) for f in fups],
                })

            emp_followups = fu_base.filter(assigned_to=emp)
            total_fups = emp_followups.count()
            contacted_fups = emp_followups.filter(status='contacted').count()
            pending_fups = emp_followups.filter(status='pending').count()
            today = timezone.now().date()
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
                    'total_leads': len(leads_data),
                    'followups_total': total_fups,
                    'followups_contacted': contacted_fups,
                    'followups_pending': pending_fups,
                    'followups_overdue': overdue_fups,
                    'followup_deficit': deficit,
                },
                'leads': leads_data,
            })

        grand_total_leads = sum(r['summary']['total_leads'] for r in results)
        grand_fu_total = sum(r['summary']['followups_total'] for r in results)
        grand_fu_contacted = sum(r['summary']['followups_contacted'] for r in results)
        grand_fu_pending = sum(r['summary']['followups_pending'] for r in results)
        grand_fu_overdue = sum(r['summary']['followups_overdue'] for r in results)

        return Response({
            'grand_summary': {
                'total_leads': grand_total_leads,
                'followups_total': grand_fu_total,
                'followups_contacted': grand_fu_contacted,
                'followups_pending': grand_fu_pending,
                'followups_overdue': grand_fu_overdue,
                'completion_rate': round((grand_fu_contacted / grand_fu_total * 100) if grand_fu_total else 0, 1),
            },
            'employees': results,
        })


def _infer_call_type(lead):
    if lead.voxbay_status:
        vs = lead.voxbay_status.lower()
        if 'inbound' in vs or 'incoming' in vs:
            return 'incoming'
        if 'outbound' in vs or 'outgoing' in vs:
            return 'outgoing'
    if lead.source == 'VOXBAY CALL':
        return 'outgoing'
    return 'unknown'


def _serialize_followup(f):
    return {
        'id': f.id,
        'follow_up_date': f.follow_up_date.isoformat() if f.follow_up_date else None,
        'follow_up_time': str(f.follow_up_time) if f.follow_up_time else None,
        'followup_type': f.followup_type,
        'status': f.status,
        'priority': f.priority,
        'notes': f.notes,
        'is_overdue': f.is_overdue,
        'created_at': f.created_at.isoformat() if f.created_at else None,
    }
