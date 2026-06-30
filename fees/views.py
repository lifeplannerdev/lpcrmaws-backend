from accounts.permissions import has_dynamic_permission
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import pandas as pd
from django.http import HttpResponse

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
    qs = User.objects.filter(is_active=True)
    if company:
        qs = qs.filter(company=company)
    return [user for user in qs if has_dynamic_permission(user, 'fees:manage')]


def _can_view_fee_account(user, account):
    if has_dynamic_permission(user, 'fees:read_tenant') or has_dynamic_permission(user, 'fees:view_reports') or has_dynamic_permission(user, 'fees:manage'):
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

    def delete(self, request, pk):
        template = get_object_or_404(FeePlanTemplate, pk=pk)
        template.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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

        if hasattr(request.user, 'trainer_profile') and not has_dynamic_permission(request.user, 'fees:read_tenant') and not has_dynamic_permission(request.user, 'fees:manage') and not has_dynamic_permission(request.user, 'fees:view_reports'):
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
        if not has_dynamic_permission(request.user, 'fees:manage'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        account = self.get_object(request, pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StudentFeeAccountCreateSerializer(account, data=request.data, context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        account.recalculate(save=True)
        return Response(StudentFeeAccountSerializer(account).data)

    def delete(self, request, pk):
        if not has_dynamic_permission(request.user, 'fees:manage'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        account = self.get_object(request, pk)
        if not account:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        account.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        if not has_dynamic_permission(request.user, 'fees:manage') and not has_dynamic_permission(request.user, 'fees:partial_payment'):
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


class FeeInstallmentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get_object(self, request, account_pk, pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        if not _can_view_fee_account(request.user, account):
            return None
        return get_object_or_404(FeeInstallment, pk=pk, account=account)

    def patch(self, request, account_pk, pk):
        installment = self.get_object(request, account_pk, pk)
        if not installment:
            return Response({'detail': 'Not found or Forbidden.'}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = FeeInstallmentSerializer(installment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        installment = serializer.save()
        installment.account.recalculate(save=True)
        return Response(serializer.data)

    def delete(self, request, account_pk, pk):
        installment = self.get_object(request, account_pk, pk)
        if not installment:
            return Response({'detail': 'Not found or Forbidden.'}, status=status.HTTP_404_NOT_FOUND)
        account = installment.account
        installment.delete()
        account.recalculate(save=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FeePaymentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get_object(self, request, account_pk, pk):
        account = get_object_or_404(StudentFeeAccount, pk=account_pk)
        if not _can_view_fee_account(request.user, account):
            return None
        return get_object_or_404(FeePayment, pk=pk, account=account)

    def patch(self, request, account_pk, pk):
        payment = self.get_object(request, account_pk, pk)
        if not payment:
            return Response({'detail': 'Not found or Forbidden.'}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = FeePaymentSerializer(payment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        payment.account.recalculate(save=True)
        return Response(serializer.data)

    def delete(self, request, account_pk, pk):
        payment = self.get_object(request, account_pk, pk)
        if not payment:
            return Response({'detail': 'Not found or Forbidden.'}, status=status.HTTP_404_NOT_FOUND)
        account = payment.account
        payment.delete()
        account.recalculate(save=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                
                from django.db.models import Sum
                total_paid = account.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
                remaining = total_paid
                
                for inst in account.installments.all().order_by('sequence_number'):
                    if remaining > 0:
                        if remaining >= inst.scheduled_amount:
                            inst.paid_amount = inst.scheduled_amount
                            inst.balance_amount = Decimal('0')
                            inst.status = 'PAID'
                            remaining -= inst.scheduled_amount
                        else:
                            inst.paid_amount = remaining
                            inst.balance_amount = inst.scheduled_amount - remaining
                            inst.status = 'PARTIAL'
                            remaining = Decimal('0')
                        inst.save(update_fields=['paid_amount', 'balance_amount', 'status'])

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
        if hasattr(request.user, 'trainer_profile') and not has_dynamic_permission(request.user, 'fees:view_reports') and not has_dynamic_permission(request.user, 'fees:manage'):
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


class FeeStudentsAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get(self, request):
        qs = Student.objects.exclude(status__in=['COMPLETED', 'DROPPED']).select_related('branch')
        if hasattr(request.user, 'trainer_profile') and not has_dynamic_permission(request.user, 'fees:read_tenant') and not has_dynamic_permission(request.user, 'fees:manage') and not has_dynamic_permission(request.user, 'fees:view_reports'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        search = request.GET.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone_number__icontains=search) | Q(email__icontains=search))

        data = []
        for s in qs.order_by('name')[:500]:
            data.append({
                'id': s.id,
                'name': s.name,
                'branch_name': s.branch.name if s.branch else '',
                'phone': s.phone_number,
            })
        return Response(data)

class ExportAdmissionsReportAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get(self, request):
        qs = StudentFeeAccount.objects.select_related('student', 'student__trainer__user', 'student__branch', 'template').prefetch_related('payments')
        
        data = []
        for i, account in enumerate(qs, start=1):
            student = account.student
            row = {
                "SL NO": i,
                "HANDLED BY": student.trainer.user.get_full_name() if student.trainer else "",
                "NAME": student.name,
                "PH NO": student.phone_number,
                "PARENT NAME": student.parent_name,
                "PARENT NO": student.parent_phone,
                "MAIL ID": student.email,
                "CAMPUS": student.branch.name if student.branch else "",
                "MODE OF STUDY": student.get_mode_of_study_display() if student.mode_of_study else "",
                "PREFERRED LEVEL": student.get_preferred_level_display() if student.preferred_level else "",
                "PACKAGE CHOSEN": account.plan_name or account.plan_type,
                "TOTAL FEE": account.total_due,
                "SPECIAL DISCOUNT": 0,
                "PENDING": account.balance_due,
                "RECEIPT GIVEN": "Yes" if account.payments.exists() else "No",
                "STATUS OF FEE": account.get_status_display()
            }
            
            payments = account.payments.all().order_by('payment_date')
            for p_idx, payment in enumerate(payments[:4], start=1):
                if p_idx == 1:
                    row["1st PAYMENT"] = payment.amount
                    row["Unnamed: 15"] = payment.get_payment_method_display()
                    row["Unnamed: 16"] = payment.payment_date.strftime("%d/%m/%Y")
                elif p_idx == 2:
                    row["2nd PAYMENT"] = payment.amount
                    row["Unnamed: 18"] = payment.get_payment_method_display()
                    row["Unnamed: 19"] = payment.payment_date.strftime("%d/%m/%Y")
                elif p_idx == 3:
                    row["3rd PAYMENT"] = payment.amount
                    row["Unnamed: 21"] = payment.get_payment_method_display()
                    row["Unnamed: 22"] = payment.payment_date.strftime("%d/%m/%Y")
                elif p_idx == 4:
                    row["4th PAYMENT"] = payment.amount
                    row["Unnamed: 24"] = payment.get_payment_method_display()
                    row["Unnamed: 25"] = payment.payment_date.strftime("%d/%m/%Y")
                    
            data.append(row)

        df = pd.DataFrame(data)
        
        columns = [
            "SL NO", "HANDLED BY", "NAME", "PH NO", "PARENT NAME", "PARENT NO", 
            "MAIL ID", "CAMPUS", "MODE OF STUDY", "PREFERRED LEVEL", "PACKAGE CHOSEN", 
            "TOTAL FEE", "SPECIAL DISCOUNT", "PENDING", 
            "1st PAYMENT", "Unnamed: 15", "Unnamed: 16", 
            "2nd PAYMENT", "Unnamed: 18", "Unnamed: 19", 
            "3rd PAYMENT", "Unnamed: 21", "Unnamed: 22", 
            "4th PAYMENT", "Unnamed: 24", "Unnamed: 25", 
            "RECEIPT GIVEN", "STATUS OF FEE"
        ]
        
        for col in columns:
            if col not in df.columns:
                df[col] = ""
                
        df = df[columns]

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="admissions_report.xlsx"'
        
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Admissions')

        return response



from .models import FeePolicy
from .serializers import FeePolicySerializer

class FeePolicyAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageFees]

    def get(self, request):
        company = request.user.company or 'LP'
        policy, created = FeePolicy.objects.get_or_create(company=company)
        return Response(FeePolicySerializer(policy).data)

    def patch(self, request):
        company = request.user.company or 'LP'
        policy, created = FeePolicy.objects.get_or_create(company=company)
        serializer = FeePolicySerializer(policy, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

from rest_framework.permissions import BasePermission
class CanViewAnalytics(BasePermission):
    def has_permission(self, request, view):
        return has_dynamic_permission(request.user, 'fees:analytics')

class FeeAnalyticsOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewAnalytics]

    def get(self, request):
        company = request.GET.get('company')
        qs = StudentFeeAccount.objects.select_related('student', 'student__branch', 'student__academic_batch')
        if company:
            qs = qs.filter(company=company)
        
        branch_id = request.GET.get('branch')
        batch_id = request.GET.get('batch')
        if branch_id:
            qs = qs.filter(student__branch_id=branch_id)
        if batch_id:
            qs = qs.filter(student__academic_batch_id=batch_id)

        data = []
        for acc in qs:
            data.append({
                'id': acc.student_id,
                'student_name': acc.student.name,
                'branch_name': acc.student.branch.name if acc.student.branch else '',
                'batch_name': acc.student.academic_batch.name if acc.student.academic_batch else '',
                'plan_name': acc.plan_name,
                'total_due': acc.total_due,
                'total_paid': acc.total_paid,
                'overdue_amount': acc.overdue_amount,
                'status': acc.status,
                'is_on_track': acc.overdue_amount <= 0
            })
            
        summary = {
            'total_students': len(data),
            'on_track': sum(1 for d in data if d['is_on_track']),
            'off_track': sum(1 for d in data if not d['is_on_track']),
            'total_overdue': sum(d['overdue_amount'] for d in data)
        }
        
        return Response({
            'summary': summary,
            'students': data
        })

class FeeStudent360APIView(APIView):
    permission_classes = [IsAuthenticated, CanViewAnalytics]

    def get(self, request, student_id):
        from students.models import Student
        from trainers.models import Attendance
        
        student = get_object_or_404(Student, id=student_id)
        account = StudentFeeAccount.objects.filter(student=student).first()
        
        attendance_qs = Attendance.objects.filter(student=student).order_by('-date')
        
        payload = {
            'student_info': {
                'id': student.id,
                'name': student.name,
                'email': student.email,
                'phone': student.phone,
                'branch': student.branch.name if student.branch else None,
                'batch': student.academic_batch.name if student.academic_batch else None,
            },
            'fee_account': None,
            'attendance_summary': {
                'total': attendance_qs.count(),
                'present': attendance_qs.filter(status='PRESENT').count(),
                'absent': attendance_qs.filter(status='ABSENT').count()
            },
            'recent_attendance': [
                {'date': a.date, 'status': a.status, 'approval_status': a.approval_status}
                for a in attendance_qs[:10]
            ]
        }
        
        if account:
            payload['fee_account'] = {
                'id': account.id,
                'plan_name': account.plan_name,
                'plan_type': account.plan_type,
                'status': account.status,
                'total_due': account.total_due,
                'total_paid': account.total_paid,
                'balance_due': account.balance_due,
                'overdue_amount': account.overdue_amount,
                'installments': [
                    {
                        'sequence': i.sequence_number,
                        'due_date': i.due_date,
                        'scheduled_amount': i.scheduled_amount,
                        'paid_amount': i.paid_amount,
                        'status': i.status
                    } for i in account.installments.all().order_by('sequence_number')
                ],
                'payments': [
                    {
                        'date': p.payment_date,
                        'amount': p.amount,
                        'method': p.payment_method,
                        'receipt': p.receipt_number
                    } for p in account.payments.all().order_by('-payment_date')
                ]
            }
            
        return Response(payload)
