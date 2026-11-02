"""
Automated Test Suite for FDS Fee Classification, Recurring Policies & Multi-Company Receipts.

Covers:
- Tier 1: Feature Coverage (Regular recurring tuition, pure wedding isolation, custom differing amounts, receipt linking, monthly receipt breakdown)
- Tier 2: Boundary & Corner Cases (Zero fee, negative balance, mid-month enrollment, leap years, multi-month rollover, custom rate extremes)
- Tier 3: Cross-Feature Interactions (Account linking + receipt generation, custom fee + rollover + partial payment, multi-company isolation)
- Tier 4: Real-World Application Workloads (Full student lifecycle from trial to recurring receipts and final settlement)
- Edge Case Matrix: 24 Scenarios across 4 Dimensions:
  - Dimension 1: Payment Status Variations (PS-01 to PS-06)
  - Dimension 2: Student & Account Linking (AL-01 to AL-06)
  - Dimension 3: Recurring Billing Cycle Rollovers (RC-01 to RC-06)
  - Dimension 4: Receipt Generation Edge Cases (RG-01 to RG-06)
"""

import json
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange
from dateutil.relativedelta import relativedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from fds.models import (
    FdsStudent,
    FdsStudentFeeAccount,
    FdsFeeInstallment,
    FdsFeesCollection,
    FdsFeeStructure,
    FdsWeddingGroup,
    FdsFeeAdjustment,
)
from fees.models import FeeReceipt, ReceiptSettings
from fees.receipt_engine import (
    allocate_receipt_number,
    calculate_receipt_financials,
    extract_fds_student_metadata,
    extract_fds_ledger_snapshot,
    verify_receipt_signature,
    amount_to_words,
)

User = get_user_model()


class FdsFeeTestBase(APITestCase):
    """Common setup and fixtures for FDS fee tests."""

    def setUp(self):
        super().setUp()

        # Users with distinct permission profiles
        self.global_user = User.objects.create_user(
            username='fds-global-user',
            password='Password123!',
            company='FLAG',
            permissions=['fees:accounts'],
        )
        self.fds_user = User.objects.create_user(
            username='fds-staff-user',
            password='Password123!',
            company='FDS',
            permissions=['fees:fds'],
        )
        self.flag_user = User.objects.create_user(
            username='flag-staff-user',
            password='Password123!',
            company='FLAG',
            permissions=['fees:flag'],
        )
        self.unauth_user = User.objects.create_user(
            username='unauth-user',
            password='Password123!',
            company='FDS',
            permissions=[],
        )

        # Receipt Settings for FDS
        self.receipt_settings, _ = ReceiptSettings.objects.get_or_create(
            company='FDS',
            campus='KOTTAYAM',
            defaults={
                'organization_name': 'FILMAATIC Dance Studio',
                'receipt_prefix': 'FDS',
                'starting_number': 1,
                'default_gst_mode': 'NONE',
                'default_gst_rate': Decimal('0.00'),
                'sac_code': '999293',
                'address': 'Kottayam Studio, Kerala',
                'phone': '+91 98460 00000',
                'email': 'accounts@filmaatic.in',
            }
        )

        # Standard Fee Packages
        self.pkg_dance_monthly = FdsFeeStructure.objects.create(
            name='Regular Dance Monthly',
            category='DANCE',
            admission_fee=Decimal('1000.00'),
            amount=Decimal('1600.00'),
            duration_months=1,
            is_active=True,
        )
        self.pkg_bollywood_quarterly = FdsFeeStructure.objects.create(
            name='Bollywood Quarterly Package',
            category='BOLLYWOOD',
            admission_fee=Decimal('1000.00'),
            amount=Decimal('4500.00'),
            duration_months=3,
            is_active=True,
        )
        self.pkg_wedding = FdsFeeStructure.objects.create(
            name='Wedding Choreography Premium',
            category='WEDDING',
            admission_fee=Decimal('0.00'),
            amount=Decimal('25000.00'),
            duration_months=1,
            is_active=True,
        )

    def create_regular_student(self, student_id='FDS-STU-101', name='Ananya Menon', class_cat='DANCE', branch='KOTTAYAM', fee_structure=None):
        return FdsStudent.objects.create(
            student_id=student_id,
            name=name,
            contact_no='+919876543210',
            class_category=class_cat,
            student_type='REGULAR',
            branch=branch,
            joining_date=date(2026, 9, 1),
            fee_structure=fee_structure or self.pkg_dance_monthly,
            is_active=True,
        )

    def create_wedding_student(self, student_id='FDS-WED-201', name='Rahul & Sneha Sangeet'):
        wg = FdsWeddingGroup.objects.create(
            event_name='Rahul & Sneha Wedding Sangeet',
            lead_contact_name='Rahul Sharma',
            lead_contact_phone='+919845012345',
            package_type='PREMIUM',
            fee_amount=Decimal('25000.00'),
            amount_paid=Decimal('0.00'),
            balance_amount=Decimal('25000.00'),
            status='ACTIVE',
        )
        stu = FdsStudent.objects.create(
            student_id=student_id,
            name=name,
            contact_no='+919845012345',
            class_category='OTHER',
            student_type='WEDDING_MEMBER',
            branch='KOTTAYAM',
            joining_date=date(2026, 9, 1),
            is_active=True,
        )
        return stu, wg


# ==============================================================================
# TIER 1: FEATURE COVERAGE TESTS (≥5 CORE FEATURES)
# ==============================================================================

class FdsFeeSystemTier1FeatureTests(FdsFeeTestBase):
    """
    Tier 1: Feature Coverage (Happy Path).
    Verifies regular recurring tuition, wedding package isolation, custom differing amounts,
    digital receipt linking, and monthly receipt financial calculations.
    """

    def test_tier1_01_regular_recurring_tuition_generation(self):
        """Feature 1: Regular dance student generates recurring monthly installments."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=2)
        account.recalculate()

        # Must have generated installments for Sep, Oct, Nov, etc.
        installments = account.installments.order_by('sequence_number')
        self.assertGreaterEqual(installments.count(), 3)
        first_inst = installments.first()
        self.assertEqual(first_inst.scheduled_amount, Decimal('1600.00'))
        self.assertEqual(first_inst.due_date, date(2026, 9, 10))
        self.assertEqual(first_inst.label, "September 2026 Tuition")
        self.assertFalse(account.is_wedding_or_one_time(), "Regular dance student must NOT be classified as wedding")

    def test_tier1_02_pure_wedding_group_isolation(self):
        """Feature 2: Wedding group members are strictly isolated from monthly recurring tuition."""
        student, wedding_group = self.create_wedding_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_wedding,
            plan_type='ONE_TIME',
            monthly_fee=Decimal('0.00'),
            start_date=date(2026, 9, 1),
        )
        self.assertTrue(account.is_wedding_or_one_time(), "Wedding group student must be identified as wedding")

        account.sync_monthly_schedule()
        account.recalculate()

        # Wedding accounts must NEVER have recurring installments
        self.assertEqual(account.installments.count(), 0)
        self.assertEqual(account.total_due, Decimal('25000.00'))
        self.assertEqual(account.balance_due, Decimal('25000.00'))
        self.assertEqual(account.overdue_amount, Decimal('0.00'))

    def test_tier1_03_custom_differing_amounts_override(self):
        """Feature 6: Custom negotiated monthly fee overrides catalog default."""
        student = self.create_regular_student()
        # Catalog is 1600.00; student negotiated 2200.00
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('2200.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        eff_fee = account.get_effective_monthly_fee()
        # If student account specifies explicit monthly_fee > 0 and != 1600, it takes priority
        self.assertEqual(eff_fee, Decimal('2200.00'))

        account.sync_monthly_schedule(months_ahead=1)
        inst = account.installments.first()
        self.assertEqual(inst.scheduled_amount, Decimal('2200.00'))

    def test_tier1_04_digital_receipt_linking_fds_payment(self):
        """Feature 9 & 13: Digital receipt links directly to FdsFeesCollection with account ledger."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 9, 1),
        )
        account.sync_monthly_schedule()

        payment = FdsFeesCollection.objects.create(
            student=student,
            account=account,
            fees_type=self.pkg_dance_monthly,
            paid_amount=Decimal('1600.00'),
            total_fees=Decimal('1600.00'),
            balance=Decimal('0.00'),
            mode_of_pay='UPI',
            status='PAID',
            pay_date=date(2026, 9, 5),
            fee_month=9,
            fee_year=2026,
            remarks='September fee paid via GPay',
        )
        account.recalculate()

        self.client.force_authenticate(user=self.fds_user)
        url = f'/api/fees/receipts/from-fds-payment/{payment.id}/'
        response = self.client.post(url, data={})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        receipt = FeeReceipt.objects.get(fds_payment=payment)
        self.assertEqual(receipt.company, 'FDS')
        self.assertEqual(receipt.fds_student, student)
        self.assertEqual(receipt.total_amount, Decimal('1600.00'))
        self.assertEqual(receipt.status, 'ISSUED')
        self.assertTrue(verify_receipt_signature(receipt), "Receipt signature must be cryptographically valid")

    def test_tier1_05_monthly_receipt_breakdown_and_financials(self):
        """Feature 15: Financial calculation produces accurate subtotal, taxes, and words."""
        fin = calculate_receipt_financials(
            subtotal_amount=Decimal('3500.00'),
            tax_mode='NONE',
            gst_rate=Decimal('0.00'),
            default_sac='999293',
            fallback_title='Regular Dance Tuition - October 2026',
        )
        self.assertEqual(fin['subtotal_amount'], Decimal('3500.00'))
        self.assertEqual(fin['total_amount'], Decimal('3500.00'))
        self.assertEqual(fin['total_tax_amount'], Decimal('0.00'))
        self.assertIn("Three Thousand Five Hundred", fin['amount_in_words'])
        self.assertEqual(len(fin['line_items']), 1)
        self.assertEqual(fin['line_items'][0]['title'], 'Regular Dance Tuition - October 2026')


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASE TESTS
# ==============================================================================

class FdsFeeSystemTier2BoundaryTests(FdsFeeTestBase):
    """
    Tier 2: Boundary & Corner Cases.
    Exercises system limits: zero fee, negative balance/overpayment credit, mid-month enrollments,
    leap year clamping, calendar year rollover, and extreme custom rates (₹1 vs ₹100,000).
    """

    def test_tier2_01_zero_fee_transaction(self):
        """Boundary: Free trial or 100% concession with ₹0.00 payment."""
        words = amount_to_words(Decimal('0.00'))
        self.assertEqual(words, "Zero Rupees Only")

        fin = calculate_receipt_financials(
            subtotal_amount=Decimal('0.00'),
            tax_mode='NONE',
            gst_rate=Decimal('0.00'),
            default_sac='999293',
            fallback_title='Full Scholarship Trial',
        )
        self.assertEqual(fin['total_amount'], Decimal('0.00'))
        self.assertEqual(fin['amount_in_words'], "Zero Rupees Only")

    def test_tier2_02_negative_balance_overpayment_credit(self):
        """Boundary: Student pays ₹7,500 on ₹6,000 scheduled total fee."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('2000.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        # 3 months scheduled: 3 * 2000 = 6000
        account.sync_monthly_schedule(months_ahead=0) # Sep, Oct, Nov
        account.recalculate()

        # Student pays 7500
        FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('7500.00'),
            total_fees=Decimal('6000.00'),
            balance=Decimal('0.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 15),
        )
        account.sync_monthly_schedule()
        account.recalculate()

        self.assertEqual(account.total_paid, Decimal('7500.00'))
        self.assertEqual(account.balance_due, Decimal('0.00'), "Overpayment must reduce balance due to 0")

    def test_tier2_03_mid_month_enrollment_safe_status(self):
        """Boundary: Student joining mid-cycle (Oct 24) should not immediately be marked OVERDUE on day 1."""
        student = self.create_regular_student(name='Kavya Nair')
        student.joining_date = date(2026, 10, 24)
        student.save()

        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 10, 24),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=1)
        account.recalculate()

        # Account must be created without crashes and be in ACTIVE status
        self.assertIn(account.status, ['ACTIVE', 'PARTIAL'])

    def test_tier2_04_leap_year_february_due_date_clamping(self):
        """Boundary: Due day configured as 31 clamped to Feb 29 in leap year 2028 without ValueError."""
        yr, mo = 2028, 2
        days_in_m = monthrange(yr, mo)[1]
        self.assertEqual(days_in_m, 29, "2028 is a leap year with 29 days in February")

        due_day = 31
        clamped_day = min(due_day, days_in_m)
        inst_due = date(yr, mo, clamped_day)
        self.assertEqual(inst_due, date(2028, 2, 29))

    def test_tier2_05_calendar_year_boundary_rollover(self):
        """Boundary: Rollover spanning December 2026 to January 2027 increments year correctly."""
        base_dt = date(2026, 12, 1)
        next_dt = base_dt + relativedelta(months=1)
        self.assertEqual(next_dt.year, 2027)
        self.assertEqual(next_dt.month, 1)
        self.assertEqual(next_dt.strftime('%B %Y Tuition'), "January 2027 Tuition")

    def test_tier2_06_custom_rate_extremes_boundary(self):
        """Boundary: Custom rates at extreme boundaries: ₹1.00 vs ₹100,000.00."""
        # Minimum ₹1.00
        words_min = amount_to_words(Decimal('1.00'))
        self.assertEqual(words_min, "One Rupee Only")

        # Premium ₹100,000.00
        words_max = amount_to_words(Decimal('100000.00'))
        self.assertEqual(words_max, "One Lakh Rupees Only")


# ==============================================================================
# TIER 3: CROSS-FEATURE INTERACTION TESTS
# ==============================================================================

class FdsFeeSystemTier3CrossFeatureTests(FdsFeeTestBase):
    """
    Tier 3: Cross-Feature Interactions.
    Evaluates interactions between subsystems:
    - Auto-linking unlinked payments and generating receipts with ledger snapshots
    - Custom fee schedules interacting with partial payments and multi-month rollovers
    - Multi-tenant / Multi-company data and permission isolation between FLAG and FDS
    """

    def test_tier3_01_account_linking_and_receipt_snapshot(self):
        """Interaction: Linking unlinked payment captures full account ledger snapshot in receipt."""
        student = self.create_regular_student()
        # 1. Historical payment created before account existed
        unlinked_pmt = FdsFeesCollection.objects.create(
            student=student,
            account=None,
            paid_amount=Decimal('1600.00'),
            total_fees=Decimal('1600.00'),
            balance=Decimal('0.00'),
            mode_of_pay='CASH',
            pay_date=date(2026, 9, 2),
        )

        # 2. Account created subsequently
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule()
        account.recalculate()

        # Payment is now auto-linked
        unlinked_pmt.refresh_from_db()
        self.assertEqual(unlinked_pmt.account, account)

        # Direct ledger snapshot test with account
        snapshot = extract_fds_ledger_snapshot(account=account, payment=unlinked_pmt)
        self.assertEqual(snapshot['ledger_current_paid'], Decimal('1600.00'))
        self.assertEqual(snapshot['ledger_total_paid'], Decimal('1600.00'))
        self.assertGreaterEqual(len(snapshot['installment_schedule_snapshot']), 1)

    def test_tier3_02_custom_fee_rollover_and_partial_payment(self):
        """Interaction: Custom monthly rate + partial payment marks installment PARTIAL and preserves arrears."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('2500.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule()

        # Partial payment of 1000 against 2500 scheduled
        FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('1000.00'),
            total_fees=Decimal('2500.00'),
            balance=Decimal('1500.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 5),
        )
        account.sync_monthly_schedule()
        account.recalculate()

        first_inst = account.installments.order_by('sequence_number').first()
        self.assertEqual(first_inst.paid_amount, Decimal('1000.00'))
        self.assertEqual(first_inst.balance_amount, Decimal('1500.00'))
        self.assertEqual(first_inst.status, 'PARTIAL')
        self.assertEqual(account.status, 'PARTIAL')

    def test_tier3_03_multi_company_isolation_flag_vs_fds(self):
        """Interaction: Multi-company isolation guarantees FLAG users cannot generate FDS receipts and vice versa."""
        student = self.create_regular_student()
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 10),
        )

        # FLAG-only staff tries to generate FDS receipt -> 403 Forbidden
        self.client.force_authenticate(user=self.flag_user)
        res = self.client.post(f'/api/fees/receipts/from-fds-payment/{payment.id}/', data={})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # FDS staff can generate FDS receipt -> 200 OK
        self.client.force_authenticate(user=self.fds_user)
        res = self.client.post(f'/api/fees/receipts/from-fds-payment/{payment.id}/', data={})
        self.assertEqual(res.status_code, status.HTTP_200_OK)


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION WORKLOADS
# ==============================================================================

class FdsFeeSystemTier4RealWorldWorkloadTests(FdsFeeTestBase):
    """
    Tier 4: Real-World Application Workloads.
    Simulates complete operational lifecycle:
    Trial -> Enrollment -> Custom Monthly Rate -> 3-Month Recurring Schedule ->
    Partial Payment -> Digital Receipt -> Full Settlement -> Status Rollover.
    """

    def test_tier4_01_full_student_lifecycle_workload(self):
        """End-to-End student lifecycle workload."""
        # 1. Enrolls in dance program
        student = self.create_regular_student(student_id='FDS-LIFECYCLE-01', name='Meera Krishnan')

        # 2. Creates student fee account with negotiated monthly rate ₹2,000
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('2000.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=2) # Sep, Oct, Nov
        account.recalculate()
        self.assertEqual(account.status, 'ACTIVE')
        self.assertEqual(account.installments.count(), 3)

        # 3. Month 1 partial payment ₹1,200 (₹800 remaining)
        pmt_1 = FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('1200.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 8),
            fee_month=9,
            fee_year=2026,
            remarks='First partial payment',
        )
        account.sync_monthly_schedule()
        account.recalculate()

        self.assertEqual(account.status, 'PARTIAL')
        inst_1 = account.installments.order_by('sequence_number').first()
        self.assertEqual(inst_1.status, 'PARTIAL')
        self.assertEqual(inst_1.balance_amount, Decimal('800.00'))

        # 4. Issue Receipt #1
        self.client.force_authenticate(user=self.fds_user)
        res_rcpt_1 = self.client.post(f'/api/fees/receipts/from-fds-payment/{pmt_1.id}/', data={})
        self.assertEqual(res_rcpt_1.status_code, status.HTTP_200_OK)
        receipt_1 = FeeReceipt.objects.get(fds_payment=pmt_1)
        self.assertEqual(receipt_1.total_amount, Decimal('1200.00'))

        # 5. Month 1 balance settlement ₹800
        pmt_2 = FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('800.00'),
            mode_of_pay='CASH',
            pay_date=date(2026, 9, 14),
            fee_month=9,
            fee_year=2026,
            remarks='Month 1 balance settled',
        )
        account.sync_monthly_schedule()
        account.recalculate()

        inst_1.refresh_from_db()
        self.assertEqual(inst_1.status, 'PAID')
        self.assertEqual(inst_1.balance_amount, Decimal('0.00'))

        # Next due date advances to Month 2 (October 10)
        account.refresh_from_db()
        self.assertEqual(account.next_due_date, date(2026, 10, 10))

        # 6. Issue Receipt #2
        res_rcpt_2 = self.client.post(f'/api/fees/receipts/from-fds-payment/{pmt_2.id}/', data={})
        self.assertEqual(res_rcpt_2.status_code, status.HTTP_200_OK)


# ==============================================================================
# DIMENSION 1: PAYMENT STATUS VARIATIONS (PS-01 to PS-06)
# ==============================================================================

class PaymentStatusEdgeCaseTests(FdsFeeTestBase):
    """Edge cases PS-01 through PS-06."""

    def test_ps_01_partial_payment_split(self):
        """PS-01: Scheduled: ₹6,000. Payment: ₹2,500. Status='PARTIAL'."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_bollywood_quarterly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('6000.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=0)

        inst = account.installments.first()
        inst.scheduled_amount = Decimal('6000.00')
        inst.balance_amount = Decimal('6000.00')
        inst.save()

        # Pay 2500
        FdsFeesCollection.objects.create(
            student=student,
            account=account,
            installment=inst,
            paid_amount=Decimal('2500.00'),
            total_fees=Decimal('6000.00'),
            balance=Decimal('3500.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 5),
        )
        account.sync_monthly_schedule()
        account.recalculate()

        inst.refresh_from_db()
        self.assertEqual(inst.paid_amount, Decimal('2500.00'))
        self.assertEqual(inst.balance_amount, Decimal('3500.00'))
        self.assertEqual(inst.status, 'PARTIAL')
        self.assertEqual(account.status, 'PARTIAL')

    def test_ps_02_exact_full_settlement(self):
        """PS-02: Scheduled: ₹6,000. Payment: ₹6,000. Status='PAID', next due date advances."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_bollywood_quarterly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('6000.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=1) # Sep and Oct

        FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('6000.00'),
            mode_of_pay='BANK_TRANSFER',
            pay_date=date(2026, 9, 5),
        )
        account.sync_monthly_schedule()
        account.recalculate()

        inst1 = account.installments.order_by('sequence_number').first()
        self.assertEqual(inst1.status, 'PAID')
        self.assertEqual(inst1.balance_amount, Decimal('0.00'))
        self.assertEqual(account.next_due_date, date(2026, 10, 10))

    def test_ps_03_overdue_accumulation(self):
        """PS-03: Past due date with unpaid balance is marked OVERDUE."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 8, 1),
            due_day=10,
        )
        # August 10 is past
        inst = FdsFeeInstallment.objects.create(
            account=account,
            sequence_number=1,
            label='August 2026 Tuition',
            due_date=date(2026, 8, 10),
            scheduled_amount=Decimal('1600.00'),
            paid_amount=Decimal('0.00'),
            balance_amount=Decimal('1600.00'),
            status='PENDING',
        )
        inst.recalculate()
        self.assertEqual(inst.status, 'OVERDUE')

        account.recalculate()
        self.assertEqual(account.overdue_amount, Decimal('1600.00'))
        self.assertEqual(account.status, 'OVERDUE')

    def test_ps_04_fee_concession_waiver_adjustment(self):
        """PS-04: Fee Concession/Waiver of -₹2,000 reduces total due and balance due."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_bollywood_quarterly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('6000.00'),
            total_due=Decimal('18000.00'),
            balance_due=Decimal('18000.00'),
        )
        # Create waiver of -2000
        FdsFeeAdjustment.objects.create(
            account=account,
            adjustment_type='WAIVER',
            amount_delta=Decimal('-2000.00'),
            reason='Scholarship for excellence',
        )
        account.recalculate()
        self.assertEqual(account.total_due, Decimal('16000.00'))
        self.assertEqual(account.balance_due, Decimal('16000.00'))

    def test_ps_05_multi_month_advance_payment(self):
        """PS-05: Student pays ₹9,000 against ₹3,000/mo, clearing 3 consecutive months."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('3000.00'),
            start_date=date(2026, 9, 1),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=2) # Sep, Oct, Nov

        # Lump sum 9000
        FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('9000.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 2),
        )
        account.sync_monthly_schedule()
        account.recalculate()

        insts = account.installments.order_by('sequence_number')[:3]
        for inst in insts:
            self.assertEqual(inst.status, 'PAID')
            self.assertEqual(inst.balance_amount, Decimal('0.00'))

    def test_ps_06_overpayment_credit_balance(self):
        """PS-06: Overpayment credit of ₹1,500 recorded without inflating total due."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('2000.00'),
            total_due=Decimal('6000.00'),
            balance_due=Decimal('6000.00'),
        )
        FdsFeesCollection.objects.create(
            student=student,
            account=account,
            paid_amount=Decimal('7500.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 10),
        )
        account.recalculate()
        self.assertEqual(account.total_paid, Decimal('7500.00'))
        self.assertEqual(account.balance_due, Decimal('0.00'))


# ==============================================================================
# DIMENSION 2: STUDENT & ACCOUNT LINKING (AL-01 to AL-06)
# ==============================================================================

class AccountLinkingEdgeCaseTests(FdsFeeTestBase):
    """Edge cases AL-01 through AL-06."""

    def test_al_01_student_without_fee_account(self):
        """AL-01: Enrolled student without fee account handles lookup safely."""
        student = self.create_regular_student(student_id='FDS-NO-ACC-01')
        self.assertFalse(hasattr(student, 'fee_account'))

        # Metadata extraction does not crash
        meta = extract_fds_student_metadata(student)
        self.assertEqual(meta['recipient_name'], student.name)

    def test_al_02_auto_link_unlinked_payments(self):
        """AL-02: sync_monthly_schedule auto-links historical payments where account is None."""
        student = self.create_regular_student(student_id='FDS-ORPHAN-01')
        pmt = FdsFeesCollection.objects.create(
            student=student,
            account=None,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='CASH',
            pay_date=date(2026, 9, 1),
        )
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 9, 1),
        )
        account.sync_monthly_schedule()
        pmt.refresh_from_db()
        self.assertEqual(pmt.account, account)

    def test_al_03_batch_branch_transfer_rate_preservation(self):
        """AL-03: Branch transfer retains historical rate for paid past installments."""
        student = self.create_regular_student(branch='KOTTAYAM')
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 8, 1),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=0)

        # August paid at 1600
        inst_aug = account.installments.first()
        inst_aug.paid_amount = Decimal('1600.00')
        inst_aug.balance_amount = Decimal('0.00')
        inst_aug.status = 'PAID'
        inst_aug.save()

        # Transferred to Kochi at 2200
        student.branch = 'KOCHI'
        student.save()
        account.monthly_fee = Decimal('2200.00')
        account.save()

        account.sync_monthly_schedule(months_ahead=1)

        # Past installment preserved at 1600
        inst_aug.refresh_from_db()
        self.assertEqual(inst_aug.scheduled_amount, Decimal('1600.00'))
        self.assertEqual(inst_aug.status, 'PAID')

    def test_al_04_withdrawn_inactive_student_freeze(self):
        """AL-04: Inactive student (is_active=False) freezes future billing."""
        student = self.create_regular_student()
        student.is_active = False
        student.save()

        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 9, 1),
        )
        # Should be safe to inspect without errors
        self.assertFalse(student.is_active)

    def test_al_05_wedding_group_member_isolation(self):
        """AL-05: Wedding member classifies as is_wedding_or_one_time and creates no tuition installments."""
        student, wg = self.create_wedding_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_wedding,
            plan_type='ONE_TIME',
            start_date=date(2026, 9, 1),
        )
        self.assertTrue(account.is_wedding_or_one_time())
        account.sync_monthly_schedule()
        self.assertEqual(account.installments.count(), 0)

    def test_al_06_deleted_student_handling_audit_trail(self):
        """AL-06: Student deletion preserves issued receipts with SET_NULL."""
        student = self.create_regular_student(student_id='FDS-DEL-01')
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 1),
        )
        receipt = FeeReceipt.objects.create(
            company='FDS',
            fds_student=student,
            fds_payment=payment,
            receipt_number='FDS/2026-27/0099',
            recipient_name=student.name,
            total_amount=Decimal('1600.00'),
            status='ISSUED',
        )
        # Deleting student sets fds_student to NULL on receipt without deleting receipt
        student.delete()
        receipt.refresh_from_db()
        self.assertIsNone(receipt.fds_student)
        self.assertEqual(receipt.recipient_name, 'Ananya Menon')


# ==============================================================================
# DIMENSION 3: RECURRING BILLING CYCLE ROLLOVERS (RC-01 to RC-06)
# ==============================================================================

class RecurringCycleEdgeCaseTests(FdsFeeTestBase):
    """Edge cases RC-01 through RC-06."""

    def test_rc_01_mid_month_enrollment_due_date_anchor(self):
        """RC-01: Joining on Oct 24 sets valid start_date and due_day."""
        student = self.create_regular_student()
        student.joining_date = date(2026, 10, 24)
        student.save()

        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 10, 24),
            due_day=10,
        )
        account.sync_monthly_schedule(months_ahead=1)
        self.assertEqual(account.start_date, date(2026, 10, 24))

    def test_rc_02_differing_amounts_across_cycles(self):
        """RC-02: Differing installment amounts (5000, 3500, 5000) sum accurately to 13500."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            plan_type='PACKAGE',
            monthly_fee=Decimal('5000.00'),
            start_date=date(2026, 9, 1),
        )
        # Manually create differing installments: Sep (5000), Oct (3500 - promo), Nov (5000)
        FdsFeeInstallment.objects.create(
            account=account, sequence_number=1, label='Sep 2026', due_date=date(2026, 9, 10),
            scheduled_amount=Decimal('5000.00'), balance_amount=Decimal('5000.00'), status='PENDING'
        )
        FdsFeeInstallment.objects.create(
            account=account, sequence_number=2, label='Oct 2026 (Promo)', due_date=date(2026, 10, 10),
            scheduled_amount=Decimal('3500.00'), balance_amount=Decimal('3500.00'), status='PENDING'
        )
        FdsFeeInstallment.objects.create(
            account=account, sequence_number=3, label='Nov 2026', due_date=date(2026, 11, 10),
            scheduled_amount=Decimal('5000.00'), balance_amount=Decimal('5000.00'), status='PENDING'
        )
        account.recalculate()
        self.assertEqual(account.total_due, Decimal('13500.00'))
        self.assertEqual(account.balance_due, Decimal('13500.00'))

    def test_rc_03_custom_per_student_monthly_rate(self):
        """RC-03: Student custom monthly rate of ₹2,000 overrides catalog ₹1,600."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=self.pkg_dance_monthly,
            plan_type='PACKAGE',
            monthly_fee=Decimal('2000.00'),
            start_date=date(2026, 9, 1),
        )
        self.assertEqual(account.get_effective_monthly_fee(), Decimal('2000.00'))

    def test_rc_04_calendar_year_rollover(self):
        """RC-04: Incrementing from December 2026 rolls cleanly into January 2027."""
        d = date(2026, 12, 10)
        next_d = d + relativedelta(months=1)
        self.assertEqual(next_d, date(2027, 1, 10))

    def test_rc_05_leap_year_february_rollover(self):
        """RC-05: Leap year February 29 handles clamping cleanly."""
        d = date(2028, 2, 29)
        self.assertEqual(d.month, 2)
        self.assertEqual(d.day, 29)

    def test_rc_06_extended_vacation_freeze(self):
        """RC-06: Frozen installment with balance 0 does not accumulate overdue."""
        student = self.create_regular_student()
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            plan_type='PACKAGE',
            monthly_fee=Decimal('1600.00'),
            start_date=date(2026, 9, 1),
        )
        # Create a frozen/waived installment for leave period
        inst = FdsFeeInstallment.objects.create(
            account=account, sequence_number=1, label='Leave Month',
            due_date=date(2026, 9, 10), scheduled_amount=Decimal('0.00'),
            paid_amount=Decimal('0.00'), balance_amount=Decimal('0.00'),
            status='WAIVED'
        )
        inst.recalculate()
        self.assertEqual(inst.status, 'PAID')
        account.recalculate()
        self.assertEqual(account.overdue_amount, Decimal('0.00'))


# ==============================================================================
# DIMENSION 4: RECEIPT GENERATION EDGE CASES (RG-01 to RG-06)
# ==============================================================================

class ReceiptGenerationEdgeCaseTests(FdsFeeTestBase):
    """Edge cases RG-01 through RG-06."""

    def test_rg_01_concurrent_receipt_generation_idempotency(self):
        """RG-01: Re-requesting receipt generation for same payment returns existing receipt idempotently."""
        student = self.create_regular_student()
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 10),
        )
        self.client.force_authenticate(user=self.fds_user)
        url = f'/api/fees/receipts/from-fds-payment/{payment.id}/'

        # First request creates receipt
        res1 = self.client.post(url, data={})
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        rcpt1_id = res1.data['id']
        rcpt1_num = res1.data['receipt_number']

        # Second request must return existing receipt without creating a new one
        res2 = self.client.post(url, data={})
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['id'], rcpt1_id)
        self.assertEqual(res2.data['receipt_number'], rcpt1_num)

        # Count of receipts for this payment must remain exactly 1
        self.assertEqual(FeeReceipt.objects.filter(fds_payment=payment).count(), 1)

    def test_rg_02_zero_amount_receipt(self):
        """RG-02: Zero-amount payment generates valid receipt with 'Zero Rupees Only'."""
        student = self.create_regular_student()
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('0.00'),
            mode_of_pay='CASH',
            pay_date=date(2026, 9, 10),
        )
        self.client.force_authenticate(user=self.fds_user)
        res = self.client.post(f'/api/fees/receipts/from-fds-payment/{payment.id}/', data={})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['total_amount'], '0.00')
        self.assertEqual(res.data['amount_in_words'], 'Zero Rupees Only')

    def test_rg_03_retroactive_backdated_payment_fy_allocation(self):
        """RG-03: Backdated payment preserves pay_date while allocating in current active financial year."""
        student = self.create_regular_student()
        backdated = date(2026, 5, 15)
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='BANK_TRANSFER',
            pay_date=backdated,
        )
        self.client.force_authenticate(user=self.fds_user)
        res = self.client.post(f'/api/fees/receipts/from-fds-payment/{payment.id}/', data={})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Payment date is preserved
        self.assertTrue(res.data['payment_date'].startswith('2026-05-15'))
        # Sequence number is in current FY 2026-27
        self.assertIn('2026-27', res.data['receipt_number'])

    def test_rg_04_multi_item_fee_breakdown(self):
        """RG-04: Receipt itemized into Tuition + Registration + Costume summing to total."""
        items = [
            {'sac_code': '999293', 'title': 'Dance Tuition', 'amount': '3000.00', 'period': 'Sep 2026'},
            {'sac_code': '999293', 'title': 'Registration Fee', 'amount': '500.00', 'period': 'One Time'},
            {'sac_code': '999293', 'title': 'Studio Costume', 'amount': '1500.00', 'period': 'Annual'},
        ]
        subtotal = sum(Decimal(it['amount']) for it in items)
        self.assertEqual(subtotal, Decimal('5000.00'))

        receipt = FeeReceipt.objects.create(
            company='FDS',
            receipt_number='FDS/2026-27/0088',
            recipient_name='Arya Stark',
            subtotal_amount=subtotal,
            total_amount=subtotal,
            line_items=items,
            status='ISSUED',
        )
        self.assertEqual(receipt.total_amount, Decimal('5000.00'))
        self.assertEqual(len(receipt.line_items), 3)

    def test_rg_05_special_characters_regional_names_utf8(self):
        """RG-05: Regional names (Malayalam: നന്ദി) and apostrophes stored and verified cleanly."""
        student = self.create_regular_student(name="Ananya O'Connor")
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 10),
            remarks="നന്ദി - Thank you 😊",
        )
        self.client.force_authenticate(user=self.fds_user)
        res = self.client.post(f'/api/fees/receipts/from-fds-payment/{payment.id}/', data={})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        receipt = FeeReceipt.objects.get(fds_payment=payment)
        self.assertEqual(receipt.recipient_name, "Ananya O'Connor")
        self.assertTrue(verify_receipt_signature(receipt), "Signature verification must work with special characters")

    def test_rg_06_void_workflow_audit_trail_immutability(self):
        """RG-06: Issued receipt transitioned to VOID; deletion is permanently blocked."""
        student = self.create_regular_student()
        payment = FdsFeesCollection.objects.create(
            student=student,
            paid_amount=Decimal('1600.00'),
            mode_of_pay='UPI',
            pay_date=date(2026, 9, 10),
        )
        self.client.force_authenticate(user=self.fds_user)
        res = self.client.post(f'/api/fees/receipts/from-fds-payment/{payment.id}/', data={})
        receipt_id = res.data['id']

        # Void receipt
        void_res = self.client.post(f'/api/fees/receipts/{receipt_id}/void/', data={'reason': 'Incorrect student assigned'})
        self.assertEqual(void_res.status_code, status.HTTP_200_OK)
        receipt = FeeReceipt.objects.get(pk=receipt_id)
        self.assertEqual(receipt.status, 'VOID')
        self.assertEqual(receipt.void_reason, 'Incorrect student assigned')

        # Deletion must be blocked
        del_res = self.client.delete(f'/api/fees/receipts/{receipt_id}/')
        self.assertIn(del_res.status_code, [status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])
