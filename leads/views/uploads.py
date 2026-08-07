import pandas as pd
import math
from datetime import date
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Count, Q as DQ
from django.shortcuts import get_object_or_404
from rest_framework import generics, filters, status
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from accounts.models import User
from leads.models import Lead, LeadAssignment
from leads.permissions import CanAccessLeads
from leads.serializers import BulkLeadCreateSerializer

# ── Helpers
def clean_value(val):
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return val

# ── Pagination
class LeadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class BulkUploadPreviewView(APIView):
    permission_classes = [CanAccessLeads]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file uploaded'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 5 * 1024 * 1024:
            return Response({'error': 'File too large (max 5MB)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Try reading with headers
            df = pd.read_excel(file)
            
            # If standard headers are missing, assume no-header format: Name, Phone, Email, Location
            if 'name' not in [str(c).lower() for c in df.columns] and 'phone' not in [str(c).lower() for c in df.columns]:
                df = pd.read_excel(file, header=None)
                # Map first 4 columns
                cols = list(df.columns)
                mapping = {}
                if len(cols) > 0: mapping[cols[0]] = 'name'
                if len(cols) > 1: mapping[cols[1]] = 'phone'
                if len(cols) > 2: mapping[cols[2]] = 'email'
                if len(cols) > 3: mapping[cols[3]] = 'location'
                df = df.rename(columns=mapping)
            else:
                df.columns = [str(c).lower().strip() for c in df.columns]
                
        except Exception:
            return Response({'error': 'Invalid Excel file'}, status=status.HTTP_400_BAD_REQUEST)

        if 'name' not in df.columns or 'phone' not in df.columns:
            return Response(
                {'error': f'Missing required columns: name, phone'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        excel_phones = set()
        for _, row in df.iterrows():
            phone = clean_value(row.get('phone'))
            if phone is not None:
                phone = str(int(float(str(phone)))) if str(phone).replace('.', '', 1).isdigit() else str(phone).strip()
                if phone:
                    excel_phones.add(phone)
                    
        existing_phones_in_db = set(Lead.objects.filter(phone__in=excel_phones).values_list('phone', flat=True))

        valid_rows = []
        failed_rows = []
        seen_phones = set()

        for index, row in df.iterrows():
            try:
                name       = clean_value(row.get('name'))
                email      = clean_value(row.get('email'))
                source     = clean_value(row.get('source'))
                status_val = clean_value(row.get('status'))
                priority   = clean_value(row.get('priority'))
                program    = clean_value(row.get('program'))
                location   = clean_value(row.get('location'))

                phone = clean_value(row.get('phone'))
                if phone is not None:
                    phone = str(int(float(str(phone)))) if str(phone).replace('.', '', 1).isdigit() else str(phone).strip()

                if not phone:
                    failed_rows.append({'row': index + 2, 'error': 'Phone number is required.', 'data': {'name': name}})
                    continue

                if phone in seen_phones:
                    failed_rows.append({'row': index + 2, 'error': f"Duplicate phone '{phone}' in this file.", 'data': {'name': name, 'phone': phone}})
                    continue

                if phone in existing_phones_in_db:
                    failed_rows.append({'row': index + 2, 'error': f"Phone '{phone}' already exists in system.", 'data': {'name': name, 'phone': phone}})
                    continue

                seen_phones.add(phone)

                data = {
                    'name': name,
                    'phone': phone,
                    'email': email,
                    'status': str(status_val).upper() if status_val else 'ENQUIRY',
                    'priority': str(priority).upper() if priority else 'MEDIUM',
                    'program': program,
                    'location': location,
                }
                if source:
                    data['source'] = str(source).upper()

                valid_rows.append(data)
            except Exception as e:
                failed_rows.append({'row': index + 2, 'error': str(e)})

        return Response({
            'message': 'Preview generated',
            'valid_count': len(valid_rows),
            'failed_count': len(failed_rows),
            'valid_rows': valid_rows,
            'failed_rows': failed_rows,
        }, status=status.HTTP_200_OK)


class BulkUploadConfirmView(APIView):
    permission_classes = [CanAccessLeads]

    def post(self, request):
        leads_data = request.data.get('leads', [])
        assigned_to_username = request.data.get('assigned_to')

        if not leads_data or not assigned_to_username:
            return Response({'error': "'leads' array and 'assigned_to' are required"}, status=status.HTTP_400_BAD_REQUEST)

        assignee_user = User.objects.filter(username__iexact=str(assigned_to_username).strip(), is_active=True).first()
        if not assignee_user:
            return Response({'error': f"User '{assigned_to_username}' not found or inactive"}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        leads_to_create = []
        lead_assignments_to_create = []

        # Double check duplicates
        phones = [l.get('phone') for l in leads_data if l.get('phone')]
        existing_phones_in_db = set(Lead.objects.filter(phone__in=phones).values_list('phone', flat=True))

        company = request.user.company if hasattr(request.user, 'company') else None
        
        remark_text = f"Assigned by {request.user.username} on {now.strftime('%Y-%m-%d %H:%M:%S')}"

        valid_leads = []
        for data in leads_data:
            phone = data.get('phone')
            if phone in existing_phones_in_db:
                continue

            lead_obj = Lead(
                name=data.get('name'),
                phone=phone,
                email=data.get('email'),
                status=data.get('status', 'ENQUIRY'),
                priority=data.get('priority', 'MEDIUM'),
                program=data.get('program'),
                location=data.get('location'),
                source=data.get('source'),
                remarks=remark_text,
                created_by=request.user,
                assigned_to=assignee_user,
                assigned_by=request.user,
                assigned_date=now,
                company=company
            )
            valid_leads.append(lead_obj)

        if not valid_leads:
            return Response({'error': 'No valid new leads to create (possibly all duplicates).'}, status=status.HTTP_400_BAD_REQUEST)

        created_leads = Lead.objects.bulk_create(valid_leads)

        for lead in created_leads:
            lead_assignments_to_create.append(LeadAssignment(
                lead=lead,
                assigned_to=assignee_user,
                assigned_by=request.user,
                assignment_type='PRIMARY',
                notes='Assigned during bulk upload',
            ))

        LeadAssignment.objects.bulk_create(lead_assignments_to_create)

        return Response({
            'message': 'Leads created and assigned successfully',
            'success_count': len(created_leads)
        }, status=status.HTTP_200_OK)

class BulkLeadUploadView(APIView):
    # Keep legacy intact just in case
    permission_classes = [CanAccessLeads]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        return Response({'error': 'Use the new preview/confirm flow'}, status=status.HTTP_400_BAD_REQUEST)
