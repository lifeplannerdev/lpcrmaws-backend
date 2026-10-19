import base64
import binascii
from decimal import Decimal

from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import escape
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import ActivityLog
from accounts.permissions import has_dynamic_permission
from students.models import Student

from .models import FeePayment, FeeReceipt, ReceiptSettings, StudentFeeAccount
from .permissions import (
    CanManageFees,
    CanManageReceipts,
    CanViewFees,
    _can_manage_receipt_admin_actions,
    _can_view_fee_account,
)
from .receipt_engine import (
    DEFAULT_DISPLAY_OPTIONS,
    amount_to_words,
    build_issuer_snapshot,
    calculate_receipt_financials,
    extract_account_ledger_snapshot,
    extract_student_metadata,
    get_indian_financial_year,
    get_or_create_receipt_settings,
    to_decimal,
)
from .serializers import (
    FeeReceiptSerializer,
    PublicReceiptVerificationSerializer,
    ReceiptSettingsSerializer,
)


def _is_global_fee_viewer(user):
    return (
        getattr(user, 'is_superuser', False)
        or has_dynamic_permission(user, 'fees:read_tenant')
        or has_dynamic_permission(user, 'fees:manage')
        or has_dynamic_permission(user, 'fees:view_reports')
        or has_dynamic_permission(user, 'flag:admin')
        or has_dynamic_permission(user, 'flag:fees')
    )


def _clean_display_options_response(opts):
    merged_opts = dict(DEFAULT_DISPLAY_OPTIONS)
    if isinstance(opts, dict):
        for k, v in opts.items():
            if k not in ('fy_sequences', 'active_fy'):
                merged_opts[k] = v
    return merged_opts


class ReceiptSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def get(self, request):
        company = (request.GET.get('company') or getattr(request.user, 'company', None) or 'FLAG').upper()
        campus_id = request.GET.get('campus') or request.GET.get('campus_id')

        if request.GET.get('list') == 'true':
            qs = ReceiptSettings.objects.filter(company=company).select_related('campus')
            if not qs.exists():
                get_or_create_receipt_settings(company=company, campus=None)
                qs = ReceiptSettings.objects.filter(company=company).select_related('campus')
            items = ReceiptSettingsSerializer(qs, many=True).data
            for item in items:
                item['default_display_options'] = _clean_display_options_response(item.get('default_display_options'))
            return Response(items)

        campus = None
        if campus_id and str(campus_id).isdigit():
            from students.models import Campus
            campus = Campus.objects.filter(pk=int(campus_id)).first()

        settings_obj = get_or_create_receipt_settings(company=company, campus=campus)
        data = ReceiptSettingsSerializer(settings_obj).data
        data['default_display_options'] = _clean_display_options_response(data.get('default_display_options'))
        return Response(data)

    def _upsert(self, request):
        if not _can_manage_receipt_admin_actions(request.user):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        company = (request.data.get('company') or getattr(request.user, 'company', None) or 'FLAG').upper()
        campus_id = request.data.get('campus')
        campus = None
        if campus_id not in (None, ''):
            from students.models import Campus
            campus = get_object_or_404(Campus, pk=campus_id)

        settings_obj = ReceiptSettings.objects.filter(company=company, campus=campus).first()
        if not settings_obj:
            settings_obj = ReceiptSettings(
                company=company,
                campus=campus,
                default_display_options=dict(DEFAULT_DISPLAY_OPTIONS),
            )

        existing_opts = dict(DEFAULT_DISPLAY_OPTIONS)
        if isinstance(settings_obj.default_display_options, dict):
            existing_opts.update(settings_obj.default_display_options)

        payload = {}
        if isinstance(request.data, dict):
            payload.update(request.data)
        else:
            payload.update(request.data.dict())

        incoming_opts = request.data.get('default_display_options')
        if isinstance(incoming_opts, dict):
            merged_opts = dict(existing_opts)
            for k, v in incoming_opts.items():
                if k not in ('fy_sequences', 'active_fy'):
                    merged_opts[k] = v
            payload['default_display_options'] = merged_opts
        else:
            payload['default_display_options'] = existing_opts

        serializer = ReceiptSettingsSerializer(settings_obj, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        saved = serializer.save(company=company, campus=campus, updated_by=request.user)

        if 'next_sequence_number' in request.data:
            opts_after = dict(saved.default_display_options or {})
            fy_seq = dict(opts_after.get('fy_sequences') or {})
            active_fy = opts_after.get('active_fy') or get_indian_financial_year(timezone.now())
            fy_seq[active_fy] = max(1, int(saved.next_sequence_number or 1))
            opts_after['fy_sequences'] = fy_seq
            opts_after['active_fy'] = active_fy
            saved.default_display_options = opts_after
            saved.save(update_fields=['default_display_options', 'updated_at'])

        ActivityLog.objects.create(
            user=request.user,
            company=company,
            action='STUDENT_UPDATED',
            entity_type='ReceiptSettings',
            entity_id=saved.id,
            entity_name=saved.organization_name,
            description=f"Receipt branding & numbering settings updated for {company}",
            metadata={'receipt_prefix': saved.receipt_prefix, 'default_gst_mode': saved.default_gst_mode},
        )
        resp_data = ReceiptSettingsSerializer(saved).data
        resp_data['default_display_options'] = _clean_display_options_response(resp_data.get('default_display_options'))
        return Response(resp_data)

    def post(self, request):
        return self._upsert(request)

    def put(self, request):
        return self._upsert(request)

    def patch(self, request):
        return self._upsert(request)


class FeeReceiptListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageReceipts]

    def get(self, request):
        qs = FeeReceipt.objects.select_related(
            'student', 'account', 'payment', 'created_by', 'updated_by', 'voided_by'
        )

        if not _is_global_fee_viewer(request.user):
            qs = qs.filter(Q(student__trainer=request.user) | Q(created_by=request.user))

        company = request.GET.get('company')
        status_filter = request.GET.get('status')
        doc_type = request.GET.get('document_type')
        payment_method = request.GET.get('payment_method')
        tax_mode = request.GET.get('tax_mode')
        student_id = request.GET.get('student')
        account_id = request.GET.get('account')
        payment_id = request.GET.get('payment')
        campus = request.GET.get('campus')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        search = request.GET.get('search')

        if company:
            qs = qs.filter(company=company.upper())
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        if doc_type:
            qs = qs.filter(document_type=doc_type.upper())
        if payment_method:
            qs = qs.filter(payment_method=payment_method.upper())
        if tax_mode:
            qs = qs.filter(tax_mode=tax_mode.upper())
        if student_id:
            qs = qs.filter(student_id=student_id)
        if account_id:
            qs = qs.filter(account_id=account_id)
        if payment_id:
            qs = qs.filter(payment_id=payment_id)
        if campus:
            if str(campus).isdigit():
                qs = qs.filter(student__campus_id=int(campus))
            else:
                qs = qs.filter(campus_name__icontains=campus)
        if start_date:
            qs = qs.filter(issue_date__date__gte=start_date)
        if end_date:
            qs = qs.filter(issue_date__date__lte=end_date)
        if search:
            qs = qs.filter(
                Q(receipt_number__icontains=search)
                | Q(recipient_name__icontains=search)
                | Q(recipient_phone__icontains=search)
                | Q(recipient_email__icontains=search)
                | Q(payment_reference__icontains=search)
                | Q(course_or_package_name__icontains=search)
                | Q(batch_name__icontains=search)
                | Q(student_enrollment_code__icontains=search)
            )

        receipts = qs.order_by('-issue_date', '-created_at')[:500]
        return Response(FeeReceiptSerializer(receipts, many=True).data)

    def post(self, request):
        serializer = FeeReceiptSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()
        return Response(FeeReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)


class FeeReceiptDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageReceipts]

    def get_object(self, request, pk):
        receipt = get_object_or_404(
            FeeReceipt.objects.select_related('student', 'account', 'payment', 'created_by', 'updated_by', 'voided_by'),
            pk=pk,
        )
        if not _is_global_fee_viewer(request.user):
            can_access = (
                receipt.created_by_id == request.user.id
                or getattr(receipt.student, 'trainer_id', None) == request.user.id
                or (receipt.account and _can_view_fee_account(request.user, receipt.account))
            )
            if not can_access:
                return None
        return receipt

    def get(self, request, pk):
        receipt = self.get_object(request, pk)
        if not receipt:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(FeeReceiptSerializer(receipt).data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def patch(self, request, pk):
        receipt = self.get_object(request, pk)
        if not receipt:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = FeeReceiptSerializer(receipt, data=request.data, context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(FeeReceiptSerializer(updated).data)

    def delete(self, request, pk):
        if not _can_manage_receipt_admin_actions(request.user):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        receipt = self.get_object(request, pk)
        if not receipt:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if receipt.status != 'DRAFT':
            return Response(
                {'detail': 'Issued receipts cannot be deleted for audit compliance. Please void the receipt instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        receipt.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FeeReceiptFromPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageReceipts]

    def post(self, request, payment_id):
        with transaction.atomic():
            payment = get_object_or_404(
                FeePayment.objects.select_for_update().select_related('account', 'account__student'),
                pk=payment_id,
            )
            if payment.account and not _can_view_fee_account(request.user, payment.account):
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

            force_new = str(request.data.get('force_new', 'false')).lower() in ('true', '1', 'yes')

            existing = (
                payment.receipts.exclude(status='VOID')
                .order_by('-created_at')
                .first()
            )

            if existing and not force_new:
                override_keys = set(request.data.keys()) - {'force_new', 'payment', 'account', 'student'}
                if override_keys:
                    serializer = FeeReceiptSerializer(existing, data=request.data, context={'request': request}, partial=True)
                    serializer.is_valid(raise_exception=True)
                    existing = serializer.save()
                return Response(FeeReceiptSerializer(existing).data, status=status.HTTP_200_OK)

            payload = {}
            if isinstance(request.data, dict):
                payload.update(request.data)
            else:
                payload.update(request.data.dict())
            payload.pop('force_new', None)
            payload['payment'] = payment.id
            payload['account'] = payment.account_id
            payload['student'] = payment.account.student_id
            if 'payment_date' not in payload and payment.payment_date:
                payload['payment_date'] = payment.payment_date
            if 'issue_date' not in payload:
                payload['issue_date'] = timezone.now()

            serializer = FeeReceiptSerializer(data=payload, context={'request': request})
            serializer.is_valid(raise_exception=True)
            receipt = serializer.save()
            return Response(FeeReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)


class FeeReceiptVoidAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageReceipts]

    def post(self, request, pk):
        if not _can_manage_receipt_admin_actions(request.user):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        receipt = get_object_or_404(FeeReceipt.objects.select_related('account', 'account__student'), pk=pk)
        if receipt.account and not _can_view_fee_account(request.user, receipt.account):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        reason = (request.data.get('void_reason') or request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'void_reason': 'A mandatory reason is required to void an official receipt.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if receipt.status == 'VOID':
            return Response(
                {'detail': 'Receipt is already voided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            receipt.status = 'VOID'
            receipt.payment_status_badge = 'VOID'
            receipt.void_reason = reason
            receipt.voided_at = timezone.now()
            receipt.voided_by = request.user
            receipt.updated_by = request.user
            receipt.version = (receipt.version or 1) + 1

            snap = dict(receipt.snapshot_data or {})
            revisions = list(snap.get('revisions') or [])
            revisions.append({
                'version': receipt.version,
                'action': 'VOIDED',
                'timestamp': receipt.voided_at.isoformat(),
                'actor': request.user.get_full_name() or request.user.username,
                'void_reason': reason,
                'receipt_number': receipt.receipt_number,
                'total_amount': str(receipt.total_amount),
                'status': 'VOID',
            })
            snap['revisions'] = revisions
            receipt.snapshot_data = snap
            receipt.save()

            ActivityLog.objects.create(
                user=request.user,
                company=receipt.company,
                action='STUDENT_UPDATED',
                entity_type='FeeReceipt',
                entity_id=receipt.id,
                entity_name=receipt.recipient_name,
                description=f"Receipt {receipt.receipt_number} VOIDED. Reason: {reason}",
                metadata={
                    'receipt_number': receipt.receipt_number,
                    'void_reason': reason,
                    'total_amount': str(receipt.total_amount),
                },
            )

        return Response(FeeReceiptSerializer(receipt).data, status=status.HTTP_200_OK)


class FeeReceiptCalculatePreviewAPIView(APIView):
    permission_classes = [IsAuthenticated, CanViewFees]

    def post(self, request):
        data = request.data
        for num_field in (
            'gst_rate', 'cgst_rate', 'sgst_rate', 'igst_rate',
            'subtotal_amount', 'discount_amount', 'total_amount',
        ):
            val = data.get(num_field)
            if val not in (None, '') and to_decimal(val) < Decimal('0.00'):
                return Response(
                    {num_field: f'{num_field} cannot be negative.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        payment_id = data.get('payment')
        account_id = data.get('account')
        student_id = data.get('student')

        payment = (
            get_object_or_404(FeePayment.objects.select_related('account', 'account__student', 'installment'), pk=payment_id)
            if payment_id not in (None, '')
            else None
        )
        account = (
            get_object_or_404(StudentFeeAccount.objects.select_related('student'), pk=account_id)
            if account_id not in (None, '')
            else None
        )
        student = (
            get_object_or_404(Student.objects.select_related('campus', 'batch', 'academic_package'), pk=student_id)
            if student_id not in (None, '')
            else None
        )

        if payment and account and payment.account_id != account.id:
            return Response(
                {'account': 'Selected payment does not belong to the specified fee account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if payment and not account:
            account = payment.account

        if account and student and account.student_id != student.id:
            return Response(
                {'student': 'Selected fee account does not belong to the specified student.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account and not student:
            student = account.student

        if student and not account:
            account = student.fee_account

        if account and not _can_view_fee_account(request.user, account):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if student and not account and not _is_global_fee_viewer(request.user):
            if getattr(student, 'trainer_id', None) != request.user.id:
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        company = (
            data.get('company')
            or (payment.company if payment else None)
            or (account.company if account else None)
            or (getattr(student, 'company', None) if student else None)
            or getattr(request.user, 'company', None)
            or 'FLAG'
        )
        campus = getattr(student, 'campus', None) if student else None
        settings_obj = get_or_create_receipt_settings(company=company, campus=campus)

        student_meta = extract_student_metadata(student) if student else {}
        ledger_meta = extract_account_ledger_snapshot(account, payment=payment)

        fallback_amount = (
            data.get('subtotal_amount')
            or data.get('total_amount')
            or (payment.amount if payment else Decimal('0.00'))
        )
        fallback_title = (
            data.get('course_or_package_name')
            or student_meta.get('course_or_package_name')
            or (account.plan_name if account else '')
            or 'Course Tuition Fee'
        )
        fallback_period = (
            data.get('installment_label')
            or (payment.installment.label if (payment and payment.installment) else '')
        )

        fin = calculate_receipt_financials(
            line_items=data.get('line_items'),
            subtotal_amount=fallback_amount,
            discount_amount=data.get('discount_amount', Decimal('0.00')),
            tax_mode=data.get('tax_mode') or settings_obj.default_gst_mode or 'NONE',
            supply_type=data.get('supply_type') or 'INTRA_STATE',
            gst_rate=data.get('gst_rate') if data.get('gst_rate') not in (None, '') else settings_obj.default_gst_rate,
            cgst_rate=data.get('cgst_rate'),
            sgst_rate=data.get('sgst_rate'),
            igst_rate=data.get('igst_rate'),
            default_sac=settings_obj.sac_code or '999293',
            fallback_title=fallback_title,
            fallback_period=fallback_period,
        )

        return Response({
            'student_metadata': student_meta,
            'ledger_snapshot': {
                k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in ledger_meta.items()
            },
            'financials': {
                k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in fin.items()
            },
            'issuer_snapshot': build_issuer_snapshot(settings_obj, company=company),
        })


FeeReceiptPreviewAPIView = FeeReceiptCalculatePreviewAPIView


class FeeReceiptSendEmailAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageReceipts]

    def post(self, request, pk):
        receipt = get_object_or_404(FeeReceipt.objects.select_related('student', 'account', 'account__student'), pk=pk)
        if receipt.account and not _can_view_fee_account(request.user, receipt.account):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        to_email = (
            request.data.get('to_email')
            or request.data.get('email')
            or receipt.recipient_email
            or (receipt.student.email if receipt.student else '')
            or ''
        ).strip()

        if not to_email or '@' not in to_email:
            return Response(
                {'to_email': 'A valid recipient email address is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = None
        pdf_base64 = request.data.get('pdf_base64')
        if pdf_base64:
            if not isinstance(pdf_base64, str):
                return Response(
                    {'pdf_base64': 'Invalid PDF attachment payload.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raw_b64 = ''.join(pdf_base64.split(',', 1)[-1].split())
            if len(raw_b64) > 14_000_000:
                return Response(
                    {'pdf_base64': 'PDF attachment exceeds the 10 MB maximum size limit.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                if not raw_b64:
                    raise ValueError('Empty base64 payload')
                pdf_bytes = base64.b64decode(raw_b64, validate=True)
            except (binascii.Error, ValueError):
                return Response(
                    {'pdf_base64': 'Invalid base64 encoding for PDF attachment.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not pdf_bytes.startswith(b'%PDF-'):
                return Response(
                    {'pdf_base64': 'Attachment is not a valid PDF document (missing %PDF- header).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        issuer_snap = receipt.issuer_snapshot or {}
        raw_org_name = issuer_snap.get('organization_name') or 'FLAG German Language Academy'
        raw_org_email = issuer_snap.get('email') or ''
        raw_org_phone = issuer_snap.get('phone') or ''

        subject = (
            request.data.get('subject')
            or f"Official Fee Receipt {receipt.receipt_number} - {raw_org_name}"
        ).strip()
        custom_message = (
            request.data.get('message')
            or 'Thank you for your payment. Please find the summary of your official digital receipt below:'
        ).strip()
        verify_url = request.data.get('verify_url') or f"/verify-receipt/{receipt.verification_token}"

        org_name = escape(raw_org_name)
        org_email = escape(raw_org_email)
        org_phone = escape(raw_org_phone)
        recipient_name = escape(receipt.recipient_name or '')
        receipt_num = escape(receipt.receipt_number or '')
        issue_date_str = escape(receipt.issue_date.strftime('%d %b %Y') if receipt.issue_date else '-')
        course_str = escape(receipt.course_or_package_name or '-')
        payment_mode = escape(
            f"{receipt.payment_method} ({receipt.payment_reference})"
            if receipt.payment_reference
            else str(receipt.payment_method or '')
        )
        total_str = escape(str(receipt.total_amount))
        words_str = escape(receipt.amount_in_words or '')
        custom_message_escaped = escape(custom_message)
        token_escaped = escape(receipt.verification_token or '')
        verify_url_escaped = escape(verify_url)
        contact_line = ' • '.join(filter(None, [org_email, org_phone]))

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
            <div style="background: #1e1b4b; color: #ffffff; padding: 24px;">
                <h2 style="margin: 0; font-size: 20px;">{org_name}</h2>
                <p style="margin: 4px 0 0; opacity: 0.85; font-size: 13px;">Official Digital Fee Receipt • {receipt_num}</p>
            </div>
            <div style="padding: 24px; color: #1e293b;">
                <p>Dear <strong>{recipient_name}</strong>,</p>
                <p>{custom_message_escaped}</p>
                <table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 14px;">
                    <tr><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; color: #64748b;">Receipt Number</td><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-weight: bold;">{receipt_num}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; color: #64748b;">Issue Date</td><td style="padding: 8px; border-bottom: 1px solid #f1f5f9;">{issue_date_str}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; color: #64748b;">Course / Package</td><td style="padding: 8px; border-bottom: 1px solid #f1f5f9;">{course_str}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; color: #64748b;">Payment Mode</td><td style="padding: 8px; border-bottom: 1px solid #f1f5f9;">{payment_mode}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; color: #64748b;">Total Amount</td><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-weight: bold; color: #047857;">₹{total_str}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #f1f5f9; color: #64748b;">Amount in Words</td><td style="padding: 8px; border-bottom: 1px solid #f1f5f9;">{words_str}</td></tr>
                </table>
                <p style="font-size: 12px; color: #64748b;">Verification Token: <code>{token_escaped}</code> ({verify_url_escaped})</p>
                {f'<p style="font-size: 11px; color: #94a3b8; margin-top: 12px;">Contact: {contact_line}</p>' if contact_line else ''}
            </div>
        </div>
        """
        text_body = (
            f"{raw_org_name}\n"
            f"Official Receipt: {receipt.receipt_number}\n"
            f"Recipient: {receipt.recipient_name}\n"
            f"Total Amount: INR {receipt.total_amount} ({receipt.amount_in_words})\n"
            f"Verify authenticity: {verify_url}\n"
        )

        sent_ok = False
        error_detail = ''
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                to=[to_email],
            )
            msg.attach_alternative(html_body, "text/html")

            if pdf_bytes is not None:
                safe_num = receipt.receipt_number.replace('/', '_')
                msg.attach(f"Receipt_{safe_num}.pdf", pdf_bytes, "application/pdf")

            msg.send(fail_silently=False)
            sent_ok = True
        except Exception as exc:
            error_detail = str(exc)

        snap = dict(receipt.snapshot_data or {})
        email_logs = list(snap.get('email_dispatches') or [])
        email_logs.append({
            'to_email': to_email,
            'subject': subject,
            'timestamp': timezone.now().isoformat(),
            'sent_by': request.user.get_full_name() or request.user.username,
            'delivered_via_smtp': sent_ok,
        })
        snap['email_dispatches'] = email_logs
        receipt.snapshot_data = snap
        if not receipt.recipient_email:
            receipt.recipient_email = to_email
        receipt.save(update_fields=['snapshot_data', 'recipient_email', 'updated_at'])

        ActivityLog.objects.create(
            user=request.user,
            company=receipt.company,
            action='STUDENT_UPDATED',
            entity_type='FeeReceipt',
            entity_id=receipt.id,
            entity_name=receipt.recipient_name,
            description=f"Receipt {receipt.receipt_number} emailed to {to_email}",
            metadata={'to_email': to_email, 'sent_ok': sent_ok, 'error': error_detail},
        )

        if not sent_ok:
            return Response(
                {
                    'error': 'Failed to send email via SMTP server.',
                    'detail': error_detail,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            'status': 'sent',
            'to_email': to_email,
            'receipt_number': receipt.receipt_number,
            'detail': 'Receipt email dispatched successfully.',
        })


class PublicReceiptVerifyAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, verification_token):
        token = (verification_token or '').strip()
        receipt = (
            FeeReceipt.objects.select_related('created_by')
            .filter(verification_token=token)
            .first()
        )
        if not receipt:
            return Response(
                {
                    'verified': False,
                    'is_authentic': False,
                    'verification_status': 'NOT_FOUND',
                    'detail': 'No official receipt matches this verification token.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(PublicReceiptVerificationSerializer(receipt).data, status=status.HTTP_200_OK)


PublicReceiptVerificationAPIView = PublicReceiptVerifyAPIView
