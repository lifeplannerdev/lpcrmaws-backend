"""
Empirical Challenger Test Suite: Multi-Company Fees Access Control & Zero Data Bleed
Stress-testing access control enforcement, parameter tampering, and cross-company isolation
across FLAG, FDS, and LP domains.
"""

from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from fees.models import FeeReceipt, ReceiptSettings, StudentFeeAccount
from fds.models import FdsStudent, FdsFeesCollection, FdsFeeStructure, FdsStudentFeeAccount
from trainers.models import ProcessingStudent, ProcessingFeePayment
from students.models import Student, Campus, AcademicPackage, Grade

User = get_user_model()


class AdversarialMultiCompanyFeeIsolationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Accounts global user
        cls.global_user = User.objects.create_user(
            username='challenger-global-acct',
            password='Password123!',
            company='FLAG',
            permissions=['fees:accounts'],
        )

        # 2. Company-scoped users
        cls.fds_user = User.objects.create_user(
            username='challenger-fds-user',
            password='Password123!',
            company='FDS',
            permissions=['fees:fds'],
        )
        cls.lp_user = User.objects.create_user(
            username='challenger-lp-user',
            password='Password123!',
            company='LP',
            permissions=['fees:lp'],
        )
        cls.flag_user = User.objects.create_user(
            username='challenger-flag-user',
            password='Password123!',
            company='FLAG',
            permissions=['fees:flag'],
        )

        # 3. Unauthorized users
        cls.unauth_user = User.objects.create_user(
            username='challenger-unauth-user',
            password='Password123!',
            company='FLAG',
            permissions=[],
        )
        cls.unrelated_perm_user = User.objects.create_user(
            username='challenger-unrelated-user',
            password='Password123!',
            company='LP',
            permissions=['leads:read_own', 'tasks:read_own'],
        )

        # 4. Seed FLAG Students and Accounts
        cls.campus = Campus.objects.create(name='Ernakulam Hub', code='FLG-EKM')
        cls.grade = Grade.objects.create(code='B1', name='B1 Level', order=2)
        cls.pkg = AcademicPackage.objects.create(
            name='FLAG German B1 Mastery',
            starting_grade=cls.grade,
            ending_grade=cls.grade,
        )

        cls.flag_students = []
        for i in range(3):
            s = Student.objects.create(
                name=f'FLAG Student Alpha {i+1}',
                phone=f'+91980000000{i}',
                email=f'flag.student{i+1}@flagacademy.test',
                campus=cls.campus,
                academic_package=cls.pkg,
                status='active',
            )
            StudentFeeAccount.objects.create(
                student=s,
                company='FLAG',
                total_due=Decimal('45000.00'),
                total_paid=Decimal('20000.00'),
                balance_due=Decimal('25000.00'),
                status='PARTIAL',
            )
            cls.flag_students.append(s)

        # 5. Seed FDS Students and Accounts
        cls.fds_pkg = FdsFeeStructure.objects.create(
            name='Contemporary Intensive 6 Months',
            category='DANCE',
            admission_fee=Decimal('1500.00'),
            amount=Decimal('12000.00'),
            duration_months=6,
        )
        cls.fds_students = []
        for i in range(3):
            fs = FdsStudent.objects.create(
                student_id=f'FDS-2026-{i+1:03d}',
                name=f'FDS Dancer Beta {i+1}',
                branch='Kochi',
                contact_no=f'+91981111111{i}',
                fee_structure=cls.fds_pkg,
                is_active=True,
            )
            FdsStudentFeeAccount.objects.create(
                student=fs,
                active_package=cls.fds_pkg,
                total_due=Decimal('13500.00'),
                total_paid=Decimal('5000.00'),
                balance_due=Decimal('8500.00'),
                status='PARTIAL',
            )
            cls.fds_students.append(fs)

        # 6. Seed LP Processing Students and Payments
        cls.lp_students = []
        cls.lp_payments = []
        for i in range(3):
            ps = ProcessingStudent.objects.create(
                name=f'LP Scholar Gamma {i+1}',
                mobile_number=f'+91982222222{i}',
                email=f'lp.scholar{i+1}@lifeplanner.test',
                category='Study Abroad',
                program_applied='Masters in Robotics (TUM)',
                processing_fee_applicable=True,
                processing_fee_amount=Decimal('60000.00'),
                processing_fee_paid=Decimal('0.00'),
                fee_admission_applicable=True,
                fee_admission_amount=Decimal('30000.00'),
                fee_admission_paid=Decimal('0.00'),
            )
            pay = ProcessingFeePayment.objects.create(
                student=ps,
                fee_head='PROCESSING',
                amount=Decimal('30000.00'),
                payment_method='BANK_TRANSFER',
                reference=f'TXN-LP-ADV-{i+1}',
            )
            cls.lp_students.append(ps)
            cls.lp_payments.append(pay)

    # ── Section 1: Access Control Adversarial Enforcement ─────────────────────

    def test_unauthenticated_requests_strictly_rejected_401(self):
        """Unauthenticated requests must be rejected with 401 across multicompany endpoints."""
        self.client.force_authenticate(user=None)

        # 1. Company registry
        res_comp = self.client.get(reverse('fee-companies'))
        self.assertEqual(res_comp.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Multi-company student fees with company parameters
        res_flag = self.client.get(reverse('fee-students'), {'company': 'FLAG'})
        self.assertEqual(res_flag.status_code, status.HTTP_401_UNAUTHORIZED)

        res_fds = self.client.get(reverse('fee-students'), {'company': 'FDS'})
        self.assertEqual(res_fds.status_code, status.HTTP_401_UNAUTHORIZED)

        res_lp = self.client.get(reverse('fee-students'), {'company': 'LP'})
        self.assertEqual(res_lp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unrelated_permission_user_strictly_rejected_403(self):
        """Authenticated user without fee permissions must be rejected with 403."""
        self.client.force_authenticate(user=self.unrelated_perm_user)

        res_comp = self.client.get(reverse('fee-companies'))
        self.assertEqual(res_comp.status_code, status.HTTP_403_FORBIDDEN)

        for co in ('FLAG', 'FDS', 'LP'):
            res = self.client.get(reverse('fee-students'), {'company': co})
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_company_scoped_privilege_isolation(self):
        """
        Company-scoped user is strictly forbidden from querying other company datasets.
        """
        # LP fee user can ONLY access LP
        self.client.force_authenticate(user=self.lp_user)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'LP'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'FLAG'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'FDS'}).status_code, 403)

        # FDS fee user can ONLY access FDS
        self.client.force_authenticate(user=self.fds_user)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'FDS'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'FLAG'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'LP'}).status_code, 403)

        # FLAG fee user can ONLY access FLAG
        self.client.force_authenticate(user=self.flag_user)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'FLAG'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'FDS'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('fee-students'), {'company': 'LP'}).status_code, 403)

    # ── Section 2: Strict Cross-Company Data Isolation & Zero Bleed ───────────

    def test_lp_100_percent_isolated_from_flag_and_fds(self):
        """
        CRITICAL USER DIRECTIVE:
        When company=LP:
        - 100% of student fee records MUST be sourced from ProcessingStudent & ProcessingFeePayment.
        - ZERO records, IDs, foreign keys, or references to FLAG or FDS students appear.
        """
        self.client.force_authenticate(user=self.global_user)
        res = self.client.get(reverse('fee-students'), {'company': 'LP'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['company'], 'LP')

        results = res.data['results']
        lp_names = {ps.name for ps in self.lp_students}
        flag_names = {s.name for s in self.flag_students}
        fds_names = {fs.name for fs in self.fds_students}

        # Check all returned students
        returned_names = [r['student_name'] for r in results]
        self.assertTrue(all(name in lp_names for name in returned_names), "Non-LP student leaked into LP dataset!")

        # Absolute zero bleed check
        for name in returned_names:
            self.assertNotIn(name, flag_names, f"FLAG student {name} leaked into LP results!")
            self.assertNotIn(name, fds_names, f"FDS student {name} leaked into LP results!")

        for r in results:
            self.assertTrue(r['student_id'].startswith('LP-'), f"Invalid LP student_id format: {r['student_id']}")
            self.assertEqual(r['division'], 'Study Abroad')
            self.assertEqual(r['total_fee'], 90000.0) # 60k processing + 30k admission
            self.assertEqual(r['total_paid'], 30000.0)
            self.assertEqual(r['balance_due'], 60000.0)
            self.assertIsNone(r['fee_account_id']) # LP does NOT use StudentFeeAccount

    def test_fds_100_percent_isolated_from_flag_and_lp(self):
        """
        When company=FDS:
        - 100% of student fee records MUST be sourced from FdsStudent & FDS models.
        - ZERO FLAG or LP student records appear.
        """
        self.client.force_authenticate(user=self.global_user)
        res = self.client.get(reverse('fee-students'), {'company': 'FDS'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['company'], 'FDS')

        results = res.data['results']
        fds_names = {fs.name for fs in self.fds_students}
        flag_names = {s.name for s in self.flag_students}
        lp_names = {ps.name for ps in self.lp_students}

        returned_names = [r['student_name'] for r in results]
        self.assertTrue(all(name in fds_names for name in returned_names), "Non-FDS student leaked into FDS dataset!")

        for name in returned_names:
            self.assertNotIn(name, flag_names, f"FLAG student {name} leaked into FDS results!")
            self.assertNotIn(name, lp_names, f"LP student {name} leaked into FDS results!")

        for r in results:
            self.assertTrue(r['student_id'].startswith('FDS-'), f"Invalid FDS student_id format: {r['student_id']}")
            self.assertEqual(r['division'], 'Kochi')

    def test_flag_100_percent_isolated_from_fds_and_lp(self):
        """
        When company=FLAG:
        - 100% of student fee records MUST be sourced from Student & StudentFeeAccount.
        - ZERO FDS or LP student records appear.
        """
        self.client.force_authenticate(user=self.global_user)
        res = self.client.get(reverse('fee-students'), {'company': 'FLAG'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['company'], 'FLAG')

        results = res.data['results']
        flag_names = {s.name for s in self.flag_students}
        fds_names = {fs.name for fs in self.fds_students}
        lp_names = {ps.name for ps in self.lp_students}

        returned_names = [r['student_name'] for r in results]
        self.assertTrue(all(name in flag_names for name in returned_names), "Non-FLAG student leaked into FLAG dataset!")

        for name in returned_names:
            self.assertNotIn(name, fds_names, f"FDS student {name} leaked into FLAG results!")
            self.assertNotIn(name, lp_names, f"LP student {name} leaked into FLAG results!")

        for r in results:
            self.assertTrue(r['student_id'].startswith('STU-'), f"Invalid FLAG student_id format: {r['student_id']}")
            self.assertEqual(r['division'], 'FLG-EKM')

    # ── Section 3: Adversarial Inputs & Parameter Tampering ───────────────────

    def test_casing_and_whitespace_tolerance(self):
        """Case insensitivity and whitespace stripping on company parameter."""
        self.client.force_authenticate(user=self.global_user)

        for param in ('lp', 'Lp', ' LP ', '  lp  '):
            res = self.client.get(reverse('fee-students'), {'company': param})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data['company'], 'LP')
            self.assertEqual(res.data['count'], 3)

        for param in ('fds', 'Fds', ' FDS '):
            res = self.client.get(reverse('fee-students'), {'company': param})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data['company'], 'FDS')
            self.assertEqual(res.data['count'], 3)

        for param in ('flag', 'Flag', ' FLAG '):
            res = self.client.get(reverse('fee-students'), {'company': param})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data['company'], 'FLAG')
            self.assertEqual(res.data['count'], 3)

    def test_adversarial_company_codes_rejected(self):
        """Adversarial, injection, and invalid company codes must return 400 Bad Request."""
        self.client.force_authenticate(user=self.global_user)

        adversarial_payloads = [
            'UNKNOWN',
            'HACK',
            "LP' OR '1'='1",
            "FLAG; DROP TABLE fees_feereceipt;--",
            "../FLAG",
            "<script>alert(1)</script>",
            "null",
            "12345",
        ]

        for payload in adversarial_payloads:
            res = self.client.get(reverse('fee-students'), {'company': payload})
            self.assertEqual(
                res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Payload '{payload}' was not rejected with 400! Got {res.status_code}",
            )
            self.assertIn('Invalid company', res.data.get('detail', ''))

    def test_search_isolation_and_sql_injection_resistance(self):
        """Adversarial search queries do not cause 500 crashes or cross-domain leaks."""
        self.client.force_authenticate(user=self.global_user)

        # 1. Searching for 'FLAG' under company=LP must return 0 records (no cross leak)
        res_cross = self.client.get(reverse('fee-students'), {'company': 'LP', 'search': 'FLAG'})
        self.assertEqual(res_cross.status_code, 200)
        self.assertEqual(res_cross.data['count'], 0)

        # 2. Searching for 'LP' under company=FLAG must return 0 records
        res_cross_flag = self.client.get(reverse('fee-students'), {'company': 'FLAG', 'search': 'LP Scholar'})
        self.assertEqual(res_cross_flag.status_code, 200)
        self.assertEqual(res_cross_flag.data['count'], 0)

        # 3. SQL injection pattern in search parameter
        injection_queries = [
            "' OR 1=1 --",
            "admin'--",
            "UNION SELECT * FROM accounts_user--",
            "<svg onload=alert(document.cookie)>",
        ]
        for query in injection_queries:
            res_inj = self.client.get(reverse('fee-students'), {'company': 'LP', 'search': query})
            self.assertEqual(res_inj.status_code, 200)
            self.assertEqual(res_inj.data['count'], 0)

    # ── Section 4: Cross-Company Receipt Tampering Attacks ─────────────────────

    def test_cross_company_receipt_endpoint_tampering(self):
        """Cannot generate an LP receipt from an FDS payment or vice versa."""
        self.client.force_authenticate(user=self.global_user)

        # Passing an LP payment ID to FDS receipt endpoint
        lp_payment_id = self.lp_payments[0].id
        url_fds = reverse('fee-receipt-from-fds-payment', kwargs={'payment_id': lp_payment_id})
        res_tamper_fds = self.client.post(url_fds, {}, format='json')
        # Expect 404 because FdsFeesCollection does not have this payment id
        self.assertEqual(res_tamper_fds.status_code, status.HTTP_404_NOT_FOUND)

        # Passing an invalid ID to LP receipt endpoint
        url_lp = reverse('fee-receipt-from-processing-payment', kwargs={'payment_id': 999999})
        res_tamper_lp = self.client.post(url_lp, {}, format='json')
        self.assertEqual(res_tamper_lp.status_code, status.HTTP_404_NOT_FOUND)
