"""
Dashboard Aggregation Service for LP CRM
Milestone 2: Unified CRM Operational Data Model & RBAC Aggregation Engine
"""

from decimal import Decimal
from django.db.models import Count, Sum, Q, Case, When, IntegerField
from django.utils import timezone
from accounts.models import User, ActivityLog
from accounts.permissions import has_dynamic_permission
from leads.models import Lead, FollowUp, LeadConversionDetail
from tasks.models import Task
from fees.models import StudentFeeAccount, FeePayment


class DashboardAggregationService:
    """
    High-performance aggregation service executing unified, single-round-trip
    operational CRM aggregations over leads, tasks, followups, and fees.
    Enforces dynamic role and permission filtering.
    """

    @staticmethod
    def get_dashboard_data(user, company=None):
        """
        Aggregate operational metrics for the given user and optional company tenant.

        :param user: The requesting accounts.User instance
        :param company: Optional company code (e.g. 'LP', 'FLAG', 'FDS', 'ALL')
        :return: Dict containing structured metrics, pipeline, followups, tasks, and financials
        """
        today = timezone.localtime(timezone.now()).date()
        month_start = today.replace(day=1)

        # ── 1. Role & Permission Evaluations ──
        has_admin_dash = has_dynamic_permission(user, 'admin:dashboard') or user.is_superuser
        can_read_all_leads = (
            has_admin_dash
            or has_dynamic_permission(user, 'leads:read_all')
        )
        can_read_fees = (
            has_admin_dash
            or has_dynamic_permission(user, 'fees:accounts')
            or has_dynamic_permission(user, 'fees:manage')
            or has_dynamic_permission(user, 'fees:view')
        )

        target_company = company

        # ── 2. Lead Pipeline QuerySet & Aggregation ──
        lead_qs = Lead.objects.all()
        if target_company and target_company != 'ALL':
            lead_qs = lead_qs.filter(company=target_company)

        # Non-admin / non-manager scoping: only assigned or created leads
        if not can_read_all_leads:
            lead_qs = lead_qs.filter(
                Q(assigned_to=user) | Q(sub_assigned_to=user) | Q(created_by=user)
            )

        lead_metrics = lead_qs.aggregate(
            total=Count('id'),
            hot=Count(Case(When(status='HOT', then=1), output_field=IntegerField())),
            warm=Count(Case(When(status='WARM', then=1), output_field=IntegerField())),
            cold=Count(Case(When(status='COLD', then=1), output_field=IntegerField())),
            enquiry=Count(Case(When(status='ENQUIRY', then=1), output_field=IntegerField())),
            job_enquiry=Count(Case(When(status='JOB_ENQUIRY', then=1), output_field=IntegerField())),
            b2b=Count(Case(When(status='B2B', then=1), output_field=IntegerField())),
            registered=Count(Case(When(status='REGISTERED', then=1), output_field=IntegerField())),
            converted=Count(Case(When(status='CONVERTED', then=1), output_field=IntegerField())),
            closed=Count(Case(When(status='CLOSED', then=1), output_field=IntegerField())),
            new_today=Count(Case(When(created_at__date=today, then=1), output_field=IntegerField())),
            new_this_month=Count(Case(When(created_at__date__gte=month_start, then=1), output_field=IntegerField()))
        )

        total_leads = lead_metrics['total'] or 0
        total_won = (lead_metrics['converted'] or 0) + (lead_metrics['registered'] or 0)
        conversion_rate = round((total_won / total_leads * 100), 1) if total_leads > 0 else 0.0

        # ── 3. Follow-Ups QuerySet & Aggregation ──
        # Active pending followups (excluding terminal leads: CLOSED, CONVERTED)
        followup_qs = FollowUp.objects.filter(status='pending').exclude(
            lead__status__in=['CLOSED', 'CONVERTED']
        )

        if target_company and target_company != 'ALL':
            followup_qs = followup_qs.filter(lead__company=target_company)

        if not can_read_all_leads:
            followup_qs = followup_qs.filter(assigned_to=user)

        followup_metrics = followup_qs.aggregate(
            due_today=Count(Case(When(follow_up_date=today, then=1), output_field=IntegerField())),
            overdue=Count(Case(When(follow_up_date__lt=today, then=1), output_field=IntegerField())),
            high_priority=Count(Case(When(priority__iexact='high', then=1), output_field=IntegerField())),
            total_pending=Count('id')
        )

        due_today = followup_metrics['due_today'] or 0
        overdue_followups = followup_metrics['overdue'] or 0
        high_priority_followups = followup_metrics['high_priority'] or 0

        # ── 4. Tasks QuerySet & Aggregation ──
        task_qs = Task.objects.exclude(status__in=['COMPLETED', 'CANCELLED'])

        if target_company and target_company != 'ALL':
            task_qs = task_qs.filter(company=target_company)

        if not has_admin_dash:
            task_qs = task_qs.filter(Q(assigned_to=user) | Q(assigned_by=user))

        task_metrics = task_qs.aggregate(
            urgent=Count(Case(When(priority__in=['HIGH', 'URGENT'], then=1), output_field=IntegerField())),
            overdue=Count(Case(When(deadline__lt=today, then=1), output_field=IntegerField())),
            pending_approval=Count(Case(When(status='PENDING_APPROVAL', then=1), output_field=IntegerField())),
            total_pending=Count('id')
        )

        my_tasks_qs = Task.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).filter(assigned_to=user)
        if target_company and target_company != 'ALL':
            my_tasks_qs = my_tasks_qs.filter(company=target_company)
        my_pending_tasks = my_tasks_qs.count()

        # ── 5. Executive Financials (Gated to admin:dashboard / fees perms) ──
        executive_financials = None
        if can_read_fees:
            fee_accounts_qs = StudentFeeAccount.objects.all()
            if target_company and target_company != 'ALL':
                fee_accounts_qs = fee_accounts_qs.filter(company=target_company)

            fee_metrics = fee_accounts_qs.aggregate(
                total_outstanding=Sum('balance_due'),
                total_overdue=Sum('overdue_amount'),
                total_due=Sum('total_due'),
                total_paid=Sum('total_paid')
            )

            payments_qs = FeePayment.objects.filter(payment_date__date__gte=month_start)
            if target_company and target_company != 'ALL':
                payments_qs = payments_qs.filter(company=target_company)
            collections_month = payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

            conv_qs = LeadConversionDetail.objects.all()
            if target_company and target_company != 'ALL':
                conv_qs = conv_qs.filter(lead__company=target_company)
            conv_metrics = conv_qs.aggregate(
                total_fees=Sum('total_fees'),
                amount_paid=Sum('amount_paid')
            )

            total_outstanding = fee_metrics['total_outstanding'] or Decimal('0')
            total_overdue = fee_metrics['total_overdue'] or Decimal('0')
            conv_fees = conv_metrics['total_fees'] or Decimal('0')
            conv_paid = conv_metrics['amount_paid'] or Decimal('0')
            total_fee_due = fee_metrics['total_due'] or Decimal('0')

            total_revenue = conv_fees + total_fee_due

            executive_financials = {
                "total_revenue": float(total_revenue),
                "collections_this_month": float(collections_month),
                "pending_receivables": float(total_outstanding),
                "total_outstanding_receivable": float(total_outstanding),
                "total_overdue_balance": float(total_overdue),
                "conversion_total_fees": float(conv_fees),
                "conversion_amount_paid": float(conv_paid),
            }

        # ── 6. Recent Activities ──
        recent_activities = []
        try:
            act_qs = ActivityLog.objects.select_related('user').all()
            if not has_admin_dash:
                act_qs = act_qs.filter(
                    Q(user=user) | Q(user__isnull=True, entity_type='Staff', entity_id=user.pk)
                )
            else:
                act_qs = act_qs.exclude(action__in=['USER_LOGIN', 'USER_LOGOUT'])
            recent_activities = list(
                act_qs.order_by('-created_at')[:10].values(
                    'id', 'action', 'entity_type', 'entity_id', 'entity_name', 'description', 'created_at'
                )
            )
        except Exception:
            recent_activities = []

        # ── 7. Construct Consolidated Response Payload ──
        role_names = (
            list(user.db_roles.values_list('name', flat=True))
            if getattr(user, 'pk', None) and hasattr(user, 'db_roles')
            else []
        )
        primary_role = role_names[0] if role_names else ('ADMIN' if user.is_superuser else 'USER')

        payload = {
            "user_role": primary_role,
            "has_admin_dashboard": has_admin_dash,
            "user": {
                "id": getattr(user, 'id', None),
                "name": user.get_full_name() or getattr(user, 'username', 'Anonymous'),
                "username": getattr(user, 'username', ''),
                "company": getattr(user, 'company', None),
                "role_names": role_names,
                "has_admin_dashboard": has_admin_dash,
            },
            "metrics": {
                "leads": {
                    "total": total_leads,
                    "hot": lead_metrics['hot'] or 0,
                    "warm": lead_metrics['warm'] or 0,
                    "cold": lead_metrics['cold'] or 0,
                    "enquiry": lead_metrics['enquiry'] or 0,
                    "job_enquiry": lead_metrics['job_enquiry'] or 0,
                    "b2b": lead_metrics['b2b'] or 0,
                    "registered": lead_metrics['registered'] or 0,
                    "converted": lead_metrics['converted'] or 0,
                    "closed": lead_metrics['closed'] or 0,
                    "conversion_rate": conversion_rate,
                },
                "followups": {
                    "today_total": due_today,
                    "today_pending": due_today,
                    "overdue": overdue_followups,
                    "high_priority": high_priority_followups,
                },
                "tasks": {
                    "my_pending": my_pending_tasks,
                    "urgent": task_metrics['urgent'] or 0,
                    "overdue": task_metrics['overdue'] or 0,
                    "team_pending": task_metrics['total_pending'] or 0,
                },
                "executive_financials": executive_financials,
            },
            "lead_pipeline": {
                "total_leads": total_leads,
                "conversion_rate": conversion_rate,
                "metrics": lead_metrics,
            },
            "followup_stats": {
                "due_today": due_today,
                "overdue": overdue_followups,
                "high_priority": high_priority_followups,
            },
            "task_stats": {
                "total_pending": task_metrics['total_pending'] or 0,
                "urgent": task_metrics['urgent'] or 0,
                "overdue": task_metrics['overdue'] or 0,
                "pending_approval": task_metrics['pending_approval'] or 0,
            },
            "recent_activities": recent_activities,
            "role_sections": {},
        }

        if executive_financials is not None:
            payload["role_sections"]["executive_financials"] = executive_financials

        return payload
