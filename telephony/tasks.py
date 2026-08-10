from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

@shared_task
def snapshot_voxbay_ai_daily():
    # Run at 23:59 to get today's data and snapshot it.
    from telephony.views import VoxbayAIReportView
    from telephony.models import VoxbayDailySnapshot
    from rest_framework.test import APIRequestFactory
    
    target_date = timezone.now().date()
    
    try:
        # Instead of calling API via HTTP, we can just instantiate the view logic
        factory = APIRequestFactory()
        request = factory.get(f'/api/telephony/voxbay-ai/report/?date={target_date}')
        
        # We need a mock user with permissions, or we just extract the logic.
        # Actually it's cleaner to just extract the logic, but since it's in a view, let's just duplicate the data fetching for reliability, or use the View method.
        # It's better to just write the specific logic here to avoid coupling.
        from telephony.models import VoxbayCallLog
        from leads.models import Lead, FollowUp
        from accounts.models import User
        from django.db.models import Q
        from datetime import datetime

        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())
        from django.utils.timezone import make_aware, is_naive
        if is_naive(start_dt):
            start_dt = make_aware(start_dt)
            end_dt = make_aware(end_dt)

        call_logs = VoxbayCallLog.objects.filter(
            call_type='outgoing',
            created_at__gte=start_dt,
            created_at__lte=end_dt
        ).order_by('-created_at')

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
            search_num = lead_number[-10:] if lead_number and len(lead_number) >= 10 else lead_number
            lead = None
            if search_num:
                lead = Lead.objects.filter(Q(phone=lead_number) | Q(phone__endswith=search_num)).first()
            
            lead_name = lead.name if lead else f"Unknown ({lead_number})"
            lead_status = lead.status if lead else "UNKNOWN"
            
            last_msg = ""
            if lead:
                last_followup = FollowUp.objects.filter(lead=lead).order_by('-created_at').first()
                if last_followup:
                    last_msg = last_followup.notes[:200] if last_followup.notes else ""
            
            category = "Uncategorized"
            l_msg = last_msg.lower()
            if "not interested" in l_msg:
                category = "Not Interested"
            elif "joined elsewhere" in l_msg or "lost" in l_msg:
                category = "Lost - Joined Elsewhere"
            elif "callback" in l_msg or "call back" in l_msg:
                category = "Callback Requested"
            elif "wrong number" in l_msg:
                category = "Wrong Number"
            elif "busy" in l_msg:
                category = "Busy"
            elif "future prospect" in l_msg or "prospect" in l_msg:
                category = "Future Prospect"
            elif "unreachable" in l_msg or "not reachable" in l_msg or "switch off" in l_msg or "switched off" in l_msg or "not lifting" in l_msg:
                category = "Unreachable"
            else:
                if lead_status == 'ENQUIRY':
                    category = "Unreachable" if obj.call_status != "ANSWERED" else "Contacted"
                elif lead_status == 'CONTACTED':
                    category = "Callback Requested"
                elif lead_status == 'NOT_INTERESTED':
                    category = "Not Interested"
                elif lead_status == 'ADMISSION_PROSPECT':
                    category = "Future Prospect"
            
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
        
        VoxbayDailySnapshot.objects.update_or_create(
            date=target_date,
            defaults={"report_data": report_payload}
        )
        logger.info(f"Successfully snapshotted Voxbay AI data for {target_date}")
        
    except Exception as e:
        logger.error(f"Failed to snapshot Voxbay AI data: {e}")
