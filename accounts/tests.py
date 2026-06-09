from django.test import TestCase

from accounts.permission_templates import get_permissions_for_role


class PermissionTemplateTests(TestCase):
    def test_trainer_template_includes_fee_and_attendance_visibility(self):
        permissions = get_permissions_for_role('TRAINER')
        self.assertIn('students:read_tenant', permissions)
        self.assertIn('fees:read_tenant', permissions)
        self.assertIn('attendance:mark', permissions)

    def test_accounts_template_includes_fee_management_permissions(self):
        permissions = get_permissions_for_role('ACCOUNTS')
        self.assertIn('fees:read_tenant', permissions)
        self.assertIn('fees:manage', permissions)
        self.assertIn('fees:restructure', permissions)
        self.assertIn('fees:partial_payment', permissions)

