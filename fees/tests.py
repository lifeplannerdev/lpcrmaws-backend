from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.permission_templates import get_permissions_for_role
from fees.models import FeePlanTemplate, StudentFeeAccount, FeeInstallment
from trainers.models import Branch, Trainer, Student


User = get_user_model()


class FeeAccessTests(APITestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='FLAG Branch', location='Kochi')

        self.trainer_user = User.objects.create_user(
            username='trainer-fee',
            password='pass12345',
            company='FLAG',
            permissions=get_permissions_for_role('TRAINER'),
        )
        self.trainer = Trainer.objects.create(user=self.trainer_user, branch=self.branch)

        self.accounts_user = User.objects.create_user(
            username='accounts',
            password='pass12345',
            company='FLAG',
            permissions=get_permissions_for_role('ACCOUNTS'),
        )

        self.student = Student.objects.create(
            name='Fee Student',
            batch='A1',
            branch=self.branch,
            trainer=self.trainer,
            status='ACTIVE',
            admission_date=date(2026, 1, 1),
            company='FLAG',
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
            batch='B1',
            branch=self.branch,
            trainer=self.trainer,
            status='ACTIVE',
            admission_date=date(2026, 1, 1),
            company='FLAG',
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
