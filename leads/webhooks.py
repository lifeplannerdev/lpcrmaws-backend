from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .models import WebhookLog
from .tasks import process_meta_webhook, process_voxbay_webhook

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def meta_webhook(request):
    """
    Webhook endpoint for Meta Lead Ads.
    Handles GET for verification (hub.challenge) and POST for lead data.
    Enqueues to Celery task instantly.
    """
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        challenge = request.GET.get('hub.challenge')
        
        if mode == 'subscribe' and challenge:
            from django.http import HttpResponse
            return HttpResponse(challenge, content_type='text/plain')
        return Response('Error, wrong validation token', status=status.HTTP_403_FORBIDDEN)
        
    elif request.method == 'POST':
        payload = request.data
        
        # Save log instantly
        log = WebhookLog.objects.create(
            source='META',
            payload=payload,
            headers=dict(request.headers),
            status_code=200,
            processed=False
        )
        
        # Dispatch to Celery background worker to prevent timeout
        process_meta_webhook.delay(log.id, payload)
        
        return Response({'status': 'success'}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def meta_process_webhook(request):
    """
    Legacy QStash process endpoint. Kept returning 200 OK so existing Vercel hooks don't error out during migration, but no longer processes data.
    """
    return Response({'status': 'obsolete_endpoint_migrated_to_celery'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def voxbay_webhook(request):
    """
    Webhook endpoint for Voxbay call logs.
    """
    payload = request.data
    
    # Save log instantly
    log = WebhookLog.objects.create(
        source='VOXBAY',
        payload=payload,
        headers=dict(request.headers),
        status_code=200,
        processed=False
    )
    
    # Dispatch to Celery
    process_voxbay_webhook.delay(log.id, payload)
    
    return Response({'status': 'success'}, status=status.HTTP_200_OK)
