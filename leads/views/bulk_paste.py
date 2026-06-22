from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from leads.models import Lead, LeadAssignment
from accounts.models import User
from django.utils import timezone

class BulkPasteLeadsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        assignee_id = request.data.get('assignee_id')
        leads_data = request.data.get('leads', [])
        
        if not assignee_id:
            return Response({"error": "assignee_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            assignee = User.objects.get(id=assignee_id)
        except User.DoesNotExist:
            return Response({"error": "Assignee not found."}, status=status.HTTP_404_NOT_FOUND)
            
        company = request.user.company if hasattr(request.user, 'company') else 'LP'

        processed_count = 0
        updated_count = 0
        new_count = 0
        
        for lead_row in leads_data:
            phone = lead_row.get('phone')
            if not phone:
                continue # Skip rows without phone numbers

            # Map front-end fields to backend fields
            name = lead_row.get('name') or '' # Allows blank name
            email = lead_row.get('email')
            interested_country = lead_row.get('interested_country')
            interested_course = lead_row.get('interested_course')
            previous_qualification = lead_row.get('previous_qualification')
            work_experience = lead_row.get('work_experience')
            budget = lead_row.get('budget')
            location = lead_row.get('location')
            lead_status = lead_row.get('status', 'ENQUIRY') or 'ENQUIRY'

            # Graceful deduplication
            existing_lead = Lead.objects.filter(phone=phone).first()
            
            if existing_lead:
                # Update existing
                existing_lead.assigned_to = assignee
                existing_lead.assigned_date = timezone.now()
                existing_lead.status = lead_status
                if name and not existing_lead.name:
                    existing_lead.name = name
                if interested_country: existing_lead.interested_country = interested_country
                if interested_course: existing_lead.interested_course = interested_course
                if previous_qualification: existing_lead.previous_qualification = previous_qualification
                if work_experience: existing_lead.work_experience = work_experience
                if budget: existing_lead.budget = budget
                if location: existing_lead.location = location
                
                # Append remark
                note = f"Re-assigned via Spreadsheet Upload by {request.user.get_full_name()} on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                if existing_lead.remarks:
                    existing_lead.remarks = existing_lead.remarks + "\n" + note
                else:
                    existing_lead.remarks = note
                    
                existing_lead.save()
                
                # Track Assignment History
                LeadAssignment.objects.create(
                    lead=existing_lead,
                    assigned_to=assignee,
                    assigned_by=request.user,
                    assignment_type='REASSIGNMENT',
                    notes="Spreadsheet Bulk Paste"
                )
                updated_count += 1
            else:
                # Create new
                new_lead = Lead.objects.create(
                    phone=phone,
                    name=name,
                    email=email if email else None,
                    interested_country=interested_country,
                    interested_course=interested_course,
                    previous_qualification=previous_qualification,
                    work_experience=work_experience,
                    budget=budget,
                    location=location,
                    status=lead_status,
                    assigned_to=assignee,
                    assigned_by=request.user,
                    assigned_date=timezone.now(),
                    company=company,
                    source='BULK DATA',
                    created_by=request.user
                )
                LeadAssignment.objects.create(
                    lead=new_lead,
                    assigned_to=assignee,
                    assigned_by=request.user,
                    assignment_type='PRIMARY',
                    notes="Spreadsheet Bulk Paste"
                )
                new_count += 1
                
            processed_count += 1
            
        return Response({
            "message": f"Successfully processed {processed_count} leads.",
            "new_created": new_count,
            "updated": updated_count
        }, status=status.HTTP_200_OK)
