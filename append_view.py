

# ─── Voxbay AI Report ─────────────────────────────────────────────────────────

from .models import VoxbayDailySnapshot
from django.utils import timezone
from datetime import timedelta, datetime

class VoxbayAIReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_dynamic_permission(request.user, 'voxbay_ai:admin'):
            return Response({"error": "Admin access required"}, status=403)
            
        date_str = request.query_params.get("date")
        if not date_str:
            target_date = timezone.now().date()
        else:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Invalid date format"}, status=400)

        # If date is in the past, try to fetch from snapshot first
        if target_date < timezone.now().date():
            snapshot = VoxbayDailySnapshot.objects.filter(date=target_date).first()
            if snapshot:
                return Response(snapshot.report_data)

        # Compute dynamic report
        # We only want OUTGOING calls for that date
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())
        
        # Django timezone handling if needed
        from django.utils.timezone import make_aware, is_naive
        if is_naive(start_dt):
            start_dt = make_aware(start_dt)
            end_dt = make_aware(end_dt)

        call_logs = VoxbayCallLog.objects.filter(
            call_type='outgoing',
            created_at__gte=start_dt,
            created_at__lte=end_dt
        ).order_by('-created_at')

        # To build the response, we need Lead info
        from leads.models import Lead, FollowUp
        from accounts.models import User
        
        # Map agent extensions to User Names
        agents = User.objects.filter(is_active=True).values('id', 'first_name', 'last_name', 'voxbay_number', 'voxbay_extension')
        ext_to_name = {}
        for a in agents:
            name = f"{a['first_name']} {a['last_name']}".strip()
            if a['voxbay_number']:
                ext_to_name[a['voxbay_number']] = name
            if a['voxbay_extension']:
                ext_to_name[a['voxbay_extension']] = name

        employees_data = {}

        for obj in call_logs:
            agent_ext = obj.extension
            agent_name = ext_to_name.get(agent_ext) or agent_ext or "Unknown Agent"
            
            if agent_name not in employees_data:
                employees_data[agent_name] = []
                
            lead_number = obj.destination
            # Find the lead
            search_num = lead_number[-10:] if lead_number and len(lead_number) >= 10 else lead_number
            lead = None
            if search_num:
                lead = Lead.objects.filter(Q(phone=lead_number) | Q(phone__endswith=search_num)).first()
            
            lead_name = lead.name if lead else f"Unknown ({lead_number})"
            lead_status = lead.status if lead else "UNKNOWN"
            
            # Map standard statuses to the categories the UI expects if possible
            category = "No Remark"
            if lead_status == 'ENQUIRY':
                category = "Unreachable" if obj.call_status != "ANSWERED" else "Contacted"
            elif lead_status == 'CONTACTED':
                category = "Callback Requested"
            elif lead_status == 'NOT_INTERESTED':
                category = "Not Interested"
            elif lead_status == 'ADMISSION_PROSPECT':
                category = "Future Prospect"
                
            last_msg = ""
            if lead:
                last_followup = FollowUp.objects.filter(lead=lead).order_by('-created_at').first()
                if last_followup:
                    last_msg = last_followup.notes[:100] if last_followup.notes else ""
            
            call_time = obj.created_at.strftime("%H:%M") if obj.created_at else ""
            call_date_fmt = obj.created_at.strftime("%Y-%m-%d") if obj.created_at else ""
            
            employees_data[agent_name].append({
                "lead_name": lead_name,
                "call_time": call_time,
                "call_date": call_date_fmt,
                "call_status": obj.call_status or "UNKNOWN",
                "lead_status": lead_status,
                "category": category,
                "last_msg": last_msg,
                "duration_sec": obj.duration or 0,
                "recording": obj.recording_url or ""
            })

        report_payload = {
            "employees": employees_data
        }
        
        # If past date and no snapshot existed, save it now
        if target_date < timezone.now().date():
            VoxbayDailySnapshot.objects.update_or_create(
                date=target_date,
                defaults={"report_data": report_payload}
            )

        return Response(report_payload)
