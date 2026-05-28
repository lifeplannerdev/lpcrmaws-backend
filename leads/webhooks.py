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
            status_code=200
        )
        
        try:
            # Meta sends changes in entry -> changes -> value
            if 'entry' in payload:
                for entry in payload['entry']:
                    if 'changes' in entry:
                        for change in entry['changes']:
                            if change.get('field') == 'leadgen':
                                value = change.get('value', {})
                                leadgen_id = value.get('leadgen_id')
                                
                                # Typically, you'd fetch the lead details via Graph API here.
                                # For this implementation, we will create a Lead with the leadgen_id as phone
                                # or if data is passed directly in the payload.
                                
                                # Let's assume some basic data is available or we create a placeholder Lead
                                Lead.objects.create(
                                    name=f"Meta Lead {leadgen_id}",
                                    phone=f"meta_{leadgen_id}"[:20],
                                    source='ADS',
                                    remarks=f"Form ID: {value.get('form_id')}, Ad ID: {value.get('ad_id')}"
                                )
                                
            log.processed = True
            log.save()
            return Response({'status': 'success'}, status=status.HTTP_200_OK)
        except Exception as e:
            log.error_message = str(e)
            log.save()
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
