"""
Automated Test Suite for LP CRM Dashboard Permissions and RBAC Gating
Requirements Covered: R2 (Database Permission Correlation), R3 (Admin Dashboard Permission), R6 (Automated Test Coverage)
Methodology: 4-Tier Opaque-Box Testing Architecture (Feature, Boundary, Integration, Real-World)
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.request import Request
from django.test.client import RequestFactory

from accounts.models import AppPermission, Role
from accounts.permissions import (
    has_dynamic_permission,
    HasPermission,
    HasAnyPermission,
    IsManagement,
    IsSuperAdmin
)
from accounts.services import PermissionService
from leads.models import Lead

User = get_user_model()


class DashboardPermissionUnitTests(TestCase):
    """
    Tier 1 & Tier 2: Unit-level tests for dynamic permission evaluation,
    caching mechanics, PermissionService serialization, and factory checks.
    """

    def setUp(self):
        # 1. Seed standard permissions
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Full access to executive admin dashboard'}
        )
        self.perm_leads_read, _ = AppPermission.objects.get_or_create(
            name='leads:read_tenant',
            defaults={'description': 'Read tenant leads'}
        )
        self.perm_staff_read, _ = AppPermission.objects.get_or_create(
            name='staff:read_tenant',
            defaults={'description': 'Read tenant staff list'}
        )
        self.perm_tasks_edit, _ = AppPermission.objects.get_or_create(
            name='tasks:edit_any',
            defaults={'description': 'Edit any task'}
        )

        # 2. Seed standard roles
        self.role_admin = Role.objects.create(name='ADMIN', description='Administrator')
        self.role_admin.permissions.add(self.perm_admin_dash, self.perm_leads_read, self.perm_staff_read, self.perm_tasks_edit)

        self.role_ceo = Role.objects.create(name='CEO', description='Chief Executive Officer')
        self.role_ceo.permissions.add(self.perm_admin_dash, self.perm_leads_read, self.perm_staff_read)

        self.role_sales = Role.objects.create(name='SALES_EXECUTIVE', description='Sales Representative')
        self.role_sales.permissions.add(self.perm_leads_read)

        self.role_empty = Role.objects.create(name='GUEST', description='Guest role without permissions')

        # 3. Create users
        self.admin_user = User.objects.create_user(
            username='test_admin', password='password123', company='LP', email='admin@example.com'
        )
        self.admin_user.db_roles.add(self.role_admin)

        self.ceo_user = User.objects.create_user(
            username='test_ceo', password='password123', company='LP', email='ceo@example.com'
        )
        self.ceo_user.db_roles.add(self.role_ceo)

        self.sales_user = User.objects.create_user(
            username='test_sales', password='password123', company='LP', email='sales@example.com'
        )
        self.sales_user.db_roles.add(self.role_sales)

        self.plain_user = User.objects.create_user(
            username='test_plain', password='password123', company='LP', email='plain@example.com'
        )

        self.superuser = User.objects.create_superuser(
            username='test_super', password='password123', company='LP', email='super@example.com'
        )

        self.request_factory = RequestFactory()

    # ── Tier 1: Feature Coverage (Happy Path) ───────────────────────────────────

    def test_admin_dashboard_permission_granted_via_role(self):
        """Users assigned to ADMIN or CEO role must have admin:dashboard."""
        self.assertTrue(
            has_dynamic_permission(self.admin_user, 'admin:dashboard'),
            "User with ADMIN role must have admin:dashboard"
        )
        self.assertTrue(
            has_dynamic_permission(self.ceo_user, 'admin:dashboard'),
            "User with CEO role must have admin:dashboard"
        )

    def test_admin_dashboard_permission_denied_for_unauthorized_role(self):
        """Sales role without admin:dashboard must be denied."""
        self.assertFalse(
            has_dynamic_permission(self.sales_user, 'admin:dashboard'),
            "Sales executive must not have admin:dashboard permission"
        )
        self.assertFalse(
            has_dynamic_permission(self.plain_user, 'admin:dashboard'),
            "User with no roles must not have admin:dashboard permission"
        )

    def test_admin_dashboard_granted_via_user_specific_json(self):
        """Directly assigning admin:dashboard in user.permissions JSON grants access."""
        custom_user = User.objects.create_user(
            username='custom_user', password='password123', company='LP',
            permissions=['admin:dashboard']
        )
        self.assertTrue(
            has_dynamic_permission(custom_user, 'admin:dashboard'),
            "Direct user JSON permission should grant admin:dashboard"
        )

    def test_superuser_bypass_for_admin_dashboard(self):
        """Superusers automatically have all permissions without explicit DB assignment."""
        self.assertTrue(
            has_dynamic_permission(self.superuser, 'admin:dashboard'),
            "Superuser must automatically evaluate to True"
        )
        self.assertTrue(
            has_dynamic_permission(self.superuser, 'non_existent:permission'),
            "Superuser must evaluate to True even for arbitrary unseeded permissions"
        )

    def test_permission_service_serialization_format(self):
        """PermissionService.get_user_permissions must serialize into resource: [actions] dictionary."""
        perms = PermissionService.get_user_permissions(self.admin_user)
        self.assertIn('admin', perms)
        self.assertIn('dashboard', perms['admin'])
        self.assertIn('leads', perms)
        self.assertIn('read_tenant', perms['leads'])
        self.assertIn('staff', perms)
        self.assertIn('read_tenant', perms['staff'])

    def test_permission_service_superuser_wildcard(self):
        """Superuser permission dictionary must be wildcard {'*': ['*']}."""
        perms = PermissionService.get_user_permissions(self.superuser)
        self.assertEqual(perms, {"*": ["*"]})

    # ── Tier 2: Boundary & Corner Cases ─────────────────────────────────────────

    def test_unauthenticated_user_always_denied(self):
        """Anonymous or unauthenticated users must always return False."""
        anon = AnonymousUser()
        self.assertFalse(has_dynamic_permission(anon, 'admin:dashboard'))
        self.assertFalse(has_dynamic_permission(anon, 'leads:read_tenant'))

    def test_nonexistent_permission_string(self):
        """Querying a permission not registered in DB returns False safely."""
        self.assertFalse(has_dynamic_permission(self.admin_user, 'finance:view_nuclear_codes'))

    def test_empty_or_whitespace_permission_string(self):
        """Querying empty string returns False without raising exception."""
        self.assertFalse(has_dynamic_permission(self.admin_user, ''))
        self.assertFalse(has_dynamic_permission(self.admin_user, '   '))

    def test_malformed_json_permissions_on_user_handled_gracefully(self):
        """User with non-standard permissions attribute (e.g. integer, None, invalid list items) does not crash."""
        user_with_bad_perms = User.objects.create_user(username='bad_perms', password='password123')
        user_with_bad_perms.permissions = None
        self.assertFalse(has_dynamic_permission(user_with_bad_perms, 'admin:dashboard'))

        user_with_bad_perms.permissions = "not_a_list"
        if hasattr(user_with_bad_perms, '_dynamic_perms_cache'):
            delattr(user_with_bad_perms, '_dynamic_perms_cache')
        self.assertFalse(has_dynamic_permission(user_with_bad_perms, 'admin:dashboard'))

        user_with_bad_perms.permissions = ["not_a_perm", 123, "leads:fake"]
        if hasattr(user_with_bad_perms, '_dynamic_perms_cache'):
            delattr(user_with_bad_perms, '_dynamic_perms_cache')
        self.assertFalse(has_dynamic_permission(user_with_bad_perms, 'admin:dashboard'))

    # ── Tier 3: Cross-Feature Integration (Caching & Reassignment) ──────────────

    def test_dynamic_permission_caching_behavior(self):
        """First call caches permissions on user instance, subsequent calls read cache."""
        user = User.objects.create_user(username='cache_tester', password='password123')
        user.db_roles.add(self.role_admin)

        self.assertFalse(hasattr(user, '_dynamic_perms_cache'), "Cache should not exist before first call")
        has_perm = has_dynamic_permission(user, 'admin:dashboard')
        self.assertTrue(has_perm)
        self.assertTrue(hasattr(user, '_dynamic_perms_cache'), "Cache must be populated after first call")
        self.assertIn('admin:dashboard', user._dynamic_perms_cache)

        # Modifying DB without clearing cache should still return cached result on same instance
        user.db_roles.clear()
        self.assertTrue(
            has_dynamic_permission(user, 'admin:dashboard'),
            "Cached value should persist until cache is invalidated"
        )

        # Clearing cache forces reload from DB
        delattr(user, '_dynamic_perms_cache')
        self.assertFalse(
            has_dynamic_permission(user, 'admin:dashboard'),
            "After cache invalidation, stripped roles must result in False"
        )

    def test_multiple_roles_union(self):
        """User having multiple roles inherits union of all permissions."""
        role_special = Role.objects.create(name='SPECIALIST')
        perm_special, _ = AppPermission.objects.get_or_create(name='special:action')
        role_special.permissions.add(perm_special)

        multi_role_user = User.objects.create_user(username='multi_role', password='password123')
        multi_role_user.db_roles.add(self.role_sales, role_special)

        self.assertTrue(has_dynamic_permission(multi_role_user, 'leads:read_tenant'))
        self.assertTrue(has_dynamic_permission(multi_role_user, 'special:action'))
        self.assertFalse(has_dynamic_permission(multi_role_user, 'admin:dashboard'))

    def test_permission_factories(self):
        """DRF Permission factories HasPermission and HasAnyPermission enforce dynamic checks."""
        request = self.request_factory.get('/api/stats/')
        request.user = self.admin_user

        perm_class = HasPermission('admin:dashboard')()
        self.assertTrue(perm_class.has_permission(request, None))

        request.user = self.sales_user
        self.assertFalse(perm_class.has_permission(request, None))

        any_perm_class = HasAnyPermission('admin:dashboard', 'leads:read_tenant')()
        self.assertTrue(any_perm_class.has_permission(request, None), "Sales user has leads:read_tenant")

        request.user = self.plain_user
        self.assertFalse(any_perm_class.has_permission(request, None), "Plain user has neither permission")


class DashboardAPIAccessGatingIntegrationTests(TestCase):
    """
    Tier 3 & Tier 4: Integration and End-to-End API endpoint access tests
    verifying authentication and authorization gating on /api/stats/.
    """

    def setUp(self):
        self.client = APIClient()

        # Seed Permissions
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Full access to executive admin dashboard'}
        )
        self.perm_leads_read, _ = AppPermission.objects.get_or_create(
            name='leads:read_tenant',
            defaults={'description': 'Read tenant leads'}
        )
        self.perm_staff_read, _ = AppPermission.objects.get_or_create(
            name='staff:read_tenant',
            defaults={'description': 'Read tenant staff'}
        )

        # Seed Roles
        self.role_admin = Role.objects.create(name='ADMIN')
        self.role_admin.permissions.add(self.perm_admin_dash, self.perm_leads_read, self.perm_staff_read)

        self.role_staff = Role.objects.create(name='STAFF')
        self.role_staff.permissions.add(self.perm_leads_read)

        # Seed Users
        self.admin = User.objects.create_user(username='api_admin', password='password123', company='LP')
        self.admin.db_roles.add(self.role_admin)

        self.staff_user = User.objects.create_user(username='api_staff', password='password123', company='LP')
        self.staff_user.db_roles.add(self.role_staff)

        self.unprivileged_user = User.objects.create_user(username='api_unprivileged', password='password123', company='LP')

        # Seed sample data so endpoints have something to aggregate
        Lead.objects.create(name="Sample Lead", phone="9998887771", status="HOT", company="LP")

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated requests must be rejected with HTTP 401 Unauthorized."""
        response = self.client.get('/api/stats/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_receives_complete_dashboard_stats(self):
        """Authenticated Admin with admin:dashboard receives HTTP 200 with stats data."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_leads', response.data)
        self.assertIn('active_staff', response.data)
        self.assertEqual(response.data['total_leads'], 1)

    def test_staff_user_with_leads_permission_receives_leads_stat(self):
        """Staff user with leads:read_tenant receives 200 with total_leads but not staff on leave."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_leads', response.data)
        self.assertNotIn('staff_on_leave', response.data)

    def test_unprivileged_user_receives_forbidden(self):
        """User with no permissions accessing /api/stats/ receives HTTP 403 PermissionDenied."""
        self.client.force_authenticate(user=self.unprivileged_user)
        response = self.client.get('/api/stats/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
