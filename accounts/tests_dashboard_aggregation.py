"""
Automated Test Suite for LP CRM Dashboard Data Model and Aggregation Engine
Requirements Covered: R4 (Dashboard Data Model and Aggregation), R6 (Automated Test Coverage)
Methodology: 4-Tier Opaque-Box Testing Architecture (Feature, Boundary, Integration, Real-World)
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Count, Sum, Q, Case, When, IntegerField
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import AppPermission, Role
from leads.models import Lead, FollowUp, LeadConversionDetail
from tasks.models import Task
from fees.models import StudentFeeAccount, FeePayment, FeePlanTemplate
from students.models import Student, Campus, AcademicPackage, Grade

# Progressive testability: Conditionally import DashboardAggregationService if implemented by M2
try:
    from accounts.dashboard_service import DashboardAggregationService
except ImportError:
    try:
        from accounts.services import DashboardAggregationService
    except ImportError:
        DashboardAggregationService = None

User = get_user_model()


class DashboardAggregationCoreModelTests(TestCase):
    """
    Tier 1 & Tier 2: Validates the mathematical precision of the dashboard data model queries,
    conversion rate formula, overdue detection boundaries, and zero-division edge cases.
    """

    def setUp(self):
        self.today = timezone.localtime(timezone.now()).date()

        # Seed users
        self.admin = User.objects.create_user(username='agg_admin', password='password123', company='LP')
        self.rep1 = User.objects.create_user(username='agg_rep1', password='password123', company='LP')
        self.rep2 = User.objects.create_user(username='agg_rep2', password='password123', company='FLAG')

        # ── Seed Leads across stages ──
        self.lead_hot = Lead.objects.create(name="Hot Lead", phone="9111111101", status="HOT", assigned_to=self.rep1, company="LP")
        self.lead_warm = Lead.objects.create(name="Warm Lead", phone="9111111102", status="WARM", assigned_to=self.rep1, company="LP")
        self.lead_cold = Lead.objects.create(name="Cold Lead", phone="9111111103", status="COLD", assigned_to=self.rep1, company="LP")
        self.lead_enquiry = Lead.objects.create(name="Enquiry Lead", phone="9111111104", status="ENQUIRY", assigned_to=self.rep1, company="LP")
        self.lead_conv = Lead.objects.create(name="Converted Lead", phone="9111111105", status="CONVERTED", assigned_to=self.rep1, company="LP")
        self.lead_reg = Lead.objects.create(name="Registered Lead", phone="9111111106", status="REGISTERED", assigned_to=self.rep1, company="LP")
        self.lead_closed = Lead.objects.create(name="Closed Lead", phone="9111111107", status="CLOSED", assigned_to=self.rep1, company="LP")
        self.lead_flag = Lead.objects.create(name="FLAG Lead", phone="9111111108", status="HOT", assigned_to=self.rep2, company="FLAG")

        # ── Seed Tasks ──
        # Urgent task due tomorrow
        self.t1 = Task.objects.create(
            title="Urgent Pitch", description="Pitch to client",
            priority="URGENT", status="PENDING",
            deadline=self.today + timedelta(days=1),
            assigned_to=self.rep1, assigned_by=self.admin, company="LP"
        )
        # High priority task overdue
        self.t2 = Task.objects.create(
            title="Overdue Documentation", description="Verify documents",
            priority="HIGH", status="PENDING",
            deadline=self.today - timedelta(days=2),
            assigned_to=self.rep1, assigned_by=self.admin, company="LP"
        )
        # Completed task (should be excluded from pending)
        self.t3 = Task.objects.create(
            title="Old Completed Task", description="Done already",
            priority="URGENT", status="COMPLETED",
            deadline=self.today - timedelta(days=5),
            assigned_to=self.rep1, assigned_by=self.admin, company="LP"
        )

        # ── Seed Follow-Ups ──
        # Due today
        self.f_today = FollowUp.objects.create(
            lead=self.lead_hot, phone_number="9111111101",
            follow_up_date=self.today, status="pending",
            priority="high", assigned_to=self.rep1
        )
        # Overdue (yesterday)
        self.f_overdue = FollowUp.objects.create(
            lead=self.lead_warm, phone_number="9111111102",
            follow_up_date=self.today - timedelta(days=1), status="pending",
            priority="medium", assigned_to=self.rep1
        )
        # Completed follow-up (should be excluded from pending)
        self.f_completed = FollowUp.objects.create(
            lead=self.lead_cold, phone_number="9111111103",
            follow_up_date=self.today - timedelta(days=3), status="completed",
            priority="low", assigned_to=self.rep1
        )
        # Follow-up on a lead that is now CONVERTED (auto-resolved from active queue)
        self.f_converted_lead = FollowUp.objects.create(
            lead=self.lead_conv, phone_number="9111111105",
            follow_up_date=self.today, status="pending",
            priority="high", assigned_to=self.rep1
        )

    # ── Tier 1: Lead Pipeline & Conversion Metrics ─────────────────────────────

    def test_lead_pipeline_aggregation_counts(self):
        """Verifies aggregations for individual pipeline stages."""
        lp_leads = Lead.objects.filter(company="LP")
        metrics = lp_leads.aggregate(
            total=Count('id'),
            hot=Count(Case(When(status='HOT', then=1), output_field=IntegerField())),
            warm=Count(Case(When(status='WARM', then=1), output_field=IntegerField())),
            cold=Count(Case(When(status='COLD', then=1), output_field=IntegerField())),
            enquiry=Count(Case(When(status='ENQUIRY', then=1), output_field=IntegerField())),
            converted=Count(Case(When(status='CONVERTED', then=1), output_field=IntegerField())),
            registered=Count(Case(When(status='REGISTERED', then=1), output_field=IntegerField())),
            closed=Count(Case(When(status='CLOSED', then=1), output_field=IntegerField())),
        )

        self.assertEqual(metrics['total'], 7)
        self.assertEqual(metrics['hot'], 1)
        self.assertEqual(metrics['warm'], 1)
        self.assertEqual(metrics['cold'], 1)
        self.assertEqual(metrics['enquiry'], 1)
        self.assertEqual(metrics['converted'], 1)
        self.assertEqual(metrics['registered'], 1)
        self.assertEqual(metrics['closed'], 1)

    def test_lead_conversion_rate_mathematical_precision(self):
        """Conversion rate formula: (converted + registered) / total * 100."""
        lp_leads = Lead.objects.filter(company="LP")
        metrics = lp_leads.aggregate(
            total=Count('id'),
            converted=Count(Case(When(status='CONVERTED', then=1), output_field=IntegerField())),
            registered=Count(Case(When(status='REGISTERED', then=1), output_field=IntegerField())),
        )
        total = metrics['total']
        won = metrics['converted'] + metrics['registered']  # 1 + 1 = 2
        rate = round((won / total * 100), 1) if total > 0 else 0.0

        # 2 won out of 7 total = 28.5714% -> 28.6%
        self.assertEqual(rate, 28.6)

    # ── Tier 2: Boundary & Corner Cases ─────────────────────────────────────────

    def test_zero_leads_zero_division_guard(self):
        """Ensures an empty company returns 0.0 conversion rate without ZeroDivisionError."""
        fds_leads = Lead.objects.filter(company="FDS")
        total = fds_leads.count()
        rate = round((0 / total * 100), 1) if total > 0 else 0.0
        self.assertEqual(rate, 0.0)

    def test_followup_overdue_boundary_calculations(self):
        """
        Pending follow-ups with date < today must be flagged overdue.
        Follow-ups with date == today must be flagged due today.
        Follow-ups attached to closed/converted leads must be filtered out.
        """
        pending_followups = FollowUp.objects.filter(status='pending').exclude(
            lead__status__in=['CLOSED', 'CONVERTED']
        )
        counts = pending_followups.aggregate(
            due_today=Count(Case(When(follow_up_date=self.today, then=1), output_field=IntegerField())),
            overdue=Count(Case(When(follow_up_date__lt=self.today, then=1), output_field=IntegerField()))
        )

        # f_today is active on lead_hot (due today)
        self.assertEqual(counts['due_today'], 1)
        # f_overdue is active on lead_warm (yesterday)
        self.assertEqual(counts['overdue'], 1)
        # f_converted_lead is on lead_conv (status CONVERTED), so excluded!
        self.assertNotIn(self.f_converted_lead, pending_followups)

    def test_task_urgency_and_overdue_aggregation(self):
        """
        Active tasks (excluding COMPLETED, CANCELLED) aggregate urgent vs overdue counts.
        """
        active_tasks = Task.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).filter(company="LP")
        task_metrics = active_tasks.aggregate(
            urgent=Count(Case(When(priority__in=['HIGH', 'URGENT'], then=1), output_field=IntegerField())),
            overdue=Count(Case(When(deadline__lt=self.today, then=1), output_field=IntegerField())),
            total=Count('id')
        )

        self.assertEqual(task_metrics['total'], 2)  # t1 and t2
        self.assertEqual(task_metrics['urgent'], 2) # t1 (URGENT) and t2 (HIGH)
        self.assertEqual(task_metrics['overdue'], 1) # t2 deadline < today (t3 is COMPLETED so excluded)


class DashboardAggregationScopingAndIntegrationTests(TestCase):
    """
    Tier 3 & Tier 4: Multi-company tenant isolation, role-based scoping,
    and DashboardAggregationService end-to-end integration.
    """

    def setUp(self):
        self.today = timezone.localtime(timezone.now()).date()

        # Seed roles & permissions
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Full admin dashboard metrics'}
        )
        self.perm_leads_read_all, _ = AppPermission.objects.get_or_create(
            name='leads:read_all',
            defaults={'description': 'Read all leads in tenant'}
        )

        self.role_admin = Role.objects.create(name='ADMIN')
        self.role_admin.permissions.add(self.perm_admin_dash, self.perm_leads_read_all)

        self.role_sales = Role.objects.create(name='SALES')

        # Users
        self.admin = User.objects.create_user(username='integ_admin', password='password123', company='LP')
        self.admin.db_roles.add(self.role_admin)

        self.rep_a = User.objects.create_user(username='integ_rep_a', password='password123', company='LP')
        self.rep_a.db_roles.add(self.role_sales)

        self.rep_b = User.objects.create_user(username='integ_rep_b', password='password123', company='LP')
        self.rep_b.db_roles.add(self.role_sales)

        # Assign leads
        Lead.objects.create(name="Rep A Lead 1", phone="9200000001", status="HOT", assigned_to=self.rep_a, company="LP")
        Lead.objects.create(name="Rep A Lead 2", phone="9200000002", status="CONVERTED", assigned_to=self.rep_a, company="LP")
        Lead.objects.create(name="Rep B Lead 1", phone="9200000003", status="WARM", assigned_to=self.rep_b, company="LP")
        Lead.objects.create(name="Rep B Lead 2", phone="9200000004", status="CLOSED", assigned_to=self.rep_b, company="LP")

    def test_sales_rep_ownership_scoping(self):
        """
        A sales rep without admin:dashboard or leads:read_all should only see
        leads assigned to them or created by them.
        """
        # Rep A sees only their 2 leads
        rep_a_leads = Lead.objects.filter(
            Q(assigned_to=self.rep_a) | Q(created_by=self.rep_a)
        )
        self.assertEqual(rep_a_leads.count(), 2)

        # Rep B sees only their 2 leads
        rep_b_leads = Lead.objects.filter(
            Q(assigned_to=self.rep_b) | Q(created_by=self.rep_b)
        )
        self.assertEqual(rep_b_leads.count(), 2)

        # Admin with leads:read_all sees all 4 leads in company LP
        admin_leads = Lead.objects.filter(company="LP")
        self.assertEqual(admin_leads.count(), 4)

    def test_multi_company_lead_isolation(self):
        """Leads created under company FLAG do not bleed into LP aggregations."""
        Lead.objects.create(name="FLAG Lead", phone="9300000001", status="HOT", company="FLAG")

        lp_count = Lead.objects.filter(company="LP").count()
        flag_count = Lead.objects.filter(company="FLAG").count()

        self.assertEqual(lp_count, 4)
        self.assertEqual(flag_count, 1)

    def test_dashboard_aggregation_service_if_present(self):
        """
        If DashboardAggregationService is implemented (M2), verify get_dashboard_data
        returns structured payload with user, lead_pipeline, task_stats, and followup_stats.
        """
        if DashboardAggregationService is None:
            self.skipTest("DashboardAggregationService not yet implemented (scheduled in Milestone 2)")

        result = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertIsNotNone(result)
        self.assertIn('lead_pipeline', result)
        self.assertIn('task_stats', result)
        self.assertIn('followup_stats', result)
        self.assertTrue(result.get('user', {}).get('has_admin_dashboard', False))

    def test_dashboard_aggregation_service_financials_for_admin(self):
        """Verifies that admin receives executive financials aggregated from fees and conversions."""
        # Seed student, fee account, fee payment, and lead conversion
        campus = Campus.objects.create(name="Kottayam Campus", code="KTM")
        grade = Grade.objects.create(code="A1", name="A1 - Beginner", order=1)
        pkg = AcademicPackage.objects.create(name="German A1", starting_grade=grade, ending_grade=grade)
        student = Student.objects.create(name="Finance Student", phone="9400000001", campus=campus, academic_package=pkg)
        fee_account = StudentFeeAccount.objects.create(
            student=student, company="LP", total_due=Decimal('60000.00'),
            total_paid=Decimal('20000.00'), balance_due=Decimal('40000.00'),
            overdue_amount=Decimal('10000.00')
        )
        from fees.models import FeeInstallment
        FeeInstallment.objects.create(
            account=fee_account, sequence_number=1, due_date=timezone.now().date() - timedelta(days=5),
            scheduled_amount=Decimal('30000.00'), paid_amount=Decimal('20000.00'),
            balance_amount=Decimal('10000.00'), status='OVERDUE'
        )
        FeePayment.objects.create(
            account=fee_account, receipt_number="RCP-M2-001", amount=Decimal('20000.00'),
            company="LP", payment_date=timezone.now()
        )
        lead_conv = Lead.objects.filter(assigned_to=self.rep_a, status="CONVERTED").first()
        LeadConversionDetail.objects.create(
            lead=lead_conv, total_fees=Decimal('50000.00'), amount_paid=Decimal('25000.00'),
            payment_status="PARTIAL"
        )

        result = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertIsNotNone(result['metrics']['executive_financials'])
        fin = result['metrics']['executive_financials']

        # Total revenue = conversion fees (50,000) + student fee total due (30,000 from installments) = 80,000
        self.assertEqual(fin['total_revenue'], 80000.0)
        self.assertEqual(fin['collections_this_month'], 20000.0)
        self.assertEqual(fin['pending_receivables'], 10000.0)
        self.assertEqual(fin['total_overdue_balance'], 10000.0)
        self.assertIn('executive_financials', result['role_sections'])

    def test_dashboard_aggregation_service_hides_financials_for_non_admin(self):
        """Verifies that non-admin without fee perms receives None for executive financials and scoped leads."""
        result = DashboardAggregationService.get_dashboard_data(self.rep_a, company='LP')
        self.assertFalse(result.get('user', {}).get('has_admin_dashboard', True))
        self.assertIsNone(result['metrics']['executive_financials'])
        self.assertNotIn('executive_financials', result['role_sections'])

        # Rep A only sees their 2 assigned leads
        self.assertEqual(result['lead_pipeline']['total_leads'], 2)
        self.assertEqual(result['metrics']['leads']['total'], 2)

    def test_dashboard_aggregation_api_endpoints(self):
        """Tests /api/dashboard/stats/ and /api/dashboard/overview/ endpoints for authorized users."""
        client = APIClient()

        # Unauthenticated -> 401
        res = client.get('/api/dashboard/stats/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Authenticated Admin -> 200
        client.force_authenticate(user=self.admin)
        res_admin = client.get('/api/dashboard/stats/?company=LP')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertTrue(res_admin.data.get('has_admin_dashboard'))
        self.assertIn('metrics', res_admin.data)
        self.assertIn('leads', res_admin.data['metrics'])

        # Authenticated Sales Rep with leads:read_tenant -> 200 with scoped metrics
        perm_leads_read_tenant, _ = AppPermission.objects.get_or_create(
            name='leads:read_tenant',
            defaults={'description': 'Read tenant leads'}
        )
        self.role_sales.permissions.add(perm_leads_read_tenant)
        if hasattr(self.rep_a, '_dynamic_perms_cache'):
            delattr(self.rep_a, '_dynamic_perms_cache')

        client.force_authenticate(user=self.rep_a)
        res_rep = client.get('/api/dashboard/stats/?company=LP')
        self.assertEqual(res_rep.status_code, status.HTTP_200_OK)
        self.assertFalse(res_rep.data.get('has_admin_dashboard'))
        self.assertIsNone(res_rep.data['metrics']['executive_financials'])
        self.assertEqual(res_rep.data['metrics']['leads']['total'], 2)

        # Unprivileged User -> 403 Forbidden
        unprivileged = User.objects.create_user(username='api_plain_unprivileged', password='password123')
        client.force_authenticate(user=unprivileged)
        res_unprivileged = client.get('/api/dashboard/stats/')
        self.assertEqual(res_unprivileged.status_code, status.HTTP_403_FORBIDDEN)


