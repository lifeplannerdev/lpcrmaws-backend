import json
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from fees.models import FeeReceipt, ReceiptSettings, StudentFeeAccount
from fees.receipt_engine import allocate_receipt_number, verify_receipt_signature
from fds.models import FdsStudent, FdsFeesCollection, FdsFeeStructure, FdsWeddingGroup, FdsStudentFeeAccount
from trainers.models import ProcessingStudent, ProcessingFeePayment
from students.models import Student, Campus, AcademicPackage, Grade

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

        # Seed FLAG Campus, Grade, AcademicPackage, Student & StudentFeeAccount
        self.flag_grade = Grade.objects.create(code='A1', name='A1 - Beginner', order=1)
        self.flag_campus = Campus.objects.create(name='Kochi Campus', code='FLG-KOC')
        self.flag_package = AcademicPackage.objects.create(
            name='FLAG German A1 Beginner Package',
            starting_grade=self.flag_grade,
            ending_grade=self.flag_grade,
        )
        self.flag_student = Student.objects.create(
            name='Ananya Sen',
            phone='+919876500001',
            email='ananya.sen@example.com',
            campus=self.flag_campus,
            academic_package=self.flag_package,
            status='active',
        )
        self.flag_account = StudentFeeAccount.objects.create(
            student=self.flag_student,
            company='FLAG',
            total_due=Decimal('50000.00'),
            total_paid=Decimal('25000.00'),
            balance_due=Decimal('25000.00'),
            status='PARTIAL',
        )

        # Seed FDS Student Fee Account
        self.fds_account = FdsStudentFeeAccount.objects.create(
            student=self.fds_student,
            active_package=self.fds_package,
            total_due=Decimal('6000.00'),
            total_paid=Decimal('3500.00'),
            balance_due=Decimal('2500.00'),
            status='PARTIAL',
        )

    def test_compact_fy_numbering_for_fds_and_lp(self):
        """Verify CBIC Rule 46 compact FY numbering (<=16 chars) for FLAG, FDS and LP."""
        flag_num, flag_fy, flag_seq, _ = allocate_receipt_number('FLAG', issue_date=date(2026, 6, 15))
        self.assertEqual(flag_num, 'FLAG/26-27/0001')
        self.assertEqual(flag_fy, '2026-27')
        self.assertEqual(flag_seq, 1)
        self.assertLessEqual(len(flag_num), 16)

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

    def test_fee_company_registry_global_user(self):
        """User with fees:accounts can retrieve all 3 companies with complete branding/division specs."""
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-companies')
        res = self.client.get(url, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('companies', res.data)
        self.assertIn('default_company', res.data)
        self.assertEqual(res.data['default_company'], 'FLAG')

        company_codes = [c['code'] for c in res.data['companies']]
        self.assertEqual(company_codes, ['FLAG', 'FDS', 'LP'])

        flag_co = next(c for c in res.data['companies'] if c['code'] == 'FLAG')
        self.assertEqual(flag_co['name'], 'FLAG German Language Academy')
        self.assertEqual(flag_co['prefix'], 'FLAG')
        self.assertEqual(flag_co['brand_color'], '#312e81')
        self.assertIn('FLG-KOC', flag_co['divisions'])
        self.assertTrue(flag_co['is_active'])

        fds_co = next(c for c in res.data['companies'] if c['code'] == 'FDS')
        self.assertEqual(fds_co['name'], 'FILMAATIC Dance Studio')
        self.assertEqual(fds_co['prefix'], 'FDS')
        self.assertEqual(fds_co['brand_color'], '#4f46e5')
        self.assertTrue(fds_co['is_active'])

        lp_co = next(c for c in res.data['companies'] if c['code'] == 'LP')
        self.assertEqual(lp_co['name'], 'Life Planner Universal')
        self.assertEqual(lp_co['prefix'], 'LP')
        self.assertEqual(lp_co['brand_color'], '#0f766e')
        self.assertTrue(lp_co['is_active'])

    def test_fee_company_registry_denies_unauthorized_user(self):
        """User without fee permissions is denied access to company registry (403)."""
        self.client.force_authenticate(user=self.unauth_user)
        url = reverse('fee-companies')
        res = self.client.get(url, format='json')
        self.assertEqual(res.status_code, 403)

    def test_fee_company_registry_company_scoped_user(self):
        """FDS-scoped user receives only FDS in company registry."""
        self.client.force_authenticate(user=self.fds_user)
        url = reverse('fee-companies')
        res = self.client.get(url, format='json')
        self.assertEqual(res.status_code, 200)
        codes = [c['code'] for c in res.data['companies']]
        self.assertEqual(codes, ['FDS'])
        self.assertEqual(res.data['default_company'], 'FDS')

    def test_student_fees_endpoint_flag_isolation(self):
        """
        When company=FLAG, returns only FLAG students with complete isolation.
        Zero FDS or LP records, names, or IDs can bleed into the response.
        """
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-students')
        res = self.client.get(url, {'company': 'FLAG'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['company'], 'FLAG')
        self.assertGreaterEqual(res.data['count'], 1)

        names = [s['student_name'] for s in res.data['results']]
        self.assertIn('Ananya Sen', names)
        # Strict zero-bleed check
        self.assertNotIn('Aarav Menon', names)
        self.assertNotIn('Diya Nair', names)

        student_rec = next(s for s in res.data['results'] if s['student_name'] == 'Ananya Sen')
        self.assertEqual(student_rec['student_id'], f"STU-{self.flag_student.id:04d}")
        self.assertEqual(student_rec['email'], 'ananya.sen@example.com')
        self.assertEqual(student_rec['division'], 'FLG-KOC')
        self.assertEqual(student_rec['total_fee'], 50000.0)
        self.assertEqual(student_rec['total_paid'], 25000.0)
        self.assertEqual(student_rec['balance_due'], 25000.0)
        self.assertEqual(student_rec['fee_account_id'], self.flag_account.id)
        self.assertEqual(student_rec['status'], 'PARTIAL')

    def test_student_fees_endpoint_fds_isolation(self):
        """
        When company=FDS, returns only FDS students from fds.models.FdsStudent.
        Zero FLAG or LP records can bleed into the response.
        """
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-students')
        res = self.client.get(url, {'company': 'FDS'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['company'], 'FDS')
        self.assertGreaterEqual(res.data['count'], 1)

        names = [s['student_name'] for s in res.data['results']]
        self.assertIn('Aarav Menon', names)
        # Strict zero-bleed check
        self.assertNotIn('Ananya Sen', names)
        self.assertNotIn('Diya Nair', names)

        student_rec = next(s for s in res.data['results'] if s['student_name'] == 'Aarav Menon')
        self.assertEqual(student_rec['student_id'], 'FDS-STU-001')
        self.assertEqual(student_rec['phone'], '+919876543210')
        self.assertEqual(student_rec['division'], 'KOTTAYAM')
        self.assertEqual(student_rec['total_fee'], 6000.0)
        self.assertEqual(student_rec['total_paid'], 3500.0)
        self.assertEqual(student_rec['balance_due'], 2500.0)
        self.assertEqual(student_rec['fee_account_id'], self.fds_account.id)
        self.assertEqual(student_rec['status'], 'PARTIAL')

    def test_student_fees_endpoint_lp_isolation(self):
        """
        CRITICAL USER DIRECTIVE:
        When company=LP, students, fee balances, and payment records MUST be
        fetched directly from trainers.models.ProcessingStudent and ProcessingFeePayment.
        Zero records, IDs, foreign keys, or references to FLAG students can appear.
        """
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-students')
        res = self.client.get(url, {'company': 'LP'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['company'], 'LP')
        self.assertGreaterEqual(res.data['count'], 1)

        names = [s['student_name'] for s in res.data['results']]
        self.assertIn('Diya Nair', names)
        # Strict zero-bleed check against FLAG and FDS
        self.assertNotIn('Ananya Sen', names)
        self.assertNotIn('Aarav Menon', names)

        student_rec = next(s for s in res.data['results'] if s['student_name'] == 'Diya Nair')
        self.assertEqual(student_rec['student_id'], f"LP-{self.processing_student.id:04d}")
        self.assertEqual(student_rec['email'], 'diya.nair@example.com')
        self.assertEqual(student_rec['phone'], '+919811223344')
        self.assertEqual(student_rec['division'], 'STUDY_ABROAD')
        # Total fee = 50,000 (processing) + 25,000 (admission) = 75,000.00
        # Total paid = 25,000.00
        # Balance due = 50,000.00
        self.assertEqual(student_rec['total_fee'], 75000.0)
        self.assertEqual(student_rec['total_paid'], 25000.0)
        self.assertEqual(student_rec['balance_due'], 50000.0)
        self.assertIsNone(student_rec['fee_account_id'])
        self.assertEqual(student_rec['status'], 'PARTIAL')

    def test_student_fees_search_filter(self):
        """Search query filters results within the selected company domain."""
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-students')

        # 1. Search matching Diya in LP
        res_diya = self.client.get(url, {'company': 'LP', 'search': 'Diya'}, format='json')
        self.assertEqual(res_diya.status_code, 200)
        self.assertEqual(res_diya.data['count'], 1)
        self.assertEqual(res_diya.data['results'][0]['student_name'], 'Diya Nair')

        # 2. Search non-matching in LP
        res_none = self.client.get(url, {'company': 'LP', 'search': 'NonExistentXYZ'}, format='json')
        self.assertEqual(res_none.status_code, 200)
        self.assertEqual(res_none.data['count'], 0)

        # 3. Search matching phone in FDS
        res_fds_phone = self.client.get(url, {'company': 'FDS', 'search': '9876543210'}, format='json')
        self.assertEqual(res_fds_phone.status_code, 200)
        self.assertEqual(res_fds_phone.data['count'], 1)
        self.assertEqual(res_fds_phone.data['results'][0]['student_name'], 'Aarav Menon')

    def test_student_fees_permission_enforcement(self):
        """Verify role-based access control and company authorization on /api/fees/students/."""
        url = reverse('fee-students')

        # 1. Unauthorized user denied on all companies
        self.client.force_authenticate(user=self.unauth_user)
        self.assertEqual(self.client.get(url, {'company': 'FLAG'}).status_code, 403)
        self.assertEqual(self.client.get(url, {'company': 'FDS'}).status_code, 403)
        self.assertEqual(self.client.get(url, {'company': 'LP'}).status_code, 403)

        # 2. FDS fee user allowed on FDS, denied on FLAG and LP
        self.client.force_authenticate(user=self.fds_user)
        self.assertEqual(self.client.get(url, {'company': 'FDS'}).status_code, 200)
        self.assertEqual(self.client.get(url, {'company': 'FLAG'}).status_code, 403)
        self.assertEqual(self.client.get(url, {'company': 'LP'}).status_code, 403)

        # 3. LP fee user allowed on LP, denied on FLAG and FDS
        self.client.force_authenticate(user=self.lp_user)
        self.assertEqual(self.client.get(url, {'company': 'LP'}).status_code, 200)
        self.assertEqual(self.client.get(url, {'company': 'FLAG'}).status_code, 403)
        self.assertEqual(self.client.get(url, {'company': 'FDS'}).status_code, 403)

    def test_student_fees_invalid_company_rejected(self):
        """Invalid company code returns 400 Bad Request."""
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-students')
        res = self.client.get(url, {'company': 'INVALID_CO'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid company', res.data['detail'])

    def test_student_fees_legacy_pending_only_fallback(self):
        """When pending_only is passed without company, retains legacy list format."""
        self.client.force_authenticate(user=self.global_user)
        url = reverse('fee-students')
        res = self.client.get(url, {'pending_only': 'true'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, list)

    def test_student_fees_latest_receipt_isolation(self):
        """Verify latest receipt numbers are populated accurately per company without cross-company leakage."""
        self.client.force_authenticate(user=self.global_user)

        # Issue an explicit LP receipt
        FeeReceipt.objects.create(
            company='LP',
            processing_student=self.processing_student,
            processing_payment=self.processing_payment,
            receipt_number='LP/26-27/0099',
            total_amount=Decimal('25000.00'),
            recipient_name='Diya Nair',
            financial_year='2026-27',
            status='ISSUED',
        )

        # Issue an explicit FLAG receipt
        FeeReceipt.objects.create(
            company='FLAG',
            student=self.flag_student,
            account=self.flag_account,
            receipt_number='FLAG/26-27/0088',
            total_amount=Decimal('25000.00'),
            recipient_name='Ananya Sen',
            financial_year='2026-27',
            status='ISSUED',
        )

        url = reverse('fee-students')

        # Check LP endpoint returns LP/26-27/0099 for Diya Nair
        res_lp = self.client.get(url, {'company': 'LP'}, format='json')
        diya_rec = next(s for s in res_lp.data['results'] if s['student_name'] == 'Diya Nair')
        self.assertEqual(diya_rec['latest_receipt_number'], 'LP/26-27/0099')

        # Check FLAG endpoint returns FLAG/26-27/0088 for Ananya Sen
        res_flag = self.client.get(url, {'company': 'FLAG'}, format='json')
        ananya_rec = next(s for s in res_flag.data['results'] if s['student_name'] == 'Ananya Sen')
        self.assertEqual(ananya_rec['latest_receipt_number'], 'FLAG/26-27/0088')

        # Check FDS endpoint does not leak either receipt
        res_fds = self.client.get(url, {'company': 'FDS'}, format='json')
        aarav_rec = next(s for s in res_fds.data['results'] if s['student_name'] == 'Aarav Menon')
        self.assertNotEqual(aarav_rec['latest_receipt_number'], 'LP/26-27/0099')
        self.assertNotEqual(aarav_rec['latest_receipt_number'], 'FLAG/26-27/0088')
