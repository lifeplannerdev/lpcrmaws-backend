import logging
import mimetypes
import os
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.functions import Coalesce
from google_auth_oauthlib.flow import Flow
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Role
from accounts.permissions import has_dynamic_permission

from .models import EmailAttachment, EmailMessage, EmailSignature, EmailTemplate, MailAccount
from .serializers import (
    EmailAttachmentSerializer,
    EmailMessageCreateUpdateSerializer,
    EmailMessageSerializer,
    EmailSignatureSerializer,
    EmailTemplateSerializer,
    MailAccountSerializer,
)
from .services import (
    MailError,
    get_gmail_attachment,
    send_draft,
    sync_account_threads,
    sync_draft_to_gmail,
    sync_student,
)

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
logger = logging.getLogger(__name__)
User = get_user_model()

AVAILABLE_MAIL_PAGES = [
    {'id': 'tasks', 'label': 'Tasks & Assignments', 'category': 'Executive & Ops'},
    {'id': 'penalties', 'label': 'Penalties & Disciplinary', 'category': 'HR & Ops'},
    {'id': 'reports', 'label': 'Daily Staff Reports', 'category': 'Executive & Ops'},
    {'id': 'staff_analysis', 'label': 'Staff Analysis & Leads Hub', 'category': 'Sales & Executive'},
    {'id': 'processing_students', 'label': 'Processing & Admissions', 'category': 'Academics'},
    {'id': 'receipts', 'label': 'Fees & Digital Receipts', 'category': 'Finance'},
    {'id': 'leads', 'label': 'Leads & Command Centre', 'category': 'Sales & Executive'},
    {'id': 'staff', 'label': 'Staff Directory & Profiles', 'category': 'HR & Ops'},
    {'id': 'candidates', 'label': 'Recruitment & Candidates', 'category': 'HR & Ops'},
]


def is_mail_admin(user):
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or has_dynamic_permission(user, 'mail:manage'))


def has_mail_access(user):
    if not user or not user.is_authenticated:
        return False
    return bool(
        user.is_superuser
        or has_dynamic_permission(user, 'mail:manage')
        or has_dynamic_permission(user, 'mail:use')
    )


def get_user_default_module_scope(user):
    if not user or not user.is_authenticated:
        return MailAccount.SCOPE_PROCESSING
    role_names = {r.upper() for r in user.db_roles.values_list('name', flat=True)}
    if role_names & {'MANAGING_DIRECTOR', 'MD', 'DIRECTOR', 'CEO'}:
        return MailAccount.SCOPE_EXECUTIVE
    if role_names & {'ACCOUNTANT', 'ACCOUNTS', 'FINANCE'} or has_dynamic_permission(user, 'fees:accounts'):
        return MailAccount.SCOPE_FEES
    if role_names & {'HR', 'HR_MANAGER'}:
        return MailAccount.SCOPE_HR
    if role_names & {'ADM_MANAGER', 'ADM_COUNSELLOR', 'BUSINESS_HEAD', 'CM'}:
        return MailAccount.SCOPE_SALES
    return MailAccount.SCOPE_PROCESSING


def get_user_own_accounts_queryset(user):
    """
    Return the queryset of MailAccounts that belong specifically to `user`'s own Role(s) or User assignment.
    For legacy accounts that have no `assigned_roles` and no `assigned_users` yet, falls back to matching
    `module_scope` to the user's default role scope.
    """
    if not user or not user.is_authenticated:
        return MailAccount.objects.none()

    user_role_ids = list(user.db_roles.values_list('id', flat=True))
    default_scope = get_user_default_module_scope(user)

    explicit_q = Q(assigned_users=user)
    if user_role_ids:
        explicit_q |= Q(assigned_roles__id__in=user_role_ids)

    # Legacy fallback: accounts that have no roles and no users assigned, matching the user's role scope
    unassigned_same_scope_q = (
        Q(assigned_roles__isnull=True)
        & Q(assigned_users__isnull=True)
        & Q(module_scope=default_scope)
    )

    return MailAccount.objects.filter(explicit_q | unassigned_same_scope_q).distinct()


class MailPermissionMixin:
    """Ensure user has mail:use or mail:manage permission."""
    def check_permissions(self, request):
        if getattr(self, 'action', None) == 'download':
            return
        super().check_permissions(request)
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated("Authentication credentials were not provided.")
        if not has_mail_access(request.user):
            raise PermissionDenied("You do not have permission to access mail features.")


class MailAccountViewSet(MailPermissionMixin, viewsets.ModelViewSet):
    queryset = MailAccount.objects.all()
    serializer_class = MailAccountSerializer

    def get_queryset(self):
        user = self.request.user
        admin = is_mail_admin(user)
        view_mode = (self.request.query_params.get('view_mode') or '').strip().lower()
        module = (
            self.request.query_params.get('module')
            or self.request.query_params.get('module_scope')
            or ''
        ).strip().upper()
        company = (self.request.query_params.get('company') or '').strip().upper()
        page_key = (self.request.query_params.get('page') or '').strip().lower()
        role_id = self.request.query_params.get('role_id')

        if admin:
            if view_mode == 'own':
                qs = get_user_own_accounts_queryset(user)
            else:
                qs = MailAccount.objects.all()
        else:
            # Strict data isolation for mail:use users: ONLY their own role/user assigned accounts
            qs = get_user_own_accounts_queryset(user)

        if module and module != 'ALL':
            if admin:
                qs = qs.filter(Q(module_scope=module) | Q(module_scope=MailAccount.SCOPE_GLOBAL))
            else:
                qs = qs.filter(module_scope=module)

        if company and company != 'ALL':
            qs = qs.filter(company=company)

        if role_id and str(role_id).isdigit() and admin:
            qs = qs.filter(assigned_roles__id=int(role_id))

        qs = qs.prefetch_related('assigned_roles', 'assigned_users').distinct()

        if page_key:
            # Filter accounts where allowed_pages is empty (all allowed in scope) or contains page_key
            matching_ids = [
                acc.id for acc in qs
                if not acc.allowed_pages or page_key in [str(p).lower() for p in acc.allowed_pages]
            ]
            qs = qs.filter(id__in=matching_ids)

        return qs

    def check_write_permission(self, request, account=None):
        if is_mail_admin(request.user):
            return
        raise PermissionDenied(
            "Only users with 'mail:manage' permission can modify mailbox configurations or role assignments."
        )

    def perform_create(self, serializer):
        self.check_write_permission(self.request)
        serializer.save(connected_by=self.request.user)

    def perform_update(self, serializer):
        self.check_write_permission(self.request, serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self.check_write_permission(self.request, instance)
        instance.delete()

    @action(detail=False, methods=['get'])
    def access_metadata(self, request):
        """
        Return RBAC metadata, available roles, staff, scopes, and pages for the standalone
        Mail Accounts & Settings page (/mail-settings) and Mail Control Center (/mail-center).
        """
        user = request.user
        admin = is_mail_admin(user)
        user_roles = [
            {'id': r.id, 'name': r.name, 'description': r.description or ''}
            for r in user.db_roles.all()
        ]
        default_scope = get_user_default_module_scope(user)

        if admin:
            all_roles = [
                {'id': r.id, 'name': r.name, 'description': r.description or ''}
                for r in Role.objects.all().order_by('name')
            ]
            all_staff = [
                {
                    'id': u.id,
                    'username': u.username,
                    'full_name': u.get_full_name() or u.username,
                    'email': u.email or '',
                    'roles': list(u.db_roles.values_list('name', flat=True)),
                    'company': u.company,
                }
                for u in User.objects.filter(is_active=True).prefetch_related('db_roles').order_by('first_name', 'username')
            ]
        else:
            all_roles = user_roles
            all_staff = [
                {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.get_full_name() or user.username,
                    'email': user.email or '',
                    'roles': [r['name'] for r in user_roles],
                    'company': user.company,
                }
            ]

        return Response({
            'can_manage': admin,
            'can_use': has_mail_access(user),
            'user_id': user.id,
            'user_roles': user_roles,
            'default_scope': default_scope,
            'available_scopes': [
                {'id': k, 'label': v} for k, v in MailAccount.SCOPE_CHOICES
            ],
            'available_pages': AVAILABLE_MAIL_PAGES,
            'roles': all_roles,
            'staff': all_staff,
        })

    @action(detail=True, methods=['get'])
    def send_as_aliases(self, request, pk=None):
        """Fetch Send-As aliases configured in the underlying Gmail account."""
        account = self.get_object()
        from .gmail_client import GmailClient
        try:
            client = GmailClient(account)
            aliases = client.send_as_list()
            return Response(aliases)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['post'])
    def set_send_as(self, request, pk=None):
        self.check_write_permission(request)
        account = self.get_object()
        send_as_email = (request.data.get('send_as_email') or '').strip().lower()
        display_name = (request.data.get('display_name') or '').strip()
        account.send_as_email = send_as_email
        if display_name:
            account.display_name = display_name
        if 'custom_aliases' in request.data and isinstance(request.data.get('custom_aliases'), list):
            account.custom_aliases = request.data.get('custom_aliases')
        account.save(update_fields=['send_as_email', 'display_name', 'custom_aliases'])
        return Response(MailAccountSerializer(account).data)

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
                    sig, created = EmailSignature.objects.get_or_create(
                        name=f"Gmail: {alias['email']}",
                        owner=request.user,
                        defaults={
                            'body_html': alias['signature'],
                            'module_scope': account.module_scope,
                            'account': account,
                        }
                    )
                    if not created and sig.body_html != alias['signature']:
                        sig.body_html = alias['signature']
                        sig.save(update_fields=['body_html'])
                    imported += 1
            return Response({'imported': imported, 'message': f'Synced {imported} signatures.'})
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['post'])
    def sync_threads(self, request, pk=None):
        """Sync recent Gmail threads for this specific mailbox."""
        account = self.get_object()
        target_email = (request.data.get('target_email') or '').strip() or None
        res = sync_account_threads(account, target_email=target_email)
        return Response({
            'detail': f"Synced {res.get('imported', 0)} new messages.",
            'imported': res.get('imported', 0),
            'errors': res.get('errors', []),
        })


class EmailSignatureViewSet(MailPermissionMixin, viewsets.ModelViewSet):
    serializer_class = EmailSignatureSerializer

    def get_queryset(self):
        user = self.request.user
        admin = is_mail_admin(user)
        user_role_ids = list(user.db_roles.values_list('id', flat=True))
        default_scope = get_user_default_module_scope(user)
        requested_scope = (self.request.query_params.get('module_scope') or '').strip().upper()

        if admin:
            qs = EmailSignature.objects.filter(Q(owner=None) | Q(owner=user))
            if requested_scope and requested_scope != 'ALL':
                qs = qs.filter(
                    Q(module_scope=requested_scope)
                    | Q(module_scope=MailAccount.SCOPE_GLOBAL)
                    | Q(owner=user)
                )
            return qs.distinct()

        # Strict isolation for mail:use users: own signatures OR shared signatures for their role/scope
        shared_for_role = Q(owner=None) & (
            Q(scope_roles__id__in=user_role_ids)
            | (Q(scope_roles__isnull=True) & Q(module_scope=default_scope))
        )
        return EmailSignature.objects.filter(Q(owner=user) | shared_for_role).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        is_shared = bool(self.request.data.get('is_shared', False))
        scope = (
            self.request.data.get('module_scope')
            or get_user_default_module_scope(user)
        ).upper()
        if is_shared and is_mail_admin(user):
            sig = serializer.save(owner=None, module_scope=scope)
        else:
            sig = serializer.save(owner=user, module_scope=scope)
        if not sig.scope_roles.exists():
            user_roles = list(user.db_roles.all())
            if user_roles:
                sig.scope_roles.set(user_roles)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.owner and instance.owner != self.request.user and not is_mail_admin(self.request.user):
            raise PermissionDenied("You cannot edit another user's signature.")
        if instance.owner is None and not is_mail_admin(self.request.user):
            raise PermissionDenied("Only mail managers can edit shared signatures.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner and instance.owner != self.request.user and not is_mail_admin(self.request.user):
            raise PermissionDenied("You cannot delete another user's signature.")
        if instance.owner is None and not is_mail_admin(self.request.user):
            raise PermissionDenied("Only mail managers can delete shared signatures.")
        instance.delete()


class EmailTemplateViewSet(MailPermissionMixin, viewsets.ModelViewSet):
    serializer_class = EmailTemplateSerializer

    def get_queryset(self):
        user = self.request.user
        admin = is_mail_admin(user)
        user_role_ids = list(user.db_roles.values_list('id', flat=True))
        default_scope = get_user_default_module_scope(user)
        requested_scope = (self.request.query_params.get('module_scope') or '').strip().upper()

        qs = EmailTemplate.objects.filter(is_active=True).prefetch_related('scope_roles')

        if admin:
            if requested_scope and requested_scope != 'ALL':
                qs = qs.filter(
                    Q(module_scope=requested_scope)
                    | Q(module_scope=MailAccount.SCOPE_GLOBAL)
                )
            return qs.distinct()

        # Strict isolation for mail:use users: templates assigned to their role, created by them, or in their role's module_scope
        role_filter = (
            Q(created_by=user)
            | Q(scope_roles__id__in=user_role_ids)
            | (Q(scope_roles__isnull=True) & Q(module_scope=default_scope))
        )
        return qs.filter(role_filter).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        scope = (
            self.request.data.get('module_scope')
            or get_user_default_module_scope(user)
        ).upper()
        tpl = serializer.save(created_by=user, module_scope=scope)
        if not tpl.scope_roles.exists() and not is_mail_admin(user):
            user_roles = list(user.db_roles.all())
            if user_roles:
                tpl.scope_roles.set(user_roles)

    def perform_update(self, serializer):
        instance = self.get_object()
        if not is_mail_admin(self.request.user) and instance.created_by != self.request.user:
            raise PermissionDenied("You can only edit templates created by you.")
        serializer.save()

    def perform_destroy(self, instance):
        if not is_mail_admin(self.request.user) and instance.created_by != self.request.user:
            raise PermissionDenied("You can only delete templates created by you.")
        instance.delete()


class EmailMessageViewSet(MailPermissionMixin, viewsets.ModelViewSet):
    serializer_class = EmailMessageSerializer

    def get_queryset(self):
        user = self.request.user
        admin = is_mail_admin(user)
        requested_scope = (self.request.query_params.get('module_scope') or '').strip().upper()

        qs = (
            EmailMessage.objects.all()
            .select_related('account', 'template', 'created_by', 'student', 'recipient_staff', 'lead')
            .prefetch_related('attachments')
            .annotate(sort_time=Coalesce('sent_at', 'created_at'))
            .order_by('-sort_time')
        )

        # Role & Mailbox Data Separation
        if admin:
            if requested_scope and requested_scope != 'ALL':
                scoped_accounts = MailAccount.objects.filter(module_scope=requested_scope)
                qs = qs.filter(
                    Q(account__in=scoped_accounts)
                    | Q(context_module=requested_scope)
                )
        else:
            own_accounts = get_user_own_accounts_queryset(user)
            qs = qs.filter(Q(account__in=own_accounts) | Q(created_by=user))

        # Specific Context / Entity Filters
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=student_id)

        recipient_staff_id = self.request.query_params.get('recipient_staff_id')
        if recipient_staff_id and str(recipient_staff_id).isdigit():
            qs = qs.filter(recipient_staff_id=int(recipient_staff_id))

        lead_id = self.request.query_params.get('lead_id')
        if lead_id and str(lead_id).isdigit():
            qs = qs.filter(lead_id=int(lead_id))

        context_module = (self.request.query_params.get('context_module') or '').strip().upper()
        if context_module:
            qs = qs.filter(context_module=context_module)

        context_id = (self.request.query_params.get('context_id') or '').strip()
        if context_id:
            qs = qs.filter(context_id=context_id)

        account_id = self.request.query_params.get('account_id')
        if account_id and str(account_id).isdigit():
            qs = qs.filter(account_id=int(account_id))

        gmail_thread_id = (self.request.query_params.get('gmail_thread_id') or '').strip()
        if gmail_thread_id:
            qs = qs.filter(gmail_thread_id=gmail_thread_id)

        target_email = (self.request.query_params.get('target_email') or '').strip().lower()
        if target_email:
            qs = qs.filter(
                Q(from_email__icontains=target_email)
                | Q(to__icontains=target_email)
                | Q(recipient_staff__email__iexact=target_email)
                | Q(lead__email__iexact=target_email)
                | Q(student__email__iexact=target_email)
            )

        return qs

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EmailMessageCreateUpdateSerializer
        return EmailMessageSerializer

    def _validate_account_access(self, account):
        if not account:
            return
        if is_mail_admin(self.request.user):
            return
        own_accounts = get_user_own_accounts_queryset(self.request.user)
        if not own_accounts.filter(pk=account.pk).exists():
            raise PermissionDenied("You do not have permission to send from this mailbox.")

    def perform_create(self, serializer):
        account = serializer.validated_data.get('account')
        self._validate_account_access(account)
        context_module = (
            serializer.validated_data.get('context_module')
            or (account.module_scope if account else get_user_default_module_scope(self.request.user))
        )
        msg = serializer.save(
            created_by=self.request.user,
            context_module=context_module,
            body_text=serializer.validated_data.get('body_html', ''),
        )
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            logger.warning('Failed to sync draft to gmail: %s', e)

    def perform_update(self, serializer):
        message = self.get_object()
        if message.state != EmailMessage.STATE_DRAFT:
            raise PermissionDenied("Only drafts can be edited.")
        account = serializer.validated_data.get('account', message.account)
        self._validate_account_access(account)
        msg = serializer.save()
        try:
            sync_draft_to_gmail(msg)
        except Exception as e:
            logger.warning('Failed to sync draft to gmail: %s', e)

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
        self._validate_account_access(message.account)
        force = bool(request.data.get('force', True))
        try:
            sent_msg = send_draft(message.id, request.user, force=force)
            serializer = EmailMessageSerializer(sent_msg)
            return Response(serializer.data)
        except MailError as e:
            return Response({"detail": str(e), **e.extra}, status=e.status)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def send_now(self, request):
        """
        Create (or update) a draft and immediately dispatch it through Gmail in a single request.
        Ideal for the Contextual Mail Thread & Compose Drawer across Tasks, Penalties, Reports, and Staff Analysis.
        """
        draft_id = request.data.get('id') or request.data.get('draft_id')
        if draft_id:
            instance = EmailMessage.objects.filter(pk=draft_id, state=EmailMessage.STATE_DRAFT).first()
            if instance:
                serializer = EmailMessageCreateUpdateSerializer(instance, data=request.data, partial=True)
            else:
                serializer = EmailMessageCreateUpdateSerializer(data=request.data)
        else:
            serializer = EmailMessageCreateUpdateSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        account = serializer.validated_data.get('account')
        self._validate_account_access(account)

        context_module = (
            serializer.validated_data.get('context_module')
            or (account.module_scope if account else get_user_default_module_scope(request.user))
        )
        msg = serializer.save(
            created_by=request.user,
            context_module=context_module,
        )
        force = bool(request.data.get('force', True))
        try:
            sent_msg = send_draft(msg.id, request.user, force=force)
            return Response(EmailMessageSerializer(sent_msg).data, status=status.HTTP_200_OK)
        except MailError as e:
            return Response({"detail": str(e), "draft_id": msg.id, **e.extra}, status=e.status)
        except Exception as e:
            return Response({"detail": str(e), "draft_id": msg.id}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def sync_all(self, request):
        module_scope = (request.data.get('module_scope') or request.query_params.get('module_scope') or '').strip().upper()
        target_email = (request.data.get('target_email') or '').strip() or None

        if is_mail_admin(request.user):
            accounts = MailAccount.objects.filter(is_active=True, status=MailAccount.STATUS_CONNECTED)
            if module_scope and module_scope != 'ALL':
                accounts = accounts.filter(module_scope=module_scope)
        else:
            accounts = get_user_own_accounts_queryset(request.user).filter(
                is_active=True, status=MailAccount.STATUS_CONNECTED
            )

        total_imported = 0
        errors = []
        for acc in accounts:
            res = sync_account_threads(acc, target_email=target_email, max_results=25)
            total_imported += res.get('imported', 0)
            errors.extend(res.get('errors', []))

        # Also trigger background student sync if in PROCESSING scope
        if not module_scope or module_scope in ('PROCESSING', 'ALL'):
            try:
                from .tasks import sync_emails_for_all_students_task
                sync_emails_for_all_students_task.delay()
            except Exception:
                pass

        return Response({
            "detail": f"Synced {total_imported} messages across {accounts.count()} mailbox(es).",
            "imported": total_imported,
            "errors": errors,
        })

    @action(detail=False, methods=['post'])
    def sync(self, request):
        student_id = request.data.get('student_id')
        account_id = request.data.get('account_id')
        target_email = (request.data.get('target_email') or '').strip() or None

        if student_id:
            from trainers.models import ProcessingStudent
            try:
                student = ProcessingStudent.objects.get(id=student_id)
                sync_student(student)
                return Response({"detail": "Sync completed successfully."})
            except ProcessingStudent.DoesNotExist:
                return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if account_id:
            acc = MailAccount.objects.filter(pk=account_id, is_active=True).first()
            if not acc:
                return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
            self._validate_account_access(acc)
            res = sync_account_threads(acc, target_email=target_email, max_results=30)
            return Response({"detail": "Sync completed.", **res})

        if target_email:
            accounts = (
                MailAccount.objects.filter(is_active=True, status=MailAccount.STATUS_CONNECTED)
                if is_mail_admin(request.user)
                else get_user_own_accounts_queryset(request.user).filter(is_active=True, status=MailAccount.STATUS_CONNECTED)
            )
            imported = 0
            for acc in accounts:
                r = sync_account_threads(acc, target_email=target_email, max_results=20)
                imported += r.get('imported', 0)
            return Response({"detail": f"Synced {imported} messages.", "imported": imported})

        return Response({"detail": "Provide student_id, account_id, or target_email."}, status=status.HTTP_400_BAD_REQUEST)


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

    @action(detail=True, methods=['get'], permission_classes=[], authentication_classes=[])
    def download(self, request, pk=None):
        token = request.GET.get('token')
        if not token:
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            from django.http import HttpResponse
            return HttpResponse('Unauthorized', status=401)

        from rest_framework_simplejwt.tokens import AccessToken
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = User.objects.get(id=user_id)
        except Exception:
            from django.http import HttpResponse
            return HttpResponse('Unauthorized', status=401)

        if not has_mail_access(user):
            from django.http import HttpResponse
            return HttpResponse('Forbidden', status=403)

        attachment = self.get_object()

        from django.http import HttpResponse, HttpResponseRedirect
        if attachment.gmail_attachment_id and not attachment.file:
            from .gmail_client import GmailClient
            try:
                client = GmailClient(attachment.message.account)
                data = client.get_attachment(attachment.message.gmail_message_id, attachment.gmail_attachment_id)
                response = HttpResponse(data, content_type=attachment.content_type or 'application/octet-stream')
                response['Content-Disposition'] = f'inline; filename="{attachment.filename}"'
                return response
            except Exception as e:
                return HttpResponse(f"Failed to fetch attachment: {str(e)}", status=400)

        if attachment.file:
            return HttpResponseRedirect(attachment.file.url)
        elif attachment.student_document and attachment.student_document.document:
            return HttpResponseRedirect(attachment.student_document.document.url)

        return HttpResponse("Attachment file not found", status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_template_variables(request):
    from .variables import VARIABLES_WITH_GROUP
    vars_list = [
        {'id': v[0], 'label': v[1], 'example': v[2], 'group': v[3]}
        for v in VARIABLES_WITH_GROUP
    ]

    try:
        from trainers.models import ProcessingDynamicField
        for d in ProcessingDynamicField.objects.all():
            clean_k = re.sub(r'[^a-zA-Z0-9_]', '_', d.name.lower().strip())
            if clean_k not in [v['id'] for v in vars_list]:
                vars_list.append({
                    'id': clean_k,
                    'label': d.name,
                    'example': '',
                    'group': 'Student & Admissions',
                })
    except Exception:
        pass

    return Response(vars_list)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def gmail_authorize(request):
    if not (has_dynamic_permission(request.user, 'mail:manage') or has_dynamic_permission(request.user, 'fees:manage')):
        return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

    module_scope = (
        request.query_params.get('module_scope')
        or request.query_params.get('module')
        or get_user_default_module_scope(request.user)
    ).upper()
    company = (request.query_params.get('company') or 'FLAG').upper()
    role_ids = request.query_params.get('role_ids') or ''
    request.session['gmail_oauth_module_scope'] = module_scope
    request.session['gmail_oauth_company'] = company
    request.session['gmail_oauth_role_ids'] = role_ids

    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_SHEETS_CREDENTIALS_FILE,
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
    if not (has_dynamic_permission(request.user, 'mail:manage') or has_dynamic_permission(request.user, 'fees:manage')):
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

        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        email_address = profile.get('emailAddress')

        module_scope = request.data.get('module_scope') or request.session.get('gmail_oauth_module_scope')
        company = request.data.get('company') or request.session.get('gmail_oauth_company') or 'FLAG'
        role_ids_raw = request.data.get('role_ids') or request.session.get('gmail_oauth_role_ids') or ''
        allowed_pages = request.data.get('allowed_pages')

        if not module_scope:
            if 'account' in (email_address or '').lower() or 'jayesh' in (email_address or '').lower():
                module_scope = 'FEES'
            else:
                module_scope = get_user_default_module_scope(request.user)

        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }

        defaults = {
            'credentials': creds_data,
            'status': MailAccount.STATUS_CONNECTED,
            'connected_by': request.user,
            'module_scope': module_scope,
            'company': company,
        }
        if isinstance(allowed_pages, list):
            defaults['allowed_pages'] = allowed_pages

        account, created = MailAccount.objects.update_or_create(
            email=email_address,
            defaults=defaults,
        )

        # Assign roles if specified
        if role_ids_raw:
            if isinstance(role_ids_raw, str):
                r_ids = [int(x) for x in role_ids_raw.split(',') if x.strip().isdigit()]
            elif isinstance(role_ids_raw, list):
                r_ids = [int(x) for x in role_ids_raw if str(x).isdigit()]
            else:
                r_ids = []
            if r_ids:
                account.assigned_roles.set(Role.objects.filter(id__in=r_ids))

        # Auto-detect Send As aliases configured in Gmail
        detected_alias = None
        detected_custom_aliases = []
        try:
            from .gmail_client import GmailClient
            g_client = GmailClient(account)
            aliases = g_client.send_as_list()
            for a in aliases:
                a_email = (a.get('email') or '').strip().lower()
                if a_email and a_email != (email_address or '').lower():
                    detected_custom_aliases.append({
                        'email': a_email,
                        'display_name': a.get('display_name') or '',
                        'is_default': bool(a.get('is_default')),
                    })
                    if not detected_alias and not a_email.endswith('@gmail.com'):
                        account.send_as_email = a_email
                        detected_alias = a_email
                        if a.get('display_name'):
                            account.display_name = a['display_name']
            if detected_custom_aliases and not account.custom_aliases:
                account.custom_aliases = detected_custom_aliases
            account.save(update_fields=['send_as_email', 'display_name', 'custom_aliases'])
        except Exception as exc:
            logger.warning("Could not auto-detect sendAs aliases for %s: %s", email_address, exc)

        return Response({
            "detail": "Gmail connected successfully",
            "email": email_address,
            "send_as_email": detected_alias or account.send_as_email,
            "module_scope": account.module_scope,
            "company": account.company,
        })
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
