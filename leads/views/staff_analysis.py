from datetime import date, timedelta, datetime
from django.utils import timezone
from django.db.models import Count, Q, Prefetch, Case, When, Value, CharField, Sum, Avg
from rest_framework.views import APIView
from rest_framework import generics, filters
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from accounts.permissions import has_dynamic_permission
from leads.models import Lead, FollowUp
from leads.permissions import FULL_ACCESS_ROLES
from telephony.models import VoxbayCallLog


def _get_date_range(request):
    preset = request.query_params.get('date_preset', 'all_time')
    today = timezone.now().date()
    if preset == 'today':
        return today, today
    elif preset == 'yesterday':
        y = today - timedelta(days=1)
        return y, y
    elif preset == 'this_week':
        start = today - timedelta(days=today.weekday())
        return start, today
    elif preset == 'this_month':
        start = today.replace(day=1)
        return start, today
    elif preset == 'previous_month':
        first_of_this_month = today.replace(day=1)
        last_of_prev = first_of_this_month - timedelta(days=1)
        first_of_prev = last_of_prev.replace(day=1)
        return first_of_prev, last_of_prev
    elif preset in ('custom', 'range', 'custom_range', 'single_date', 'custom_date'):
        start = request.query_params.get('start_date') or request.query_params.get('single_date')
        end = request.query_params.get('end_date') or start
        if start and end:
            try:
                from datetime import date as dt_date
                return dt_date.fromisoformat(start), dt_date.fromisoformat(end)
            except ValueError:
                pass
        elif start:
            try:
                from datetime import date as dt_date
                d = dt_date.fromisoformat(start)
                return d, d
            except ValueError:
                pass
        return None, None
    elif preset == 'all_time':
        return None, None
    else:
        return None, None


def _format_seconds(total_sec):
    if not total_sec:
        return "0s"
    total_sec = int(total_sec)
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _extract_recording_url(notes):
    if not notes:
        return None
    import re
    m = re.search(r'(?:Recording:\s*|\[Audio Recording:\s*|\bAudio:\s*)(https?://[^\s\]]+)', notes, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r'(https?://[^\s\]]+(?:voiceapi\.voxbay\.com|callcenter|callrecordings|\.wav|\.mp3)[^\s\]]*)', notes, re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None


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

        team_filter = request.query_params.get('team', 'Sales')
        employees_qs = User.objects.filter(is_active=True).prefetch_related('db_roles').order_by('first_name', 'username')
        if team_filter and team_filter.lower() != 'all':
            employees_qs = employees_qs.filter(team__iexact=team_filter)

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

        # Base for telephony call logs
        call_qs = VoxbayCallLog.objects.all()
        if start_date and end_date:
            dt_start = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            dt_end = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
            call_qs = call_qs.filter(created_at__gte=dt_start, created_at__lte=dt_end)

        results = []
        today = timezone.now().date()

        for emp in employees_qs:
            # 1. Lead metrics
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

                emp_leads_qs = lead_base.filter(
                    Q(assigned_to=emp) | Q(sub_assigned_to=emp)
                ).filter(
                    Q(created_at__date__gte=start_date, created_at__date__lte=end_date) |
                    Q(followups__follow_up_date__gte=start_date, followups__follow_up_date__lte=end_date)
                ).distinct()
            else:
                emp_leads_qs = lead_base.filter(Q(assigned_to=emp) | Q(sub_assigned_to=emp)).distinct()
                fresh_count = emp_leads_qs.count()
                followup_count = 0

            total_leads = emp_leads_qs.count()

            # Pipeline stage breakdown
            hot_count = emp_leads_qs.filter(status='HOT').count()
            warm_count = emp_leads_qs.filter(status='WARM').count()
            cold_count = emp_leads_qs.filter(status='COLD').count()
            enquiry_count = emp_leads_qs.filter(status='ENQUIRY').count()
            job_enquiry_count = emp_leads_qs.filter(status='JOB_ENQUIRY').count()
            b2b_count = emp_leads_qs.filter(status='B2B').count()
            closed_count = emp_leads_qs.filter(status='CLOSED').count()
            converted_count = emp_leads_qs.filter(status__in=['CONVERTED', 'REGISTERED']).count()

            # Converted lead details for report
            converted_leads_qs = emp_leads_qs.filter(status__in=['CONVERTED', 'REGISTERED']).order_by('-created_at')
            converted_leads_detail = [
                {
                    'id': cl.id,
                    'name': cl.name,
                    'phone': cl.phone,
                    'email': cl.email,
                    'program': cl.program,
                    'location': cl.location,
                    'status': cl.status,
                    'created_at': cl.created_at.strftime('%Y-%m-%d') if cl.created_at else None,
                    'source': cl.source,
                    'assigned_to_name': cl.assigned_to.get_full_name() if cl.assigned_to else '',
                }
                for cl in converted_leads_qs[:50]
            ]

            # Legacy statuses breakdown
            contacted_lead_count = emp_leads_qs.filter(status='CONTACTED').count()
            qualified_lead_count = emp_leads_qs.filter(status='QUALIFIED').count()
            not_interested_lead_count = emp_leads_qs.filter(status='NOT_INTERESTED').count()
            cnr_lead_count = emp_leads_qs.filter(status='CNR').count()
            registered_lead_count = emp_leads_qs.filter(status='REGISTERED').count()

            conversion_rate = round((converted_count / total_leads * 100), 1) if total_leads > 0 else 0.0

            # 2. Follow-up metrics
            emp_followups = fu_qs.filter(assigned_to=emp)
            total_fups = emp_followups.count()
            contacted_fups = emp_followups.filter(status='contacted').count()
            completed_fups = emp_followups.filter(status='completed').count()
            total_resolved_fups = contacted_fups + completed_fups
            pending_fups = emp_followups.filter(status='pending').count()
            overdue_fups = emp_followups.filter(status='pending', follow_up_date__lt=today).count()
            rescheduled_fups = emp_followups.filter(status='rescheduled').count()
            not_interested_fups = emp_followups.filter(status='not_interested').count()

            # Followups created in period (vs done in period)
            if start_date and end_date:
                followups_created_in_period = FollowUp.objects.filter(
                    assigned_to=emp,
                    created_at__date__gte=start_date,
                    created_at__date__lte=end_date
                ).count()
            else:
                followups_created_in_period = FollowUp.objects.filter(assigned_to=emp).count()

            # Overdue pending (excluding future - i.e. due today or past, status pending)
            overdue_pending_excl_future = FollowUp.objects.filter(
                assigned_to=emp,
                status='pending',
                follow_up_date__lte=today
            ).count()
            
            resolution_rate = round((total_resolved_fups / total_fups * 100), 1) if total_fups > 0 else 0.0
            unresolved_count = max(0, total_fups - total_resolved_fups)

            # 3. Telephony calls & talktime
            emp_ext = getattr(emp, 'voxbay_extension', None)
            emp_num = getattr(emp, 'voxbay_number', None)
            q_calls = Q()
            if emp_ext:
                q_calls |= Q(extension=emp_ext) | Q(agent_number=emp_ext)
            if emp_num:
                q_calls |= Q(called_number=emp_num) | Q(caller_number=emp_num) | Q(agent_number=emp_num)
            
            if q_calls:
                emp_calls = call_qs.filter(q_calls)
            else:
                emp_calls = call_qs.none()

            calls_total = emp_calls.count()
            calls_incoming = emp_calls.filter(call_type='incoming').count()
            calls_outgoing = emp_calls.filter(call_type='outgoing').count()
            calls_answered = emp_calls.filter(call_status__in=['ANSWER', 'ANSWERED']).count()
            calls_missed = emp_calls.filter(call_status__in=['MISSED', 'NOANSWER', 'CANCELLED']).count()
            
            talktime_agg = emp_calls.aggregate(Sum('conversation_duration'))['conversation_duration__sum'] or 0
            total_talktime_sec = int(talktime_agg)
            avg_talktime_sec = round(total_talktime_sec / calls_answered, 1) if calls_answered > 0 else 0.0
            talktime_display = _format_seconds(total_talktime_sec)

            # 4. Balanced Performance Scorecard (0 to 100)
            if total_fups > 0:
                fu_score = (resolution_rate / 100.0) * 40.0
            else:
                fu_score = 25.0 if total_leads > 0 else 10.0
            # Overdue penalty (-2 pts per overdue, max 10 pts penalty)
            fu_score = max(0.0, fu_score - min(10.0, overdue_fups * 2.0))

            sales_score = min(20.0, converted_count * 5.0)
            pipeline_ratio = ((hot_count * 2.0 + warm_count * 1.0) / max(total_leads, 1))
            pipeline_score = min(10.0, pipeline_ratio * 15.0)

            talk_score = min(20.0, (total_talktime_sec / 3600.0) * 10.0)
            call_activity_score = min(10.0, (calls_total / 20.0) * 10.0)

            raw_perf = fu_score + sales_score + pipeline_score + talk_score + call_activity_score
            perf_score = round(max(0.0, min(100.0, raw_perf)), 1)

            results.append({
                'employee': {
                    'id': emp.id,
                    'username': emp.username,
                    'full_name': emp.get_full_name() or emp.username,
                    'email': emp.email,
                    'roles': list(emp.db_roles.values_list('name', flat=True)),
                    'voxbay_extension': emp_ext,
                    'voxbay_number': emp_num,
                    'team': emp.team,
                },
                'summary': {
                    'total_leads': total_leads,
                    'fresh_leads': fresh_count,
                    'followup_leads': followup_count,
                    # Pipeline stages
                    'hot_leads': hot_count,
                    'warm_leads': warm_count,
                    'cold_leads': cold_count,
                    'enquiry_leads': enquiry_count,
                    'job_enquiry_leads': job_enquiry_count,
                    'b2b_leads': b2b_count,
                    'closed_leads': closed_count,
                    'converted_leads': converted_count,
                    'conversion_rate': conversion_rate,
                    # Legacy lead statuses
                    'contacted_leads': contacted_lead_count,
                    'qualified_leads': qualified_lead_count,
                    'not_interested_leads': not_interested_lead_count,
                    'cnr_leads': cnr_lead_count,
                    'registered_leads': registered_lead_count,
                    # Followups
                    'followups_total': total_fups,
                    'followups_contacted': contacted_fups,
                    'followups_completed': completed_fups,
                    'followups_resolved': total_resolved_fups,
                    'followups_pending': pending_fups,
                    'followups_overdue': overdue_fups,
                    'followups_rescheduled': rescheduled_fups,
                    'followups_not_interested': not_interested_fups,
                    'followups_created_in_period': followups_created_in_period,
                    'followups_overdue_pending_total': overdue_pending_excl_future,
                    'resolution_rate': resolution_rate,
                    'unresolved_count': unresolved_count,
                    'followup_deficit': total_resolved_fups - total_fups,
                    # Telephony
                    'calls_total': calls_total,
                    'calls_incoming': calls_incoming,
                    'calls_outgoing': calls_outgoing,
                    'calls_answered': calls_answered,
                    'calls_missed': calls_missed,
                    'total_talktime_sec': total_talktime_sec,
                    'avg_talktime_sec': avg_talktime_sec,
                    'talktime_display': talktime_display,
                    # Scorecard & Rank
                    'performance_score': perf_score,
                    'rank': 1,
                    'is_top_performer': False,
                },
                'converted_leads_detail': converted_leads_detail,
            })

        # Sort employees by performance_score descending, then converted_leads, then total_talktime_sec
        results.sort(key=lambda r: (r['summary']['performance_score'], r['summary']['converted_leads'], r['summary']['total_talktime_sec']), reverse=True)
        for idx, r in enumerate(results, start=1):
            r['summary']['rank'] = idx
            if idx == 1 and r['summary']['performance_score'] > 0:
                r['summary']['is_top_performer'] = True

        grand_total_leads = sum(r['summary']['total_leads'] for r in results)
        grand_fresh_leads = sum(r['summary']['fresh_leads'] for r in results)
        grand_followup_leads = sum(r['summary']['followup_leads'] for r in results)
        grand_converted = sum(r['summary']['converted_leads'] for r in results)
        grand_hot = sum(r['summary']['hot_leads'] for r in results)
        grand_warm = sum(r['summary']['warm_leads'] for r in results)
        grand_cold = sum(r['summary']['cold_leads'] for r in results)
        grand_fu_total = sum(r['summary']['followups_total'] for r in results)
        grand_fu_contacted = sum(r['summary']['followups_contacted'] for r in results)
        grand_fu_completed = sum(r['summary']['followups_completed'] for r in results)
        grand_fu_resolved = sum(r['summary']['followups_resolved'] for r in results)
        grand_fu_pending = sum(r['summary']['followups_pending'] for r in results)
        grand_fu_overdue = sum(r['summary']['followups_overdue'] for r in results)
        grand_calls_total = sum(r['summary']['calls_total'] for r in results)
        grand_calls_answered = sum(r['summary']['calls_answered'] for r in results)
        grand_calls_missed = sum(r['summary']['calls_missed'] for r in results)
        grand_talktime_sec = sum(r['summary']['total_talktime_sec'] for r in results)

        top_emp = results[0]['employee'] if results and results[0]['summary']['performance_score'] > 0 else None

        return Response({
            'grand_summary': {
                'total_leads': grand_total_leads,
                'fresh_leads': grand_fresh_leads,
                'followup_leads': grand_followup_leads,
                'converted_leads': grand_converted,
                'conversion_rate': round((grand_converted / grand_total_leads * 100), 1) if grand_total_leads else 0.0,
                'hot_leads': grand_hot,
                'warm_leads': grand_warm,
                'cold_leads': grand_cold,
                'followups_total': grand_fu_total,
                'followups_contacted': grand_fu_contacted,
                'followups_completed': grand_fu_completed,
                'followups_resolved': grand_fu_resolved,
                'followups_pending': grand_fu_pending,
                'followups_overdue': grand_fu_overdue,
                'completion_rate': round((grand_fu_resolved / grand_fu_total * 100), 1) if grand_fu_total else 0.0,
                'calls_total': grand_calls_total,
                'calls_answered': grand_calls_answered,
                'calls_missed': grand_calls_missed,
                'total_talktime_sec': grand_talktime_sec,
                'talktime_display': _format_seconds(grand_talktime_sec),
                'top_performer': top_emp,
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
    search_fields = ['name', 'phone', 'email', 'remarks', 'program', 'location']

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

        if employee_id and str(employee_id).isdigit():
            emp_id = int(employee_id)
            lead_qs = lead_qs.filter(
                Q(assigned_to_id=emp_id) |
                Q(sub_assigned_to_id=emp_id) |
                Q(followups__assigned_to_id=emp_id)
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
            ctype = 'unknown'
            if lead.voxbay_status:
                vs = lead.voxbay_status.lower()
                if 'inbound' in vs or 'incoming' in vs: ctype = 'incoming'
                elif 'outbound' in vs or 'outgoing' in vs: ctype = 'outgoing'
            elif lead.source == 'VOXBAY CALL':
                ctype = 'outgoing'
                
            all_fups = list(lead.followups.all())
            is_fresh = False
            if start_date and end_date:
                is_fresh = bool(lead.created_at and start_date <= lead.created_at.date() <= end_date)
            else:
                is_fresh = (len(all_fups) <= 1)
                
            lead_tag = 'FRESH' if is_fresh else 'FOLLOWUP'
            lead_tag_display = 'Fresh Lead' if is_fresh else 'Follow-up Lead'

            period_fup = None
            if start_date and end_date:
                for f in all_fups:
                    if f.follow_up_date and start_date <= f.follow_up_date <= end_date:
                        period_fup = f
                        break
            latest_fup = period_fup or (all_fups[0] if all_fups else None)

            latest_fup_data = None
            if latest_fup:
                latest_fup_data = {
                    'id': latest_fup.id,
                    'follow_up_date': latest_fup.follow_up_date.isoformat() if latest_fup.follow_up_date else None,
                    'status': latest_fup.status,
                    'notes': latest_fup.notes,
                    'recording_url': _extract_recording_url(latest_fup.notes),
                    'is_overdue': bool(latest_fup.is_overdue),
                }

            assigned_name = ''
            if lead.assigned_to:
                assigned_name = lead.assigned_to.get_full_name() or lead.assigned_to.username
            elif lead.sub_assigned_to:
                assigned_name = lead.sub_assigned_to.get_full_name() or lead.sub_assigned_to.username
                
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
                'assigned_to_name': assigned_name,
                'followups': [
                    {
                        'id': f.id,
                        'follow_up_date': f.follow_up_date.isoformat() if f.follow_up_date else None,
                        'status': f.status,
                        'notes': f.notes,
                        'recording_url': _extract_recording_url(f.notes),
                        'is_overdue': bool(f.is_overdue),
                    } for f in all_fups
                ]
            }

        if page is not None:
            data = [_serialize(lead) for lead in page]
            return self.get_paginated_response(data)

        data = [_serialize(lead) for lead in queryset]
        return Response(data)


class StaffAnalysisFollowUpsAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StaffAnalysisPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'phone_number', 'notes', 'lead__name', 'lead__phone']

    def get_queryset(self):
        user = self.request.user
        is_admin = (
            user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists()
            or has_dynamic_permission(user, 'leads:read_tenant')
            or has_dynamic_permission(user, 'leads:read_any')
            or has_dynamic_permission(user, 'staff_analysis:admin')
        )
        if not is_admin:
            return FollowUp.objects.none()

        start_date, end_date = _get_date_range(self.request)
        employee_id = self.request.query_params.get('employee_id')
        status_filter = self.request.query_params.get('status', '')

        fu_qs = FollowUp.objects.select_related('lead', 'assigned_to')

        if employee_id and str(employee_id).isdigit():
            fu_qs = fu_qs.filter(assigned_to_id=int(employee_id))

        if start_date and end_date:
            fu_qs = fu_qs.filter(follow_up_date__gte=start_date, follow_up_date__lte=end_date)

        if status_filter:
            statuses = [s.strip().lower() for s in status_filter.split(',') if s.strip()]
            fu_qs = fu_qs.filter(status__in=statuses)

        return fu_qs.order_by('-follow_up_date', '-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        today = timezone.now().date()

        def _serialize_fu(f):
            is_overdue = bool(f.status == 'pending' and f.follow_up_date and f.follow_up_date < today)
            follow_up_time_str = None
            if f.follow_up_time:
                follow_up_time_str = f.follow_up_time.isoformat() if hasattr(f.follow_up_time, 'isoformat') else str(f.follow_up_time)
            assigned_name = ''
            if f.assigned_to:
                assigned_name = f.assigned_to.get_full_name() or f.assigned_to.username
            return {
                'id': f.id,
                'name': f.name or (f.lead.name if f.lead else ''),
                'phone': f.phone_number or (f.lead.phone if f.lead else ''),
                'follow_up_date': f.follow_up_date.isoformat() if hasattr(f.follow_up_date, 'isoformat') else (str(f.follow_up_date) if f.follow_up_date else None),
                'follow_up_time': follow_up_time_str,
                'status': f.status,
                'priority': f.priority,
                'followup_type': f.followup_type,
                'notes': f.notes,
                'recording_url': _extract_recording_url(f.notes),
                'is_overdue': is_overdue,
                'assigned_to_name': assigned_name,
                'lead': {
                    'id': f.lead.id,
                    'name': f.lead.name,
                    'phone': f.lead.phone,
                    'status': f.lead.status,
                    'program': f.lead.program,
                } if f.lead else None,
            }

        if page is not None:
            data = [_serialize_fu(f) for f in page]
            return self.get_paginated_response(data)

        data = [_serialize_fu(f) for f in queryset]
        return Response(data)
