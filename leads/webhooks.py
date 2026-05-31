import json
import hmac
import hashlib
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

from .models import WebhookLog, Lead, FollowUp

User = get_user_model()


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def meta_webhook(request):
    """
    Webhook endpoint for Meta Lead Ads.
    Handles GET for verification (hub.challenge) and POST for lead data.
    Acts as a receiver and forwards to QStash.
    """
    if request.method == 'GET':
        # Meta verification challenge
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        # In a real app, verify against settings.META_VERIFY_TOKEN
        if mode == 'subscribe' and challenge:
            return Response(int(challenge), status=status.HTTP_200_OK)
        return Response('Error, wrong validation token', status=status.HTTP_403_FORBIDDEN)
        
    elif request.method == 'POST':
        payload = request.data
        
        # Save log
        log = WebhookLog.objects.create(
            source='META',
            payload=payload,
            headers=dict(request.headers),
            status_code=200,
            processed=False
        )
        
        try:
            from upstash_qstash import Client
            token = getattr(settings, 'QSTASH_TOKEN', '')
            if token:
                client = Client(token)
                process_url = request.build_absolute_uri('/leads/api/meta/process/')
                client.publish_json(
                    url=process_url,
                    body={"webhook_log_id": log.id, "payload": payload}
                )
            return Response({'status': 'success'}, status=status.HTTP_200_OK)
        except Exception as e:
            log.error_message = f"QStash publish error: {str(e)}"
            log.save()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def meta_process_webhook(request):
    """
    Processes the Meta webhook payload received from QStash.
    """
    try:
        from upstash_qstash import Receiver
        # Verify signature
        current_key = getattr(settings, 'QSTASH_CURRENT_SIGNING_KEY', '')
        next_key = getattr(settings, 'QSTASH_NEXT_SIGNING_KEY', '')
        
        if current_key and next_key:
            receiver = Receiver(
                current_signing_key=current_key,
                next_signing_key=next_key
            )
            signature = request.headers.get("Upstash-Signature")
            body = request.body.decode('utf-8')
            if signature:
                receiver.verify(body=body, signature=signature)
                
        data = request.data
        webhook_log_id = data.get("webhook_log_id")
        payload = data.get("payload", {})
        
        log = None
        if webhook_log_id:
            log = WebhookLog.objects.filter(id=webhook_log_id).first()
            
        # Meta sends changes in entry -> changes -> value
        if 'entry' in payload:
            import requests
            for entry in payload['entry']:
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change.get('field') == 'leadgen':
                            value = change.get('value', {})
                            leadgen_id = value.get('leadgen_id')
                            
                            # 3.1 Fetch Graph API
                            meta_token = getattr(settings, 'META_ACCESS_TOKEN', '')
                            if not meta_token:
                                continue
                            
                            graph_url = f"https://graph.facebook.com/v19.0/{leadgen_id}?access_token={meta_token}"
                            response = requests.get(graph_url)
                            if response.status_code == 200:
                                lead_data = response.json()
                                field_data = lead_data.get('field_data', [])
                                
                                # 3.2 Dynamic field normalization
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
                                
                                # 3.3 Campaign Details
                                campaign_name = lead_data.get('campaign_name', '')
                                adset_name = lead_data.get('adset_name', '')
                                ad_name = lead_data.get('ad_name', '')
                                
                                # 3.4 Deduplication
                                existing_lead = Lead.objects.filter(phone=phone_val).first() if phone_val else None
                                
                                if existing_lead:
                                    # Update remarks & schedule followup (Task 4.1)
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
                                    
                                    # Task 4.2 Auto assignment
                                    # Placeholder: assign to admin if no rule matches
                                    admin_user = User.objects.filter(is_superuser=True).first()
                                    if admin_user:
                                        new_lead.assigned_to = admin_user
                                        new_lead.save()
                                        
                                        # Task 4.3 Standard Call FollowUp
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
            
        return Response({'status': 'success'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['POST'])
@permission_classes([AllowAny])
def voxbay_webhook(request):
    """
    Webhook endpoint for Voxbay call logs.
    """
    payload = request.data
    
    # Save log
    log = WebhookLog.objects.create(
        source='VOXBAY',
        payload=payload,
        headers=dict(request.headers),
        status_code=200
    )
    
    try:
        # Assuming payload has 'caller_number', 'call_type', 'agent_number'
        caller_number = payload.get('caller_number') or payload.get('phone') or payload.get('number')
        call_status = payload.get('status', '')
        
        if caller_number:
            # Check if this caller is an existing lead
            lead = Lead.objects.filter(phone=caller_number).first()
            
            if lead:
                # 2.4 Auto-schedule follow-up
                # Assign to the current handler or an admin if none
                assignee = lead.current_handler or User.objects.filter(is_superuser=True).first()
                if assignee:
                    FollowUp.objects.create(
                        lead=lead,
                        phone_number=lead.phone,
                        name=lead.name,
                        follow_up_date=(timezone.now() + timedelta(days=1)).date(),
                        followup_type='call',
                        notes=f"Auto-scheduled from Voxbay call log. Call status: {call_status}",
                        priority='high',
                        status='pending',
                        assigned_to=assignee
                    )
            else:
                # Unknown caller: We don't auto-create the lead here, but the WebhookLog
                # will be visible in the UI for "1-Click Lead Conversion".
                pass
                
        log.processed = True
        log.save()
        return Response({'status': 'success'}, status=status.HTTP_200_OK)
    except Exception as e:
        log.error_message = str(e)
        log.save()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
