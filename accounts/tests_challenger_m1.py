"""
Adversarial & Empirical Challenger Test Suite for Milestone 1 (M1)
Agent: challenger_m1_1
Target:
1. Idempotency of scripts/add_admin_dashboard_perm.py & management command (1x, 2x, 5x, 10x).
2. Permission checks under edge cases:
   - User with no roles
   - User inactive (is_active=False)
   - User with multiple roles (admin + non-admin, non-admin combinations)
   - AnonymousUser and unsaved User instances
   - Explicit verification: ADMIN, CEO, managing_director vs standard staff roles
"""
import io
import sys
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test.client import RequestFactory

from accounts.models import AppPermission, Role
from accounts.permissions import (
    has_dynamic_permission,
    HasPermission,
    HasAnyPermission,
)
from accounts.services import PermissionService
from scripts.add_admin_dashboard_perm import (
    add_admin_dashboard_permission,
    PERMISSION_NAME,
    PERMISSION_DESCRIPTION,
    ADMIN_ROLES_TO_ASSIGN
)

User = get_user_model()


class ChallengerIdempotencyStressTestCase(TestCase):
    """
    Stress tests the idempotency of adding the admin:dashboard permission.
    Evaluates execution of both the script function and the Django management command
    across 1, 2, 5, and 10 iterations.
    """

    def setUp(self):
        # Create administrative roles
        self.role_admin = Role.objects.create(name='ADMIN', description='System Admin')
        self.role_ceo = Role.objects.create(name='CEO', description='Chief Executive')
        self.role_md = Role.objects.create(name='managing_director', description='Managing Director')
        
        # Create non-admin role
        self.role_staff = Role.objects.create(name='STAFF', description='General Staff')

        # Pre-seed other permissions to ensure they are NOT wiped
        self.perm_existing1 = AppPermission.objects.create(
            name='leads:read_tenant', description='Read leads'
        )
        self.perm_existing2 = AppPermission.objects.create(
            name='staff:read_tenant', description='Read staff'
        )
        self.role_admin.permissions.add(self.perm_existing1, self.perm_existing2)
        self.role_ceo.permissions.add(self.perm_existing1)
        self.role_staff.permissions.add(self.perm_existing1)

    def test_script_function_idempotency_10_iterations(self):
        """
        Verify that running add_admin_dashboard_permission() 10 times consecutively:
        1. Does not create duplicate permissions in permissions table.
        2. Does not create duplicate entries in role_permissions table.
        3. Preserves all pre-existing role permissions.
        4. Does not assign admin:dashboard to non-admin roles.
        """
        initial_admin_perms_count = self.role_admin.permissions.count()  # 2
        initial_ceo_perms_count = self.role_ceo.permissions.count()      # 1
        initial_staff_perms_count = self.role_staff.permissions.count()  # 1

        for iteration in range(1, 11):
            perm_obj = add_admin_dashboard_permission()
            self.assertIsNotNone(perm_obj)
            self.assertEqual(perm_obj.name, PERMISSION_NAME)

            # Check 1: Exactly 1 AppPermission row exists for admin:dashboard
            dash_perm_qs = AppPermission.objects.filter(name=PERMISSION_NAME)
            self.assertEqual(
                dash_perm_qs.count(), 1,
                f"Iteration {iteration}: AppPermission duplicate detected! Count: {dash_perm_qs.count()}"
            )

            # Check 2: Check mapping count for each admin role
            for role_name in ADMIN_ROLES_TO_ASSIGN:
                role = Role.objects.get(name=role_name)
                matching = role.permissions.filter(name=PERMISSION_NAME)
                self.assertEqual(
                    matching.count(), 1,
                    f"Iteration {iteration}: Role {role_name} has {matching.count()} instances of {PERMISSION_NAME}"
                )

            # Check 3: Check total role_permissions mappings for admin:dashboard
            total_role_mappings = Role.permissions.through.objects.filter(
                apppermission=dash_perm_qs.first()
            ).count()
            self.assertEqual(
                total_role_mappings, 3,
                f"Iteration {iteration}: Expected 3 total mappings in role_permissions, found {total_role_mappings}"
            )

            # Check 4: Pre-existing permissions are preserved and not cleared
            self.assertEqual(
                self.role_admin.permissions.count(), initial_admin_perms_count + 1,
                f"Iteration {iteration}: ADMIN role permissions count modified unexpectedly"
            )
            self.assertEqual(
                self.role_ceo.permissions.count(), initial_ceo_perms_count + 1,
                f"Iteration {iteration}: CEO role permissions count modified unexpectedly"
            )
            self.assertEqual(
                self.role_staff.permissions.count(), initial_staff_perms_count,
                f"Iteration {iteration}: STAFF role permissions count was modified!"
            )
            self.assertFalse(
                self.role_staff.permissions.filter(name=PERMISSION_NAME).exists(),
                f"Iteration {iteration}: STAFF role was erroneously assigned {PERMISSION_NAME}!"
            )

    def test_management_command_idempotency_10_iterations(self):
        """
        Verify that running 'manage.py add_admin_dashboard_perm' 10 times consecutively:
        1. Maintains exactly 1 permission row.
        2. Maintains exactly 1 mapping per administrative role.
        3. Never raises IntegrityError or duplicates records.
        """
        out = io.StringIO()
        for iteration in range(1, 11):
            call_command('add_admin_dashboard_perm', stdout=out)
            dash_perm_qs = AppPermission.objects.filter(name=PERMISSION_NAME)
            self.assertEqual(dash_perm_qs.count(), 1, f"Iteration {iteration}: Duplicate AppPermission found!")

            for role_name in ADMIN_ROLES_TO_ASSIGN:
                role = Role.objects.get(name=role_name)
                self.assertEqual(role.permissions.filter(name=PERMISSION_NAME).count(), 1)

            total_mappings = Role.permissions.through.objects.filter(
                apppermission=dash_perm_qs.first()
            ).count()
            self.assertEqual(total_mappings, 3)

    def test_idempotency_when_description_is_altered(self):
        """
        If description in DB deviates or is empty, running the script updates the description
        without creating duplicate rows.
        """
        # Update existing permission description to altered description
        perm, _ = AppPermission.objects.get_or_create(name=PERMISSION_NAME)
        perm.description = "Old description"
        perm.save(update_fields=['description'])
        self.assertEqual(AppPermission.objects.filter(name=PERMISSION_NAME).count(), 1)

        # Run script
        add_admin_dashboard_permission()
        perm.refresh_from_db()
        self.assertEqual(AppPermission.objects.filter(name=PERMISSION_NAME).count(), 1)
        self.assertEqual(perm.description, PERMISSION_DESCRIPTION)

    def test_idempotency_with_missing_roles(self):
        """
        If some administrative roles do not exist in the database, the script does not crash
        and safely assigns to the roles that do exist.
        """
        Role.objects.filter(name='managing_director').delete()
        self.assertFalse(Role.objects.filter(name='managing_director').exists())

        # Should complete gracefully without raising DoesNotExist
        add_admin_dashboard_permission()
        
        self.assertEqual(AppPermission.objects.filter(name=PERMISSION_NAME).count(), 1)
        self.assertTrue(Role.objects.get(name='ADMIN').permissions.filter(name=PERMISSION_NAME).exists())
        self.assertTrue(Role.objects.get(name='CEO').permissions.filter(name=PERMISSION_NAME).exists())


class ChallengerEdgeCasesPermissionsTestCase(TestCase):
    """
    Adversarial test cases covering permission resolution edge cases:
    - User with no roles
    - Inactive user (is_active=False)
    - Multiple roles (admin + non-admin, non-admin combinations)
    - AnonymousUser and unsaved User instances
    - Explicit role mapping checks for ADMIN, CEO, MD vs standard staff
    """

    def setUp(self):
        # Register permissions
        self.perm_admin_dash, _ = AppPermission.objects.get_or_create(
            name='admin:dashboard',
            defaults={'description': 'Full admin dashboard access'}
        )
        self.perm_leads_read, _ = AppPermission.objects.get_or_create(
            name='leads:read_tenant',
            defaults={'description': 'Read leads'}
        )
        self.perm_tasks_view, _ = AppPermission.objects.get_or_create(
            name='tasks:view_tenant',
            defaults={'description': 'View tasks'}
        )

        # Roles
        self.role_admin = Role.objects.create(name='ADMIN')
        self.role_admin.permissions.add(self.perm_admin_dash, self.perm_leads_read)

        self.role_ceo = Role.objects.create(name='CEO')
        self.role_ceo.permissions.add(self.perm_admin_dash, self.perm_tasks_view)

        self.role_md = Role.objects.create(name='managing_director')
        self.role_md.permissions.add(self.perm_admin_dash)

        self.role_sales = Role.objects.create(name='SALES_EXECUTIVE')
        self.role_sales.permissions.add(self.perm_leads_read)

        self.role_counselor = Role.objects.create(name='COUNSELOR')
        self.role_counselor.permissions.add(self.perm_tasks_view)

        self.role_telecaller = Role.objects.create(name='TELECALLER')

        self.rf = RequestFactory()

    # ── Edge Case 1: User with No Roles ─────────────────────────────────────────

    def test_user_with_no_roles(self):
        """
        User with zero roles and empty JSON permissions must evaluate to False
        for all dynamic permission checks without throwing exceptions.
        """
        user = User.objects.create_user(username='no_roles_user', password='password123', company='LP')
        self.assertEqual(user.db_roles.count(), 0)
        self.assertEqual(user.permissions, [])

        self.assertFalse(has_dynamic_permission(user, 'admin:dashboard'))
        self.assertFalse(has_dynamic_permission(user, 'leads:read_tenant'))
        self.assertFalse(has_dynamic_permission(user, 'nonexistent:perm'))

        # PermissionService check
        user_perms = PermissionService.get_user_permissions(user)
        self.assertEqual(user_perms, {})

    # ── Edge Case 2: Inactive User (is_active=False) ─────────────────────────────

    def test_inactive_user_with_admin_role_behavior(self):
        """
        Empirically test what has_dynamic_permission returns for an inactive user (is_active=False).
        Investigate whether has_dynamic_permission checks user.is_active or relies purely on authentication.
        """
        inactive_admin = User.objects.create_user(
            username='inactive_admin', password='password123', company='LP', is_active=False
        )
        inactive_admin.db_roles.add(self.role_admin)

        # Empirical measurement
        result = has_dynamic_permission(inactive_admin, 'admin:dashboard')

        # In standard Django permissions, inactive users ALWAYS return False for has_perm.
        # But in DRF/custom has_dynamic_permission:
        # Let's record the exact empirical behavior:
        # Django's user.is_authenticated is True even when is_active is False!
        # If has_dynamic_permission does not check is_active, it returns True.
        print(f"\n[EMPIRICAL OBSERVATION] has_dynamic_permission for inactive admin (is_active=False): {result}")
        print(f"[EMPIRICAL OBSERVATION] inactive_admin.is_authenticated: {inactive_admin.is_authenticated}")
        print(f"[EMPIRICAL OBSERVATION] inactive_admin.is_active: {inactive_admin.is_active}")

        # Document and assert the empirical reality:
        # Note: In Django auth, is_active=False accounts cannot log in (authenticate fails at credential validation),
        # but if an inactive User model instance is passed directly to has_dynamic_permission:
        # This is an important distinction to report to orchestrator!

    # ── Edge Case 3: Multiple Roles (Admin + Non-Admin Combinations) ────────────

    def test_user_with_admin_and_non_admin_roles(self):
        """
        User possessing both ADMIN and SALES_EXECUTIVE roles must have admin:dashboard (union of privileges).
        """
        user = User.objects.create_user(username='admin_sales', password='password123', company='LP')
        user.db_roles.add(self.role_admin, self.role_sales)

        self.assertTrue(has_dynamic_permission(user, 'admin:dashboard'))
        self.assertTrue(has_dynamic_permission(user, 'leads:read_tenant'))

    def test_user_with_ceo_and_telecaller_roles(self):
        """
        User possessing CEO and TELECALLER roles must have admin:dashboard and tasks:view_tenant.
        """
        user = User.objects.create_user(username='ceo_telecaller', password='password123', company='LP')
        user.db_roles.add(self.role_ceo, self.role_telecaller)

        self.assertTrue(has_dynamic_permission(user, 'admin:dashboard'))
        self.assertTrue(has_dynamic_permission(user, 'tasks:view_tenant'))
        self.assertFalse(has_dynamic_permission(user, 'leads:read_tenant'))

    def test_user_with_managing_director_and_staff_roles(self):
        """
        User possessing managing_director and counselor roles must have admin:dashboard.
        """
        user = User.objects.create_user(username='md_counselor', password='password123', company='LP')
        user.db_roles.add(self.role_md, self.role_counselor)

        self.assertTrue(has_dynamic_permission(user, 'admin:dashboard'))
        self.assertTrue(has_dynamic_permission(user, 'tasks:view_tenant'))
        self.assertFalse(has_dynamic_permission(user, 'leads:read_tenant'))

    def test_user_with_multiple_non_admin_roles_denied(self):
        """
        User possessing multiple non-admin roles (SALES_EXECUTIVE + COUNSELOR + TELECALLER)
        must NOT have admin:dashboard under any circumstances.
        """
        user = User.objects.create_user(username='pure_staff', password='password123', company='LP')
        user.db_roles.add(self.role_sales, self.role_counselor, self.role_telecaller)

        self.assertFalse(has_dynamic_permission(user, 'admin:dashboard'))
        self.assertTrue(has_dynamic_permission(user, 'leads:read_tenant'))
        self.assertTrue(has_dynamic_permission(user, 'tasks:view_tenant'))

    # ── Edge Case 4: AnonymousUser and Unsaved User ──────────────────────────────

    def test_anonymous_user_evaluation(self):
        """
        AnonymousUser must always return False without throwing exceptions or querying DB.
        """
        anon = AnonymousUser()
        self.assertFalse(anon.is_authenticated)
        self.assertFalse(has_dynamic_permission(anon, 'admin:dashboard'))
        self.assertFalse(has_dynamic_permission(anon, 'leads:read_tenant'))
        self.assertFalse(has_dynamic_permission(anon, ''))

    def test_unsaved_user_evaluation(self):
        """
        Unsaved User instance (pk is None) must return False without throwing ValueError.
        """
        unsaved = User(username='unsaved_user', company='LP')
        self.assertIsNone(unsaved.pk)
        self.assertTrue(unsaved.is_authenticated)

        # Must not raise: ValueError: Model instances passed to related filters must be saved.
        result = has_dynamic_permission(unsaved, 'admin:dashboard')
        self.assertFalse(result)

    def test_unsaved_user_with_json_permissions(self):
        """
        Unsaved User with direct JSON permissions in user.permissions resolves them safely.
        """
        unsaved = User(username='unsaved_with_json', company='LP', permissions=['admin:dashboard'])
        self.assertIsNone(unsaved.pk)
        result = has_dynamic_permission(unsaved, 'admin:dashboard')
        self.assertTrue(result)
        self.assertFalse(has_dynamic_permission(unsaved, 'leads:read_tenant'))

    # ── Edge Case 5: Role-Specific Verification (ADMIN/CEO/MD vs Staff) ────────

    def test_admin_roles_matrix(self):
        """
        Verify that has_dynamic_permission(user, 'admin:dashboard') strictly evaluates:
        - ADMIN -> True
        - CEO -> True
        - managing_director -> True
        - SALES_EXECUTIVE -> False
        - COUNSELOR -> False
        - TELECALLER -> False
        """
        roles_expectation = {
            self.role_admin: True,
            self.role_ceo: True,
            self.role_md: True,
            self.role_sales: False,
            self.role_counselor: False,
            self.role_telecaller: False,
        }

        for role, expected in roles_expectation.items():
            user = User.objects.create_user(
                username=f"user_{role.name.lower()}", password='password123', company='LP'
            )
            user.db_roles.add(role)
            actual = has_dynamic_permission(user, 'admin:dashboard')
            self.assertEqual(
                actual, expected,
                f"Role {role.name} expected admin:dashboard={expected}, got {actual}"
            )

    # ── Edge Case 6: DRF Permission Classes with Anonymous & Inactive Users ─────

    def test_drf_has_permission_factory_edge_cases(self):
        """
        Test HasPermission('admin:dashboard') under DRF request context.
        """
        perm_checker = HasPermission('admin:dashboard')()

        # 1. Anonymous
        req_anon = self.rf.get('/')
        req_anon.user = AnonymousUser()
        self.assertFalse(perm_checker.has_permission(req_anon, None))

        # 2. Staff user
        staff_user = User.objects.create_user(username='drf_staff', password='password123')
        staff_user.db_roles.add(self.role_sales)
        req_staff = self.rf.get('/')
        req_staff.user = staff_user
        self.assertFalse(perm_checker.has_permission(req_staff, None))

        # 3. Admin user
        admin_user = User.objects.create_user(username='drf_admin', password='password123')
        admin_user.db_roles.add(self.role_admin)
        req_admin = self.rf.get('/')
        req_admin.user = admin_user
        self.assertTrue(perm_checker.has_permission(req_admin, None))
