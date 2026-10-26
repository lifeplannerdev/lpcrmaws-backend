import json
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from fees.models import FeeReceipt, ReceiptSettings
from fees.receipt_engine import allocate_receipt_number, verify_receipt_signature
from fds.models import FdsStudent, FdsFeesCollection, FdsFeeStructure, FdsWeddingGroup
from trainers.models import ProcessingStudent, ProcessingFeePayment

User = get_user_model()


class MultiCompanyFeePermissionsAndReceiptTests(APITestCase):
    def setUp(self):
        # 1. Accounts user with global multi-company fee permissions
        self.global_user = User.objects.create_user(
            username='global-accounts-user',
            password='Password123!',
            company='FLAG',
            permissions=['fees:accounts'],
        )

        # 2. FDS-only fee manager
        self.fds_user = User.objects.create_user(
            username='fds-fee-user',
            password='Password123!',
            company='FDS',
            permissions=['fees:fds'],
        )

        # 3. LP-only fee manager
        self.lp_user = User.objects.create_user(
            username='lp-fee-user',
            password='Password123!',
            company='LP',
            permissions=['fees:lp'],
        )

        # 4. FLAG-only fee manager
        self.flag_user = User.objects.create_user(
            username='flag-fee-user',
            password='Password123!',
            company='FLAG',
            permissions=['fees:flag'],
        )

        # 5. User without fee permissions
        self.unauth_user = User.objects.create_user(
            username='unauthorized-user',
            password='Password123!',
            company='FLAG',
            permissions=[],
        )

        # 6. Processing counselor who can edit students, but lacks any fee permissions
        self.counselor_user = User.objects.create_user(
            username='counselor-user',
            password='Password123!',
            company='LP',
            permissions=['processing_students:edit_any', 'processing_students:read_any'],
        )

        # Seed FDS data
        self.fds_package = FdsFeeStructure.objects.create(
            name='Bollywood Dance 3 Months',
            category='DANCE',
            admission_fee=Decimal('1000.00'),
            amount=Decimal('6000.00'),
            duration_months=3,
        )
        self.fds_student = FdsStudent.objects.create(
            student_id='FDS-STU-001',
            name='Aarav Menon',
            branch='KOTTAYAM',
            contact_no='+919876543210',
            fee_structure=self.fds_package,
        )
        self.fds_payment = FdsFeesCollection.objects.create(
            student=self.fds_student,
            fees_type=self.fds_package,
            paid_amount=Decimal('3500.00'),
            total_fees=Decimal('6000.00'),
            balance=Decimal('2500.00'),
            mode_of_pay='UPI',
            status='PAID',
            pay_date=date.today(),
            remarks='First month fee payment',
        )

        # Seed FDS Wedding Group & Payment
        self.wedding_group = FdsWeddingGroup.objects.create(
            event_name='Rahul & Sneha Sangeet',
            lead_contact_name='Rahul Sharma',
            lead_contact_phone='+919845012345',
            package_type='BASIC',
            fee_amount=Decimal('25000.00'),
            amount_paid=Decimal('10000.00'),
            status='CONFIRMED',
        )
        self.wedding_payment = FdsFeesCollection.objects.create(
            wedding_group=self.wedding_group,
            fees_type=self.fds_package,
            paid_amount=Decimal('10000.00'),
            total_fees=Decimal('25000.00'),
            balance=Decimal('15000.00'),
            mode_of_pay='BANK_TRANSFER',
            status='PAID',
            pay_date=date.today(),
            remarks='NEFT-WED-1234',
        )

        # Seed LP Processing Student
        self.processing_student = ProcessingStudent.objects.create(
            name='Diya Nair',
            mobile_number='+919811223344',
            email='diya.nair@example.com',
            category='STUDY_ABROAD',
            program_applied='German Masters Direct Entry',
            processing_fee_applicable=True,
            processing_fee_amount=Decimal('50000.00'),
            processing_fee_paid=Decimal('0.00'),
            fee_admission_applicable=True,
            fee_admission_amount=Decimal('25000.00'),
            fee_admission_paid=Decimal('0.00'),
        )
        self.processing_payment = ProcessingFeePayment.objects.create(
            student=self.processing_student,
            fee_head='PROCESSING',
            amount=Decimal('25000.00'),
            payment_method='ONLINE',
            reference='TXN-PROC-5544',
            notes='Initial 50% application advance',
        )

    def test_compact_fy_numbering_for_fds_and_lp(self):
        """Verify CBIC Rule 46 compact FY numbering (<=16 chars) for FDS and LP."""
        fds_num, fds_fy, fds_seq, _ = allocate_receipt_number('FDS', issue_date=date(2026, 6, 15))
        self.assertEqual(fds_num, 'FDS/26-27/0001')
        self.assertEqual(fds_fy, '2026-27')
        self.assertEqual(fds_seq, 1)
        self.assertLessEqual(len(fds_num), 16)

        lp_num, lp_fy, lp_seq, _ = allocate_receipt_number('LP', issue_date=date(2026, 6, 15))
        self.assertEqual(lp_num, 'LP/26-27/0001')
        self.assertEqual(lp_fy, '2026-27')
        self.assertEqual(lp_seq, 1)
        self.assertLessEqual(len(lp_num), 16)

    def test_global_user_can_access_all_companies(self):
        """User with fees:accounts can view and manage receipts across FLAG, FDS, and LP."""
        self.client.force_authenticate(user=self.global_user)

        # Create FDS Receipt via from-fds-payment
        url = reverse('fee-receipt-from-fds-payment', kwargs={'payment_id': self.fds_payment.id})
        res = self.client.post(url, {}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['company'], 'FDS')
        self.assertEqual(res.data['recipient_name'], 'Aarav Menon')
        self.assertEqual(str(res.data['total_amount']), '3500.00')
        self.assertTrue(res.data['receipt_number'].startswith('FDS/26-27/'))
        self.assertIsNotNone(res.data['verification_token'])

        # Create LP Receipt via from-processing-payment
        url_lp = reverse('fee-receipt-from-processing-payment', kwargs={'payment_id': self.processing_payment.id})
        res_lp = self.client.post(url_lp, {}, format='json')
        self.assertEqual(res_lp.status_code, 201)
        self.assertEqual(res_lp.data['company'], 'LP')
        self.assertEqual(res_lp.data['recipient_name'], 'Diya Nair')
        self.assertEqual(str(res_lp.data['total_amount']), '25000.00')
        self.assertTrue(res_lp.data['receipt_number'].startswith('LP/26-27/'))

    def test_company_scoped_permissions_enforcement(self):
        """Verify that company-specific permissions isolate fee access properly."""
        # 1. FDS user trying to access LP receipt endpoint -> 403
        self.client.force_authenticate(user=self.fds_user)
        url_lp = reverse('fee-receipt-from-processing-payment', kwargs={'payment_id': self.processing_payment.id})
        res = self.client.post(url_lp, {}, format='json')
        self.assertEqual(res.status_code, 403)

        # 2. FDS user can access FDS receipt endpoint -> 201
        url_fds = reverse('fee-receipt-from-fds-payment', kwargs={'payment_id': self.fds_payment.id})
        res_fds = self.client.post(url_fds, {}, format='json')
        self.assertEqual(res_fds.status_code, 201)

        # 3. LP user trying to access FDS receipt endpoint -> 403
        self.client.force_authenticate(user=self.lp_user)
        res_fds_forbidden = self.client.post(url_fds, {}, format='json')
        self.assertEqual(res_fds_forbidden.status_code, 403)

        # 4. LP user can access LP receipt endpoint -> 201
        res_lp = self.client.post(url_lp, {}, format='json')
        self.assertEqual(res_lp.status_code, 201)

        # 5. Unauthorized user cannot access any
        self.client.force_authenticate(user=self.unauth_user)
        self.assertEqual(self.client.post(url_fds, {}, format='json').status_code, 403)
        self.assertEqual(self.client.post(url_lp, {}, format='json').status_code, 403)

    def test_public_verification_sanitization(self):
        """Public verification endpoint verifies authentic tokens and strips sensitive bank/sig details."""
        self.client.force_authenticate(user=self.global_user)
        url_fds = reverse('fee-receipt-from-fds-payment', kwargs={'payment_id': self.fds_payment.id})
        create_res = self.client.post(url_fds, {}, format='json')
        self.assertEqual(create_res.status_code, 201)
        token = create_res.data['verification_token']

        # Ensure settings have bank details to verify masking
        settings_obj = ReceiptSettings.objects.get(company='FDS', campus__isnull=True)
        settings_obj.account_number = '123456789012'
        settings_obj.bank_name = 'HDFC Bank'
        settings_obj.save()

        # Update receipt snapshot
        receipt = FeeReceipt.objects.get(verification_token=token)
        receipt.issuer_snapshot['account_number'] = '123456789012'
        receipt.issuer_snapshot['signature_image'] = 'data:image/png;base64,SECRET'
        receipt.save()

        self.client.force_authenticate(user=None)
        verify_url = reverse('fee-receipt-verify', kwargs={'verification_token': token})
        verify_res = self.client.get(verify_url)
        self.assertEqual(verify_res.status_code, 200)
        self.assertTrue(verify_res.data['verified'])
        self.assertTrue(verify_res.data['is_authentic'])
        self.assertEqual(verify_res.data['verification_status'], 'VALID')
        self.assertEqual(verify_res.data['issued_by_name'], 'FDS Accounts Department')

        # Check bank account masking
        issuer_snap = verify_res.data['issuer_snapshot']
        self.assertEqual(issuer_snap.get('account_number'), 'XXXXXXXX9012')
        self.assertNotIn('signature_image', issuer_snap)

    def test_processing_fee_payment_syncs_student_totals(self):
        """Adding/deleting a ProcessingFeePayment auto-recalculates ProcessingStudent totals."""
        self.client.force_authenticate(user=self.lp_user)

        self.processing_student.refresh_from_db()
        self.assertEqual(self.processing_student.processing_fee_paid, Decimal('25000.00'))
        self.assertEqual(self.processing_student.processing_fee_status, 'PARTIAL')

        # Add second payment to complete processing fee
        payment_url = reverse('processing-student-payments', kwargs={'student_pk': self.processing_student.id})
        res = self.client.post(
            payment_url,
            {
                'fee_head': 'PROCESSING',
                'amount': '25000.00',
                'payment_method': 'UPI',
                'reference': 'TXN-PROC-5545',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)

        self.processing_student.refresh_from_db()
        self.assertEqual(self.processing_student.processing_fee_paid, Decimal('50000.00'))
        self.assertEqual(self.processing_student.processing_fee_status, 'PAID')

        # Delete payment and verify reversion
        del_url = reverse('processing-student-payment-detail', kwargs={'pk': res.data['id']})
        del_res = self.client.delete(del_url)
        self.assertEqual(del_res.status_code, 204)

        self.processing_student.refresh_from_db()
        self.assertEqual(self.processing_student.processing_fee_paid, Decimal('25000.00'))
        self.assertEqual(self.processing_student.processing_fee_status, 'PARTIAL')

    def test_document_immutability_on_issued_receipt(self):
        """Once a receipt is ISSUED, core financial and identity fields are locked against modification."""
        self.client.force_authenticate(user=self.global_user)
        # 1. Create an ISSUED receipt
        url_fds = reverse('fee-receipt-from-fds-payment', kwargs={'payment_id': self.fds_payment.id})
        res = self.client.post(url_fds, {}, format='json')
        self.assertEqual(res.status_code, 201)
        receipt_id = res.data['id']
        receipt = FeeReceipt.objects.get(id=receipt_id)
        self.assertEqual(receipt.status, 'ISSUED')

        # 2. Attempt to modify total_amount on ISSUED receipt -> 400 with immutability error
        detail_url = reverse('fee-receipt-detail', kwargs={'pk': receipt_id})
        patch_res = self.client.patch(detail_url, {'total_amount': '9999.00'}, format='json')
        self.assertEqual(patch_res.status_code, 400)
        self.assertIn('total_amount', patch_res.data)
        self.assertIn('Document immutability', str(patch_res.data['total_amount'][0]))

        # 3. Attempt to modify recipient_name on ISSUED receipt -> 400 with immutability error
        patch_res_name = self.client.patch(detail_url, {'recipient_name': 'Changed Name'}, format='json')
        self.assertEqual(patch_res_name.status_code, 400)
        self.assertIn('recipient_name', patch_res_name.data)
        self.assertIn('Document immutability', str(patch_res_name.data['recipient_name'][0]))

        # 4. Modifying notes or remarks does not violate immutability
        patch_res_notes = self.client.patch(detail_url, {'notes': 'Updated internal note'}, format='json')
        self.assertEqual(patch_res_notes.status_code, 200)
        receipt.refresh_from_db()
        self.assertEqual(receipt.notes, 'Updated internal note')

    def test_from_payment_preview_does_not_create_db_receipt(self):
        """GET /from-*-payment/<id>/?preview=true returns preview without inserting FeeReceipt into DB."""
        self.client.force_authenticate(user=self.fds_user)
        # Ensure no receipt exists for fds_payment yet
        FeeReceipt.objects.filter(fds_payment=self.fds_payment).delete()
        self.assertEqual(FeeReceipt.objects.filter(fds_payment=self.fds_payment).count(), 0)

        preview_url = f"{reverse('fee-receipt-from-fds-payment', kwargs={'payment_id': self.fds_payment.id})}?preview=true"
        res = self.client.get(preview_url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get('is_preview'))
        self.assertIsNone(res.data.get('id'))
        self.assertEqual(res.data.get('company'), 'FDS')
        # Database count must still be 0!
        self.assertEqual(FeeReceipt.objects.filter(fds_payment=self.fds_payment).count(), 0)

        # Same for LP
        self.client.force_authenticate(user=self.lp_user)
        FeeReceipt.objects.filter(processing_payment=self.processing_payment).delete()
        self.assertEqual(FeeReceipt.objects.filter(processing_payment=self.processing_payment).count(), 0)

        lp_preview_url = f"{reverse('fee-receipt-from-processing-payment', kwargs={'payment_id': self.processing_payment.id})}?preview=true"
        res_lp = self.client.get(lp_preview_url)
        self.assertEqual(res_lp.status_code, 200)
        self.assertTrue(res_lp.data.get('is_preview'))
        self.assertIsNone(res_lp.data.get('id'))
        self.assertEqual(res_lp.data.get('company'), 'LP')
        # Database count must still be 0!
        self.assertEqual(FeeReceipt.objects.filter(processing_payment=self.processing_payment).count(), 0)

    def test_processing_student_unauthorized_fee_modification_rejected(self):
        """Unauthorized user attempting to create or patch fee fields on ProcessingStudent is rejected with 400."""
        self.client.force_authenticate(user=self.counselor_user)

        # 1. Patching fee fields as unauthorized user -> 400
        detail_url = reverse('processing-student-detail', kwargs={'pk': self.processing_student.id})
        patch_res = self.client.patch(
            detail_url,
            {'processing_fee_amount': '99999.00'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, 400)
        self.assertIn('fee_fields', patch_res.data)
        self.assertIn('Permission denied', str(patch_res.data['fee_fields']))

        # 2. Creating student with fee fields as unauthorized user -> 400
        list_url = reverse('processing-student-list-create')
        create_res = self.client.post(
            list_url,
            {
                'name': 'Hacker Student',
                'mobile_number': '+919999988888',
                'category': 'STUDY_ABROAD',
                'program_applied': 'Bachelors',
                'processing_fee_applicable': True,
                'processing_fee_amount': '60000.00',
            },
            format='json',
        )
        self.assertEqual(create_res.status_code, 400)
        self.assertIn('fee_fields', create_res.data)

        # 3. LP fee user can modify fee fields -> 200
        self.client.force_authenticate(user=self.lp_user)
        patch_ok = self.client.patch(
            detail_url,
            {'processing_fee_amount': '55000.00'},
            format='json',
        )
        self.assertEqual(patch_ok.status_code, 200)
        self.processing_student.refresh_from_db()
        self.assertEqual(self.processing_student.processing_fee_amount, Decimal('55000.00'))
