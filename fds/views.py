import openpyxl
import re
from io import BytesIO
from datetime import datetime, date, time

from django.db.models import Q, Sum, Count, Max
from django.http import HttpResponse
from django.core.management import call_command
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from accounts.models import User
from .models import (
    FdsFeeStructure, FdsBatch, FdsEnquiry, FdsTrial,
    FdsStudent, FdsWeddingGroup, FdsAttendance, FdsFeesCollection,
    FdsStudentFeeAccount, FdsLeadSourcing
)
from .serializers import (
    FdsFeeStructureSerializer, FdsBatchSerializer,
    FdsEnquirySerializer, FdsTrialSerializer,
    FdsStudentSerializer, FdsWeddingGroupSerializer,
    FdsAttendanceSerializer, FdsAttendanceBulkSerializer,
    FdsFeesCollectionSerializer, FdsStudentFeeAccountSerializer,
    FdsLeadSourcingSerializer
)

from accounts.permissions import has_dynamic_permission

# ── Permission helpers ───────────────────────────────────────────

def has_fds_permission(user, *perms):
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


# ── Parsing Helpers ──────────────────────────────────────────────

def clean_str(val):
    if val is None:
        return ''
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()

def parse_date(val):
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def parse_time(val):
    if not val:
        return None, ''
    if isinstance(val, time):
        return val, val.strftime('%H:%M')
    if isinstance(val, datetime):
        return val.time(), val.strftime('%H:%M')
    return None, str(val).strip()


# ── 1. Fee Structure (Sheet 5 Mirror) ────────────────────────────

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
    def import_excel(self, request):
        """Import from FEES STRUCTURE sheet."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file, data_only=False)
            ws = wb['FEES STRUCTURE'] if 'FEES STRUCTURE' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            for r in range(2, ws.max_row + 1):
                cat = clean_str(ws.cell(r, 1).value)
                if not cat:
                    skipped += 1
                    continue
                details = clean_str(ws.cell(r, 2).value)
                amt_text = clean_str(ws.cell(r, 3).value)
                notes = clean_str(ws.cell(r, 4).value)
                
                amount = 0.0
                try:
                    clean_num = re.sub(r'[^\d.]', '', amt_text.split('\n')[0].replace(',', ''))
                    amount = float(clean_num) if clean_num else 0.0
                except Exception:
                    amount = 0.0

                obj, is_new = FdsFeeStructure.objects.update_or_create(
                    category=cat,
                    defaults={
                        'category_name': cat,
                        'details': details,
                        'amount': amount,
                        'amount_text': amt_text,
                        'notes': notes,
                        'is_active': True,
                    }
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
                    
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export matching FEES STRUCTURE sheet exactly."""
        if not fds_read(request.user) and not fds_fees_access(request.user):
            return Response(status=403)
        qs = self.get_queryset()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "FEES STRUCTURE"
        ws.append(['CATEGORY', 'DETAILS', ' AMOUNT (RUPEES)', 'NOTES /OFFER'])
        for item in qs:
            ws.append([
                item.category,
                item.details or '',
                item.amount_text or (float(item.amount) if item.amount else ''),
                item.notes or '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Fees_Structure.xlsx"'
        return resp


# ── 2. Batch ─────────────────────────────────────────────────────

class FdsBatchViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsBatchSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['class_category', 'batch_type', 'status', 'trainer']
    search_fields = ['name']
    ordering_fields = ['name', 'class_category', 'created_at']
    ordering = ['class_category', 'name', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsBatch.objects.none()
        qs = FdsBatch.objects.select_related('trainer').all()
        if fds_admin_all(self.request.user):
            trainer_id = self.request.query_params.get('trainer')
            if trainer_id:
                qs = qs.filter(trainer_id=trainer_id)
        elif fds_admin_own(self.request.user):
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
        batch = self.get_object()
        students = FdsStudent.objects.filter(batch=batch, is_active=True)
        serializer = FdsStudentSerializer(students, many=True)
        return Response(serializer.data)


# ── 3. Enquiry (Sheet 1 Mirror - All 15 columns) ──────────────────

class FdsEnquiryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsEnquirySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'class_interest', 'source', 'joined']
    search_fields = ['name', 'parent_name', 'phone', 'whatsapp_no', 'enquiry_id', 'location', 'remarks']
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

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        follow_up_due = self.request.query_params.get('follow_up_due')
        if follow_up_due:
            today = timezone.now().date()
            qs = qs.filter(
                Q(follow_up_1__lte=today) | Q(follow_up_2__lte=today),
                ~Q(status__in=['CONVERTED', 'LOST', 'not interested'])
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
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        today = timezone.now().date()
        return Response({
            'total': qs.count(),
            'interested': qs.filter(status__icontains='interested').count(),
            'callback': qs.filter(status__icontains='call').count(),
            'joined': qs.filter(Q(joined=True) | Q(joined_status__icontains='join')).count(),
            'follow_up_due': qs.filter(
                Q(follow_up_1__lte=today) | Q(follow_up_2__lte=today)
            ).count(),
        })

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        """Import enquiries matching sheet ENQUIRY (all 15 columns)."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file, data_only=False)
            ws = wb['ENQUIRY'] if 'ENQUIRY' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            for r in range(2, ws.max_row + 1):
                enq_id = clean_str(ws.cell(r, 1).value)
                date_val = parse_date(ws.cell(r, 2).value) or date.today()
                name = clean_str(ws.cell(r, 3).value)
                if not enq_id and not name:
                    skipped += 1
                    continue
                
                parent = clean_str(ws.cell(r, 4).value)
                location = clean_str(ws.cell(r, 5).value)
                age = clean_str(ws.cell(r, 6).value)
                source = clean_str(ws.cell(r, 7).value) or 'WALK_IN'
                whatsapp = clean_str(ws.cell(r, 8).value)
                prev_exp = clean_str(ws.cell(r, 9).value)
                timing = clean_str(ws.cell(r, 10).value)
                status_val = clean_str(ws.cell(r, 11).value) or 'interested'
                fu1 = parse_date(ws.cell(r, 12).value)
                fu2 = parse_date(ws.cell(r, 13).value)
                joined_st = clean_str(ws.cell(r, 14).value)
                remarks = clean_str(ws.cell(r, 15).value)
                
                if not enq_id:
                    enq_id = f'ENQ{r:03d}'
                    
                obj, is_new = FdsEnquiry.objects.update_or_create(
                    enquiry_id=enq_id,
                    defaults={
                        'date': date_val,
                        'name': name or f'Enquiry {enq_id}',
                        'parent_name': parent,
                        'location': location,
                        'age': age,
                        'source': source,
                        'whatsapp_no': whatsapp,
                        'phone': whatsapp,
                        'previous_exp': prev_exp,
                        'preferred_timing': timing,
                        'status': status_val,
                        'follow_up_1': fu1,
                        'follow_up_2': fu2,
                        'joined': 'join' in joined_st.lower() or joined_st.lower() in ['yes', 'true'],
                        'joined_status': joined_st,
                        'remarks': remarks,
                        'created_by': request.user,
                    }
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
                    
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export enquiries matching sheet ENQUIRY exactly."""
        if not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ENQUIRY"
        ws.append([
            'Enquiry ID', 'Date', 'Student Name', 'Parent Name', 'Location',
            'Age', 'Source', "What's App no.", 'Previous Exp.', 'Preffered Timing',
            'Status', 'Follow Up1', 'Follow Up 2', 'Joined Or Not', 'Remarks / Concerns'
        ])
        for e in qs:
            ws.append([
                e.enquiry_id,
                e.date.strftime('%d/%m/%Y') if e.date else '',
                e.name,
                e.parent_name or '',
                e.location or '',
                e.age or '',
                e.source or '',
                e.whatsapp_no or e.phone or '',
                e.previous_exp or '',
                e.preferred_timing or '',
                e.status or '',
                e.follow_up_1.strftime('%d/%m/%Y') if e.follow_up_1 else '',
                e.follow_up_2.strftime('%d/%m/%Y') if e.follow_up_2 else '',
                e.joined_status or ('Joined' if e.joined else ''),
                e.remarks or '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Enquiries.xlsx"'
        return resp


# ── 4. Trial (Sheet 2 Mirror - All 16 columns) ────────────────────

class FdsTrialViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsTrialSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'class_category', 'converted']
    search_fields = ['name', 'phone', 'trial_id', 'location', 'remarks', 'feedback']
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
            today = timezone.now().date()
            qs = qs.filter(follow_up_date__lte=today, converted=False)

        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        trial = serializer.save(created_by=self.request.user)
        if trial.enquiry:
            trial.enquiry.status = 'TRIAL_SCHEDULED'
            trial.enquiry.save(update_fields=['status'])

    def perform_update(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'will_inform': qs.filter(status__icontains='inform').count(),
            'converted': qs.filter(Q(converted=True) | Q(converted_text__icontains='join')).count(),
            'pending_fee': qs.filter(fee_status__icontains='pending').count(),
        })

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        """Import from sheet TRIAL matching all 16 columns."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file, data_only=False)
            ws = wb['TRIAL'] if 'TRIAL' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            for r in range(2, ws.max_row + 1):
                trl_id = clean_str(ws.cell(r, 1).value)
                date_val = parse_date(ws.cell(r, 2).value) or date.today()
                t_obj, t_txt = parse_time(ws.cell(r, 3).value)
                name = clean_str(ws.cell(r, 4).value)
                if not trl_id and not name:
                    skipped += 1
                    continue
                
                age = clean_str(ws.cell(r, 5).value)
                phone = clean_str(ws.cell(r, 6).value)
                location = clean_str(ws.cell(r, 7).value)
                fee_quoted = clean_str(ws.cell(r, 8).value)
                feedback = clean_str(ws.cell(r, 9).value)
                rating = clean_str(ws.cell(r, 10).value)
                status_val = clean_str(ws.cell(r, 11).value) or 'WILL INFORM'
                follow_up = parse_date(ws.cell(r, 12).value)
                converted_st = clean_str(ws.cell(r, 13).value)
                join_date = parse_date(ws.cell(r, 14).value)
                fee_st = clean_str(ws.cell(r, 15).value) or 'PENDING'
                remarks = clean_str(ws.cell(r, 16).value)
                
                if not trl_id:
                    trl_id = f'TRL{r:03d}'
                    
                obj, is_new = FdsTrial.objects.update_or_create(
                    trial_id=trl_id,
                    defaults={
                        'date': date_val,
                        'time': t_obj,
                        'time_text': t_txt,
                        'name': name or f'Trial {trl_id}',
                        'age': age,
                        'phone': phone,
                        'location': location,
                        'fee_quoted': fee_quoted,
                        'feedback': feedback,
                        'trainer_rating': rating,
                        'status': status_val,
                        'follow_up_date': follow_up,
                        'converted': 'join' in converted_st.lower() or converted_st.lower() in ['yes', 'true'],
                        'converted_text': converted_st,
                        'join_date': join_date,
                        'fee_status': fee_st,
                        'remarks': remarks,
                        'created_by': request.user,
                    }
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
                    
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export trials matching sheet TRIAL exactly."""
        if not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TRIAL"
        ws.append([
            'TRIAL ID', 'DATE', 'TIME', 'NAME', 'AGE', 'PHONE', 'LOCATION',
            'FEE QUOTED', 'FEEDBACK', 'TRAINER RATING(IN 5⭐)', 'STATUS',
            'FOLLOW UP ', 'CONVERTED', 'JOIN DATE', 'FEE', 'REMARKS'
        ])
        for t in qs:
            ws.append([
                t.trial_id,
                t.date.strftime('%d/%m/%Y') if t.date else '',
                t.time_text or (t.time.strftime('%H:%M') if t.time else ''),
                t.name,
                t.age or '',
                t.phone or '',
                t.location or '',
                t.fee_quoted or '',
                t.feedback or '',
                t.trainer_rating or '',
                t.status or '',
                t.follow_up_date.strftime('%d/%m/%Y') if t.follow_up_date else '',
                t.converted_text or ('JOINED' if t.converted else ''),
                t.join_date.strftime('%d/%m/%Y') if t.join_date else '',
                t.fee_status or '',
                t.remarks or '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Trials.xlsx"'
        return resp


# ── 5. Student (Sheet 4 Mirror - REGISTRATION DETAILS) ────────────

class FdsStudentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsStudentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'student_type', 'batch']
    search_fields = ['name', 'student_id', 'contact_no', 'parent_name', 'emergency_contact_no']
    ordering_fields = ['joining_date', 'name', 'created_at']
    ordering = ['name', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsStudent.objects.none()
        qs = FdsStudent.objects.select_related('batch', 'fee_structure', 'enquiry', 'trial')
        
        batch_id = self.request.query_params.get('batch')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)

        class_cat = self.request.query_params.get('class_category')
        if class_cat:
            qs = qs.filter(batch__class_category=class_cat)

        return qs

    def perform_create(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        """Import students from REGISTRATION DETAILS matching all 12 columns."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file, data_only=False)
            ws = wb['REGISTRATION DETAILS'] if 'REGISTRATION DETAILS' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            for r in range(2, ws.max_row + 1):
                stu_id = clean_str(ws.cell(r, 1).value)
                name = clean_str(ws.cell(r, 2).value)
                if not stu_id or not name:
                    skipped += 1
                    continue
                
                joining_date = parse_date(ws.cell(r, 3).value) or date.today()
                age_gender = clean_str(ws.cell(r, 4).value)
                parent_name = clean_str(ws.cell(r, 5).value)
                contact_no = clean_str(ws.cell(r, 6).value)
                emergency_contact = clean_str(ws.cell(r, 7).value)
                batch_time = clean_str(ws.cell(r, 8).value)
                medical = clean_str(ws.cell(r, 9).value) or 'NO'
                pickup_no = clean_str(ws.cell(r, 10).value)
                can_leave = clean_str(ws.cell(r, 11).value) or 'NO'
                fee_paid_date = parse_date(ws.cell(r, 12).value)
                
                obj, is_new = FdsStudent.objects.update_or_create(
                    student_id=stu_id,
                    defaults={
                        'name': name,
                        'joining_date': joining_date,
                        'age_gender': age_gender,
                        'parent_name': parent_name,
                        'contact_no': contact_no,
                        'emergency_contact_no': emergency_contact,
                        'batch_time_text': batch_time,
                        'medical_condition': medical,
                        'pickup_person_1_no': pickup_no,
                        'can_leave_alone': can_leave,
                        'fee_paid_date': fee_paid_date,
                        'admission_fee_paid_date': fee_paid_date,
                        'is_active': True,
                        'created_by': request.user,
                    }
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
                    
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export students matching sheet REGISTRATION DETAILS exactly."""
        if not fds_read(request.user):
            return Response(status=403)
        qs = self.filter_queryset(self.get_queryset())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "REGISTRATION DETAILS"
        ws.append([
            'Student ID', 'Name ', 'Joining Date', 'Age &Gender', 'Parent Name ',
            'Contact No.', 'Emergency contact No.', 'Batch/Time', 'Medical Condition',
            'Pickup Person 1 NO.', 'Can Leave alone', 'Admission Fee /Monthly fee Paid Date'
        ])
        for s in qs:
            ws.append([
                s.student_id,
                s.name,
                s.joining_date.strftime('%d/%m/%Y') if s.joining_date else '',
                s.age_gender or '',
                s.parent_name or '',
                s.contact_no or '',
                s.emergency_contact_no or '',
                s.batch_time_text or (str(s.batch) if s.batch else ''),
                s.medical_condition or 'NO',
                s.pickup_person_1_no or '',
                s.can_leave_alone or 'NO',
                s.fee_paid_date.strftime('%d/%m/%Y') if s.fee_paid_date else '',
            ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Registration_Details.xlsx"'
        return resp


# ── 6. Wedding Group ─────────────────────────────────────────────

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
        return FdsWeddingGroup.objects.select_related('batch', 'trainer').all()

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


# ── 7. Attendance ────────────────────────────────────────────────

class FdsAttendanceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsAttendanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['batch', 'date', 'status', 'class_category']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date', '-id']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsAttendance.objects.none()
        return FdsAttendance.objects.select_related('student', 'batch', 'marked_by').all()

    @action(detail=False, methods=['post'])
    def bulk_mark(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        serializer = FdsAttendanceBulkSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        data = serializer.validated_data
        batch_id = data['batch_id']
        date_val = data['date']
        records = data['records']
        
        batch = FdsBatch.objects.filter(id=batch_id).first()
        if not batch:
            return Response({"error": "Batch not found."}, status=404)
            
        created = 0
        for rec in records:
            student_id = rec.get('student_id')
            st = rec.get('status', 'PRESENT')
            late = rec.get('late_arrival', False)
            notes = rec.get('notes', '')
            
            student = FdsStudent.objects.filter(id=student_id).first()
            if not student:
                continue
                
            FdsAttendance.objects.update_or_create(
                student=student,
                batch=batch,
                date=date_val,
                defaults={
                    'class_category': batch.class_category,
                    'status': st,
                    'late_arrival': late,
                    'notes': notes,
                    'marked_by': request.user,
                }
            )
            created += 1
            
        return Response({"status": "success", "records_marked": created})


# ── 8. Fee Accounts & Fees Collection (Sheet 6 Mirror) ───────────

class FdsStudentFeeAccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsStudentFeeAccountSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'active_package']
    search_fields = ['student__name', 'student__student_id']
    ordering_fields = ['updated_at', 'balance_due']
    ordering = ['-updated_at']

    def get_queryset(self):
        if not fds_fees_access(self.request.user) and not fds_read(self.request.user):
            return FdsStudentFeeAccount.objects.none()
        qs = FdsStudentFeeAccount.objects.select_related('student', 'active_package')
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs


class FdsFeesCollectionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsFeesCollectionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'mode_of_pay', 'fees_type', 'fee_month', 'fee_year']
    search_fields = ['payment_id', 'student__name', 'student__student_id', 'student_name_text', 'student_id_code', 'transaction_id']
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
            qs = qs.filter(Q(student_id=student_id) | Q(student__student_id=student_id) | Q(student_id_code=student_id))
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
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        payment = serializer.save()
        if payment.student and hasattr(payment.student, 'fee_account'):
            payment.student.fee_account.recalculate()

    def destroy(self, request, *args, **kwargs):
        if not fds_write(self.request.user):
            self.permission_denied(self.request, message="FDS write permission required.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def monthly_ledger(self, request):
        """Returns student-wise monthly ledger matching FEES COLLECTION 2026 sheet."""
        if not fds_fees_access(request.user) and not fds_read(request.user):
            return Response(status=403)

        students_qs = FdsStudent.objects.all().order_by('student_id')
        payments = FdsFeesCollection.objects.all().order_by('fee_year', 'id')
        
        # Standard tracking months
        ALL_MONTHS = ['SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER', 'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST']
        
        ledger_data = []
        for stu in students_qs:
            stu_payments = payments.filter(Q(student=stu) | Q(student_id_code=stu.student_id))
            pay_by_month = {}
            for p in stu_payments:
                m_key = p.month_name.strip().upper() if p.month_name else ''
                if m_key:
                    pay_by_month[m_key] = p

            months_list = []
            # Gather active months from payments or defaults
            active_month_names = ['SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
            for m in active_month_names:
                p = pay_by_month.get(m)
                months_list.append({
                    'month': m,
                    'paid_amount': p.paid_amount_text if p else '',
                    'mode_of_pay': p.mode_of_pay if p else '',
                    'transaction_id': p.transaction_id if p else '',
                    'status_remarks': p.status_remarks if p else '',
                    'pay_date': p.pay_date.strftime('%Y-%m-%d') if p and p.pay_date else '',
                    'payment_id': p.payment_id if p else '',
                    'id': p.id if p else None,
                })

            ledger_data.append({
                'student_id': stu.student_id,
                'name': stu.name,
                'joined_date': stu.joining_date.strftime('%Y-%m-%d') if stu.joining_date else '',
                'batch_time': stu.batch_time_text or (str(stu.batch) if stu.batch else ''),
                'fees_type': stu.fee_structure.category if stu.fee_structure else 'MONTHLY',
                'months': months_list,
            })

        return Response(ledger_data)

    @action(detail=False, methods=['post'])
    def update_month_cell(self, request):
        """Update or create a specific student month fee row directly."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)

        stu_id = request.data.get('student_id')
        month = request.data.get('month', '').strip().upper()
        if not stu_id or not month:
            return Response({"error": "student_id and month required."}, status=400)

        paid_amount_text = str(request.data.get('paid_amount', '')).strip()
        mode_of_pay = str(request.data.get('mode_of_pay', 'ONLINE')).strip()
        transaction_id = str(request.data.get('transaction_id', '')).strip()
        status_remarks = str(request.data.get('status_remarks', '')).strip()
        pay_date_val = parse_date(request.data.get('pay_date')) or date.today()

        paid_amount = 0.0
        try:
            clean_num = re.sub(r'[^\d.]', '', paid_amount_text.replace(',', ''))
            paid_amount = float(clean_num) if clean_num else 0.0
        except Exception:
            paid_amount = 0.0

        stu = FdsStudent.objects.filter(student_id=stu_id).first()
        payment_id = f"PAY-{stu_id}-{month[:3]}-2026"

        obj, _ = FdsFeesCollection.objects.update_or_create(
            payment_id=payment_id,
            defaults={
                'student': stu,
                'student_id_code': stu_id,
                'student_name_text': stu.name if stu else '',
                'batch_time_text': stu.batch_time_text if stu else '',
                'fees_type_text': stu.fee_structure.category if stu and stu.fee_structure else 'MONTHLY',
                'month_name': month,
                'paid_amount_text': paid_amount_text,
                'paid_amount': paid_amount,
                'mode_of_pay': mode_of_pay,
                'transaction_id': transaction_id,
                'status_remarks': status_remarks,
                'pay_date': pay_date_val,
                'fee_year': 2026,
                'status': 'PAID' if paid_amount > 0 else 'PENDING',
                'collected_by': request.user,
            }
        )
        return Response({"status": "success", "payment_id": obj.payment_id})

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        """Import from sheet FEES COLLECTION 2026 handling multi-row student layout."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file, data_only=False)
            ws = wb['FEES COLLECTION 2026'] if 'FEES COLLECTION 2026' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            curr_stu = {}
            for r in range(2, ws.max_row + 1):
                stu_id = clean_str(ws.cell(r, 1).value)
                if stu_id:
                    curr_stu = {
                        'student_id': stu_id,
                        'name': clean_str(ws.cell(r, 2).value),
                        'joined_date': parse_date(ws.cell(r, 3).value),
                        'batch_time': clean_str(ws.cell(r, 4).value),
                        'fees_type': clean_str(ws.cell(r, 5).value) or 'MONTHLY',
                    }
                month = clean_str(ws.cell(r, 6).value)
                amt_text = clean_str(ws.cell(r, 7).value)
                mode = clean_str(ws.cell(r, 8).value) or 'ONLINE'
                txn_id = clean_str(ws.cell(r, 9).value)
                status_remarks = clean_str(ws.cell(r, 10).value)
                
                if month and curr_stu.get('student_id'):
                    paid_amount = 0.0
                    try:
                        clean_num = re.sub(r'[^\d.]', '', amt_text.replace(',', ''))
                        paid_amount = float(clean_num) if clean_num else 0.0
                    except Exception:
                        paid_amount = 0.0
                        
                    student_obj = FdsStudent.objects.filter(student_id=curr_stu['student_id']).first()
                    month_clean = month.split()[0].upper()
                    payment_id = f"PAY-{curr_stu['student_id']}-{month_clean[:3]}-2026"
                    
                    obj, is_new = FdsFeesCollection.objects.update_or_create(
                        payment_id=payment_id,
                        defaults={
                            'student': student_obj,
                            'student_id_code': curr_stu['student_id'],
                            'student_name_text': curr_stu.get('name', ''),
                            'batch_time_text': curr_stu.get('batch_time', ''),
                            'fees_type_text': curr_stu.get('fees_type', 'MONTHLY'),
                            'month_name': month,
                            'paid_amount_text': amt_text,
                            'paid_amount': paid_amount,
                            'mode_of_pay': mode,
                            'transaction_id': txn_id,
                            'status_remarks': status_remarks,
                            'fee_year': 2026,
                            'pay_date': curr_stu.get('joined_date') or date(2026, 9, 1),
                            'status': 'PAID' if paid_amount > 0 else 'PENDING',
                        }
                    )
                    if is_new:
                        created += 1
                    else:
                        updated += 1
                else:
                    skipped += 1
                    
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export sheet FEES COLLECTION 2026 with exact grouped layout."""
        if not fds_fees_access(request.user) and not fds_read(request.user):
            return Response(status=403)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "FEES COLLECTION 2026"
        ws.append([
            'Student ID', 'Student name', 'Joined Date', 'Batch/Time',
            'Fees Type', 'Month', 'Paid Amount', 'Mode Of Pay',
            'TRANSACTION ID', 'Status/Remarks'
        ])

        students = FdsStudent.objects.all().order_by('student_id')
        payments = FdsFeesCollection.objects.all().order_by('pay_date', 'id')
        active_months = ['SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']

        for stu in students:
            stu_payments = payments.filter(Q(student=stu) | Q(student_id_code=stu.student_id))
            pay_map = {p.month_name.strip().upper(): p for p in stu_payments if p.month_name}
            
            first_row = True
            for m in active_months:
                p = pay_map.get(m)
                if first_row:
                    ws.append([
                        stu.student_id,
                        stu.name,
                        stu.joining_date.strftime('%Y-%m-%d') if stu.joining_date else '',
                        stu.batch_time_text or '',
                        stu.fee_structure.category if stu.fee_structure else 'MONTHLY',
                        m,
                        p.paid_amount_text if p else '',
                        p.mode_of_pay if p else '',
                        p.transaction_id if p else '',
                        p.status_remarks if p else '',
                    ])
                    first_row = False
                else:
                    ws.append([
                        '', '', '', '', '',
                        m,
                        p.paid_amount_text if p else '',
                        p.mode_of_pay if p else '',
                        p.transaction_id if p else '',
                        p.status_remarks if p else '',
                    ])
            ws.append(['', '', '', '', '', '', '', '', '', '']) # Blank separator row

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Fees_Collection_2026.xlsx"'
        return resp


# ── 9. Lead Sourcing (Sheet 3 Mirror - All 6 Directory Categories) ──

class FdsLeadSourcingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FdsLeadSourcingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category']
    search_fields = ['name', 'location', 'phone', 'email_website', 'extra_info']
    ordering_fields = ['category', 'name', 'created_at']
    ordering = ['category', 'name']

    def get_queryset(self):
        if not fds_read(self.request.user):
            return FdsLeadSourcing.objects.none()
        qs = FdsLeadSourcing.objects.all()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
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
    def import_excel(self, request):
        """Import all sections from LEAD SOURCING sheet."""
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=400)
        try:
            wb = openpyxl.load_workbook(file, data_only=False)
            ws = wb['LEAD SOURCING'] if 'LEAD SOURCING' in wb.sheetnames else wb.active
            created, updated, skipped = 0, 0, 0
            
            curr_cat = None
            for r in range(1, ws.max_row + 1):
                c1 = clean_str(ws.cell(r, 1).value)
                c2 = clean_str(ws.cell(r, 2).value)
                c3 = clean_str(ws.cell(r, 3).value)
                c4 = clean_str(ws.cell(r, 4).value)
                if not c1 and not c2:
                    continue
                
                low = c1.lower()
                if 'prominent colleges' in low:
                    curr_cat = 'COLLEGES'
                    continue
                elif 'prominent schools' in low:
                    curr_cat = 'SCHOOLS'
                    continue
                elif 'social clubs' in low or 'recreation' in low:
                    curr_cat = 'CLUBS'
                    continue
                elif 'resident welfare' in low:
                    curr_cat = 'RESIDENTS'
                    continue
                elif 'villa' in low:
                    curr_cat = 'VILLAS'
                    continue
                elif 'residency / builder' in low:
                    curr_cat = 'BUILDERS'
                    continue
                
                if any(h in low for h in ['institution name', 'school name', 'organization', 'association', 'villa project', 'residency / builder']):
                    continue
                    
                if curr_cat and c1:
                    obj, is_new = FdsLeadSourcing.objects.update_or_create(
                        category=curr_cat,
                        name=c1,
                        defaults={
                            'location': c2,
                            'phone': c3,
                            'email_website': c4 if curr_cat != 'RESIDENTS' else '',
                            'extra_info': c4 if curr_cat in ['RESIDENTS', 'SCHOOLS'] else '',
                        }
                    )
                    if is_new:
                        created += 1
                    else:
                        updated += 1
                else:
                    skipped += 1
                    
            return Response({"created": created, "updated": updated, "skipped": skipped})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """Export sheet LEAD SOURCING matching the original categorized directory."""
        if not fds_read(request.user):
            return Response(status=403)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "LEAD SOURCING"

        SECTIONS = [
            ('COLLEGES', 'Prominent Colleges in & around Kottayam', ['Institution Name', 'Location / Area', 'Phone Number', 'Email / Website']),
            ('SCHOOLS', 'Prominent Schools in & around Kottayam', ['School Name', 'Location / Area', 'Phone Number', 'Board / Type']),
            ('CLUBS', 'Recreation & Social Clubs in Kottayam', ['Organization / Club Name', 'Area / Landmark', 'Contact Number', 'Email / Website']),
            ('RESIDENTS', 'Resident Welfare Associations & Housing Hubs (Proper Kottayam)', ['Association / Residence Hub', 'Locality / Location', 'Contact / Remarks', 'contact number']),
            ('VILLAS', 'Prominent Villa Projects & Gated Communities in Kottayam', ['Villa Project / Community', 'Location / Area', 'Contact Number', 'Email / Website']),
            ('BUILDERS', 'Residency / Builder', ['Residency / Builder', 'Location / Area', 'Contact Number', 'Email / Website']),
        ]

        for cat_code, title, headers in SECTIONS:
            ws.append([title])
            ws.append(headers)
            items = FdsLeadSourcing.objects.filter(category=cat_code).order_by('name')
            for item in items:
                ws.append([
                    item.name,
                    item.location or '',
                    item.phone or '',
                    item.extra_info if cat_code in ['RESIDENTS', 'SCHOOLS'] else (item.email_website or ''),
                ])
            ws.append([]) # Blank spacing row

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(buf, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="FDS_Lead_Sourcing.xlsx"'
        return resp


# ── 10. Dashboard & Trainers ─────────────────────────────────────

class FdsDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not fds_read(request.user) and not fds_fees_access(request.user):
            return Response({"error": "Permission denied."}, status=403)

        today = timezone.now().date()
        this_month_start = today.replace(day=1)

        students = FdsStudent.objects.filter(is_active=True)
        batches = FdsBatch.objects.filter(status='ACTIVE')
        enquiries = FdsEnquiry.objects.all()
        trials = FdsTrial.objects.all()
        payments = FdsFeesCollection.objects.all()

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
                'pending': enquiries.filter(status__icontains='call').count(),
            },
            'trials': {
                'total': trials.count(),
                'active': trials.filter(converted=False).count(),
                'this_week': trials.filter(date__gte=today - timezone.timedelta(days=7)).count(),
                'conversion_rate': round(
                    trials.filter(converted=True).count() / trials.count() * 100, 1
                ) if trials.count() > 0 else 0,
            },
            'fees': {
                'this_month_collected': payments.filter(
                    month_name__icontains=today.strftime('%B')
                ).aggregate(t=Sum('paid_amount'))['t'] or 0,
                'total_collected': payments.aggregate(t=Sum('paid_amount'))['t'] or 0,
            },
            'wedding_groups': {
                'total_active': FdsWeddingGroup.objects.filter(status__in=['CONFIRMED', 'IN_PROGRESS']).count(),
            },
            'lead_sourcing': {
                'total_entries': FdsLeadSourcing.objects.count(),
            }
        }
        return Response(response)


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


class FdsMasterSyncView(APIView):
    """Triggers 1-way ingestion: Google Sheets / Excel ➔ CRM Master Mirror."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not fds_write(request.user):
            return Response({"error": "FDS write permission required."}, status=403)
        try:
            call_command('sync_fds_sheets')
            return Response({
                "status": "success",
                "message": "All 6 Google Sheets / Excel workbooks ingested and mirrored into CRM successfully!",
                "stats": {
                    "fee_structures": FdsFeeStructure.objects.count(),
                    "students": FdsStudent.objects.count(),
                    "collections": FdsFeesCollection.objects.count(),
                    "enquiries": FdsEnquiry.objects.count(),
                    "trials": FdsTrial.objects.count(),
                    "lead_sourcing": FdsLeadSourcing.objects.count(),
                }
            })
        except Exception as e:
            return Response({"error": str(e)}, status=500)
