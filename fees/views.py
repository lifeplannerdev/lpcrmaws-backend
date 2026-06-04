from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import ActivityLog, User
from notifications.models import Notification
from trainers.models import Student

from .models import FeePlanTemplate, StudentFeeAccount, FeeInstallment, FeePayment, FeeAdjustment
from .permissions import CanViewFees, CanManageFees, CanRestructureFees, CanRecordPartialPayment, CanIssueFeeNotice
from .serializers import (
    FeePlanTemplateSerializer,
    StudentFeeAccountSerializer,
    FeePaymentSerializer,
    FeeAdjustmentSerializer,
    StudentFeeAccountCreateSerializer,
    FeeRestructureSerializer,
    FeeSummarySerializer,
    FeeInstallmentSerializer,
)


def _notify_users(users, notif_type, message, by='System'):
    for user in users:
        Notification.objects.create(user=user, type=notif_type, message=message, by=by)


def _finance_recipients(company=None):
    qs = User.objects.filter(is_active=True, permissions__contains=['manage_fees'])
    if company:
        qs = qs.filter(company=company)
    return qs


def _perm_list(user):
    return user.permissions or []


def _can_view_fee_account(user, account):
    perms = _perm_list(user)
    if 'view_fees' in perms or 'view_fee_reports' in perms or 'manage_fees' in perms:
        return True
    return hasattr(user, 'trainer_profile') and account.student.trainer_id == user.trainer_profile.id


class FeePlanTemplateListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get(self, request):
        qs = FeePlanTemplate.objects.all().order_by('company', 'plan_type', 'name')
        company = request.GET.get('company')
        plan_type = request.GET.get('plan_type')
        active = request.GET.get('active')
        if company:
            qs = qs.filter(company=company)
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        if active in ('true', 'false'):
            qs = qs.filter(is_active=(active == 'true'))
        return Response(FeePlanTemplateSerializer(qs, many=True).data)

    def post(self, request):
        serializer = FeePlanTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FeePlanTemplateDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get(self, request, pk):
        template = get_object_or_404(FeePlanTemplate, pk=pk)
        return Response(FeePlanTemplateSerializer(template).data)

    def patch(self, request, pk):
        template = get_object_or_404(FeePlanTemplate, pk=pk)
        serializer = FeePlanTemplateSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class FeeAccountListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get(self, request):
        qs = StudentFeeAccount.objects.select_related('student', 'student__trainer__user', 'student__branch', 'template').prefetch_related('installments', 'payments', 'adjustments')
        company = request.GET.get('company')
        status_filter = request.GET.get('status')
        student_id = request.GET.get('student')
        search = request.GET.get('search')
        plan_type = request.GET.get('plan_type')
        branch_id = request.GET.get('branch_id')

        if hasattr(request.user, 'trainer_profile') and 'view_fees' not in _perm_list(request.user) and 'manage_fees' not in _perm_list(request.user) and 'view_fee_reports' not in _perm_list(request.user):
            qs = qs.filter(student__trainer=request.user.trainer_profile)

        if company:
            qs = qs.filter(company=company)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        if branch_id:
            qs = qs.filter(student__branch_id=branch_id)
        if search:
            qs = qs.filter(
                Q(student__name__icontains=search) |
                Q(plan_name__icontains=search) |
                Q(plan_code__icontains=search)
            )

        return Response(StudentFeeAccountSerializer(qs.order_by('-updated_at'), many=True).data)

    def post(self, request):
        serializer = StudentFeeAccountCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        account = serializer.save()

        ActivityLog.objects.create(
            user=request.user,
            company=account.company,
            action='STUDENT_ENROLLED',
            entity_type='StudentFeeAccount',
            entity_id=account.id,
            entity_name=account.student.name,
            description=f"Fee account created for {account.student.name}",
            metadata={'plan_type': account.plan_type, 'total_due': str(account.total_due)},
        )

        _notify_users(
            _finance_recipients(account.company),
            'fee',
            f"Fee account created for {account.student.name}",
            by=request.user.get_full_name() or request.user.username,
        )

        return Response(StudentFeeAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class FeeAccountDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get_object(self, request, pk):
        account = get_object_or_404(
            StudentFeeAccount.objects.select_related('student', 'student__trainer__user', 'student__branch', 'template'),
            pk=pk
        )
        if not _can_view_fee_account(request.user, account):
            return None
        return account

    def get(self, request, pk):
        account = self.get_object(request, pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(StudentFeeAccountSerializer(account).data)

    def patch(self, request, pk):
        if 'manage_fees' not in _perm_list(request.user):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        account = self.get_object(request, pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StudentFeeAccountCreateSerializer(account, data=request.data, context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        account.recalculate(save=True)
        return Response(StudentFeeAccountSerializer(account).data)


class FeeInstallmentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get(self, request, account_pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        return Response(FeeInstallmentSerializer(account.installments.all(), many=True).data)

    def post(self, request, account_pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        serializer = FeeInstallmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        installment = serializer.save(account=account)
        account.recalculate(save=True)
        return Response(FeeInstallmentSerializer(installment).data, status=status.HTTP_201_CREATED)


class FeePaymentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get(self, request, account_pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        if not _can_view_fee_account(request.user, account):
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(FeePaymentSerializer(account.payments.all(), many=True).data)

    def post(self, request, account_pk):
        if 'manage_fees' not in _perm_list(request.user) and 'record_partial_payment' not in _perm_list(request.user):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        payload = request.data.copy()
        payload['account'] = account.id
        serializer = FeePaymentSerializer(data=payload, context={'request': request})
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()

        if payment.amount < (payment.installment.scheduled_amount if payment.installment else payment.amount):
            account.status = 'PARTIAL'
            account.save(update_fields=['status', 'updated_at'])

        return Response(FeePaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class FeeAdjustmentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get(self, request, account_pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        return Response(FeeAdjustmentSerializer(account.adjustments.all(), many=True).data)

    def post(self, request, account_pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        payload = request.data.copy()
        payload['account'] = account.id
        serializer = FeeAdjustmentSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        adjustment = serializer.save(created_by=request.user)
        account.version += 1
        account.last_restructure_date = timezone.now() if adjustment.adjustment_type == 'RESTRUCTURE' else account.last_restructure_date
        account.updated_by = request.user
        account.save(update_fields=['version', 'last_restructure_date', 'updated_by', 'updated_at'])
        ActivityLog.objects.create(
            user=request.user,
            company=account.company,
            action='STUDENT_UPDATED',
            entity_type='StudentFeeAccount',
            entity_id=account.id,
            entity_name=account.student.name,
            description=f"Fee adjustment recorded for {account.student.name}",
            metadata={'adjustment_type': adjustment.adjustment_type, 'amount_delta': str(adjustment.amount_delta)},
        )
        return Response(FeeAdjustmentSerializer(adjustment).data, status=status.HTTP_201_CREATED)


class FeeRestructureAPIView(APIView):
    permission_classes = [IsAuthenticated, CanRestructureFees]

    def post(self, request, pk):
        account = get_object_or_404(StudentFeeAccount, pk=pk)
        serializer = FeeRestructureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            template = None
            if data.get('template_id'):
                template = get_object_or_404(FeePlanTemplate, pk=data['template_id'])

            account.plan_snapshot = {
                'previous_plan_code': account.plan_code,
                'previous_plan_name': account.plan_name,
                'previous_plan_type': account.plan_type,
                'previous_total_due': str(account.total_due),
                'restructured_at': timezone.now().isoformat(),
            }
            account.version += 1
            account.plan_type = data['plan_type']
            account.template = template
            if template:
                account.plan_code = template.code
                account.plan_name = template.name
                account.registration_amount = template.registration_amount
                account.due_day = template.due_day
            if data.get('total_due') is not None:
                account.total_due = data['total_due']
            if data.get('registration_amount') is not None:
                account.registration_amount = data['registration_amount']
            if data.get('due_day') is not None:
                account.due_day = data['due_day']
            if data.get('next_due_date') is not None:
                account.next_due_date = data['next_due_date']
            account.status = 'RESTRUCTURED'
            account.last_restructure_date = timezone.now()
            account.updated_by = request.user
            account.save()

            FeeAdjustment.objects.create(
                account=account,
                adjustment_type='RESTRUCTURE',
                amount_delta=Decimal('0'),
                reason=data.get('notes') or 'Plan restructured',
                metadata={'new_plan_type': data['plan_type']},
                created_by=request.user,
            )

            installment_payloads = data.get('installments') or []
            if installment_payloads:
                account.installments.all().delete()
                for idx, item in enumerate(installment_payloads, start=1):
                    FeeInstallment.objects.create(
                        account=account,
                        sequence_number=idx,
                        label=item.get('label') or f'Installment {idx}',
                        due_date=item['due_date'],
                        scheduled_amount=item['scheduled_amount'],
                        paid_amount=Decimal('0'),
                        balance_amount=item['scheduled_amount'],
                        status='PENDING',
                        notes=item.get('notes', ''),
                    )

            account.recalculate(save=True)

        _notify_users(
            _finance_recipients(account.company),
            'fee',
            f"Fee plan restructured for {account.student.name}",
            by=request.user.get_full_name() or request.user.username,
        )

        return Response(StudentFeeAccountSerializer(account).data)


class FeeSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get(self, request):
        qs = StudentFeeAccount.objects.select_related('student', 'student__branch', 'student__trainer__user')
        company = request.GET.get('company')
        if company:
            qs = qs.filter(company=company)
        if hasattr(request.user, 'trainer_profile') and 'view_fee_reports' not in _perm_list(request.user) and 'manage_fees' not in _perm_list(request.user):
            qs = qs.filter(student__trainer=request.user.trainer_profile)

        student_id = request.GET.get('student')
        batch_id = request.GET.get('academic_batch')
        branch_id = request.GET.get('branch_id')
        status_filter = request.GET.get('status')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if batch_id:
            qs = qs.filter(student__academic_batch_id=batch_id)
        if branch_id:
            qs = qs.filter(student__branch_id=branch_id)
        if status_filter:
            qs = qs.filter(status=status_filter)

        rows = [
            {
                'student_id': account.student_id,
                'student_name': account.student.name,
                'company': account.company,
                'plan_name': account.plan_name,
                'plan_type': account.plan_type,
                'total_due': account.total_due,
                'total_paid': account.total_paid,
                'balance_due': account.balance_due,
                'overdue_amount': account.overdue_amount,
                'status': account.status,
                'next_due_date': account.next_due_date,
                'last_payment_date': account.last_payment_date,
            }
            for account in qs
        ]

        return Response(FeeSummarySerializer(rows, many=True).data)


class FeeCatalogSeedAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def post(self, request):
        templates = [
            {
                'company': 'FLAG',
                'code': 'FLAG-A1-B2-FULL',
                'name': 'FLAG German A1-B2 Full Package',
                'course_label': 'A1-B2',
                'plan_type': 'ONE_TIME',
                'total_amount': '106200.00',
                'notes': 'One-time payment package from fee sheet.',
            },
            {
                'company': 'FLAG',
                'code': 'FLAG-A1-B2-3INST',
                'name': 'FLAG German A1-B2 3 Installments',
                'course_label': 'A1-B2',
                'plan_type': 'INSTALLMENT',
                'total_amount': '114000.00',
                'installment_count': 3,
                'installment_amount': '38000.00',
                'notes': '38,000 x 3 installments.',
            },
            {
                'company': 'FLAG',
                'code': 'FLAG-A1-B2-MONTHLY',
                'name': 'FLAG German Monthly Plan',
                'course_label': 'A1-B2',
                'plan_type': 'MONTHLY',
                'total_amount': '115000.00',
                'registration_amount': '20000.00',
                'monthly_amount': '9500.00',
                'duration_months': 10,
                'due_day': 10,
                'notes': '20,000 registration plus 9,500 monthly for 10 months.',
            },
            {'company': 'FLAG', 'code': 'FLAG-A1', 'name': 'FLAG A1 Level', 'course_label': 'A1', 'plan_type': 'PACKAGE', 'total_amount': '21240.00'},
            {'company': 'FLAG', 'code': 'FLAG-A2', 'name': 'FLAG A2 Level', 'course_label': 'A2', 'plan_type': 'PACKAGE', 'total_amount': '21240.00'},
            {'company': 'FLAG', 'code': 'FLAG-B1', 'name': 'FLAG B1 Level', 'course_label': 'B1', 'plan_type': 'PACKAGE', 'total_amount': '29500.00'},
            {'company': 'FLAG', 'code': 'FLAG-B2', 'name': 'FLAG B2 Level', 'course_label': 'B2', 'plan_type': 'PACKAGE', 'total_amount': '47200.00'},
        ]
        created = []
        for item in templates:
            obj, _ = FeePlanTemplate.objects.update_or_create(code=item['code'], defaults=item)
            created.append(obj)
        return Response(FeePlanTemplateSerializer(created, many=True).data, status=status.HTTP_201_CREATED)
