import openpyxl
from io import BytesIO
from datetime import datetime

from django.db.models import Q, Sum, Count
from django.http import HttpResponse
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination

class FdsPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 250

from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import User
from .models import (
    FdsFeeStructure, FdsBatch, FdsEnquiry, FdsTrial,
    FdsStudent, FdsWeddingGroup, FdsAttendance, FdsFeesCollection,
    FdsStudentFeeAccount, FdsFeeInstallment, FdsFeeAdjustment
)
from .serializers import (
    FdsFeeStructureSerializer, FdsBatchSerializer,
    FdsEnquirySerializer, FdsTrialSerializer,
    FdsStudentSerializer, FdsWeddingGroupSerializer,
    FdsAttendanceSerializer, FdsAttendanceBulkSerializer,
    FdsFeesCollectionSerializer, FdsStudentFeeAccountSerializer,
    FdsStudentFeeAccountCreateSerializer, FdsFeeInstallmentSerializer,
    FdsFeeAdjustmentSerializer
)


from accounts.permissions import has_dynamic_permission

# ── Permission helper ─────────────────────────────────────────────

def has_fds_permission(user, *perms):
    """Check if user has any of the given FDS permissions."""
    return any(has_dynamic_permission(user, p) for p in perms)

def fds_admin_all(user):
    return has_fds_permission(user, 'fds:admin')

def fds_admin_own(user):
    return has_fds_permission(user, 'fds:admin_own')

def fds_write(user):
    return has_fds_permission(user, 'fds:admin', 'fds:admin_own')

def fds_read(user):
    return has_fds_permission(user, 'fds:admin', 'fds:admin_own', 'fds:view')

def fds_fees_access(user):
    return has_fds_permission(user, 'fds:admin', 'fds_fees:view')


# ── Fee Structure ────────────────────────────────────────────────

class FdsFeeStructureViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsFeeStructureSerializer
    queryset = FdsFeeStructure.objects.all()

    def get_queryset(self):
        if not fds_read(self.request.user) and not fds_fees_access(self.request.user):
            return FdsFeeStructure.objects.none()
        qs = FdsFeeStructure.objects.all()
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return qs

    def check_write_permission(self):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")

    def create(self, request, *args, **kwargs):
        self.check_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_write_permission()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.check_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    @action(detail=False, methods=['post'])
    def bulk_import_excel(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        data = request.data.get('records', [])
        created = 0
        from datetime import datetime
        for row in data:
            try:
                date_str = row.get('date')
                if date_str:
                    date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
                else:
                    date_val = datetime.now().date()
            except Exception:
                date_val = datetime.now().date()

            FdsEnquiry.objects.create(
                date=date_val,
                name=row.get('name', ''),
                location=row.get('location', ''),
                age=row.get('age') or None,
                phone=row.get('phone', ''),
                whatsapp_no=row.get('whatsapp_no', ''),
                preferred_timing=row.get('preferred_timing', ''),
                remarks=row.get('remarks', ''),
                source=row.get('source', 'WALK_IN'),
                class_interest=row.get('class_interest', 'DANCE'),
                created_by=request.user,
            )
            created += 1
        return Response({"created": created, "skipped": 0})

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file)
            ws = wb['FEES STRUCTURE'] if 'FEES STRUCTURE' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            cat_map = {
                'Monthly Fee': 'MONTHLY',
                'Package 3 months': 'PACKAGE_3M',
                'Package 6 months': 'PACKAGE_6M',
                'Admissions /Registration Fee': 'ADMISSION',
                'Trial Fee': 'TRIAL',
                'Wedding - Basic': 'WEDDING_BASIC',
                'Wedding -Couple': 'WEDDING_COUPLE',
                'Wedding -Premium': 'WEDDING_PREMIUM',
                'Wedding - Family /Group': 'WEDDING_GROUP'
            }
            
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0: continue
                raw_cat = str(row[0]).strip() if row[0] else ''
                if not raw_cat or raw_cat not in cat_map:
                    skipped += 1
                    continue
                
                cat_key = cat_map[raw_cat]
                details = str(row[1]).strip() if row[1] else ''
                
                try:
                    amount = float(str(row[2]).replace(',', '').strip()) if row[2] else 0.0
                except:
                    amount = 0.0
                    
                notes = str(row[3]).strip() if row[3] else ''
                
                obj, is_new = FdsFeeStructure.objects.update_or_create(
                    category=cat_key,
                    defaults={'details': details, 'amount': amount, 'notes': notes}
                )
                if is_new: created += 1
                else: updated += 1
                
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# ── Batch ────────────────────────────────────────────────────────

class FdsBatchViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsBatchSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['class_category', 'batch_type', 'status', 'trainer']
    search_fields = ['name']
    ordering = ['class_category', 'name', '-id']
    pagination_class = FdsPagination


    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsBatch.objects.none()
        qs = FdsBatch.objects.select_related('trainer').all()
        trainer_id = self.request.query_params.get('trainer')
        if trainer_id:
            qs = qs.filter(trainer_id=trainer_id)
        elif getattr(self.request.user, 'role', None) == 'TRAINER':
            qs = qs.filter(trainer=self.request.user)
        return qs


    def check_write_permission(self):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")

    def create(self, request, *args, **kwargs):
        self.check_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_write_permission()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.check_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def students(self, request, pk=None):
        """List all students in this batch."""
        batch = self.get_object()
        students = FdsStudent.objects.filter(batch=batch, is_active=True)
        serializer = FdsStudentSerializer(students, many=True)
        return Response(serializer.data)


# ── Enquiry ──────────────────────────────────────────────────────

class FdsEnquiryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsEnquirySerializer
    pagination_class = FdsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'class_interest', 'source', 'joined']
    search_fields = ['name', 'phone', 'whatsapp_no', 'enquiry_id', 'location']
    ordering_fields = ['date', 'name', 'created_at', 'status']
    ordering = ['-date', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsEnquiry.objects.none()
        qs = FdsEnquiry.objects.select_related('created_by').prefetch_related('trials')
        
        if fds_admin_all(self.request.user):
            location = self.request.query_params.get('location')
            if location:
                qs = qs.filter(location__icontains=location)
        elif fds_admin_own(self.request.user):
            qs = qs.filter(created_by=self.request.user)

        # Date range filter
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        # Follow-up due filter
        follow_up_due = self.request.query_params.get('follow_up_due')
        if follow_up_due:
            from django.utils import timezone
            today = timezone.now().date()
            qs = qs.filter(
                Q(follow_up_1__lte=today) | Q(follow_up_2__lte=today),
                ~Q(status__in=['CONVERTED', 'LOST'])
            )

        status_in = self.request.query_params.get('status__in')
        if status_in:
            qs = qs.filter(status__in=status_in.split(','))

        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        student = serializer.save()
        if hasattr(student, 'fee_account'):
            if student.fee_account.active_package != student.fee_structure:
                student.fee_account.active_package = student.fee_structure
                # If package changed, we might want to update total_due? 
                # For simplicity, we just change the active_package. Recalculate handles past invoices.
                student.fee_account.save(update_fields=['active_package'])

    def update(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        from django.utils import timezone
        today = timezone.now().date()
        return Response({
            'total': qs.count(),
            'new': qs.filter(status='NEW').count(),
            'contacted': qs.filter(status='CONTACTED').count(),
            'trial_scheduled': qs.filter(status='TRIAL_SCHEDULED').count(),
            'converted': qs.filter(status='CONVERTED').count(),
            'lost': qs.filter(status='LOST').count(),
            'by_class': {
                'dance': qs.filter(class_interest='DANCE').count(),
                'zumba': qs.filter(class_interest='ZUMBA').count(),
                'yoga': qs.filter(class_interest='YOGA').count(),
            },
            'follow_up_due': qs.filter(
                Q(follow_up_1__lte=today) | Q(follow_up_2__lte=today),
                ~Q(status__in=['CONVERTED', 'LOST'])
            ).count(),
        })

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export enquiries to Excel matching the original template."""
        if not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ENQUIRY"
        headers = [
            'Enquiry ID', 'Date', 'Name', 'Location', 'Age', 'Source',
            'Phone', "What's App no.", 'Preffered Timing', 'Status',
            'Follow Up1', 'Follow Up 2', 'Joined Or Not', 'Remarks / Concerns',
            'Class Interest'
        ]
        ws.append(headers)
        for e in qs:
            ws.append([
                e.enquiry_id, e.date.strftime('%d/%m/%Y') if e.date else '',
                e.name, e.location or '', e.age or '',
                e.get_source_display(), e.phone or '', e.whatsapp_no or '',
                e.preferred_timing or '', e.get_status_display(),
                e.follow_up_1.strftime('%d/%m/%Y') if e.follow_up_1 else '',
                e.follow_up_2.strftime('%d/%m/%Y') if e.follow_up_2 else '',
                'Yes' if e.joined else 'No',
                e.remarks or '', e.get_class_interest_display(),
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Enquiries.xlsx"'
        return resp

    @action(detail=False, methods=['post'])
    @action(detail=False, methods=['post'])
    def bulk_import_excel(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        data = request.data.get('records', [])
        created = 0
        from datetime import datetime
        for row in data:
            try:
                date_str = row.get('date')
                if date_str:
                    date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
                else:
                    date_val = datetime.now().date()
            except Exception:
                date_val = datetime.now().date()

            FdsEnquiry.objects.create(
                date=date_val,
                name=row.get('name', ''),
                location=row.get('location', ''),
                age=row.get('age') or None,
                phone=row.get('phone', ''),
                whatsapp_no=row.get('whatsapp_no', ''),
                preferred_timing=row.get('preferred_timing', ''),
                remarks=row.get('remarks', ''),
                source=row.get('source', 'WALK_IN'),
                class_interest=row.get('class_interest', 'DANCE'),
                created_by=request.user,
            )
            created += 1
        return Response({"created": created, "skipped": 0})

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        """Import enquiries from Excel."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file)
            ws = wb.active
            created, skipped = 0, 0
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    continue  # Skip header
                if not row[2]:  # Name required
                    skipped += 1
                    continue
                raw_date = row[1]
                if isinstance(raw_date, datetime):
                    date = raw_date.date()
                elif isinstance(raw_date, str):
                    try:
                        date = datetime.strptime(raw_date, '%d/%m/%Y').date()
                    except Exception:
                        date = datetime.now().date()
                else:
                    date = datetime.now().date()
                FdsEnquiry.objects.create(
                    date=date,
                    name=str(row[2]).strip(),
                    location=str(row[3]).strip() if row[3] else '',
                    age=int(row[4]) if row[4] and str(row[4]).isdigit() else None,
                    phone=str(row[6]).strip() if row[6] else '',
                    whatsapp_no=str(row[7]).strip() if row[7] else '',
                    preferred_timing=str(row[8]).strip() if row[8] else '',
                    remarks=str(row[13]).strip() if row[13] else '',
                    created_by=request.user,
                )
                created += 1
            return Response({"created": created, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# ── Trial ────────────────────────────────────────────────────────

class FdsTrialViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsTrialSerializer
    pagination_class = FdsPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'class_category', 'converted']
    search_fields = ['name', 'phone', 'trial_id']
    ordering_fields = ['date', 'name', 'created_at']
    ordering = ['-date', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsTrial.objects.none()
        qs = FdsTrial.objects.select_related('enquiry', 'conducted_by', 'created_by')
        
        if fds_admin_all(self.request.user):
            location = self.request.query_params.get('location')
            if location:
                qs = qs.filter(location__icontains=location)
        elif fds_admin_own(self.request.user):
            qs = qs.filter(created_by=self.request.user)
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        follow_up_due = self.request.query_params.get('follow_up_due')
        if follow_up_due:
            from django.utils import timezone
            today = timezone.now().date()
            qs = qs.filter(follow_up_date__lte=today, converted=False)

        status_in = self.request.query_params.get('status__in')
        if status_in:
            qs = qs.filter(status__in=status_in.split(','))

        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        trial = serializer.save(created_by=self.request.user)
        if trial.enquiry:
            trial.enquiry.status = 'TRIAL_SCHEDULED'
            trial.enquiry.save(update_fields=['status'])

    def perform_update(self, serializer):
        student = serializer.save()
        if hasattr(student, 'fee_account'):
            if student.fee_account.active_package != student.fee_structure:
                student.fee_account.active_package = student.fee_structure
                # If package changed, we might want to update total_due? 
                # For simplicity, we just change the active_package. Recalculate handles past invoices.
                student.fee_account.save(update_fields=['active_package'])

    def update(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        ratings = []
        for r in qs.exclude(trainer_rating__isnull=True).values_list('trainer_rating', flat=True):
            try:
                if r is not None and str(r).strip() != '':
                    ratings.append(float(r))
            except (ValueError, TypeError):
                pass
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
        return Response({
            'total': qs.count(),
            'scheduled': qs.filter(status='SCHEDULED').count(),
            'completed': qs.filter(status='COMPLETED').count(),
            'no_show': qs.filter(status='NO_SHOW').count(),
            'cancelled': qs.filter(status='CANCELLED').count(),
            'converted': qs.filter(converted=True).count(),
            'conversion_rate': round(
                qs.filter(converted=True).count() / qs.filter(status='COMPLETED').count() * 100, 1
            ) if qs.filter(status='COMPLETED').count() > 0 else 0,
            'avg_rating': avg_rating,
            'by_class': {
                'dance': qs.filter(class_category='DANCE').count(),
                'zumba': qs.filter(class_category='ZUMBA').count(),
                'yoga': qs.filter(class_category='YOGA').count(),
            },
        })

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        if not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TRIAL"
        ws.append([
            'TRIAL ID', 'DATE', 'TIME', 'NAME', 'AGE', 'PHONE', 'LOCATION',
            'CLASS CATEGORY', 'FEE QUOTED', 'FEEDBACK', 'TRAINER RATING(IN 5)',
            'STATUS', 'CONVERTED', 'JOIN DATE', 'FOLLOW UP DATE', 'REMARKS'
        ])
        for t in qs:
            ws.append([
                t.trial_id,
                t.date.strftime('%d/%m/%Y') if t.date else '',
                t.time.strftime('%H:%M') if t.time else '',
                t.name, t.age or '', t.phone or '', t.location or '',
                t.get_class_category_display(),
                float(t.fee_quoted),
                t.feedback or '', t.trainer_rating or '',
                t.get_status_display(),
                'Yes' if t.converted else 'No',
                t.join_date.strftime('%d/%m/%Y') if t.join_date else '',
                t.follow_up_date.strftime('%d/%m/%Y') if t.follow_up_date else '',
                t.remarks or '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Trials.xlsx"'
        return resp


# ── Student ──────────────────────────────────────────────────────

class FdsStudentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsStudentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'batch', 'batch__class_category', 'student_type', 'gender', 'media_consent', 'can_leave_alone']
    search_fields = ['name', 'student_id', 'contact_no', 'whatsapp_no', 'parent_name']
    ordering_fields = ['name', 'joining_date', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsStudent.objects.none()
        qs = FdsStudent.objects.select_related(
            'batch', 'fee_structure', 'created_by', 'enquiry', 'trial'
        ).prefetch_related('fds_attendances')

        if fds_admin_all(self.request.user):
            trainer_id = self.request.query_params.get('trainer')
            if trainer_id:
                qs = qs.filter(batch__trainer_id=trainer_id)
        elif fds_admin_own(self.request.user):
            qs = qs.filter(created_by=self.request.user)

        # Class category filter (via batch)
        class_cat = self.request.query_params.get('class_category')
        if class_cat:
            qs = qs.filter(batch__class_category=class_cat)

        date_from = self.request.query_params.get('joining_date_from')
        date_to = self.request.query_params.get('joining_date_to')
        if date_from:
            qs = qs.filter(joining_date__gte=date_from)
        if date_to:
            qs = qs.filter(joining_date__lte=date_to)

        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        student = serializer.save(created_by=self.request.user)
        
        if student.enquiry:
            student.enquiry.status = 'CONVERTED'
            student.enquiry.joined = True
            student.enquiry.save(update_fields=['status', 'joined'])
        if student.trial:
            student.trial.status = 'COMPLETED'
            student.trial.converted = True
            student.trial.save(update_fields=['status', 'converted'])
            
        # Automatically create FdsStudentFeeAccount based on their selected fee package
        from .models import FdsStudentFeeAccount
        account = FdsStudentFeeAccount.objects.create(
            student=student,
            active_package=student.fee_structure
        )
        if student.fee_structure:
            account.total_due = student.fee_structure.amount
            account.balance_due = student.fee_structure.amount
            account.save(update_fields=['total_due', 'balance_due'])

    def perform_update(self, serializer):
        student = serializer.save()
        if hasattr(student, 'fee_account'):
            if student.fee_account.active_package != student.fee_structure:
                student.fee_account.active_package = student.fee_structure
                # If package changed, we might want to update total_due? 
                # For simplicity, we just change the active_package. Recalculate handles past invoices.
                student.fee_account.save(update_fields=['active_package'])

    def update(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        if not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "REGISTRATION DETAILS"
        ws.append([
            'Student ID', 'Name ', 'Joining Date', 'Age &Gender', 'Parent Name ',
            'Contact No.', 'Emergency contact NO.', 'Batch/Time', 'Medical Condition',
            'Media Consent', 'Pickup Person 1 NO.', 'Can Leave alone',
            'Admission Fee Paid Date', 'Class Category', 'Fee Type'
        ])
        for s in qs:
            age_gender = f"{s.age or ''} / {s.get_gender_display() if s.gender else ''}".strip(' /')
            ws.append([
                s.student_id, s.name,
                s.joining_date.strftime('%d/%m/%Y') if s.joining_date else '',
                age_gender, s.parent_name or '',
                s.contact_no or '', s.emergency_contact_no or '',
                str(s.batch) if s.batch else '',
                s.medical_condition or '',
                'Yes' if s.media_consent else 'No',
                s.pickup_person_1_no or '',
                'Yes' if s.can_leave_alone else 'No',
                s.admission_fee_paid_date.strftime('%d/%m/%Y') if s.admission_fee_paid_date else '',
                s.class_category or '',
                str(s.fee_structure) if s.fee_structure else '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Students.xlsx"'
        return resp

    @action(detail=False, methods=['post'])
    @action(detail=False, methods=['post'])
    def bulk_import_excel(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        data = request.data.get('records', [])
        created = 0
        from datetime import datetime
        for row in data:
            try:
                date_str = row.get('date')
                if date_str:
                    date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
                else:
                    date_val = datetime.now().date()
            except Exception:
                date_val = datetime.now().date()

            FdsEnquiry.objects.create(
                date=date_val,
                name=row.get('name', ''),
                location=row.get('location', ''),
                age=row.get('age') or None,
                phone=row.get('phone', ''),
                whatsapp_no=row.get('whatsapp_no', ''),
                preferred_timing=row.get('preferred_timing', ''),
                remarks=row.get('remarks', ''),
                source=row.get('source', 'WALK_IN'),
                class_interest=row.get('class_interest', 'DANCE'),
                created_by=request.user,
            )
            created += 1
        return Response({"created": created, "skipped": 0})

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file)
            ws = wb.active
            created, skipped = 0, 0
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    continue
                if not row[1]:
                    skipped += 1
                    continue
                raw_date = row[2]
                if isinstance(raw_date, datetime):
                    joining_date = raw_date.date()
                elif isinstance(raw_date, str):
                    try:
                        joining_date = datetime.strptime(raw_date, '%d/%m/%Y').date()
                    except Exception:
                        joining_date = datetime.now().date()
                else:
                    joining_date = datetime.now().date()
                FdsStudent.objects.create(
                    name=str(row[1]).strip(),
                    joining_date=joining_date,
                    parent_name=str(row[4]).strip() if row[4] else '',
                    contact_no=str(row[5]).strip() if row[5] else '',
                    emergency_contact_no=str(row[6]).strip() if row[6] else '',
                    medical_condition=str(row[8]).strip() if row[8] else '',
                    media_consent=str(row[9]).strip().lower() in ['yes', 'true', '1'] if row[9] else False,
                    pickup_person_1_no=str(row[10]).strip() if row[10] else '',
                    can_leave_alone=str(row[11]).strip().lower() in ['yes', 'true', '1'] if row[11] else False,
                    created_by=request.user,
                )
                created += 1
            return Response({"created": created, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


# ── Wedding Group ─────────────────────────────────────────────────

class FdsWeddingGroupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsWeddingGroupSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'package_type', 'trainer']
    search_fields = ['event_name', 'lead_contact_name', 'group_id', 'lead_contact_phone']
    ordering_fields = ['event_date', 'created_at', 'event_name']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsWeddingGroup.objects.none()
        qs = FdsWeddingGroup.objects.select_related('batch', 'trainer', 'created_by')
        
        if fds_admin_all(self.request.user):
            trainer_id = self.request.query_params.get('trainer')
            if trainer_id:
                qs = qs.filter(trainer_id=trainer_id)
        elif fds_admin_own(self.request.user):
            qs = qs.filter(created_by=self.request.user)
            
        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        student = serializer.save()
        if hasattr(student, 'fee_account'):
            if student.fee_account.active_package != student.fee_structure:
                student.fee_account.active_package = student.fee_structure
                # If package changed, we might want to update total_due? 
                # For simplicity, we just change the active_package. Recalculate handles past invoices.
                student.fee_account.save(update_fields=['active_package'])

    def update(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)


# ── Attendance ────────────────────────────────────────────────────

class FdsAttendanceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsAttendanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['batch', 'date', 'status', 'class_category', 'late_arrival']
    search_fields = ['student__name', 'student__student_id']
    ordering_fields = ['date', 'class_category']
    ordering = ['-date', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsAttendance.objects.none()
        qs = FdsAttendance.objects.select_related('student', 'batch', 'marked_by')
        
        if fds_admin_all(self.request.user):
            trainer_id = self.request.query_params.get('trainer')
            if trainer_id:
                qs = qs.filter(batch__trainer_id=trainer_id)
        elif fds_admin_own(self.request.user):
            qs = qs.filter(marked_by=self.request.user)
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        student_id = self.request.query_params.get('student')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        # Auto-fill time fields from batch
        batch = serializer.validated_data.get('batch')
        if batch:
            serializer.save(
                marked_by=self.request.user,
                class_start_time=batch.time_slot_start,
                class_end_time=batch.time_slot_end,
                class_category=batch.class_category,
            )
        else:
            serializer.save(marked_by=self.request.user)

    def perform_update(self, serializer):
        student = serializer.save()
        if hasattr(student, 'fee_account'):
            if student.fee_account.active_package != student.fee_structure:
                student.fee_account.active_package = student.fee_structure
                # If package changed, we might want to update total_due? 
                # For simplicity, we just change the active_package. Recalculate handles past invoices.
                student.fee_account.save(update_fields=['active_package'])

    def update(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    def bulk_mark(self, request):
        """Mark attendance for all students in a batch on a date."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        serializer = FdsAttendanceBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            batch = FdsBatch.objects.get(id=data['batch_id'])
        except FdsBatch.DoesNotExist:
            return Response({"error": "Batch not found."}, status=404)

        created, updated = 0, 0
        for record in data['records']:
            student_id = record.get('student_id')
            att_status = record.get('status', 'PRESENT')
            late_arrival = record.get('late_arrival', False)
            notes = record.get('notes', '')
            try:
                student = FdsStudent.objects.get(id=student_id)
            except FdsStudent.DoesNotExist:
                continue
            obj, is_new = FdsAttendance.objects.update_or_create(
                student=student,
                batch=batch,
                date=data['date'],
                defaults={
                    'status': att_status,
                    'late_arrival': late_arrival,
                    'notes': notes,
                    'marked_by': request.user,
                    'class_start_time': batch.time_slot_start,
                    'class_end_time': batch.time_slot_end,
                    'class_category': batch.class_category,
                }
            )
            if is_new:
                created += 1
            else:
                updated += 1
        return Response({"created": created, "updated": updated})

    @action(detail=False, methods=['get'])
    def monthly_report(self, request):
        """Per-student monthly attendance summary for a batch."""
        if not fds_read(request.user):
            return Response(status=403)
        batch_id = request.query_params.get('batch_id')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        if not all([batch_id, month, year]):
            return Response({"error": "batch_id, month, and year are required."}, status=400)
        atts = FdsAttendance.objects.filter(
            batch_id=batch_id, date__month=month, date__year=year
        ).select_related('student')
        # Group by student
        report = {}
        for att in atts:
            sid = att.student.student_id
            if sid not in report:
                report[sid] = {
                    'student_id': att.student.student_id,
                    'name': att.student.name,
                    'days': {}
                }
            report[sid]['days'][str(att.date)] = att.status
        # Add summary counts
        for sid in report:
            days = report[sid]['days']
            report[sid]['present'] = sum(1 for v in days.values() if v == 'PRESENT')
            report[sid]['absent'] = sum(1 for v in days.values() if v == 'ABSENT')
            report[sid]['leave'] = sum(1 for v in days.values() if v == 'LEAVE')
            report[sid]['total'] = len(days)
            report[sid]['pct'] = round(report[sid]['present'] / report[sid]['total'] * 100, 1) if report[sid]['total'] else 0
        return Response(list(report.values()))


# ── Fees Collection ───────────────────────────────────────────────

from .serializers import FdsStudentFeeAccountSerializer
from .models import FdsStudentFeeAccount

class FdsStudentFeeAccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsStudentFeeAccountSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'active_package', 'plan_type']
    search_fields = ['student__name', 'student__student_id', 'plan_name', 'plan_code']
    ordering_fields = ['updated_at', 'balance_due', 'total_due', 'total_paid']
    ordering = ['-updated_at']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FdsStudentFeeAccountCreateSerializer
        return FdsStudentFeeAccountSerializer

    def get_queryset(self):
        if not fds_fees_access(self.request.user) and not fds_read(self.request.user):
            return FdsStudentFeeAccount.objects.none()

        qs = FdsStudentFeeAccount.objects.select_related(
            'student', 'student__batch', 'student__batch__trainer', 'active_package'
        ).prefetch_related('installments', 'payments', 'adjustments')

        student_id = self.request.query_params.get('student_id') or self.request.query_params.get('student')
        class_cat = self.request.query_params.get('class_category')
        status_filter = self.request.query_params.get('status')
        plan_type = self.request.query_params.get('plan_type')
        search = self.request.query_params.get('search')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if class_cat and class_cat != 'ALL':
            qs = qs.filter(student__batch__class_category=class_cat)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        if search:
            qs = qs.filter(
                Q(student__name__icontains=search) |
                Q(student__student_id__icontains=search) |
                Q(plan_name__icontains=search) |
                Q(plan_code__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save()

    def perform_update(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        if not fds_write(request.user):
            self.permission_denied(request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def recalculate(self, request, pk=None):
        account = self.get_object()
        account.recalculate(save=True)
        return Response({'status': 'recalculated', 'balance_due': account.balance_due, 'total_due': account.total_due, 'total_paid': account.total_paid})

    @action(detail=True, methods=['post'], url_path='payments')
    def record_payment(self, request, pk=None):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        account = self.get_object()
        data = request.data

        amount = Decimal(str(data.get('amount') or data.get('paid_amount') or 0))
        if amount <= 0:
            return Response({"error": "Payment amount must be greater than 0."}, status=400)

        installment_id = data.get('installment') or data.get('installment_id')
        installment = None
        if installment_id:
            installment = account.installments.filter(id=installment_id).first()

        fees_type = None
        fees_type_id = data.get('fees_type') or data.get('fees_type_id')
        if fees_type_id:
            fees_type = FdsFeeStructure.objects.filter(id=fees_type_id).first()
        if not fees_type:
            fees_type = account.active_package or (account.student.fee_structure if account.student else None) or FdsFeeStructure.objects.filter(is_active=True).first()
            if not fees_type:
                fees_type = FdsFeeStructure.objects.first()

        pay_date = data.get('pay_date') or data.get('payment_date')
        if pay_date:
            if 'T' in str(pay_date):
                pay_date = pay_date.split('T')[0]
        else:
            pay_date = timezone.localdate()

        mode_of_pay = data.get('mode_of_pay') or data.get('payment_method') or 'CASH'
        remarks = data.get('remarks') or data.get('notes') or ''
        pdf_link = data.get('pdf_link') or ''
        fee_month = data.get('fee_month')
        fee_year = data.get('fee_year')

        with transaction.atomic():
            payment = FdsFeesCollection.objects.create(
                account=account,
                student=account.student,
                installment=installment,
                fees_type=fees_type,
                pay_date=pay_date,
                paid_amount=amount,
                total_fees=amount,
                mode_of_pay=mode_of_pay,
                remarks=remarks,
                pdf_link=pdf_link,
                fee_month=fee_month,
                fee_year=fee_year,
                collected_by=request.user,
            )

            if installment:
                installment.paid_amount += amount
                installment.recalculate(save=True)
            elif account.installments.exists():
                rem = amount
                for inst in account.installments.filter(status__in=['PENDING', 'PARTIAL', 'OVERDUE']).order_by('sequence_number'):
                    if rem <= 0:
                        break
                    needed = inst.scheduled_amount - inst.paid_amount
                    if needed > 0:
                        alloc = min(rem, needed)
                        inst.paid_amount += alloc
                        rem -= alloc
                        inst.recalculate(save=True)

            account.recalculate(save=True)

        return Response(FdsFeesCollectionSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='restructure')
    def restructure(self, request, pk=None):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        account = self.get_object()
        data = request.data

        with transaction.atomic():
            template_id = data.get('template_id') or data.get('package_id')
            if template_id and template_id != 'custom':
                pkg = FdsFeeStructure.objects.filter(id=template_id).first()
                if pkg:
                    account.active_package = pkg
                    account.plan_code = pkg.category
                    account.plan_name = pkg.get_category_display()
                    account.total_due = pkg.amount

            if data.get('plan_type'):
                account.plan_type = data['plan_type']
            if data.get('total_due') is not None and str(data.get('total_due')).strip() != '':
                account.total_due = Decimal(str(data['total_due']))
            if data.get('registration_amount') is not None and str(data.get('registration_amount')).strip() != '':
                account.registration_amount = Decimal(str(data['registration_amount']))
            if data.get('due_day'):
                account.due_day = int(data['due_day'])
            if data.get('next_due_date'):
                account.next_due_date = data['next_due_date']

            account.status = 'RESTRUCTURED'
            account.save()

            notes = data.get('notes') or 'Plan restructured'
            FdsFeeAdjustment.objects.create(
                account=account,
                adjustment_type='RESTRUCTURE',
                amount_delta=Decimal('0'),
                reason=notes,
                created_by=request.user,
            )

            installments_data = data.get('installments')
            if installments_data:
                account.installments.all().delete()
                new_insts = []
                for idx, item in enumerate(installments_data, start=1):
                    new_insts.append(FdsFeeInstallment(
                        account=account,
                        sequence_number=idx,
                        label=item.get('label') or f'Installment {idx}',
                        due_date=item['due_date'],
                        scheduled_amount=Decimal(str(item['scheduled_amount'])),
                        paid_amount=Decimal('0'),
                        balance_amount=Decimal(str(item['scheduled_amount'])),
                        status='PENDING',
                        notes=item.get('notes', ''),
                    ))
                FdsFeeInstallment.objects.bulk_create(new_insts)

                # Re-allocate all past payments across new installments
                total_paid = account.payments.aggregate(t=Sum('paid_amount'))['t'] or Decimal('0')
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

        return Response(FdsStudentFeeAccountSerializer(account).data)

    @action(detail=True, methods=['get', 'post'], url_path='installments')
    def installments(self, request, pk=None):
        account = self.get_object()
        if request.method == 'GET':
            return Response(FdsFeeInstallmentSerializer(account.installments.all().order_by('sequence_number'), many=True).data)

        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)

        serializer = FdsFeeInstallmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inst = serializer.save(account=account)
        inst.recalculate(save=True)
        account.recalculate(save=True)
        return Response(FdsFeeInstallmentSerializer(inst).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'installments/(?P<inst_id>\d+)')
    def installment_detail(self, request, pk=None, inst_id=None):
        account = self.get_object()
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)

        inst = get_object_or_404(FdsFeeInstallment, pk=inst_id, account=account)
        if request.method == 'DELETE':
            inst.delete()
            account.recalculate(save=True)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = FdsFeeInstallmentSerializer(inst, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        inst = serializer.save()
        inst.recalculate(save=True)
        account.recalculate(save=True)
        return Response(FdsFeeInstallmentSerializer(inst).data)

    @action(detail=True, methods=['get', 'post'], url_path='adjustments')
    def adjustments(self, request, pk=None):
        account = self.get_object()
        if request.method == 'GET':
            return Response(FdsFeeAdjustmentSerializer(account.adjustments.all().order_by('-created_at'), many=True).data)

        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)

        serializer = FdsFeeAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adj = serializer.save(account=account, created_by=request.user)
        account.recalculate(save=True)
        return Response(FdsFeeAdjustmentSerializer(adj).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='pending_students')
    def pending_students(self, request):
        if not fds_read(request.user) and not fds_fees_access(request.user):
            return Response(status=403)

        qs = FdsStudent.objects.filter(is_active=True, fee_account__isnull=True).select_related('batch', 'fee_structure')
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(student_id__icontains=search) | Q(contact_no__icontains=search))
        class_cat = request.query_params.get('class_category')
        if class_cat and class_cat != 'ALL':
            qs = qs.filter(batch__class_category=class_cat)

        data = []
        for s in qs.order_by('name'):
            data.append({
                'id': s.id,
                'student_id': s.student_id,
                'name': s.name,
                'contact_no': s.contact_no,
                'whatsapp_no': s.whatsapp_no,
                'class_category': s.class_category,
                'batch_name': s.batch.name if s.batch else '',
                'suggested_package_id': s.fee_structure_id,
                'suggested_package_name': s.fee_structure.get_category_display() if s.fee_structure else '',
                'suggested_amount': str(s.fee_structure.amount) if s.fee_structure else '',
            })
        return Response(data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        if not fds_fees_access(request.user) and not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        total_billed = qs.aggregate(t=Sum('total_due'))['t'] or Decimal('0')
        total_collected = qs.aggregate(t=Sum('total_paid'))['t'] or Decimal('0')
        total_balance = qs.aggregate(t=Sum('balance_due'))['t'] or Decimal('0')
        total_overdue = qs.aggregate(t=Sum('overdue_amount'))['t'] or Decimal('0')

        pending_count = FdsStudent.objects.filter(is_active=True, fee_account__isnull=True).count()

        return Response({
            'totalDue': float(total_billed),
            'totalPaid': float(total_collected),
            'balanceDue': float(total_balance),
            'overdueAmount': float(total_overdue),
            'total_billed': float(total_billed),
            'total_collected': float(total_collected),
            'total_balance': float(total_balance),
            'pending_count': pending_count,
            'active_accounts_count': qs.count(),
        })

    @action(detail=False, methods=['get', 'patch'], url_path='policies')
    def policies(self, request):
        from fees.models import FeePolicy
        policy, _ = FeePolicy.objects.get_or_create(company='FDS')
        if request.method == 'PATCH':
            if not fds_write(request.user):
                return Response({"error": "FDS write permission required."}, status=403)
            if 'block_without_fee_account' in request.data:
                policy.block_without_fee_account = bool(request.data['block_without_fee_account'])
            if 'pending_if_overdue' in request.data:
                policy.pending_if_overdue = bool(request.data['pending_if_overdue'])
            policy.save()
        return Response({
            'company': policy.company,
            'block_without_fee_account': policy.block_without_fee_account,
            'pending_if_overdue': policy.pending_if_overdue,
        })

class FdsFeesCollectionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsFeesCollectionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'mode_of_pay', 'fees_type', 'fee_month', 'fee_year']
    search_fields = ['payment_id', 'student__name', 'student__student_id', 'wedding_group__event_name']
    ordering_fields = ['pay_date', 'paid_amount', 'created_at']
    ordering = ['-pay_date', '-id']

    def get_queryset(self):
        if not fds_fees_access(self.request.user) and not fds_read(self.request.user):
            return FdsFeesCollection.objects.none()
        qs = FdsFeesCollection.objects.select_related(
            'student', 'wedding_group', 'fees_type', 'collected_by'
        )
        student_id = self.request.query_params.get('student_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        class_cat = self.request.query_params.get('class_category')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if date_from:
            qs = qs.filter(pay_date__gte=date_from)
        if date_to:
            qs = qs.filter(pay_date__lte=date_to)
        if class_cat:
            qs = qs.filter(student__batch__class_category=class_cat)
        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save(collected_by=self.request.user)

    def perform_update(self, serializer):
        payment = serializer.save()
        if payment.installment:
            payment.installment.recalculate(save=True)
        if payment.account:
            payment.account.recalculate(save=True)
        elif payment.student and hasattr(payment.student, 'fee_account'):
            payment.student.fee_account.recalculate(save=True)

    def update(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        instance = self.get_object()
        account = instance.account
        student = instance.student
        installment = instance.installment
        res = super().destroy(request, *args, **kwargs)
        if installment:
            installment.paid_amount = max(Decimal('0'), installment.paid_amount - instance.paid_amount)
            installment.recalculate(save=True)
        if account:
            account.recalculate(save=True)
        elif student and hasattr(student, 'fee_account'):
            student.fee_account.recalculate(save=True)
        return res

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Financial summary stats."""
        if not fds_fees_access(request.user) and not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        total_collected = qs.aggregate(t=Sum('paid_amount'))['t'] or 0

        # Query student fee accounts matching any filter (like class_category, student_id)
        account_qs = FdsStudentFeeAccount.objects.select_related('student')
        student_id = request.query_params.get('student_id')
        class_cat = request.query_params.get('class_category')
        if student_id:
            account_qs = account_qs.filter(student_id=student_id)
        if class_cat:
            account_qs = account_qs.filter(student__batch__class_category=class_cat)

        acc_billed = account_qs.aggregate(t=Sum('total_due'))['t'] or 0
        acc_balance = account_qs.aggregate(t=Sum('balance_due'))['t'] or 0

        wed_billed = 0
        wed_balance = 0
        if not student_id and (not class_cat or class_cat == 'ALL'):
            wed_qs = FdsWeddingGroup.objects.filter(status__in=['CONFIRMED', 'IN_PROGRESS', 'COMPLETED'])
            wed_billed = wed_qs.aggregate(t=Sum('fee_amount'))['t'] or 0
            wed_paid = wed_qs.aggregate(t=Sum('amount_paid'))['t'] or 0
            wed_balance = max(0, wed_billed - wed_paid)

        total_billed = acc_billed + wed_billed
        # Ensure total_billed is at least total_collected
        total_billed = max(total_billed, total_collected)

        total_balance = max(0, acc_balance + wed_balance)
        if total_balance == 0 and total_billed > total_collected:
            total_balance = max(0, total_billed - total_collected)

        by_mode = {}
        for r in qs.order_by().values('mode_of_pay').annotate(t=Sum('paid_amount')):
            mode = r['mode_of_pay'] or 'OTHER'
            amt = r['t'] or 0
            if amt > 0:
                by_mode[mode] = amt

        by_status = {
            s[0]: qs.filter(status=s[0]).count()
            for s in FdsFeesCollection._meta.get_field('status').choices
        }

        return Response({
            'total_collected': total_collected,
            'total_billed': total_billed,
            'total_balance': total_balance,
            'by_mode': by_mode,
            'by_status': by_status,
        })

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        if not fds_fees_access(request.user) and not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "FEES COLLECTION"
        ws.append([
            'Student ID', 'Pay Date', 'Student name', "What's app No.",
            'Joined Date', 'Batch/Time', 'Fees Type', 'Month', 'Paid Amount',
            'Total Fees', 'Balance', 'Mode Of Pay', 'PDF LINK', 'Status/Remarks'
        ])
        for p in qs:
            student_id = p.student.student_id if p.student else (p.wedding_group.group_id if p.wedding_group else '')
            student_name = p.student.name if p.student else (p.wedding_group.event_name if p.wedding_group else '')
            whatsapp = p.student.whatsapp_no if p.student else (p.wedding_group.lead_contact_phone if p.wedding_group else '')
            joined_date = p.student.joining_date.strftime('%d/%m/%Y') if p.student and p.student.joining_date else ''
            batch_str = str(p.student.batch) if p.student and p.student.batch else ''
            import calendar
            month_str = f"{calendar.month_name[p.fee_month]} {p.fee_year}" if p.fee_month and p.fee_year else ''
            ws.append([
                student_id, p.pay_date.strftime('%d/%m/%Y') if p.pay_date else '',
                student_name, whatsapp, joined_date, batch_str,
                p.fees_type.get_category_display() if p.fees_type else '',
                month_str, float(p.paid_amount), float(p.total_fees),
                float(p.balance), p.get_mode_of_pay_display(),
                p.pdf_link or '', p.remarks or '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Fees_Collection.xlsx"'
        return resp


# ── Dashboard Stats ───────────────────────────────────────────────

class FdsDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not fds_read(request.user) and not fds_fees_access(request.user):
            return Response({"error": "Permission denied."}, status=403)

        from django.utils import timezone
        today = timezone.now().date()
        this_month_start = today.replace(day=1)

        from django.db.models import Q
        students = FdsStudent.objects.filter(is_active=True)
        batches = FdsBatch.objects.filter(status='ACTIVE')
        enquiries = FdsEnquiry.objects.all()
        trials = FdsTrial.objects.all()
        payments = FdsFeesCollection.objects.all()
        if fds_admin_own(request.user) and not fds_admin_all(request.user):
            students = students.filter(Q(created_by=request.user) | Q(batch__trainer=request.user)).distinct()
            if getattr(request.user, 'role', None) == 'TRAINER':
                batches = batches.filter(trainer=request.user)
            enquiries = enquiries.filter(created_by=request.user)
            trials = trials.filter(Q(created_by=request.user) | Q(conducted_by=request.user)).distinct()
            payments = payments.filter(created_by=request.user)

        response = {
            'students': {
                'total_active': students.count(),
                'by_category': {
                    'dance': students.filter(batch__class_category='DANCE').count(),
                    'zumba': students.filter(batch__class_category='ZUMBA').count(),
                    'yoga': students.filter(batch__class_category='YOGA').count(),
                },
                'new_this_month': students.filter(joining_date__gte=this_month_start).count(),
            },
            'batches': {
                'total_active': batches.count(),
                'by_category': {
                    'dance': batches.filter(class_category='DANCE').count(),
                    'zumba': batches.filter(class_category='ZUMBA').count(),
                    'yoga': batches.filter(class_category='YOGA').count(),
                },
            },
            'enquiries': {
                'total': enquiries.count(),
                'new_this_week': enquiries.filter(date__gte=today - timezone.timedelta(days=7)).count(),
                'pending': enquiries.filter(status__in=['NEW', 'CONTACTED']).count(),
            },
            'trials': {
                'total': trials.count(),
                'active': trials.filter(converted=False, status='SCHEDULED').count(),
                'this_week': trials.filter(date__gte=today - timezone.timedelta(days=7)).count(),
                'conversion_rate': round(
                    trials.filter(converted=True).count() / trials.filter(status='COMPLETED').count() * 100, 1
                ) if trials.filter(status='COMPLETED').count() > 0 else 0,
            },
            'fees': {
                'this_month_collected': payments.filter(
                    pay_date__gte=this_month_start
                ).aggregate(t=Sum('paid_amount'))['t'] or 0,
                'total_outstanding': payments.aggregate(t=Sum('balance'))['t'] or 0,
                'pending_count': payments.filter(status='PENDING').count(),
            },
            'wedding_groups': {
                'total_active': FdsWeddingGroup.objects.filter(status__in=['CONFIRMED', 'IN_PROGRESS']).count(),
            }
        }
        return Response(response)


# ── FDS Trainers (staff filtered by company=FDS) ──────────────────

class FdsTrainerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not fds_read(request.user):
            return Response(status=403)
        trainers = User.objects.filter(company='FDS', is_active=True).values(
            'id', 'first_name', 'last_name', 'username'
        )
        data = [
            {
                'id': t['id'],
                'name': f"{t['first_name']} {t['last_name']}".strip() or t['username']
            }
            for t in trainers
        ]
        return Response(data)
