"""
Empirical Adversarial & Stress Testing Suite for Milestone 4 (M4)
Author: challenger_m4_1 (Empirical Challenger)
Milestone: Milestone 4 — Unified E2E Test Suite Execution & Forensic Certification

Target Dimensions:
1. Dynamic RBAC & Permission Enforcement Under Adversarial Stress:
   - Non-existent and malformed permission requests (`has_dynamic_permission(user, 'non:existent')`, null bytes, SQLi strings, large strings, non-string types)
   - Unauthorized user attempts to access `/api/dashboard/stats/` and `/api/stats/` (Anonymous, unprivileged, inactive, orthogonal permissions)
   - Privilege elevation attacks (Query parameter injection, header spoofing, HTTP method tampering)
2. DashboardAggregationService Boundary & Stress Testing:
   - Completely empty database state (0 leads, 0 tasks, 0 followups, 0 fee records)
   - Extreme database states (huge values near max digits, negative balances / overpayments, refunds)
   - Date boundary extremes (ancient past dates, far future dates)
   - Zero-division boundaries and conversion rate mathematical precision
   - Multi-tenant cross-company financial isolation under stress
   - Lead scoping boundary integrity under tenant filter parameters
"""

import json
from decimal import Decimal
from datetime import timedelta, date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from django.test.client import RequestFactory

from accounts.models import AppPermission, Role, ActivityLog
from accounts.permissions import (
    has_dynamic_permission,
    HasPermission,
    HasAnyPermission,
)
from accounts.dashboard_service import DashboardAggregationService
from leads.models import Lead, FollowUp, LeadConversionDetail
from tasks.models import Task
from fees.models import StudentFeeAccount, FeePayment, FeeInstallment
from students.models import Student, Campus, Grade, AcademicPackage

User = get_user_model()


class ChallengerDynamicPermissionsStressTests(TestCase):
    """
    Empirical adversarial stress testing for backend dynamic permissions.
    """

    def setUp(self):
        # 1. Get or create permissions (migration 0002 pre-seeds admin:dashboard)
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Executive dashboard access'}
        )
        self.perm_leads_read, _ = AppPermission.objects.get_or_create(
            name='leads:read_tenant',
            defaults={'description': 'Read tenant leads'}
        )
        self.perm_staff_read, _ = AppPermission.objects.get_or_create(
            name='staff:read_tenant',
            defaults={'description': 'Read staff list'}
        )
        self.perm_orthogonal, _ = AppPermission.objects.get_or_create(
            name='inventory:view',
            defaults={'description': 'View inventory'}
        )

        # 2. Get or create roles
        self.role_admin, _ = Role.objects.get_or_create(
            name='ADMIN',
            defaults={'description': 'Administrator'}
        )
        self.role_admin.permissions.add(self.perm_admin_dash, self.perm_leads_read, self.perm_staff_read)

        self.role_counselor, _ = Role.objects.get_or_create(
            name='COUNSELOR',
            defaults={'description': 'Academic Counselor'}
        )
        self.role_counselor.permissions.add(self.perm_leads_read)

        self.role_unrelated, _ = Role.objects.get_or_create(
            name='WAREHOUSE',
            defaults={'description': 'Warehouse Staff'}
        )
        self.role_unrelated.permissions.add(self.perm_orthogonal)

        # 3. Create users
        self.admin_user = User.objects.create_user(
            username='challenger_admin',
            email='admin@challenger.test',
            password='Password123!',
            company='LP'
        )
        self.admin_user.db_roles.add(self.role_admin)

        self.counselor_user = User.objects.create_user(
            username='challenger_counselor',
            email='counselor@challenger.test',
            password='Password123!',
            company='LP'
        )
        self.counselor_user.db_roles.add(self.role_counselor)

        self.unrelated_user = User.objects.create_user(
            username='challenger_unrelated',
            email='unrelated@challenger.test',
            password='Password123!',
            company='LP'
        )
        self.unrelated_user.db_roles.add(self.role_unrelated)

        self.unprivileged_user = User.objects.create_user(
            username='challenger_nobody',
            email='nobody@challenger.test',
            password='Password123!',
            company='LP'
        )
        # Note: self.unprivileged_user has 0 roles and 0 permissions

        self.inactive_user = User.objects.create_user(
            username='challenger_inactive',
            email='inactive@challenger.test',
            password='Password123!',
            company='LP',
            is_active=False
        )
        self.inactive_user.db_roles.add(self.role_admin)

        self.superuser = User.objects.create_superuser(
            username='challenger_root',
            email='root@challenger.test',
            password='Password123!',
            company='LP'
        )

        self.client = APIClient()

    def test_nonexistent_permission_requests(self):
        """
        Adversarially challenge has_dynamic_permission with non-existent, malformed,
        and attack-payload permission strings.
        """
        adversarial_inputs = [
            'non:existent',
            'admin:dashboards',
            'admin:dashboard:extra',
            'fake:permission:string',
            '',
            ' ',
            '   \t\n  ',
            'null',
            'undefined',
            'None',
            'admin:dashboard\' OR \'1\'=\'1',
            'admin:dashboard; DROP TABLE permissions; --',
            'admin:\x00dashboard',
            '<script>alert(1)</script>',
            'A' * 10000,
        ]

        # 1. Non-admin regular user must evaluate to False for all adversarial inputs
        for inp in adversarial_inputs:
            res = has_dynamic_permission(self.counselor_user, inp)
            self.assertFalse(res, f"Expected False for counselor on '{inp[:30]}', got {res}")

        # 2. Unprivileged user must evaluate to False for all adversarial inputs
        for inp in adversarial_inputs:
            res = has_dynamic_permission(self.unprivileged_user, inp)
            self.assertFalse(res, f"Expected False for unprivileged on '{inp[:30]}', got {res}")

        # 3. Anonymous user must evaluate to False for all adversarial inputs
        anon = AnonymousUser()
        for inp in adversarial_inputs:
            res = has_dynamic_permission(anon, inp)
            self.assertFalse(res, f"Expected False for AnonymousUser on '{inp[:30]}', got {res}")

        # 4. Admin user (is_superuser=False) must evaluate to False for non-existent perms
        for inp in adversarial_inputs:
            res = has_dynamic_permission(self.admin_user, inp)
            self.assertFalse(res, f"Expected False for admin on non-existent '{inp[:30]}', got {res}")

        # 5. Non-string inputs: has_dynamic_permission handles hashable types safely
        non_string_inputs = [None, 12345, 99.9]
        for inp in non_string_inputs:
            res = has_dynamic_permission(self.counselor_user, inp)
            self.assertFalse(res, f"Expected False for non-string '{inp}', got {res}")

        # Unhashable inputs (list/dict): verify TypeError is raised on unhashable permission types
        with self.assertRaises(TypeError):
            has_dynamic_permission(self.counselor_user, ['admin:dashboard'])
        with self.assertRaises(TypeError):
            has_dynamic_permission(self.counselor_user, {'name': 'admin:dashboard'})

        # 6. Superuser bypass verification: superuser returns True
        self.assertTrue(has_dynamic_permission(self.superuser, 'non:existent'))
        self.assertTrue(has_dynamic_permission(self.superuser, 'admin:dashboard'))

        # 7. DRF HasPermission / HasAnyPermission with non-existent strings
        factory = RequestFactory()
        req = factory.get('/')
        req.user = self.counselor_user

        perm_cls = HasPermission('non:existent')()
        self.assertFalse(perm_cls.has_permission(req, None))

        any_perm_cls = HasAnyPermission('non:existent', 'fake:perm:two')()
        self.assertFalse(any_perm_cls.has_permission(req, None))

    def test_unauthorized_users_attempting_to_access_dashboard_stats(self):
        """
        Verify that unauthorized users cannot access `/api/dashboard/stats/`
        or legacy `/api/stats/`.
        """
        endpoints = ['/api/dashboard/stats/', '/api/stats/']

        for endpoint in endpoints:
            # 1. Unauthenticated request -> HTTP 401
            self.client.force_authenticate(user=None)
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED, f"Expected 401 for anonymous on {endpoint}")

            # 2. Bogus Bearer token -> HTTP 401
            res_bad_token = self.client.get(endpoint, HTTP_AUTHORIZATION='Bearer invalid_forged_token_xyz')
            self.assertEqual(res_bad_token.status_code, status.HTTP_401_UNAUTHORIZED)

            # 3. User with NO permissions and NO roles -> HTTP 403 Forbidden
            self.client.force_authenticate(user=self.unprivileged_user)
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, f"Expected 403 for unprivileged on {endpoint}")

            # 4. User with only orthogonal permissions (e.g. inventory:view) -> HTTP 403 Forbidden
            self.client.force_authenticate(user=self.unrelated_user)
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, f"Expected 403 for orthogonal perms on {endpoint}")

    def test_privilege_elevation_attacks_query_params(self):
        """
        Test privilege elevation attacks where regular users pass arbitrary role/permission flags
        in URL query parameters.
        """
        self.client.force_authenticate(user=self.counselor_user)

        elevation_params = [
            {'role': 'ADMIN'},
            {'role': 'CEO'},
            {'is_admin': 'true'},
            {'is_superuser': 'true'},
            {'has_admin_dashboard': 'true'},
            {'permission': 'admin:dashboard'},
            {'permissions': 'admin:dashboard'},
            {'user_role': 'ADMIN'},
            {'role_name': 'ADMIN'},
            {
                'role': 'ADMIN',
                'is_admin': 'true',
                'is_superuser': 'true',
                'has_admin_dashboard': 'true',
                'company': 'LP'
            }
        ]

        endpoints = ['/api/dashboard/stats/', '/api/stats/']

        for endpoint in endpoints:
            for params in elevation_params:
                res = self.client.get(endpoint, params)
                self.assertEqual(res.status_code, status.HTTP_200_OK, f"Failed on {endpoint} with {params}")

                # Verify NO privilege escalation occurred
                self.assertFalse(res.data.get('has_admin_dashboard'), f"Escalated has_admin_dashboard on {params}")
                self.assertFalse(res.data.get('user', {}).get('has_admin_dashboard', False))
                self.assertEqual(res.data.get('user_role'), 'COUNSELOR', f"Escalated user_role on {params}")
                self.assertIsNone(
                    res.data.get('metrics', {}).get('executive_financials'),
                    f"Executive financials leaked on {params}"
                )
                self.assertNotIn('executive_financials', res.data.get('role_sections', {}))

        # Test privilege elevation on an unprivileged user (0 roles/perms):
        # Passing arbitrary role flags must NOT bypass the 403 Forbidden check.
        self.client.force_authenticate(user=self.unprivileged_user)
        for params in elevation_params:
            res = self.client.get('/api/dashboard/stats/', params)
            self.assertEqual(
                res.status_code,
                status.HTTP_403_FORBIDDEN,
                f"Unprivileged user bypassed 403 with params {params}"
            )

    def test_privilege_elevation_attacks_headers(self):
        """
        Test spoofed HTTP headers attempting to claim ADMIN or CEO roles.
        """
        self.client.force_authenticate(user=self.counselor_user)

        spoofed_headers = [
            {'HTTP_X_ROLE': 'ADMIN'},
            {'HTTP_X_ROLE': 'CEO'},
            {'HTTP_X_IS_ADMIN': 'true'},
            {'HTTP_X_IS_SUPERUSER': 'true'},
            {'HTTP_ROLE': 'ADMIN'},
            {'HTTP_X_ADMIN_DASHBOARD': 'true'},
        ]

        for hdr in spoofed_headers:
            res = self.client.get('/api/dashboard/stats/', **hdr)
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertFalse(res.data.get('has_admin_dashboard'))
            self.assertIsNone(res.data.get('metrics', {}).get('executive_financials'))
            self.assertEqual(res.data.get('user_role'), 'COUNSELOR')

    def test_http_method_tampering_on_dashboard_stats(self):
        """
        Verify that state-modifying HTTP methods (POST, PUT, PATCH, DELETE)
        are strictly prohibited on the aggregation endpoints.
        """
        self.client.force_authenticate(user=self.admin_user)
        endpoints = ['/api/dashboard/stats/', '/api/stats/']

        payload = {'role': 'ADMIN', 'is_superuser': True}

        for endpoint in endpoints:
            res_post = self.client.post(endpoint, payload, format='json')
            self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

            res_put = self.client.put(endpoint, payload, format='json')
            self.assertEqual(res_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

            res_patch = self.client.patch(endpoint, payload, format='json')
            self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

            res_delete = self.client.delete(endpoint)
            self.assertEqual(res_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ChallengerDashboardAggregationStressTests(TestCase):
    """
    Empirical stress testing for DashboardAggregationService.
    Covers empty database states, extreme numerical values, negative balances,
    date boundary extremes, zero-division boundaries, and multi-tenant isolation.
    """

    def setUp(self):
        # Setup roles and permissions
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(name='admin:dashboard', defaults={'description': 'Admin dash'})
        self.perm_leads_read, _ = AppPermission.objects.get_or_create(name='leads:read_tenant', defaults={'description': 'Read leads'})
        self.perm_leads_all, _ = AppPermission.objects.get_or_create(name='leads:read_all', defaults={'description': 'Read all leads'})
        self.perm_fees_accounts, _ = AppPermission.objects.get_or_create(name='fees:accounts', defaults={'description': 'Manage fees'})

        self.role_admin, _ = Role.objects.get_or_create(name='ADMIN', defaults={'description': 'Admin'})
        self.role_admin.permissions.add(self.perm_admin_dash, self.perm_leads_all, self.perm_fees_accounts)

        self.role_staff, _ = Role.objects.get_or_create(name='STAFF', defaults={'description': 'Staff'})
        self.role_staff.permissions.add(self.perm_leads_read)

        self.admin = User.objects.create_user(
            username='stress_admin', email='admin@stress.test', password='Password123!', company='LP'
        )
        self.admin.db_roles.add(self.role_admin)

        self.staff = User.objects.create_user(
            username='stress_staff', email='staff@stress.test', password='Password123!', company='LP'
        )
        self.staff.db_roles.add(self.role_staff)

        # Setup student campus, grade, and package for fees
        self.campus, _ = Campus.objects.get_or_create(name="Stress Campus", defaults={"code": "STRESS"})
        self.grade, _ = Grade.objects.get_or_create(code="A1", defaults={"name": "Level A1", "order": 1})
        self.pkg, _ = AcademicPackage.objects.get_or_create(
            name="German Level A1",
            defaults={"starting_grade": self.grade, "ending_grade": self.grade}
        )

    def test_completely_empty_database_state(self):
        """
        Verify that DashboardAggregationService handles a 100% empty database
        (0 leads, 0 tasks, 0 followups, 0 fees, 0 activity logs) with zero crashes,
        zero DivisionByZero errors, and completely sound metric zeroes.
        """
        # Ensure database is clean
        Lead.objects.all().delete()
        Task.objects.all().delete()
        FollowUp.objects.all().delete()
        StudentFeeAccount.objects.all().delete()
        FeePayment.objects.all().delete()
        LeadConversionDetail.objects.all().delete()
        ActivityLog.objects.all().delete()

        # 1. Admin user call on completely empty DB
        data_admin = DashboardAggregationService.get_dashboard_data(self.admin, company='ALL')

        self.assertIsNotNone(data_admin)
        self.assertTrue(data_admin['has_admin_dashboard'])
        self.assertTrue(data_admin['user']['has_admin_dashboard'])

        # Leads metrics
        leads_m = data_admin['metrics']['leads']
        self.assertEqual(leads_m['total'], 0)
        self.assertEqual(leads_m['hot'], 0)
        self.assertEqual(leads_m['warm'], 0)
        self.assertEqual(leads_m['cold'], 0)
        self.assertEqual(leads_m['converted'], 0)
        self.assertEqual(leads_m['closed'], 0)
        self.assertEqual(leads_m['conversion_rate'], 0.0)

        # Followup metrics
        followups_m = data_admin['metrics']['followups']
        self.assertEqual(followups_m['today_total'], 0)
        self.assertEqual(followups_m['today_pending'], 0)
        self.assertEqual(followups_m['overdue'], 0)
        self.assertEqual(followups_m['high_priority'], 0)

        # Task metrics
        tasks_m = data_admin['metrics']['tasks']
        self.assertEqual(tasks_m['my_pending'], 0)
        self.assertEqual(tasks_m['urgent'], 0)
        self.assertEqual(tasks_m['overdue'], 0)
        self.assertEqual(tasks_m['team_pending'], 0)

        # Executive financials (Admin)
        exec_fin = data_admin['metrics']['executive_financials']
        self.assertIsNotNone(exec_fin)
        self.assertEqual(exec_fin['total_revenue'], 0.0)
        self.assertEqual(exec_fin['collections_this_month'], 0.0)
        self.assertEqual(exec_fin['pending_receivables'], 0.0)
        self.assertEqual(exec_fin['total_outstanding_receivable'], 0.0)
        self.assertEqual(exec_fin['total_overdue_balance'], 0.0)
        self.assertEqual(exec_fin['conversion_total_fees'], 0.0)
        self.assertEqual(exec_fin['conversion_amount_paid'], 0.0)

        self.assertIn('executive_financials', data_admin['role_sections'])
        self.assertEqual(data_admin['recent_activities'], [])

        # 2. Staff user call on completely empty DB
        data_staff = DashboardAggregationService.get_dashboard_data(self.staff, company='ALL')
        self.assertIsNotNone(data_staff)
        self.assertFalse(data_staff['has_admin_dashboard'])
        self.assertFalse(data_staff['user']['has_admin_dashboard'])
        self.assertIsNone(data_staff['metrics']['executive_financials'])
        self.assertNotIn('executive_financials', data_staff['role_sections'])
        self.assertEqual(data_staff['metrics']['leads']['conversion_rate'], 0.0)

    def test_extreme_numerical_values_and_financial_precision(self):
        """
        Stress test aggregation service with huge numbers near maximum Decimal limits
        (e.g., billions in fees and payments).
        """
        student = Student.objects.create(
            name="Whale Student", phone="9999999999", campus=self.campus, academic_package=self.pkg
        )

        huge_balance = Decimal('9999999999.99')   # 10 billion - 0.01
        huge_total_due = Decimal('9999999999.99')
        huge_overdue = Decimal('8888888888.88')

        fee_account = StudentFeeAccount.objects.create(
            student=student,
            company="LP",
            total_due=huge_total_due,
            total_paid=Decimal('0.00'),
            balance_due=huge_balance,
            overdue_amount=huge_overdue
        )

        huge_payment = Decimal('9999999999.99')
        FeePayment.objects.create(
            account=fee_account,
            receipt_number="RCP-HUGE-001",
            amount=huge_payment,
            company="LP",
            payment_date=timezone.now()
        )

        # Huge lead conversion fees (max_digits=10)
        lead = Lead.objects.create(
            name="Mega Corp Lead",
            phone="9888888888",
            company="LP",
            status="CONVERTED",
            assigned_to=self.admin
        )
        huge_conv_fee = Decimal('99999999.99')
        LeadConversionDetail.objects.create(
            lead=lead,
            total_fees=huge_conv_fee,
            amount_paid=Decimal('50000000.00'),
            payment_status="PARTIAL"
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        fin = data['metrics']['executive_financials']

        self.assertIsNotNone(fin)
        expected_revenue = float(huge_conv_fee + huge_total_due)
        self.assertAlmostEqual(fin['total_revenue'], expected_revenue, places=2)
        self.assertAlmostEqual(fin['collections_this_month'], float(huge_payment), places=2)
        self.assertAlmostEqual(fin['conversion_total_fees'], float(huge_conv_fee), places=2)

    def test_negative_balances_and_refund_adjustments(self):
        """
        Stress test accounting edge cases: negative balance due (student overpayment / credit)
        and negative fee payment amount (refund or reversal).
        """
        student = Student.objects.create(
            name="Credit Student", phone="9444444444", campus=self.campus, academic_package=self.pkg
        )

        fee_account = StudentFeeAccount.objects.create(
            student=student,
            company="LP",
            total_due=Decimal('10000.00'),
            total_paid=Decimal('25000.00'),
            balance_due=Decimal('0.00'),
            overdue_amount=Decimal('0.00')
        )

        # Negative payment (refund of 5,000)
        FeePayment.objects.create(
            account=fee_account,
            receipt_number="RCP-REFUND-001",
            amount=Decimal('-5000.00'),
            company="LP",
            payment_date=timezone.now()
        )

        # Force negative balance due after payment creation (student has credit/overpayment of 15,000)
        # We update after payment creation so that FeePayment.save()'s recalculate() does not overwrite it
        StudentFeeAccount.objects.filter(pk=fee_account.pk).update(balance_due=Decimal('-15000.50'))

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        fin = data['metrics']['executive_financials']

        self.assertIsNotNone(fin)
        self.assertEqual(fin['pending_receivables'], -15000.5)
        self.assertEqual(fin['collections_this_month'], -5000.0)

    def test_extreme_past_and_future_dates(self):
        """
        Test date boundary conditions: ancient records (10+ years past)
        and future records (10+ years ahead).
        """
        today = timezone.localtime(timezone.now()).date()

        # 1. Followups
        lead_active = Lead.objects.create(
            name="Followup Lead", phone="9111111111", company="LP", status="HOT", assigned_to=self.admin
        )

        # Ancient followup (15 years ago) -> must be overdue
        FollowUp.objects.create(
            lead=lead_active,
            assigned_to=self.admin,
            follow_up_date=today - timedelta(days=5500),
            status='pending',
            priority='high'
        )

        # Today followup -> must be due_today
        FollowUp.objects.create(
            lead=lead_active,
            assigned_to=self.admin,
            follow_up_date=today,
            status='pending',
            priority='high'
        )

        # Far future followup (15 years in future) -> total_pending, NOT overdue, NOT due_today
        FollowUp.objects.create(
            lead=lead_active,
            assigned_to=self.admin,
            follow_up_date=today + timedelta(days=5500),
            status='pending',
            priority='normal'
        )

        # 2. Tasks
        # Ancient task (20 years ago) -> overdue
        Task.objects.create(
            title="Ancient Task",
            company="LP",
            assigned_to=self.admin,
            assigned_by=self.admin,
            deadline=today - timedelta(days=7300),
            status="PENDING",
            priority="HIGH"
        )

        # Far future task (20 years ahead) -> not overdue
        Task.objects.create(
            title="Futuristic Task",
            company="LP",
            assigned_to=self.admin,
            assigned_by=self.admin,
            deadline=today + timedelta(days=7300),
            status="PENDING",
            priority="LOW"
        )

        # 3. FeePayments: Payment in past year should NOT count towards this month's collections
        student = Student.objects.create(
            name="Historical Student", phone="9222222222", campus=self.campus, academic_package=self.pkg
        )
        fee_account = StudentFeeAccount.objects.create(
            student=student, company="LP", total_due=Decimal('50000.00'), balance_due=Decimal('20000.00')
        )

        # Payment made 2 years ago
        FeePayment.objects.create(
            account=fee_account,
            receipt_number="RCP-HIST-01",
            amount=Decimal('30000.00'),
            company="LP",
            payment_date=timezone.now() - timedelta(days=730)
        )

        # Payment made this month
        FeePayment.objects.create(
            account=fee_account,
            receipt_number="RCP-TODAY-01",
            amount=Decimal('5000.00'),
            company="LP",
            payment_date=timezone.now()
        )

        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')

        # Verify followups
        self.assertEqual(data['metrics']['followups']['today_total'], 1)
        self.assertEqual(data['metrics']['followups']['today_pending'], 1)
        self.assertEqual(data['metrics']['followups']['overdue'], 1)
        self.assertEqual(data['followup_stats']['due_today'], 1)
        self.assertEqual(data['followup_stats']['overdue'], 1)

        # Verify tasks
        self.assertEqual(data['metrics']['tasks']['overdue'], 1)
        self.assertEqual(data['metrics']['tasks']['urgent'], 1)
        self.assertEqual(data['metrics']['tasks']['team_pending'], 2)

        # Verify collections_this_month strictly includes only this month's 5,000, excluding ancient 30,000
        self.assertEqual(data['metrics']['executive_financials']['collections_this_month'], 5000.0)

    def test_zero_division_exhaustive_matrix(self):
        """
        Verify conversion rate zero-division protection and rounding precision across various fractions.
        Formula: round((total_won / total_leads * 100), 1)
        """
        # Scenario 1: 0 leads -> 0.0%
        Lead.objects.all().delete()
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 0.0)

        # Scenario 2: 1 lead, 0 won (HOT) -> 0.0%
        Lead.objects.create(name="L1", phone="9000000001", company="LP", status="HOT", assigned_to=self.admin)
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 0.0)

        # Scenario 3: 1 lead, 1 won (CONVERTED) -> 100.0%
        Lead.objects.all().delete()
        Lead.objects.create(name="L1", phone="9000000001", company="LP", status="CONVERTED", assigned_to=self.admin)
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 100.0)

        # Scenario 4: 1 lead, 1 won (REGISTERED) -> 100.0%
        Lead.objects.all().delete()
        Lead.objects.create(name="L1", phone="9000000001", company="LP", status="REGISTERED", assigned_to=self.admin)
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 100.0)

        # Scenario 5: 3 leads, 1 won (1 CONVERTED, 2 COLD) -> 33.3%
        Lead.objects.all().delete()
        Lead.objects.create(name="L1", phone="9000000001", company="LP", status="CONVERTED", assigned_to=self.admin)
        Lead.objects.create(name="L2", phone="9000000002", company="LP", status="COLD", assigned_to=self.admin)
        Lead.objects.create(name="L3", phone="9000000003", company="LP", status="COLD", assigned_to=self.admin)
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 33.3)

        # Scenario 6: 3 leads, 2 won (1 CONVERTED, 1 REGISTERED, 1 WARM) -> 66.7%
        Lead.objects.all().delete()
        Lead.objects.create(name="L1", phone="9000000001", company="LP", status="CONVERTED", assigned_to=self.admin)
        Lead.objects.create(name="L2", phone="9000000002", company="LP", status="REGISTERED", assigned_to=self.admin)
        Lead.objects.create(name="L3", phone="9000000003", company="LP", status="WARM", assigned_to=self.admin)
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 66.7)

        # Scenario 7: 7 leads, 2 won -> 28.6%
        Lead.objects.all().delete()
        Lead.objects.create(name="L1", phone="9000000001", company="LP", status="CONVERTED", assigned_to=self.admin)
        Lead.objects.create(name="L2", phone="9000000002", company="LP", status="REGISTERED", assigned_to=self.admin)
        for i in range(3, 8):
            Lead.objects.create(name=f"L{i}", phone=f"900000000{i}", company="LP", status="CLOSED", assigned_to=self.admin)
        data = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data['metrics']['leads']['conversion_rate'], 28.6)

    def test_cross_company_financial_and_lead_isolation_under_stress(self):
        """
        Verify strict multi-tenant boundary isolation between 'LP', 'FLAG', and non-existent companies.
        """
        Lead.objects.all().delete()
        StudentFeeAccount.objects.all().delete()
        FeePayment.objects.all().delete()

        student_lp = Student.objects.create(name="LP Student", phone="9111111111", campus=self.campus, academic_package=self.pkg)
        student_flag = Student.objects.create(name="FLAG Student", phone="9222222222", campus=self.campus, academic_package=self.pkg)

        # LP data
        Lead.objects.create(name="Lead LP", phone="9111111111", company="LP", status="HOT", assigned_to=self.admin)
        fee_lp = StudentFeeAccount.objects.create(student=student_lp, company="LP", total_due=Decimal('50000.00'), balance_due=Decimal('30000.00'))
        FeePayment.objects.create(account=fee_lp, receipt_number="RCP-LP-01", amount=Decimal('20000.00'), company="LP", payment_date=timezone.now())

        # FLAG data
        Lead.objects.create(name="Lead FLAG 1", phone="9222222221", company="FLAG", status="CONVERTED", assigned_to=self.admin)
        Lead.objects.create(name="Lead FLAG 2", phone="9222222222", company="FLAG", status="WARM", assigned_to=self.admin)
        fee_flag = StudentFeeAccount.objects.create(student=student_flag, company="FLAG", total_due=Decimal('80000.00'), balance_due=Decimal('10000.00'))
        FeePayment.objects.create(account=fee_flag, receipt_number="RCP-FLAG-01", amount=Decimal('70000.00'), company="FLAG", payment_date=timezone.now())

        # 1. Query company='LP'
        res_lp = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(res_lp['metrics']['leads']['total'], 1)
        self.assertEqual(res_lp['metrics']['executive_financials']['collections_this_month'], 20000.0)
        self.assertEqual(res_lp['metrics']['executive_financials']['pending_receivables'], 30000.0)

        # 2. Query company='FLAG'
        res_flag = DashboardAggregationService.get_dashboard_data(self.admin, company='FLAG')
        self.assertEqual(res_flag['metrics']['leads']['total'], 2)
        self.assertEqual(res_flag['metrics']['executive_financials']['collections_this_month'], 70000.0)
        self.assertEqual(res_flag['metrics']['executive_financials']['pending_receivables'], 10000.0)

        # 3. Query non-existent company
        res_ghost = DashboardAggregationService.get_dashboard_data(self.admin, company='GHOST_CORP_999')
        self.assertEqual(res_ghost['metrics']['leads']['total'], 0)
        self.assertEqual(res_ghost['metrics']['leads']['conversion_rate'], 0.0)
        self.assertEqual(res_ghost['metrics']['executive_financials']['collections_this_month'], 0.0)
        self.assertEqual(res_ghost['metrics']['executive_financials']['pending_receivables'], 0.0)

    def test_lead_scoping_boundary_integrity(self):
        """
        Verify that a regular staff user cannot see leads assigned to other users,
        even when explicitly filtering by company parameter.
        """
        Lead.objects.all().delete()

        # Lead assigned to staff
        Lead.objects.create(
            name="My Lead", phone="9111111111", company="LP", status="WARM", assigned_to=self.staff
        )

        # Leads assigned to admin (unrelated to staff)
        Lead.objects.create(
            name="Admin Lead 1", phone="9222222221", company="LP", status="HOT", assigned_to=self.admin
        )
        Lead.objects.create(
            name="Admin Lead 2", phone="9222222222", company="LP", status="CONVERTED", assigned_to=self.admin
        )

        # Staff query with company='LP'
        data_staff = DashboardAggregationService.get_dashboard_data(self.staff, company='LP')

        # Staff must ONLY see their 1 lead
        self.assertEqual(data_staff['metrics']['leads']['total'], 1)
        self.assertEqual(data_staff['metrics']['leads']['warm'], 1)
        self.assertEqual(data_staff['metrics']['leads']['hot'], 0)
        self.assertEqual(data_staff['metrics']['leads']['converted'], 0)

        # Admin query with company='LP' sees all 3 leads
        data_admin = DashboardAggregationService.get_dashboard_data(self.admin, company='LP')
        self.assertEqual(data_admin['metrics']['leads']['total'], 3)
