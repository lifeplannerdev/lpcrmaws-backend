from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import requests

@shared_task
def process_meta_webhook(webhook_log_id, payload):
    from .models import WebhookLog, Lead, FollowUp
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    log = None
    if webhook_log_id:
        log = WebhookLog.objects.filter(id=webhook_log_id).first()
        
    try:
        # Meta sends changes in entry -> changes -> value
        if 'entry' in payload:
            for entry in payload['entry']:
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change.get('field') == 'leadgen':
                            value = change.get('value', {})
                            leadgen_id = value.get('leadgen_id')
                            
                            # Fetch Graph API
                            meta_token = getattr(settings, 'META_ACCESS_TOKEN', '')
                            if not meta_token:
                                continue
                            
                            graph_url = f"https://graph.facebook.com/v19.0/{leadgen_id}?access_token={meta_token}"
                            response = requests.get(graph_url)
                            if response.status_code == 200:
                                lead_data = response.json()
                                field_data = lead_data.get('field_data', [])
                                
                                # Dynamic field normalization
                                extracted = {}
                                for field in field_data:
                                    name = field.get('name')
                                    values = field.get('values', [])
                                    val = values[0] if values else ""
                                    extracted[name] = val
                                
                                # Normalize
                                name_val = extracted.get('full_name') or extracted.get('student_name') or extracted.get('name') or f"Meta Lead {leadgen_id}"
                                phone_val = extracted.get('phone_number') or extracted.get('mobile') or extracted.get('whatsapp') or extracted.get('whatsapp_number') or ""
                                email_val = extracted.get('email')
                                
                                # Campaign Details
                                campaign_name = lead_data.get('campaign_name', '')
                                adset_name = lead_data.get('adset_name', '')
                                ad_name = lead_data.get('ad_name', '')
                                
                                # Deduplication
                                existing_lead = Lead.objects.filter(phone=phone_val).first() if phone_val else None
                                
                                if existing_lead:
                                    existing_remarks = existing_lead.remarks or ""
                                    existing_lead.remarks = f"{existing_remarks}\nRe-inquired via Ad: {ad_name} ({campaign_name})"
                                    existing_lead.save()
                                    
                                    assignee = existing_lead.current_handler or User.objects.filter(is_superuser=True).first()
                                    if assignee:
                                        FollowUp.objects.create(
                                            lead=existing_lead,
                                            phone_number=existing_lead.phone,
                                            name=existing_lead.name,
                                            follow_up_date=timezone.now().date(),
                                            followup_type='call',
                                            notes=f"Lead re-submitted via Meta Ad: {ad_name}",
                                            priority='high',
                                            status='pending',
                                            assigned_to=assignee
                                        )
                                else:
                                    # Create new lead
                                    new_lead = Lead.objects.create(
                                        name=name_val[:100],
                                        phone=phone_val[:20],
                                        email=email_val,
                                        source='ADS',
                                        remarks=f"Form ID: {value.get('form_id')}, Ad ID: {value.get('ad_id')}",
                                        campaign_name=campaign_name,
                                        adset_name=adset_name,
                                        ad_name=ad_name,
                                        meta_lead_id=leadgen_id,
                                        raw_form_data=lead_data
                                    )
                                    
                                    admin_user = User.objects.filter(is_superuser=True).first()
                                    if admin_user:
                                        new_lead.assigned_to = admin_user
                                        new_lead.save()
                                        
                                        FollowUp.objects.create(
                                            lead=new_lead,
                                            phone_number=new_lead.phone,
                                            name=new_lead.name,
                                            follow_up_date=timezone.now().date(),
                                            followup_type='call',
                                            notes="Initial call for new Meta Lead",
                                            priority='high',
                                            status='pending',
                                            assigned_to=admin_user
                                        )

        if log:
            log.processed = True
            log.save()
    except Exception as e:
        if log:
            log.error_message = str(e)
            log.save()
        raise e


@shared_task
def process_voxbay_webhook(webhook_log_id, payload):
    from .models import WebhookLog, Lead, FollowUp
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    log = None
    if webhook_log_id:
        log = WebhookLog.objects.filter(id=webhook_log_id).first()
        
    try:
        call_type = payload.get('Calltype') or payload.get('calltype', 'Incoming')
        
        if call_type.lower() == 'outgoing':
            # For outgoing, 'destination' is the lead's number
            lead_number = payload.get('destination') or payload.get('calledNumber') or payload.get('phone') or payload.get('number')
            call_status = payload.get('status') or payload.get('callStatus', '')
            call_duration = payload.get('duration') or payload.get('conversationDuration') or payload.get('totalCallDuration') or payload.get('callDuration') or payload.get('billsec', '')
            audio_url = payload.get('recording_URL') or payload.get('recording_url') or payload.get('recordingUrl') or payload.get('audio') or ''
            call_direction_text = "Outgoing"
        else:
            # For incoming, 'callerNumber' is the lead's number
            lead_number = payload.get('callerNumber') or payload.get('callerid') or payload.get('caller_number') or payload.get('phone') or payload.get('number')
            call_status = payload.get('callStatus') or payload.get('status', '')
            call_duration = payload.get('conversationDuration') or payload.get('totalCallDuration') or payload.get('duration') or payload.get('callDuration', '')
            audio_url = payload.get('recording_URL') or payload.get('recording_url') or payload.get('recordingUrl') or payload.get('audio') or ''
            call_direction_text = "Incoming"

        if not call_status and call_duration:
            try:
                if int(call_duration) > 0:
                    call_status = "ANSWERED"
                else:
                    call_status = "MISSED"
            except ValueError:
                pass
        
        callevent = payload.get("Callevent") or payload.get("callevent") or payload.get("event") or ""
        
        if callevent.strip().lower() in ["call start", "start", "connect", "ringing", "disconnect"]:
            if log:
                log.processed = True
                log.save()
            return
            
        if lead_number:
            lead = Lead.objects.filter(phone=lead_number).first()
            if lead:
                assignee = lead.current_handler or User.objects.filter(is_superuser=True).first()
                if assignee:
                    notes = f"Auto-scheduled from Voxbay {call_direction_text.lower()} call log. Call status: {call_status}"
                    if call_duration:
                        notes += f", Duration: {call_duration}s"
                    if audio_url:
                        notes += f"\n[Audio Recording: {audio_url}]"

                    FollowUp.objects.create(
                        lead=lead,
                        phone_number=lead.phone,
                        name=lead.name,
                        follow_up_date=timezone.localtime(timezone.now()).date(),
                        followup_type='call',
                        notes=notes,
                        priority='high',
                        status='pending',
                        assigned_to=assignee
                    )
        
        if log:
            log.processed = True
            log.save()
    except Exception as e:
        if log:
            log.error_message = str(e)
            log.save()
        raise e
