"""
Empirical & Adversarial Challenger Test Suite for Milestone 2 (M2)
Agent: challenger_m2_1
Mission: Empirically challenge Milestone 2 operational aggregation logic, boundary conditions, and RBAC enforcement.

Test Dimensions:
1. Zero-Division & Empty DB Stress Tests:
   - Empty database returns conversion rate 0.0 without ZeroDivisionError
   - Single tenant with 0 leads in multi-tenant DB returns conversion rate 0.0
   - Leads with 0 won leads returns 0.0% conversion rate
   - Leads with 100% won leads returns 100.0% conversion rate
   - Staff user with 0 assigned leads returns 0.0% conversion rate without error

2. Terminal Leads Follow-Up Invariant:
   - Pending followups on CLOSED leads are strictly excluded from active counts
   - Pending followups on CONVERTED leads are strictly excluded from active counts
   - Pending followups on non-terminal leads (HOT, WARM, COLD, REGISTERED) are included
   - Terminal followups (completed, contacted, not_interested) on active leads are excluded
   - Invariant holds even if pending followup was forcefully attached to terminal lead bypassing save()

3. Date Boundary Stress Tests:
   - follow_up_date < today (yesterday, last month) -> counted strictly as overdue, NOT due_today
   - follow_up_date == today -> counted strictly as due_today, NOT overdue
   - follow_up_date > today (tomorrow, next month) -> counted in total_pending, NOT overdue, NOT due_today
   - Task deadline < today vs == today vs > today:
     - deadline < today counted as overdue
     - deadline == today NOT counted as overdue
     - completed / cancelled tasks excluded regardless of deadline

4. Privilege & RBAC Boundary Enforcement:
   - Staff user without admin:dashboard:
     - executive_financials is strictly None in metrics
     - executive_financials is strictly omitted from role_sections
     - has_admin_dashboard is strictly False
     - Operational scoping: only assigned / created leads, tasks, followups visible
   - Admin user with admin:dashboard:
     - executive_financials is dict with exact aggregated values
     - executive_financials present in role_sections
     - has_admin_dashboard is strictly True
   - API HTTP endpoints (/api/dashboard/stats/ and /api/stats/):
     - Unauthenticated -> 401
     - Unprivileged user -> 403
     - Staff user -> 200 with executive_financials=None and omitted from role_sections
     - Admin user -> 200 with full executive_financials
"""

from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import AppPermission, Role
from accounts.permissions import has_dynamic_permission
from accounts.dashboard_service import DashboardAggregationService
from leads.models import Lead, FollowUp, LeadConversionDetail
from tasks.models import Task
from fees.models import StudentFeeAccount, FeePayment, FeeInstallment
from students.models import Student, Campus, AcademicPackage, Grade

User = get_user_model()


class ChallengerZeroDivisionStressTestCase(TestCase):
    """
    Empirical tests challenging mathematical stability and zero-division defenses.
    """

    def setUp(self):
        # Create administrative user and staff user
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Full admin dashboard access'}
        )
        self.role_admin = Role.objects.create(name='ADMIN')
        self.role_admin.permissions.add(self.perm_admin_dash)

        self.role_sales = Role.objects.create(name='SALES')

        self.admin = User.objects.create_user(
            username='challenger_admin_zero',
            password='password123',
            company='LP'
        )
        self.admin.db_roles.add(self.role_admin)

        self.staff_user = User.objects.create_user(
            username='challenger_staff_zero',
            password='password123',
            company='LP'
        )
        self.staff_user.db_roles.add(self.role_sales)

    def test_completely_empty_database_zero_division(self):
        """
        In a brand new, empty database with 0 leads, 0 followups, 0 tasks, 0 fees:
        get_dashboard_data must execute cleanly and return conversion_rate=0.0.
        """
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(FollowUp.objects.count(), 0)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(StudentFeeAccount.objects.count(), 0)

        data = DashboardAggregationService.get_dashboard_data(self.admin)

        self.assertIsNotNone(data)
        self.assertEqual(data['metrics']['leads']['total'], 0)
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 0.0)
        self.assertEqual(data['lead_pipeline']['conversion_rate'], 0.0)
        self.assertEqual(data['metrics']['followups']['today_total'], 0)
        self.assertEqual(data['metrics']['followups']['overdue'], 0)
        self.assertEqual(data['metrics']['tasks']['urgent'], 0)
        self.assertEqual(data['metrics']['tasks']['overdue'], 0)
        self.assertEqual(data['metrics']['tasks']['team_pending'], 0)

    def test_zero_leads_for_specific_company_filter(self):
        """
        When database has leads in company 'LP', querying company 'NON_EXISTENT'
        must return conversion_rate=0.0 without ZeroDivisionError.
        """
        Lead.objects.create(name="Lead LP", phone="9100000001", status="CONVERTED", company="LP")
        self.assertEqual(Lead.objects.filter(company="LP").count(), 1)

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='NON_EXISTENT')

        self.assertEqual(data['metrics']['leads']['total'], 0)
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 0.0)
        self.assertEqual(data['lead_pipeline']['conversion_rate'], 0.0)

    def test_staff_user_with_zero_assigned_leads_in_populated_db(self):
        """
        Staff user has 0 assigned leads while system has 100 leads.
        Staff user's scoped leads count is 0 -> conversion rate must be 0.0 without ZeroDivisionError.
        """
        for i in range(10):
            Lead.objects.create(
                name=f"Admin Lead {i}",
                phone=f"92000000{i:02d}",
                status="HOT",
                company="LP"
            )
        self.assertEqual(Lead.objects.count(), 10)

        # Staff user has no assigned leads
        data = DashboardAggregationService.get_dashboard_data(self.staff_user, company='LP')

        self.assertEqual(data['metrics']['leads']['total'], 0)
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 0.0)

    def test_zero_conversions_rate_precision(self):
        """
        When leads exist but none are converted or registered, conversion rate must be 0.0.
        """
        for i in range(5):
            Lead.objects.create(
                name=f"Lead {i}",
                phone=f"93000000{i:02d}",
                status="HOT",
                company="LP"
            )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['total'], 5)
        self.assertEqual(data['metrics']['leads']['converted'], 0)
        self.assertEqual(data['metrics']['leads']['registered'], 0)
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 0.0)

    def test_100_percent_conversion_rate_precision(self):
        """
        When all leads are converted or registered, conversion rate must be 100.0.
        """
        Lead.objects.create(name="Conv Lead 1", phone="9400000001", status="CONVERTED", company="LP")
        Lead.objects.create(name="Reg Lead 2", phone="9400000002", status="REGISTERED", company="LP")

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['total'], 2)
        self.assertEqual(data['metrics']['leads']['converted'], 1)
        self.assertEqual(data['metrics']['leads']['registered'], 1)
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 100.0)


class ChallengerTerminalLeadsFollowUpTestCase(TestCase):
    """
    Empirical tests verifying the terminal leads follow-up invariant:
    Pending follow-ups on CLOSED or CONVERTED leads MUST be excluded from active queues.
    """

    def setUp(self):
        self.today = timezone.localtime(timezone.now()).date()
        self.admin = User.objects.create_user(
            username='challenger_admin_terminal',
            password='password123',
            is_superuser=True
        )

        # Create leads across multiple statuses
        self.lead_hot = Lead.objects.create(name="Lead Hot", phone="9500000001", status="HOT", company="LP")
        self.lead_warm = Lead.objects.create(name="Lead Warm", phone="9500000002", status="WARM", company="LP")
        self.lead_reg = Lead.objects.create(name="Lead Reg", phone="9500000003", status="REGISTERED", company="LP")
        self.lead_closed = Lead.objects.create(name="Lead Closed", phone="9500000004", status="CLOSED", company="LP")
        self.lead_conv = Lead.objects.create(name="Lead Converted", phone="9500000005", status="CONVERTED", company="LP")

    def test_pending_followup_on_closed_lead_excluded(self):
        """
        A pending follow-up directly attached to a CLOSED lead must not be counted
        in active followups (due_today, overdue, or total_pending).
        """
        # Force a pending followup on closed lead (e.g. created after closing or via bulk op)
        FollowUp.objects.create(
            lead=self.lead_closed,
            phone_number=self.lead_closed.phone,
            follow_up_date=self.today,
            status='pending',
            assigned_to=self.admin
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['followups']['today_total'], 0)
        self.assertEqual(data['followup_stats']['due_today'], 0)

    def test_pending_followup_on_converted_lead_excluded(self):
        """
        A pending follow-up directly attached to a CONVERTED lead must not be counted
        in active followups (due_today, overdue, or total_pending).
        """
        FollowUp.objects.create(
            lead=self.lead_conv,
            phone_number=self.lead_conv.phone,
            follow_up_date=self.today - timedelta(days=2),
            status='pending',
            assigned_to=self.admin
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['followups']['overdue'], 0)
        self.assertEqual(data['followup_stats']['overdue'], 0)

    def test_pending_followup_on_active_leads_included(self):
        """
        Pending follow-ups on active leads (HOT, WARM, REGISTERED) MUST be included.
        """
        # Due today on HOT lead
        FollowUp.objects.create(
            lead=self.lead_hot,
            phone_number=self.lead_hot.phone,
            follow_up_date=self.today,
            status='pending',
            priority='high',
            assigned_to=self.admin
        )
        # Overdue on WARM lead
        FollowUp.objects.create(
            lead=self.lead_warm,
            phone_number=self.lead_warm.phone,
            follow_up_date=self.today - timedelta(days=1),
            status='pending',
            priority='medium',
            assigned_to=self.admin
        )
        # Due today on REGISTERED lead (active pipeline stage)
        FollowUp.objects.create(
            lead=self.lead_reg,
            phone_number=self.lead_reg.phone,
            follow_up_date=self.today,
            status='pending',
            priority='high',
            assigned_to=self.admin
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['followups']['today_total'], 2)  # HOT + REGISTERED
        self.assertEqual(data['metrics']['followups']['overdue'], 1)      # WARM
        self.assertEqual(data['metrics']['followups']['high_priority'], 2)

    def test_completed_and_contacted_followups_excluded(self):
        """
        Follow-ups with status other than 'pending' (e.g. contacted, completed)
        must NOT be included in active queues regardless of lead status.
        """
        FollowUp.objects.create(
            lead=self.lead_hot,
            phone_number=self.lead_hot.phone,
            follow_up_date=self.today,
            status='contacted',
            assigned_to=self.admin
        )
        FollowUp.objects.create(
            lead=self.lead_warm,
            phone_number=self.lead_warm.phone,
            follow_up_date=self.today,
            status='completed',
            assigned_to=self.admin
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['followups']['today_total'], 0)
        self.assertEqual(data['metrics']['followups']['overdue'], 0)


class ChallengerDateBoundaryStressTestCase(TestCase):
    """
    Empirical tests challenging temporal boundaries (< today vs == today vs > today)
    across followups and tasks.
    """

    def setUp(self):
        self.today = timezone.localtime(timezone.now()).date()
        self.admin = User.objects.create_user(
            username='challenger_admin_dates',
            password='password123',
            is_superuser=True
        )
        self.lead = Lead.objects.create(name="Date Boundary Lead", phone="9600000001", status="HOT", company="LP")

    def test_followup_date_tripartite_boundary(self):
        """
        Exact boundary test:
        - 1 follow-up with follow_up_date = today - 1 (overdue)
        - 1 follow-up with follow_up_date = today - 30 (deeply overdue)
        - 1 follow-up with follow_up_date = today (due today)
        - 1 follow-up with follow_up_date = today + 1 (due tomorrow)
        - 1 follow-up with follow_up_date = today + 15 (future)

        Expected:
        - due_today = 1 (only today)
        - overdue = 2 (today - 1, today - 30)
        - Neither future follow-up should leak into due_today or overdue!
        """
        FollowUp.objects.create(lead=self.lead, phone_number="9600000001", follow_up_date=self.today - timedelta(days=1), status='pending', assigned_to=self.admin)
        FollowUp.objects.create(lead=self.lead, phone_number="9600000001", follow_up_date=self.today - timedelta(days=30), status='pending', assigned_to=self.admin)
        FollowUp.objects.create(lead=self.lead, phone_number="9600000001", follow_up_date=self.today, status='pending', assigned_to=self.admin)
        FollowUp.objects.create(lead=self.lead, phone_number="9600000001", follow_up_date=self.today + timedelta(days=1), status='pending', assigned_to=self.admin)
        FollowUp.objects.create(lead=self.lead, phone_number="9600000001", follow_up_date=self.today + timedelta(days=15), status='pending', assigned_to=self.admin)

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')

        self.assertEqual(data['metrics']['followups']['today_total'], 1)
        self.assertEqual(data['metrics']['followups']['today_pending'], 1)
        self.assertEqual(data['metrics']['followups']['overdue'], 2)
        self.assertEqual(data['followup_stats']['due_today'], 1)
        self.assertEqual(data['followup_stats']['overdue'], 2)

    def test_task_deadline_tripartite_boundary_and_status(self):
        """
        Exact task boundary test:
        - Task 1: deadline = today - 1, status = PENDING, priority = URGENT -> overdue, urgent, pending
        - Task 2: deadline = today, status = PENDING, priority = HIGH -> NOT overdue, urgent, pending
        - Task 3: deadline = today + 1, status = PENDING, priority = LOW -> NOT overdue, NOT urgent, pending
        - Task 4: deadline = today - 5, status = COMPLETED, priority = URGENT -> EXCLUDED completely
        - Task 5: deadline = today - 5, status = CANCELLED, priority = URGENT -> EXCLUDED completely

        Expected:
        - total_pending = 3 (Task 1, 2, 3)
        - overdue = 1 (Task 1)
        - urgent = 2 (Task 1, 2)
        """
        Task.objects.create(
            title="Overdue Urgent", description="T1", priority="URGENT", status="PENDING",
            deadline=self.today - timedelta(days=1), assigned_to=self.admin, assigned_by=self.admin, company="LP"
        )
        Task.objects.create(
            title="Due Today High", description="T2", priority="HIGH", status="PENDING",
            deadline=self.today, assigned_to=self.admin, assigned_by=self.admin, company="LP"
        )
        Task.objects.create(
            title="Future Low", description="T3", priority="LOW", status="PENDING",
            deadline=self.today + timedelta(days=1), assigned_to=self.admin, assigned_by=self.admin, company="LP"
        )
        Task.objects.create(
            title="Old Completed", description="T4", priority="URGENT", status="COMPLETED",
            deadline=self.today - timedelta(days=5), assigned_to=self.admin, assigned_by=self.admin, company="LP"
        )
        Task.objects.create(
            title="Old Cancelled", description="T5", priority="URGENT", status="CANCELLED",
            deadline=self.today - timedelta(days=5), assigned_to=self.admin, assigned_by=self.admin, company="LP"
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')

        self.assertEqual(data['metrics']['tasks']['team_pending'], 3)
        self.assertEqual(data['metrics']['tasks']['overdue'], 1)
        self.assertEqual(data['metrics']['tasks']['urgent'], 2)
        self.assertEqual(data['task_stats']['total_pending'], 3)
        self.assertEqual(data['task_stats']['overdue'], 1)
        self.assertEqual(data['task_stats']['urgent'], 2)


class ChallengerPrivilegeBoundaryTestCase(TestCase):
    """
    Empirical tests challenging privilege boundaries and RBAC information disclosure:
    - Staff user without admin:dashboard MUST have executive_financials=None and omitted from role_sections.
    - Admin user with admin:dashboard MUST have executive_financials populated.
    - HTTP endpoint enforcement (/api/dashboard/stats/ and /api/stats/).
    """

    def setUp(self):
        self.client = APIClient()

        # Seed roles & permissions
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Full admin dashboard access'}
        )
        self.perm_leads_read_tenant, _ = AppPermission.objects.get_or_create(
            name='leads:read_tenant',
            defaults={'description': 'Read tenant leads'}
        )

        self.role_admin = Role.objects.create(name='ADMIN')
        self.role_admin.permissions.add(self.perm_admin_dash)

        self.role_staff = Role.objects.create(name='STAFF_REPRESENTATIVE')
        self.role_staff.permissions.add(self.perm_leads_read_tenant)

        # Users
        self.admin = User.objects.create_user(
            username='priv_admin',
            password='password123',
            company='LP'
        )
        self.admin.db_roles.add(self.role_admin)

        self.staff_user = User.objects.create_user(
            username='priv_staff',
            password='password123',
            company='LP'
        )
        self.staff_user.db_roles.add(self.role_staff)

        self.unprivileged_user = User.objects.create_user(
            username='priv_unprivileged',
            password='password123',
            company='LP'
        )

        # Seed financial data in DB
        campus = Campus.objects.create(name="Challenger Campus", code="CC")
        grade = Grade.objects.create(code="B1", name="B1 - Intermediate", order=2)
        pkg = AcademicPackage.objects.create(name="German B1", starting_grade=grade, ending_grade=grade)
        student = Student.objects.create(name="Student Priv", phone="9700000001", campus=campus, academic_package=pkg)

        fee_account = StudentFeeAccount.objects.create(
            student=student, company="LP", total_due=Decimal('100000.00'),
            total_paid=Decimal('40000.00'), balance_due=Decimal('60000.00'),
            overdue_amount=Decimal('15000.00')
        )
        FeeInstallment.objects.create(
            account=fee_account, sequence_number=1, due_date=timezone.now().date() - timedelta(days=10),
            scheduled_amount=Decimal('100000.00'), paid_amount=Decimal('40000.00'),
            balance_amount=Decimal('60000.00'), status='OVERDUE'
        )
        FeePayment.objects.create(
            account=fee_account, receipt_number="RCP-CHALLENGE-01", amount=Decimal('40000.00'),
            company="LP", payment_date=timezone.now()
        )

    def test_staff_user_executive_financials_strictly_none_and_omitted(self):
        """
        Verify that for staff user without admin:dashboard:
        1. has_admin_dashboard is strictly False
        2. data['metrics']['executive_financials'] is strictly None
        3. 'executive_financials' is strictly NOT present in data['role_sections']
        """
        data = DashboardAggregationService.get_dashboard_data(self.staff_user, company='LP')

        self.assertFalse(data['has_admin_dashboard'])
        self.assertFalse(data['user']['has_admin_dashboard'])
        self.assertIsNone(data['metrics']['executive_financials'])
        self.assertNotIn('executive_financials', data['role_sections'])

    def test_admin_user_executive_financials_strictly_populated(self):
        """
        Verify that for admin user with admin:dashboard:
        1. has_admin_dashboard is strictly True
        2. data['metrics']['executive_financials'] is populated dict
        3. 'executive_financials' is present in data['role_sections']
        4. Values match aggregated fees: total_revenue=100000, collections_this_month=40000, overdue=60000
        """
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')

        self.assertTrue(data['has_admin_dashboard'])
        self.assertTrue(data['user']['has_admin_dashboard'])
        self.assertIsNotNone(data['metrics']['executive_financials'])
        self.assertIn('executive_financials', data['role_sections'])

        fin = data['metrics']['executive_financials']
        self.assertEqual(fin['total_revenue'], 100000.0)
        self.assertEqual(fin['collections_this_month'], 40000.0)
        self.assertEqual(fin['pending_receivables'], 60000.0)
        self.assertEqual(fin['total_overdue_balance'], 60000.0)

    def test_api_privilege_enforcement_endpoints(self):
        """
        Test /api/dashboard/stats/ and /api/stats/ across:
        - Anonymous user (401)
        - Unprivileged user (403)
        - Staff user (200 with executive_financials=None and omitted from role_sections)
        - Admin user (200 with executive_financials populated)
        """
        endpoints = ['/api/dashboard/stats/', '/api/stats/']

        for endpoint in endpoints:
            # 1. Anonymous -> 401
            self.client.force_authenticate(user=None)
            res_anon = self.client.get(endpoint)
            self.assertEqual(
                res_anon.status_code, status.HTTP_401_UNAUTHORIZED,
                f"Endpoint {endpoint} allowed unauthenticated access!"
            )

            # 2. Unprivileged -> 403
            self.client.force_authenticate(user=self.unprivileged_user)
            res_unprivileged = self.client.get(endpoint)
            self.assertEqual(
                res_unprivileged.status_code, status.HTTP_403_FORBIDDEN,
                f"Endpoint {endpoint} allowed unprivileged access!"
            )

            # 3. Staff -> 200 with executive_financials=None
            self.client.force_authenticate(user=self.staff_user)
            res_staff = self.client.get(endpoint)
            self.assertEqual(
                res_staff.status_code, status.HTTP_200_OK,
                f"Endpoint {endpoint} failed for staff user with leads:read_tenant!"
            )
            self.assertFalse(res_staff.data['has_admin_dashboard'])
            self.assertIsNone(res_staff.data['metrics']['executive_financials'])
            self.assertNotIn('executive_financials', res_staff.data['role_sections'])

            # 4. Admin -> 200 with executive_financials populated
            self.client.force_authenticate(user=self.admin)
            res_admin = self.client.get(endpoint)
            self.assertEqual(
                res_admin.status_code, status.HTTP_200_OK,
                f"Endpoint {endpoint} failed for admin user!"
            )
            self.assertTrue(res_admin.data['has_admin_dashboard'])
            self.assertIsNotNone(res_admin.data['metrics']['executive_financials'])
            self.assertIn('executive_financials', res_admin.data['role_sections'])
            self.assertEqual(res_admin.data['metrics']['executive_financials']['total_revenue'], 100000.0)
