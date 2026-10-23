from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.permission_templates import get_permissions_for_role
from fees.models import FeePlanTemplate, StudentFeeAccount, FeeInstallment, FeeReceipt
from students.models import AcademicBatch, AcademicPackage, Campus, Grade, Student


User = get_user_model()


class FeeAccessTests(APITestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name='FLAG Branch', code='FLG-KOC', city='Kochi')
        self.grade_a1, _ = Grade.objects.get_or_create(code='A1', defaults={'name': 'A1 - Beginner', 'order': 1})
        self.package = AcademicPackage.objects.create(
            name='A1 Package',
            starting_grade=self.grade_a1,
            ending_grade=self.grade_a1,
        )

        self.trainer_user = User.objects.create_user(
            username='trainer-fee',
            password='pass12345',
            company='FLAG',
            permissions=['students:read_tenant', 'fees:read_tenant', 'attendance:mark'],
        )
        self.batch = AcademicBatch.objects.create(
            name='FLG-A1-BATCH',
            campus=self.campus,
            package=self.package,
            trainer=self.trainer_user,
            mode='offline',
            status='active',
        )

        self.accounts_user = User.objects.create_user(
            username='accounts',
            password='pass12345',
            company='FLAG',
            permissions=['fees:read_tenant', 'fees:manage', 'fees:restructure', 'fees:partial_payment'],
        )

        self.student = Student.objects.create(
            name='Fee Student',
            campus=self.campus,
            academic_package=self.package,
            batch=self.batch,
            status='active',
            joined_date=date(2026, 1, 1),
        )
        self.template = FeePlanTemplate.objects.create(
            company='FLAG',
            code='FLAG-A1',
            name='FLAG A1',
            course_label='A1',
            plan_type='PACKAGE',
            total_amount='21240.00',
        )
        self.account = StudentFeeAccount.objects.create(
            student=self.student,
            company='FLAG',
            template=self.template,
            plan_code=self.template.code,
            plan_name=self.template.name,
            plan_type='PACKAGE',
            total_due='21240.00',
            registration_amount='0.00',
            due_day=10,
            source_label='manual',
        )
        self.installment = FeeInstallment.objects.create(
            account=self.account,
            sequence_number=1,
            label='Initial installment',
            due_date=date(2026, 6, 10),
            scheduled_amount='1000.00',
            paid_amount='0.00',
            balance_amount='1000.00',
            status='PENDING',
        )

    def test_trainer_can_view_fee_account_but_cannot_post_payment(self):
        self.client.force_authenticate(user=self.trainer_user)
        response = self.client.get(reverse('fee-account-list-create'), {'student': self.student.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

        post_response = self.client.post(
            reverse('fee-payment-list-create', kwargs={'account_pk': self.account.id}),
            {
                'account': self.account.id,
                'installment': self.installment.id,
                'amount': '200.00',
                'payment_method': 'CASH',
                'payment_date': '2026-06-04T10:00:00Z',
                'receipt_number': '',
            },
            format='json',
        )
        self.assertEqual(post_response.status_code, 403)

    def test_accounts_user_can_record_payment_and_reduce_balance(self):
        self.client.force_authenticate(user=self.accounts_user)
        response = self.client.post(
            reverse('fee-payment-list-create', kwargs={'account_pk': self.account.id}),
            {
                'account': self.account.id,
                'installment': self.installment.id,
                'amount': '200.00',
                'payment_method': 'CASH',
                'payment_date': '2026-06-04T10:00:00Z',
                'receipt_number': '',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.account.refresh_from_db()
        self.installment.refresh_from_db()
        self.assertEqual(str(self.account.total_paid), '200.00')
        self.assertEqual(str(self.account.total_due), '1000.00')
        self.assertEqual(str(self.account.balance_due), '800.00')
        self.assertEqual(str(self.installment.paid_amount), '200.00')

    def test_fee_catalog_is_readable_for_trainer_visibility(self):
        self.client.force_authenticate(user=self.trainer_user)
        response = self.client.get(reverse('fee-catalog-list-create'), {'company': 'FLAG', 'active': 'true'})
        self.assertEqual(response.status_code, 200)
        codes = [item['code'] for item in response.data]
        self.assertIn(self.template.code, codes)

    def test_fee_account_create_autofills_template_defaults_and_snapshot(self):
        self.client.force_authenticate(user=self.accounts_user)

        second_student = Student.objects.create(
            name='Template Student',
            campus=self.campus,
            academic_package=self.package,
            batch=self.batch,
            status='active',
            joined_date=date(2026, 1, 1),
        )

        response = self.client.post(
            reverse('fee-account-list-create'),
            {
                'student': second_student.id,
                'template': self.template.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        account = StudentFeeAccount.objects.get(student=second_student)
        self.assertEqual(account.plan_code, self.template.code)
        self.assertEqual(account.plan_name, self.template.name)
        self.assertEqual(account.plan_type, self.template.plan_type)
        self.assertEqual(str(account.total_due), str(self.template.total_amount))
        self.assertEqual(account.registration_amount, self.template.registration_amount)
        self.assertEqual(account.due_day, self.template.due_day)
        self.assertEqual(account.plan_snapshot['template']['code'], self.template.code)


class DigitalReceiptSystemTests(APITestCase):
    def setUp(self):
        from students.models import AcademicBatch, AcademicPackage, Campus, Grade, Student as FlagStudent

        self.campus = Campus.objects.create(name='FLAG Kochi', code='KOCHI', city='Kochi')
        self.grade_a1, _ = Grade.objects.get_or_create(code='A1', defaults={'name': 'A1 - Beginner', 'order': 1})
        self.grade_b2, _ = Grade.objects.get_or_create(code='B2', defaults={'name': 'B2 - Upper Intermediate', 'order': 4})
        self.package = AcademicPackage.objects.create(
            name='A1 to B2 Full Package',
            starting_grade=self.grade_a1,
            ending_grade=self.grade_b2,
        )
        self.batch = AcademicBatch.objects.create(
            name='KOC-A1-01',
            campus=self.campus,
            package=self.package,
            mode='offline',
            status='active',
        )
        self.accounts_user = User.objects.create_user(
            username='receipt-admin',
            password='pass12345',
            company='FLAG',
            permissions=['fees:read_tenant', 'fees:manage', 'flag:fees', 'flag:admin'],
        )
        self.student = FlagStudent.objects.create(
            name='Aditi Menon',
            campus=self.campus,
            academic_package=self.package,
            batch=self.batch,
            status='active',
            joined_date=date(2026, 4, 10),
            phone='9846012345',
            email='aditi@example.com',
        )
        self.template = FeePlanTemplate.objects.create(
            company='FLAG',
            code='FLAG-FULL',
            name='FLAG A1-B2 Full Package',
            course_label='A1-B2',
            plan_type='PACKAGE',
            total_amount='106200.00',
            registration_amount='10000.00',
        )
        self.account = StudentFeeAccount.objects.create(
            student=self.student,
            company='FLAG',
            template=self.template,
            plan_code=self.template.code,
            plan_name=self.template.name,
            plan_type='PACKAGE',
            total_due='106200.00',
            registration_amount='10000.00',
            due_day=10,
            source_label='manual',
        )

    def test_amount_to_words_indian_currency_edge_cases(self):
        from fees.receipt_engine import amount_to_words

        self.assertEqual(amount_to_words(0), 'Rupees Zero Only')
        self.assertEqual(amount_to_words('21240.00'), 'Rupees Twenty-One Thousand Two Hundred Forty Only')
        self.assertEqual(amount_to_words('106200.00'), 'Rupees One Lakh Six Thousand Two Hundred Only')
        self.assertEqual(
            amount_to_words('12500.50'),
            'Rupees Twelve Thousand Five Hundred and Fifty Paise Only',
        )

    def test_gst_inclusive_and_exclusive_calculations(self):
        from fees.receipt_engine import calculate_receipt_financials

        inc = calculate_receipt_financials(
            subtotal_amount='21240.00',
            tax_mode='INCLUSIVE',
            supply_type='INTRA_STATE',
            gst_rate='18.00',
        )
        self.assertEqual(str(inc['taxable_amount']), '18000.00')
        self.assertEqual(str(inc['cgst_amount']), '1620.00')
        self.assertEqual(str(inc['sgst_amount']), '1620.00')
        self.assertEqual(str(inc['total_tax_amount']), '3240.00')
        self.assertEqual(str(inc['total_amount']), '21240.00')

        exc = calculate_receipt_financials(
            subtotal_amount='25000.00',
            tax_mode='EXCLUSIVE',
            supply_type='INTER_STATE',
            gst_rate='18.00',
        )
        self.assertEqual(str(exc['taxable_amount']), '25000.00')
        self.assertEqual(str(exc['igst_amount']), '4500.00')
        self.assertEqual(str(exc['total_amount']), '29500.00')

    def test_one_click_receipt_from_payment_and_idempotency(self):
        self.client.force_authenticate(user=self.accounts_user)
        pay_res = self.client.post(
            reverse('fee-payment-list-create', kwargs={'account_pk': self.account.id}),
            {
                'account': self.account.id,
                'amount': '21240.00',
                'payment_method': 'UPI',
                'payment_date': '2026-06-15T10:30:00Z',
                'reference': 'UTR99887766',
            },
            format='json',
        )
        self.assertEqual(pay_res.status_code, 201)
        payment_id = pay_res.data['id']

        gen_res = self.client.post(
            reverse('fee-receipt-from-payment', kwargs={'payment_id': payment_id}),
            {},
            format='json',
        )
        self.assertEqual(gen_res.status_code, 201)
        receipt_id = gen_res.data['id']
        self.assertTrue(gen_res.data['receipt_number'].startswith('FLAG/2026-27/'))
        self.assertEqual(gen_res.data['recipient_name'], 'Aditi Menon')
        self.assertEqual(str(gen_res.data['total_amount']), '21240.00')
        self.assertEqual(str(gen_res.data['taxable_amount']), '18000.00')
        self.assertTrue(gen_res.data['is_signature_valid'])

        # Calling again without force_new returns the same receipt (idempotent)
        gen_again = self.client.post(
            reverse('fee-receipt-from-payment', kwargs={'payment_id': payment_id}),
            {},
            format='json',
        )
        self.assertEqual(gen_again.status_code, 200)
        self.assertEqual(gen_again.data['id'], receipt_id)

    def test_manual_override_versioning_and_standalone_proforma(self):
        self.client.force_authenticate(user=self.accounts_user)

        # Standalone Proforma without student/account link
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'document_type': 'PROFORMA',
                'status': 'ISSUED',
                'recipient_name': 'Walk-in Sponsor Corp',
                'billed_to_type': 'SPONSOR',
                'course_or_package_name': 'Corporate German B1 Batch',
                'tax_mode': 'EXCLUSIVE',
                'supply_type': 'INTRA_STATE',
                'line_items': [
                    {
                        'title': 'Registration Fee',
                        'quantity': '1',
                        'unit_price': '10000.00',
                        'discount': '0.00',
                    },
                    {
                        'title': 'B1 Module Tuition',
                        'quantity': '1',
                        'unit_price': '15000.00',
                        'discount': '0.00',
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 201)
        self.assertEqual(str(create_res.data['subtotal_amount']), '25000.00')
        self.assertEqual(str(create_res.data['total_tax_amount']), '4500.00')
        self.assertEqual(str(create_res.data['total_amount']), '29500.00')
        self.assertEqual(create_res.data['version'], 1)

        receipt_id = create_res.data['id']
        token = create_res.data['verification_token']

        # Patch with manual override
        patch_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {
                'recipient_name': 'Walk-in Sponsor Corp Pvt Ltd',
                'discount_amount': '5000.00',
            },
            format='json',
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.data['version'], 2)
        self.assertTrue(patch_res.data['is_manual_override'])
        self.assertEqual(str(patch_res.data['taxable_amount']), '20000.00')
        self.assertEqual(str(patch_res.data['total_amount']), '23600.00')
        self.assertEqual(str(patch_res.data['ledger_current_paid']), '23600.00')
        self.assertEqual(len(patch_res.data['line_items']), 2)
        self.assertEqual(len(patch_res.data['snapshot_data']['revisions']), 2)

        # Patch with manual_financial_override=True and custom total_amount must preserve the 2 line_items
        override_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {
                'total_amount': '22000.00',
                'manual_financial_override': True,
            },
            format='json',
        )
        self.assertEqual(override_res.status_code, 200)
        self.assertEqual(str(override_res.data['total_amount']), '22000.00')
        self.assertEqual(str(override_res.data['ledger_current_paid']), '22000.00')
        self.assertEqual(len(override_res.data['line_items']), 2)

        # Public QR verification (unauthenticated)
        self.client.force_authenticate(user=None)
        verify_res = self.client.get(reverse('fee-receipt-verify', kwargs={'verification_token': token}))
        self.assertEqual(verify_res.status_code, 200)
        self.assertTrue(verify_res.data['verified'])
        self.assertEqual(verify_res.data['verification_status'], 'VALID')
        self.assertEqual(str(verify_res.data['total_amount']), '22000.00')

    def test_mode_b_account_linked_receipt_ledger_sync_and_partial_save_signature(self):
        from decimal import Decimal
        from fees.receipt_engine import verify_receipt_signature

        self.client.force_authenticate(user=self.accounts_user)
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'account': self.account.id,
                'subtotal_amount': '10000.00',
                'tax_mode': 'INCLUSIVE',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 201)
        self.assertEqual(str(create_res.data['total_amount']), '10000.00')
        self.assertEqual(str(create_res.data['ledger_current_paid']), '10000.00')
        self.assertEqual(str(create_res.data['ledger_total_paid']), '10000.00')
        self.assertEqual(str(create_res.data['ledger_balance_due']), '96200.00')
        self.assertEqual(create_res.data['payment_status_badge'], 'PARTIAL')

        # Partial save with update_fields must persist recomputed signature_hash
        receipt = FeeReceipt.objects.get(pk=create_res.data['id'])
        receipt.total_amount = Decimal('15000.00')
        receipt.save(update_fields=['total_amount'])
        receipt.refresh_from_db()
        self.assertTrue(verify_receipt_signature(receipt))

    def test_controlled_void_workflow_and_audit_protection(self):
        self.client.force_authenticate(user=self.accounts_user)
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'recipient_name': 'Rahul Nair',
                'subtotal_amount': '21240.00',
                'tax_mode': 'INCLUSIVE',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 201)
        receipt_id = create_res.data['id']
        token = create_res.data['verification_token']

        # Deleting an ISSUED receipt is blocked for audit compliance
        del_res = self.client.delete(reverse('fee-receipt-detail', kwargs={'pk': receipt_id}))
        self.assertEqual(del_res.status_code, 400)

        # Void without reason is rejected
        bad_void = self.client.post(reverse('fee-receipt-void', kwargs={'pk': receipt_id}), {}, format='json')
        self.assertEqual(bad_void.status_code, 400)

        # Void with valid reason succeeds
        void_res = self.client.post(
            reverse('fee-receipt-void', kwargs={'pk': receipt_id}),
            {'void_reason': 'Cheque dishonoured by bank'},
            format='json',
        )
        self.assertEqual(void_res.status_code, 200)
        self.assertEqual(void_res.data['status'], 'VOID')

        # Public verification now shows VOID
        self.client.force_authenticate(user=None)
        verify_res = self.client.get(reverse('fee-receipt-verify', kwargs={'verification_token': token}))
        self.assertEqual(verify_res.status_code, 200)
        self.assertFalse(verify_res.data['verified'])
        self.assertFalse(verify_res.data['is_authentic'])
        self.assertEqual(verify_res.data['verification_status'], 'VOID')
        self.assertEqual(verify_res.data['void_reason'], 'Cheque dishonoured by bank')

    def test_financial_year_ist_boundary_and_sequence_reset_across_fys(self):
        from datetime import datetime, timezone as dt_timezone
        from fees.receipt_engine import allocate_receipt_number, get_indian_financial_year

        # 2026-03-31 20:00 UTC is 2026-04-01 01:30 IST -> must be FY 2026-27
        utc_dt = datetime(2026, 3, 31, 20, 0, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(get_indian_financial_year(utc_dt), '2026-27')

        # 2026-03-31 18:00 UTC is 2026-03-31 23:30 IST -> still FY 2025-26
        utc_before_midnight_ist = datetime(2026, 3, 31, 18, 0, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(get_indian_financial_year(utc_before_midnight_ist), '2025-26')

        # Allocate numbers in FY 2026-27, then FY 2027-28, then again in FY 2026-27
        r1, fy1, _, _ = allocate_receipt_number('FLAG', issue_date=date(2026, 5, 1))
        r2, fy2, _, _ = allocate_receipt_number('FLAG', issue_date=date(2026, 5, 2))
        self.assertEqual(fy1, '2026-27')
        self.assertEqual(r1, 'FLAG/2026-27/0001')
        self.assertEqual(r2, 'FLAG/2026-27/0002')

        # Next FY resets to 0001
        r_next_fy, fy_next, _, _ = allocate_receipt_number('FLAG', issue_date=date(2027, 4, 1))
        self.assertEqual(fy_next, '2027-28')
        self.assertEqual(r_next_fy, 'FLAG/2027-28/0001')

        # Backdated receipt in 2026-27 continues from 0003
        r3, fy3, _, _ = allocate_receipt_number('FLAG', issue_date=date(2026, 6, 1))
        self.assertEqual(fy3, '2026-27')
        self.assertEqual(r3, 'FLAG/2026-27/0003')

    def test_lifecycle_guards_draft_verification_and_proforma_badge(self):
        self.client.force_authenticate(user=self.accounts_user)

        # Create DRAFT receipt
        draft_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'status': 'DRAFT',
                'recipient_name': 'Draft Student',
                'subtotal_amount': '15000.00',
            },
            format='json',
        )
        self.assertEqual(draft_res.status_code, 201)
        receipt_id = draft_res.data['id']
        token = draft_res.data['verification_token']

        # Public verify on DRAFT receipt must return verified=False, is_authentic=False, verification_status='DRAFT'
        self.client.force_authenticate(user=None)
        verify_draft = self.client.get(reverse('fee-receipt-verify', kwargs={'verification_token': token}))
        self.assertEqual(verify_draft.status_code, 200)
        self.assertFalse(verify_draft.data['verified'])
        self.assertFalse(verify_draft.data['is_authentic'])
        self.assertEqual(verify_draft.data['verification_status'], 'DRAFT')

        # Promote DRAFT -> ISSUED
        self.client.force_authenticate(user=self.accounts_user)
        issue_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'status': 'ISSUED'},
            format='json',
        )
        self.assertEqual(issue_res.status_code, 200)
        self.assertEqual(issue_res.data['status'], 'ISSUED')

        # Attempt to revert ISSUED -> DRAFT must fail with 400
        revert_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'status': 'DRAFT'},
            format='json',
        )
        self.assertEqual(revert_res.status_code, 400)

        # Attempt to transition ISSUED -> VOID via PATCH without void_reason must fail with 400
        void_no_reason = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'status': 'VOID'},
            format='json',
        )
        self.assertEqual(void_no_reason.status_code, 400)

        # Transition ISSUED -> VOID via PATCH with void_reason succeeds and sets metadata
        void_ok = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'status': 'VOID', 'void_reason': 'Duplicate receipt entry'},
            format='json',
        )
        self.assertEqual(void_ok.status_code, 200)
        self.assertEqual(void_ok.data['status'], 'VOID')
        self.assertEqual(void_ok.data['payment_status_badge'], 'VOID')
        self.assertIsNotNone(void_ok.data['voided_at'])
        self.assertEqual(void_ok.data['voided_by'], self.accounts_user.id)

        # Editing a VOID receipt must be blocked
        edit_void = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'recipient_name': 'Mutated After Void'},
            format='json',
        )
        self.assertEqual(edit_void.status_code, 400)

    def test_expanded_hmac_signature_detects_tampering(self):
        from decimal import Decimal
        from datetime import datetime, timezone as dt_timezone

        self.client.force_authenticate(user=self.accounts_user)
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'recipient_name': 'Original Student',
                'subtotal_amount': '20000.00',
                'discount_amount': '2000.00',
                'tax_mode': 'EXCLUSIVE',
                'gst_rate': '18.00',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 201)
        receipt_id = create_res.data['id']
        token = create_res.data['verification_token']
        orig = FeeReceipt.objects.get(pk=receipt_id)

        tamper_cases = [
            ('recipient_name', 'Tampered Student', orig.recipient_name),
            ('total_tax_amount', Decimal('9999.00'), orig.total_tax_amount),
            ('discount_amount', Decimal('9999.00'), orig.discount_amount),
            ('issue_date', datetime(2020, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc), orig.issue_date),
            ('document_type', 'PROFORMA', orig.document_type),
        ]

        self.client.force_authenticate(user=None)
        for field_name, tampered_val, original_val in tamper_cases:
            FeeReceipt.objects.filter(pk=receipt_id).update(**{field_name: tampered_val})
            verify_res = self.client.get(reverse('fee-receipt-verify', kwargs={'verification_token': token}))
            self.assertEqual(verify_res.status_code, 200)
            self.assertFalse(verify_res.data['verified'], f"Tampering {field_name} was not detected")
            self.assertFalse(verify_res.data['is_authentic'], f"Tampering {field_name} left is_authentic=True")
            self.assertEqual(verify_res.data['verification_status'], 'TAMPER_WARNING')
            # Restore original value and confirm signature becomes valid again
            FeeReceipt.objects.filter(pk=receipt_id).update(**{field_name: original_val})
            restored_res = self.client.get(reverse('fee-receipt-verify', kwargs={'verification_token': token}))
            self.assertTrue(restored_res.data['verified'])
            self.assertEqual(restored_res.data['verification_status'], 'VALID')

    def test_permissions_and_account_scope_restrictions(self):
        from students.models import AcademicBatch, Student as FlagStudent

        partial_user = User.objects.create_user(
            username='partial-only-trainer',
            password='pass12345',
            company='FLAG',
            permissions=['fees:read_own', 'fees:partial_payment'],
        )
        other_trainer = User.objects.create_user(
            username='other-trainer',
            password='pass12345',
            company='FLAG',
            permissions=['fees:read_own'],
        )
        other_batch = AcademicBatch.objects.create(
            name='OTHER-BATCH',
            campus=self.campus,
            package=self.package,
            trainer=other_trainer,
            mode='offline',
            status='active',
        )
        other_student = FlagStudent.objects.create(
            name='Other Trainer Student',
            campus=self.campus,
            academic_package=self.package,
            batch=other_batch,
            status='active',
            joined_date=date(2026, 4, 15),
        )
        other_account = StudentFeeAccount.objects.create(
            student=other_student,
            company='FLAG',
            template=self.template,
            plan_code=self.template.code,
            plan_name=self.template.name,
            plan_type='PACKAGE',
            total_due='50000.00',
            registration_amount='5000.00',
            due_day=10,
            source_label='manual',
        )

        # Assign self.batch to partial_user so they can access self.account but NOT other_account
        self.batch.trainer = partial_user
        self.batch.save(update_fields=['trainer'])

        self.client.force_authenticate(user=partial_user)

        # 1. Partial-only user cannot modify global ReceiptSettings
        settings_res = self.client.patch(
            reverse('fee-receipt-settings'),
            {'company': 'FLAG', 'gstin': '32AAAAA0000A1Z5'},
            format='json',
        )
        self.assertEqual(settings_res.status_code, 403)

        # 2. Partial-only user can create a receipt for their own student/account
        own_receipt_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'student': self.student.id,
                'account': self.account.id,
                'subtotal_amount': '5000.00',
                'status': 'DRAFT',
            },
            format='json',
        )
        self.assertEqual(own_receipt_res.status_code, 201)
        own_receipt_id = own_receipt_res.data['id']

        # 3. Partial-only user cannot delete drafts or void receipts
        del_res = self.client.delete(reverse('fee-receipt-detail', kwargs={'pk': own_receipt_id}))
        self.assertEqual(del_res.status_code, 403)

        void_res = self.client.post(
            reverse('fee-receipt-void', kwargs={'pk': own_receipt_id}),
            {'void_reason': 'Try void'},
            format='json',
        )
        self.assertEqual(void_res.status_code, 403)

        # 4. Partial-only user cannot access another trainer's account on calculate-preview or receipt create
        preview_other = self.client.post(
            reverse('fee-receipt-calculate-preview'),
            {'company': 'FLAG', 'account': other_account.id},
            format='json',
        )
        self.assertEqual(preview_other.status_code, 403)

        create_other = self.client.post(
            reverse('fee-receipt-list-create'),
            {'company': 'FLAG', 'account': other_account.id, 'subtotal_amount': '5000.00'},
            format='json',
        )
        self.assertEqual(create_other.status_code, 403)

        # 5. Mismatched student and account is rejected even for admin
        self.client.force_authenticate(user=self.accounts_user)
        mismatch_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'student': other_student.id,
                'account': self.account.id,
                'subtotal_amount': '5000.00',
            },
            format='json',
        )
        self.assertEqual(mismatch_res.status_code, 400)

    def test_send_email_html_escaping_pdf_validation_and_smtp_error(self):
        import base64
        from unittest.mock import patch
        from django.core import mail

        self.client.force_authenticate(user=self.accounts_user)
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'recipient_name': 'Aditi <script>alert(1)</script>',
                'recipient_email': 'aditi@example.com',
                'subtotal_amount': '10000.00',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 201)
        receipt_id = create_res.data['id']

        # 1. Invalid non-PDF attachment is rejected with 400
        bad_pdf_b64 = base64.b64encode(b'NOT_A_PDF_FILE').decode('ascii')
        bad_res = self.client.post(
            reverse('fee-receipt-send-email', kwargs={'pk': receipt_id}),
            {
                'to_email': 'aditi@example.com',
                'pdf_base64': bad_pdf_b64,
            },
            format='json',
        )
        self.assertEqual(bad_res.status_code, 400)

        # 2. Valid PDF attachment succeeds and escapes HTML in email body
        valid_pdf_b64 = base64.b64encode(b'%PDF-1.4\n%Mock PDF content\n%%EOF').decode('ascii')
        ok_res = self.client.post(
            reverse('fee-receipt-send-email', kwargs={'pk': receipt_id}),
            {
                'to_email': 'aditi@example.com',
                'message': 'Hello <b>world</b> & <script>evil()</script>',
                'pdf_base64': f'data:application/pdf;base64,{valid_pdf_b64}',
            },
            format='json',
        )
        self.assertEqual(ok_res.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        html_alt = mail.outbox[0].alternatives[0][0]
        self.assertNotIn('<script>alert(1)</script>', html_alt)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html_alt)
        self.assertNotIn('<script>evil()</script>', html_alt)

        # 3. SMTP failure returns HTTP 502
        with patch('django.core.mail.EmailMultiAlternatives.send', side_effect=RuntimeError('SMTP down')):
            fail_res = self.client.post(
                reverse('fee-receipt-send-email', kwargs={'pk': receipt_id}),
                {'to_email': 'aditi@example.com'},
                format='json',
            )
            self.assertEqual(fail_res.status_code, 502)

    def test_calculation_and_hydration_edge_cases_f3_f4_f5_f6(self):
        from decimal import Decimal
        from fees.models import FeeAdjustment, FeePayment
        from fees.receipt_engine import extract_account_ledger_snapshot, normalize_line_items

        self.client.force_authenticate(user=self.accounts_user)

        # F4: normalize_line_items defaults quantity <= 0 to 1.00
        items = normalize_line_items([{'title': 'Item A', 'quantity': 0, 'unit_price': '5000.00'}])
        self.assertEqual(items[0]['quantity'], '1.00')
        self.assertEqual(items[0]['amount'], '5000.00')

        # F3: Custom GST rate (12%) preserved across PATCH when gst_rate is not resent
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'recipient_name': 'Custom GST Student',
                'subtotal_amount': '10000.00',
                'tax_mode': 'EXCLUSIVE',
                'supply_type': 'INTRA_STATE',
                'gst_rate': '12.00',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 201)
        receipt_id = create_res.data['id']
        self.assertEqual(str(create_res.data['cgst_rate']), '6.00')
        self.assertEqual(str(create_res.data['sgst_rate']), '6.00')
        self.assertEqual(str(create_res.data['total_amount']), '11200.00')

        # F6 + F3: PATCH subtotal_amount without line_items or gst_rate syncs single line item and keeps 12% GST
        patch_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'subtotal_amount': '20000.00'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.data['line_items'][0]['amount'], '20000.00')
        self.assertEqual(patch_res.data['line_items'][0]['unit_price'], '20000.00')
        self.assertEqual(str(patch_res.data['cgst_rate']), '6.00')
        self.assertEqual(str(patch_res.data['sgst_rate']), '6.00')
        self.assertEqual(str(patch_res.data['total_amount']), '22400.00')

        # Negative gst_rate is rejected with 400 on both PATCH and calculate-preview
        neg_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'gst_rate': '-5.00'},
            format='json',
        )
        self.assertEqual(neg_res.status_code, 400)

        neg_preview = self.client.post(
            reverse('fee-receipt-calculate-preview'),
            {'company': 'FLAG', 'subtotal_amount': '10000.00', 'gst_rate': '-5.00'},
            format='json',
        )
        self.assertEqual(neg_preview.status_code, 400)

        # F5: Mode A and Mode B extract_account_ledger_snapshot subtract discount identically
        self.account.refresh_from_db()
        FeeAdjustment.objects.create(
            account=self.account,
            adjustment_type='DISCOUNT',
            amount_delta=Decimal('-6200.00'),
            reason='Scholarship discount',
            created_by=self.accounts_user,
        )
        payment = FeePayment.objects.create(
            account=self.account,
            amount=Decimal('20000.00'),
            payment_method='UPI',
            created_by=self.accounts_user,
        )
        snap_mode_a = extract_account_ledger_snapshot(self.account, payment=payment)
        snap_mode_b = extract_account_ledger_snapshot(self.account)
        self.assertEqual(str(snap_mode_a['ledger_total_fee']), '106200.00')
        self.assertEqual(str(snap_mode_a['ledger_discount']), '6200.00')
        self.assertEqual(str(snap_mode_a['ledger_total_paid']), '20000.00')
        self.assertEqual(str(snap_mode_a['ledger_balance_due']), '80000.00')
        self.assertEqual(snap_mode_a['ledger_balance_due'], snap_mode_b['ledger_balance_due'])

    def test_receipt_settings_fy_sequence_preservation_put_and_integrity_recovery(self):
        from fees.receipt_engine import allocate_receipt_number

        self.client.force_authenticate(user=self.accounts_user)

        # 1. Positional date argument on allocate_receipt_number works cleanly
        r1, fy1, seq1, _ = allocate_receipt_number(date(2026, 4, 10))
        self.assertEqual(r1, 'FLAG/2026-27/0001')
        self.assertEqual(fy1, '2026-27')
        self.assertEqual(seq1, 1)

        # 2. Updating ReceiptSettings display options preserves fy_sequences and does not leak internal keys
        patch_settings = self.client.patch(
            reverse('fee-receipt-settings'),
            {
                'company': 'FLAG',
                'default_display_options': {'show_bank_details': False},
            },
            format='json',
        )
        self.assertEqual(patch_settings.status_code, 200)
        self.assertNotIn('fy_sequences', patch_settings.data['default_display_options'])
        self.assertNotIn('active_fy', patch_settings.data['default_display_options'])
        self.assertFalse(patch_settings.data['default_display_options']['show_bank_details'])

        # Next allocated number in 2026-27 must continue from 0002 (not reset to 0001)
        r2, _, seq2, _ = allocate_receipt_number('FLAG', issue_date=date(2026, 4, 11))
        self.assertEqual(r2, 'FLAG/2026-27/0002')
        self.assertEqual(seq2, 2)

        # 3. Manual receipt with sequence_number=None at 0005 is respected by allocate_receipt_number
        create_manual = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'receipt_number': 'FLAG/2026-27/0005',
                'recipient_name': 'Manual Seq Student',
                'subtotal_amount': '5000.00',
                'issue_date': '2026-04-12T10:00:00Z',
            },
            format='json',
        )
        self.assertEqual(create_manual.status_code, 201)
        self.assertNotIn('fy_sequences', create_manual.data['display_options'])
        self.assertNotIn('active_fy', create_manual.data['display_options'])

        r_after_manual, _, seq_after, _ = allocate_receipt_number('FLAG', issue_date=date(2026, 4, 15))
        self.assertEqual(r_after_manual, 'FLAG/2026-27/0006')
        self.assertEqual(seq_after, 6)

        # 4. PUT on FeeReceiptDetailAPIView and PROFORMA payment_status_badge override
        put_res = self.client.put(
            reverse('fee-receipt-detail', kwargs={'pk': create_manual.data['id']}),
            {
                'document_type': 'PROFORMA',
                'payment_status_badge': 'PARTIAL',
            },
            format='json',
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.data['document_type'], 'PROFORMA')
        self.assertEqual(put_res.data['payment_status_badge'], 'PROFORMA')

    def test_trainer_role_locked_to_view_generated_receipts_only(self):
        """
        Verify that users with role TRAINER (flag trainers) are strictly locked to
        view generated receipts only and cannot create, edit, update, delete, or void receipts.
        """
        from decimal import Decimal
        from accounts.models import Role
        from students.models import AcademicBatch, Campus, Student as FlagStudent
        from fees.models import FeePayment, FeeReceipt, ReceiptSettings, StudentFeeAccount

        trainer_user = User.objects.create_user(
            username='flag_trainer_user',
            password='pass12345',
            email='flagtrainer@example.com',
            first_name='Flag',
            last_name='Trainer',
            permissions=['flag:trainer', 'flag:view', 'dashboard:read'],
        )
        trainer_role, _ = Role.objects.get_or_create(name='TRAINER', defaults={'description': 'Trainer role'})
        trainer_user.db_roles.add(trainer_role)

        campus = Campus.objects.create(name='Kottayam', code='KTM')
        batch = AcademicBatch.objects.create(
            name='KTM-Batch-1',
            campus=campus,
            package=self.package,
            trainer=trainer_user,
        )
        student = FlagStudent.objects.create(
            name='Trainer Test Student',
            campus=campus,
            academic_package=self.package,
            batch=batch,
        )
        account = StudentFeeAccount.objects.create(
            student=student,
            company='FLAG',
            total_due=Decimal('10000.00'),
        )
        payment = FeePayment.objects.create(
            account=account,
            company='FLAG',
            amount=Decimal('5000.00'),
            payment_method='UPI',
            created_by=self.accounts_user,
        )

        self.client.force_authenticate(user=self.accounts_user)
        gen_res = self.client.post(
            reverse('fee-receipt-from-payment', kwargs={'payment_id': payment.id}),
            {},
            format='json',
        )
        self.assertEqual(gen_res.status_code, 201)
        receipt_id = gen_res.data['id']

        self.client.force_authenticate(user=trainer_user)

        # 1. Trainer CAN VIEW generated receipt
        detail_res = self.client.get(reverse('fee-receipt-detail', kwargs={'pk': receipt_id}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(detail_res.data['recipient_name'], 'Trainer Test Student')

        # 2. Trainer CAN GET generated receipt via from-payment
        from_pay_res = self.client.get(reverse('fee-receipt-from-payment', kwargs={'payment_id': payment.id}))
        self.assertEqual(from_pay_res.status_code, 200)
        self.assertEqual(from_pay_res.data['id'], receipt_id)

        # 3. Trainer CANNOT create a new receipt
        create_res = self.client.post(
            reverse('fee-receipt-list-create'),
            {
                'company': 'FLAG',
                'recipient_name': 'Unauthorized Creation',
                'subtotal_amount': '1000.00',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 403)

        # 4. Trainer CANNOT create or update from-payment via POST
        post_from_pay = self.client.post(
            reverse('fee-receipt-from-payment', kwargs={'payment_id': payment.id}),
            {'notes': 'Unauthorized update'},
            format='json',
        )
        self.assertEqual(post_from_pay.status_code, 403)

        # 5. Trainer CANNOT edit or update receipt via PATCH
        patch_res = self.client.patch(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'recipient_name': 'Hacked Name'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, 403)

        # 6. Trainer CANNOT edit or update receipt via PUT
        put_res = self.client.put(
            reverse('fee-receipt-detail', kwargs={'pk': receipt_id}),
            {'document_type': 'PROFORMA'},
            format='json',
        )
        self.assertEqual(put_res.status_code, 403)

        # 7. Trainer CANNOT void receipt
        void_res = self.client.post(
            reverse('fee-receipt-void', kwargs={'pk': receipt_id}),
            {'void_reason': 'Trainer trying to void'},
            format='json',
        )
        self.assertEqual(void_res.status_code, 403)

        # 8. Trainer CANNOT delete receipt
        delete_res = self.client.delete(reverse('fee-receipt-detail', kwargs={'pk': receipt_id}))
        self.assertEqual(delete_res.status_code, 403)

        # 9. Trainer CANNOT update receipt settings
        settings_res = self.client.post(
            reverse('fee-receipt-settings'),
            {'company': 'FLAG', 'receipt_prefix': 'HACK'},
            format='json',
        )
        self.assertEqual(settings_res.status_code, 403)

