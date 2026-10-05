from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import MailAccount, EmailSignature, EmailTemplate, EmailMessage, EmailAttachment
from .serializers import (
    MailAccountSerializer, EmailSignatureSerializer, EmailTemplateSerializer,
    EmailMessageSerializer, EmailMessageCreateUpdateSerializer, EmailAttachmentSerializer
)
from .services import send_draft, sync_student, get_gmail_attachment, sync_draft_to_gmail
from accounts.permissions import has_dynamic_permission
from rest_framework.exceptions import PermissionDenied
import mimetypes

class MailPermissionMixin:
    """Ensure user has mail:use or mail:manage permission."""
    def check_permissions(self, request):
        super().check_permissions(request)
        if not (has_dynamic_permission(request.user, 'mail:use') or has_dynamic_permission(request.user, 'mail:manage')):
            raise PermissionDenied("You do not have permission to access mail features.")

class MailManagePermissionMixin(MailPermissionMixin):
    """Ensure user has mail:manage permission for write operations."""
    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in ['GET', 'HEAD', 'OPTIONS']:
            if not has_dynamic_permission(request.user, 'mail:manage'):
                raise PermissionDenied("You do not have permission to manage mail settings.")


class MailAccountViewSet(MailManagePermissionMixin, viewsets.ModelViewSet):
    queryset = MailAccount.objects.all()
    serializer_class = MailAccountSerializer

    def perform_create(self, serializer):
        serializer.save(connected_by=self.request.user)

    @action(detail=True, methods=['post'])
    def fetch_signatures(self, request, pk=None):
        account = self.get_object()
        from .gmail_client import GmailClient
        try:
            client = GmailClient(account)
            aliases = client.send_as_list()
            imported = 0
            for alias in aliases:
                if alias.get('signature'):
                    from .models import EmailSignature
                    sig, created = EmailSignature.objects.get_or_create(
                        name=f"Gmail: {alias['email']}",
                        owner=request.user,
                        defaults={'body_html': alias['signature']}
                    )
                    if not created and sig.body_html != alias['signature']:
                        sig.body_html = alias['signature']
                        sig.save(update_fields=['body_html'])
                    imported += 1
            return Response({'imported': imported, 'message': f'Synced {imported} signatures.'})
        except Exception as e:
            return Response({'detail': str(e)}, status=400)




class EmailSignatureViewSet(MailPermissionMixin, viewsets.ModelViewSet):
    serializer_class = EmailSignatureSerializer

    def get_queryset(self):
        # Users see shared signatures (owner=None) and their own
        return EmailSignature.objects.filter(Q(owner=None) | Q(owner=self.request.user))

    def perform_create(self, serializer):
        # If user has manage permission and wants to make it shared? 
        # For now, let's just make it personal unless they check a 'shared' flag, but model defaults to personal if owner set.
        is_shared = self.request.data.get('is_shared', False)
        if is_shared and has_dynamic_permission(self.request.user, 'mail:manage'):
            serializer.save(owner=None)
        else:
            serializer.save(owner=self.request.user)


class EmailTemplateViewSet(MailManagePermissionMixin, viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.filter(is_active=True)
    serializer_class = EmailTemplateSerializer

    def perform_create(self, serializer):
        msg = serializer.save(created_by=self.request.user)
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Failed to sync draft to gmail: %s', e)


class EmailMessageViewSet(MailPermissionMixin, viewsets.ModelViewSet):
    serializer_class = EmailMessageSerializer

    def get_queryset(self):
        qs = EmailMessage.objects.all().select_related('account', 'template', 'created_by', 'student').prefetch_related('attachments')
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EmailMessageCreateUpdateSerializer
        return EmailMessageSerializer

    def perform_create(self, serializer):
        msg = serializer.save(created_by=self.request.user)
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Failed to sync draft to gmail: %s', e)
        
    def perform_update(self, serializer):
        message = self.get_object()
        if message.state != EmailMessage.STATE_DRAFT:
            raise PermissionDenied("Only drafts can be edited.")
        msg = serializer.save()
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Failed to sync draft to gmail: %s', e)

    def perform_destroy(self, instance):
        if instance.state == EmailMessage.STATE_DRAFT and instance.gmail_draft_id and instance.account:
            from .gmail_client import GmailClient
            try:
                client = GmailClient(instance.account)
                client.delete_draft(instance.gmail_draft_id)
            except Exception:
                pass
        instance.delete()

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        message = self.get_object()
        if message.state != EmailMessage.STATE_DRAFT:
            return Response({"detail": "Only drafts can be sent."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            sent_msg = send_draft(message)
            serializer = self.get_serializer(sent_msg)
            return Response(serializer.data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def sync(self, request):
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({"detail": "student_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        from trainers.models import ProcessingStudent
        try:
            student = ProcessingStudent.objects.get(id=student_id)
            sync_student(student)
            return Response({"detail": "Sync completed successfully."})
        except ProcessingStudent.DoesNotExist:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EmailAttachmentViewSet(MailPermissionMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = EmailAttachment.objects.all()
    serializer_class = EmailAttachmentSerializer

    def perform_create(self, serializer):
        message_id = self.request.data.get('message')
        if not message_id:
            raise serializers.ValidationError({"message": "Message ID is required"})
        
        try:
            message = EmailMessage.objects.get(id=message_id)
        except EmailMessage.DoesNotExist:
            raise serializers.ValidationError({"message": "Invalid Message ID"})

        if message.state != EmailMessage.STATE_DRAFT:
            raise PermissionDenied("Can only add attachments to drafts.")
            
        file_obj = self.request.FILES.get('file')
        if file_obj:
            size = file_obj.size
            content_type, _ = mimetypes.guess_type(file_obj.name)
            serializer.save(message=message, size=size, content_type=content_type or 'application/octet-stream')
        else:
            serializer.save(message=message)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        attachment = self.get_object()
        if attachment.gmail_attachment_id and not attachment.file:
            # Need to fetch from Gmail API
            try:
                get_gmail_attachment(attachment)
            except Exception as e:
                return Response({"detail": f"Failed to fetch attachment: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
                
        if attachment.file:
            return Response({"url": attachment.file.url})
        elif attachment.student_document and attachment.student_document.document:
            return Response({"url": attachment.student_document.document.url})
        return Response({"detail": "Attachment file not found"}, status=status.HTTP_404_NOT_FOUND)

from django.conf import settings
from google_auth_oauthlib.flow import Flow
from rest_framework.decorators import api_view, permission_classes
import os

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_template_variables(request):
    from .variables import VARIABLES
    import re
    vars_list = [{'id': v[0], 'label': v[1]} for v in VARIABLES]
    
    try:
        from trainers.models import ProcessingDynamicField
        for d in ProcessingDynamicField.objects.all():
            clean_k = re.sub(r'[^a-zA-Z0-9_]', '_', d.name.lower().strip())
            if clean_k not in [v['id'] for v in vars_list]:
                vars_list.append({'id': clean_k, 'label': d.name})
    except Exception:
        pass
        
    return Response(vars_list)

@api_view(['GET'])

@permission_classes([IsAuthenticated])
def gmail_authorize(request):
    if not has_dynamic_permission(request.user, 'mail:manage'):
        return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_SHEETS_CREDENTIALS_FILE,  # Reusing the existing credentials file
        scopes=['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.settings.basic'],
        redirect_uri=f"{settings.FRONTEND_URL}/gmail-callback"
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    request.session['gmail_oauth_state'] = state
    return Response({'authorization_url': authorization_url})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def gmail_callback(request):
    if not has_dynamic_permission(request.user, 'mail:manage'):
        return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
    state = request.data.get('state')
    code = request.data.get('code')
    
    if not state or not code:
        return Response({"detail": "Missing state or code"}, status=status.HTTP_400_BAD_REQUEST)
        
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_SHEETS_CREDENTIALS_FILE,
        scopes=['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.settings.basic'],
        redirect_uri=f"{settings.FRONTEND_URL}/gmail-callback",
        state=state
    )
    
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Get email address
        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        email_address = profile.get('emailAddress')
        
        # Save to MailAccount
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        account, created = MailAccount.objects.update_or_create(
            email=email_address,
            defaults={
                'credentials': creds_data,
                'status': MailAccount.STATUS_CONNECTED,
                'connected_by': request.user
            }
        )
        
        return Response({"detail": "Gmail connected successfully", "email": email_address})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
