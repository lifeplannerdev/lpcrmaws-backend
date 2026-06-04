from django.test import TestCase

from accounts.permission_templates import get_permissions_for_role


class PermissionTemplateTests(TestCase):
    def test_trainer_template_includes_fee_and_attendance_visibility(self):
        permissions = get_permissions_for_role('TRAINER')
        self.assertIn('view_students', permissions)
        self.assertIn('view_fees', permissions)
        self.assertIn('mark_attendance', permissions)

    def test_accounts_template_includes_fee_management_permissions(self):
        permissions = get_permissions_for_role('ACCOUNTS')
        self.assertIn('view_fees', permissions)
        self.assertIn('manage_fees', permissions)
        self.assertIn('restructure_fees', permissions)
        self.assertIn('record_partial_payment', permissions)
