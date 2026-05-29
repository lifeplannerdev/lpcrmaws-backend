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

class BulkLeadUploadView(APIView):
    permission_classes = [CanAccessLeads]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get('file')

        if not file:
            return Response({'error': 'No file uploaded'}, status=status.HTTP_400_BAD_REQUEST)

        if file.size > 5 * 1024 * 1024:
            return Response({'error': 'File too large (max 5MB)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception:
            return Response({'error': 'Invalid Excel file'}, status=status.HTTP_400_BAD_REQUEST)

        required_columns = ['name', 'phone', 'assigned_to']
        missing_cols = [col for col in required_columns if col not in df.columns]

        if missing_cols:
            return Response(
                {'error': f'Missing required columns: {missing_cols}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_map = {
            user.username.lower(): user
            for user in User.objects.filter(is_active=True)
        }

        # Pre-process phones for O(1) duplicate checks
        excel_phones = set()
        for _, row in df.iterrows():
            phone = clean_value(row.get('phone'))
            if phone is not None:
                phone = str(int(float(str(phone)))) if str(phone).replace('.', '', 1).isdigit() else str(phone).strip()
                if phone:
                    excel_phones.add(phone)
                    
        existing_phones_in_db = set(Lead.objects.filter(phone__in=excel_phones).values_list('phone', flat=True))

        failed_rows      = []
        assigned_summary = {}
        seen_phones      = set()  
        
        leads_to_create = []
        lead_assignments_to_create = []

        now = timezone.now()

        for index, row in df.iterrows():
            try:
                name       = clean_value(row.get('name'))
                email      = clean_value(row.get('email'))
                source     = clean_value(row.get('source'))
                status_val = clean_value(row.get('status'))
                priority   = clean_value(row.get('priority'))
                program    = clean_value(row.get('program'))
                location   = clean_value(row.get('location'))
                raw_username = clean_value(row.get('assigned_to'))
                username = str(raw_username).strip() if raw_username is not None else None

                phone = clean_value(row.get('phone'))
                if phone is not None:
                    phone = str(int(float(str(phone)))) if str(phone).replace('.', '', 1).isdigit() else str(phone).strip()

                if phone and phone in seen_phones:
                    failed_rows.append({
                        'row':   index + 2,
                        'error': f"Duplicate phone '{phone}' already exists in this file.",
                    })
                    continue

                if phone and phone in existing_phones_in_db:
                    failed_rows.append({
                        'row':   index + 2,
                        'error': f"Phone '{phone}' already exists in the system.",
                    })
                    continue

                if phone:
                    seen_phones.add(phone)

                if not username:
                    failed_rows.append({'row': index + 2, 'error': 'assigned_to is required'})
                    continue

                assignee_user = user_map.get(str(username).lower())
                if not assignee_user:
                    failed_rows.append({
                        'row':   index + 2,
                        'error': f"User '{username}' not found",
                    })
                    continue

                data = {
                    'name':        name,
                    'phone':       phone,
                    'email':       email,
                    'status':      str(status_val).upper() if status_val else 'ENQUIRY',
                    'priority':    str(priority).upper()   if priority   else 'MEDIUM',
                    'program':     program,
                    'location':    location,
                    'assigned_to': str(username),
                }
                if source:
                    data['source'] = str(source).upper()

                serializer = BulkLeadCreateSerializer(
                    data=data,
                    context={'request': request, 'user_map': user_map},
                )

                if serializer.is_valid():
                    v_data = serializer.validated_data
                    assignee = v_data.pop('assigned_to')
                    company = request.user.company if hasattr(request.user, 'company') else None
                    
                    lead_obj = Lead(
                        **v_data,
                        created_by=request.user,
                        assigned_to=assignee,
                        assigned_by=request.user,
                        assigned_date=now,
                        company=company
                    )
                    leads_to_create.append((lead_obj, assignee))
                else:
                    failed_rows.append({
                        'row':    index + 2,
                        'data':   data,
                        'errors': serializer.errors,
                    })
            except Exception as e:
                failed_rows.append({'row': index + 2, 'error': str(e)})

        # Bulk create leads
        created_leads = Lead.objects.bulk_create([item[0] for item in leads_to_create])

        # Bulk create assignments and populate notifications
        for i, lead in enumerate(created_leads):
            assignee = leads_to_create[i][1]
            lead_assignments_to_create.append(LeadAssignment(
                lead=lead,
                assigned_to=assignee,
                assigned_by=request.user,
                assignment_type='PRIMARY',
                notes='Assigned during bulk upload',
            ))

            if assignee == request.user:
                continue

            uid = assignee.id
            if uid not in assigned_summary:
                assigned_summary[uid] = {
                    'user':  assignee,
                    'leads': [],
                }
            assigned_summary[uid]['leads'].append({
                'lead_id':   lead.id,
                'lead_name': lead.name,
                'priority':  lead.priority,
            })

        LeadAssignment.objects.bulk_create(lead_assignments_to_create)

        # Pusher notifications disabled as per user request
        # for uid, summary in assigned_summary.items():
        #     count = len(summary['leads'])
        #     ...

        return Response({
            'message':       'Bulk upload completed',
            'success_count': len(created_leads),
            'failed_count':  len(failed_rows),
            'failed_rows':   failed_rows,
        }, status=status.HTTP_200_OK)

