"""Business logic: drafting, sending (always an explicit action) and Gmail synchronisation."""
import logging
import mimetypes
import re
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, getaddresses, parseaddr

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.html import escape

from accounts.utils import log_activity
from trainers.models import ProcessingStudent

from . import gmail_client
from .gmail_client import GmailAuthError, GmailClient, GmailError
from .models import EmailAttachment, EmailMessage, MailAccount
from .sanitizer import clean_html, html_to_text, make_snippet
from .variables import find_placeholders

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


class MailError(Exception):
    """User-facing problem; `status` maps to the HTTP status code."""

    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.status = status
        self.extra = extra or {}


# ---------------------------------------------------------------- address helpers

def normalize_addresses(values, field='recipient'):
    """Accept a list or a comma separated string, return a validated list of plain addresses."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    cleaned = []
    for _name, addr in getaddresses([v for v in values if v]):
        addr = (addr or '').strip()
        if not addr:
            continue
        try:
            validate_email(addr)
        except ValidationError:
            raise MailError(f'"{addr}" is not a valid email address ({field}).')
        if addr.lower() not in [c.lower() for c in cleaned]:
            cleaned.append(addr)
    return cleaned


def parse_header_addresses(value):
    return [addr for _n, addr in getaddresses([value or '']) if addr]


# ------------------------------------------------------------------------- drafts

def _base_subject(subject):
    return re.sub(r'^\s*((re|fwd?)\s*:\s*)+', '', subject or '', flags=re.IGNORECASE).strip()


def _effective_time_ordering():
    return Coalesce('sent_at', 'created_at')


def last_thread_message(student, account=None):
    if not student:
        return None
    qs = student.mail_messages.filter(state__in=[EmailMessage.STATE_SENT, EmailMessage.STATE_RECEIVED])
    if account is not None:
        qs = qs.filter(account=account)
    return qs.annotate(_t=_effective_time_ordering()).order_by('-_t', '-id').first()


def last_thread_message_for_context(message, same_account_only=False):
    """
    Find the previous sent/received message in the same conversation thread
    across student, explicit gmail_thread_id, context (task/penalty/report), lead, or staff member.
    """
    qs = EmailMessage.objects.filter(
        state__in=[EmailMessage.STATE_SENT, EmailMessage.STATE_RECEIVED]
    ).exclude(pk=message.pk)

    if same_account_only and message.account_id:
        qs = qs.filter(account_id=message.account_id)

    if message.gmail_thread_id:
        match = qs.filter(gmail_thread_id=message.gmail_thread_id).annotate(
            _t=_effective_time_ordering()
        ).order_by('-_t', '-id').first()
        if match:
            return match

    if message.student_id:
        return qs.filter(student_id=message.student_id).annotate(
            _t=_effective_time_ordering()
        ).order_by('-_t', '-id').first()

    if message.context_module and message.context_id:
        match = qs.filter(
            context_module=message.context_module,
            context_id=str(message.context_id),
        ).annotate(_t=_effective_time_ordering()).order_by('-_t', '-id').first()
        if match:
            return match

    if message.lead_id:
        match = qs.filter(lead_id=message.lead_id).annotate(
            _t=_effective_time_ordering()
        ).order_by('-_t', '-id').first()
        if match:
            return match

    if message.recipient_staff_id:
        match = qs.filter(recipient_staff_id=message.recipient_staff_id).annotate(
            _t=_effective_time_ordering()
        ).order_by('-_t', '-id').first()
        if match:
            return match

    return None


def default_account(scope=MailAccount.SCOPE_PROCESSING):
    return (
        MailAccount.objects.filter(
            is_active=True, status=MailAccount.STATUS_CONNECTED, module_scope=scope, is_default=True
        ).first()
        or MailAccount.objects.filter(
            is_active=True, status=MailAccount.STATUS_CONNECTED, module_scope=scope
        ).first()
        or MailAccount.objects.filter(
            is_active=True, status=MailAccount.STATUS_CONNECTED
        ).first()
    )


def apply_draft_data(message, data, user):
    """Copy editable fields from request data onto a draft (sanitising HTML)."""
    if 'account' in data:
        account_id = data.get('account')
        if account_id in (None, ''):
            message.account = None
        else:
            account = MailAccount.objects.filter(pk=account_id, is_active=True).first()
            if not account:
                raise MailError('The selected sender account does not exist or is disabled.')
            message.account = account
    for field in ('to', 'cc', 'bcc'):
        if field in data:
            setattr(message, field, normalize_addresses(data.get(field), field))
    if 'subject' in data:
        message.subject = re.sub(r'[\r\n]+', ' ', str(data.get('subject') or ''))[:500]
    if 'body_html' in data:
        message.body_html = clean_html(data.get('body_html') or '')
    if 'signature_html' in data:
        message.signature_html = clean_html(data.get('signature_html') or '')
    if 'new_thread' in data:
        message.new_thread = bool(data.get('new_thread'))
    if 'template' in data:
        message.template_id = data.get('template') or None
    if 'sender_alias_email' in data:
        message.sender_alias_email = (data.get('sender_alias_email') or '').strip().lower()
    if 'sender_display_name' in data:
        message.sender_display_name = (data.get('sender_display_name') or '').strip()
    if 'context_module' in data:
        message.context_module = (data.get('context_module') or '').strip().upper()
    if 'context_id' in data:
        message.context_id = str(data.get('context_id') or '').strip()
    if 'context_label' in data:
        message.context_label = str(data.get('context_label') or '').strip()[:255]
    if 'custom_variables' in data and isinstance(data.get('custom_variables'), dict):
        message.custom_variables = data.get('custom_variables')
    if 'gmail_thread_id' in data and data.get('gmail_thread_id'):
        message.gmail_thread_id = str(data.get('gmail_thread_id')).strip()
    message.body_text = html_to_text(message.body_html)
    message.snippet = make_snippet(message.body_html)
    return message


@transaction.atomic
def create_draft(student, user, data):
    message = EmailMessage(
        student=student, created_by=user, state=EmailMessage.STATE_DRAFT, direction=EmailMessage.DIRECTION_OUT
    )
    data = dict(data or {})
    if not data.get('to') and student and student.email:
        data['to'] = [student.email]
    if not data.get('account'):
        account = default_account()
        data['account'] = account.pk if account else None
    apply_draft_data(message, data, user)
    if not message.subject and not message.new_thread:
        last = last_thread_message_for_context(message)
        if last and last.subject:
            message.subject = f"Re: {_base_subject(last.subject)}"
    message.save()
    return message


def update_draft(message, user, data):
    if message.state != EmailMessage.STATE_DRAFT:
        raise MailError('Only drafts can be edited.', status=409)
    apply_draft_data(message, data, user)
    message.error = ''
    message.save()
    return message


# ------------------------------------------------------------------------ sending

def _compose_final_html(message):
    body = message.body_html or ''
    if message.signature_html:
        body = f'{body}<br>--<br><div class="lp-signature">{message.signature_html}</div>'
    return clean_html(body)


def _resolve_from_header(message, account):
    """
    Determine the From header using the message's chosen sender_alias_email,
    falling back to the account's primary send_as_email or primary email.
    """
    sender_email = (message.sender_alias_email or account.send_as_email or account.email or '').strip()
    sender_name = (message.sender_display_name or account.display_name or '').strip()

    # Check if sender_email matches one of account.custom_aliases with its own display_name
    if message.sender_alias_email and not message.sender_display_name and isinstance(account.custom_aliases, list):
        for alias_item in account.custom_aliases:
            if isinstance(alias_item, dict) and (alias_item.get('email') or '').lower() == sender_email.lower():
                if alias_item.get('display_name'):
                    sender_name = alias_item['display_name'].strip()
                break

    return formataddr((sender_name, sender_email))


def _attachment_payloads(message):
    payloads, total = [], 0
    for att in message.attachments.select_related('student_document'):
        try:
            if att.file:
                att.file.open('rb')
                data = att.file.read()
                att.file.close()
            elif att.student_document_id and att.student_document.file:
                f = att.student_document.file
                f.open('rb')
                data = f.read()
                f.close()
            else:
                continue
        except Exception as exc:
            raise MailError(f'Could not read attachment "{att.filename}": {exc}', status=502)
        total += len(data)
        if total > MAX_ATTACHMENT_BYTES:
            raise MailError('Attachments are larger than the 20 MB limit.')
        payloads.append((
            att.filename,
            att.content_type or mimetypes.guess_type(att.filename)[0] or 'application/octet-stream',
            data,
        ))
    return payloads


def build_mime(from_header, to, cc, bcc, subject, html, text, attachments, in_reply_to='', references=''):
    msg = MimeMessage()
    msg['From'] = from_header
    msg['To'] = ', '.join(to)
    if cc:
        msg['Cc'] = ', '.join(cc)
    if bcc:
        msg['Bcc'] = ', '.join(bcc)
    msg['Subject'] = re.sub(r'[\r\n]+', ' ', subject or '')
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = (references or in_reply_to).strip()
    msg.set_content(text or ' ')
    msg.add_alternative(html or '<div></div>', subtype='html')
    for filename, ctype, data in attachments:
        maintype, _, subtype = (ctype or 'application/octet-stream').partition('/')
        msg.add_attachment(
            data, maintype=maintype or 'application', subtype=subtype or 'octet-stream', filename=filename
        )
    return msg.as_bytes()


def _threading_for(message):
    """Decide Gmail threadId + RFC headers for a draft about to be sent."""
    if message.new_thread:
        return None, '', ''
    last_any = last_thread_message_for_context(message, same_account_only=False)
    if not last_any:
        return message.gmail_thread_id or None, '', ''
    last_same_account = (
        last_thread_message_for_context(message, same_account_only=True) if message.account_id else None
    )
    in_reply_to = last_any.rfc_message_id or ''
    references = ' '.join(filter(None, [last_any.references, last_any.rfc_message_id]))
    references = ' '.join(references.split()[-10:])
    thread_id = message.gmail_thread_id or None
    if last_same_account and last_same_account.gmail_thread_id:
        thread_id = last_same_account.gmail_thread_id
        if last_same_account.pk != last_any.pk:
            in_reply_to = last_same_account.rfc_message_id or in_reply_to
            references = ' '.join(filter(None, [last_same_account.references, last_same_account.rfc_message_id]))
            references = ' '.join(references.split()[-10:])
    return thread_id, in_reply_to, references


def apply_variables(message, user=None):
    from .variables import build_context, render_string
    ctx = build_context(
        student=message.student,
        user=user or message.created_by,
        recipient_staff=message.recipient_staff,
        lead=message.lead,
        custom_variables=message.custom_variables,
    )
    changed = False

    if message.subject:
        s, _, _ = render_string(message.subject, ctx, html=False)
        if s != message.subject:
            message.subject = s
            changed = True

    if message.body_html:
        b, _, _ = render_string(message.body_html, ctx, html=True)
        if b != message.body_html:
            message.body_html = b
            changed = True

    if message.signature_html:
        s, _, _ = render_string(message.signature_html, ctx, html=True)
        if s != message.signature_html:
            message.signature_html = s
            changed = True

    if changed:
        message.save(update_fields=['subject', 'body_html', 'signature_html'])


def sync_draft_to_gmail(message):
    if message.state != EmailMessage.STATE_DRAFT or not message.account:
        return
    apply_variables(message)
    final_html = _compose_final_html(message)
    final_text = html_to_text(final_html)
    from_header = _resolve_from_header(message, message.account)
    thread_id, in_reply_to, references = _threading_for(message)
    raw = build_mime(
        from_header, message.to or [], message.cc or [], message.bcc or [], message.subject or '(no subject)',
        final_html, final_text, _attachment_payloads(message), in_reply_to, references,
    )
    from .gmail_client import GmailClient
    client = GmailClient(message.account)
    if message.gmail_draft_id:
        try:
            res = client.update_draft(message.gmail_draft_id, raw, thread_id)
            message.gmail_message_id = res.get('message', {}).get('id')
            message.save(update_fields=['gmail_message_id'])
            return
        except Exception:
            pass
    res = client.create_draft(raw, thread_id)
    message.gmail_draft_id = res.get('id')
    message.gmail_message_id = res.get('message', {}).get('id')
    message.save(update_fields=['gmail_draft_id', 'gmail_message_id'])


def send_draft(message_or_id, user=None, force=False):
    """Send a draft through Gmail. Accepts either an EmailMessage instance or a message PK."""
    if isinstance(message_or_id, EmailMessage):
        message_id = message_or_id.pk
        if user is None:
            user = message_or_id.created_by
    else:
        message_id = message_or_id

    claimed = EmailMessage.objects.filter(pk=message_id, state=EmailMessage.STATE_DRAFT).update(
        state=EmailMessage.STATE_SENDING
    )
    if not claimed:
        raise MailError('This message was already sent or is being sent.', status=409)
    message = EmailMessage.objects.select_related('student', 'recipient_staff', 'lead', 'account').get(pk=message_id)

    def _release(error):
        EmailMessage.objects.filter(pk=message_id).update(state=EmailMessage.STATE_DRAFT, error=str(error)[:490])

    try:
        apply_variables(message, user)
        account = message.account
        if not account or not account.is_active:
            raise MailError('Choose a sender account (From) before sending.')
        if account.status != MailAccount.STATUS_CONNECTED:
            raise MailError('This sender account needs to be reconnected in the Mail Settings.', status=409)
        if not message.to:
            raise MailError('Add at least one recipient (To).')
        if not (message.subject or '').strip():
            raise MailError('Add a subject before sending.')
        if not html_to_text(message.body_html).strip() and not message.attachments.exists():
            raise MailError('The message is empty.')

        placeholders = find_placeholders(message.subject, message.body_html, message.signature_html)
        if placeholders and not force:
            raise MailError(
                'Some template variables were not filled in: ' + ', '.join('{{%s}}' % p for p in placeholders),
                status=422, extra={'placeholders': placeholders},
            )

        final_html = _compose_final_html(message)
        final_text = html_to_text(final_html)
        from_header = _resolve_from_header(message, account)
        thread_id, in_reply_to, references = _threading_for(message)
        raw = build_mime(
            from_header, message.to, message.cc, message.bcc, message.subject,
            final_html, final_text, _attachment_payloads(message), in_reply_to, references,
        )

        client = GmailClient(account)
        if message.gmail_draft_id:
            try:
                client.delete_draft(message.gmail_draft_id)
            except Exception:
                pass
        try:
            response = client.send_raw(raw, thread_id=thread_id)
        except GmailAuthError:
            raise MailError('This sender account needs to be reconnected in the Mail Settings.', status=409)
        except GmailError as exc:
            raise MailError(str(exc), status=502)

        rfc_id, refs = '', references
        try:
            headers = client.get_message_headers(response['id'])
            rfc_id = headers.get('message-id', '')
            refs = headers.get('references', references)
        except GmailError:
            logger.info('Could not fetch Message-ID for sent message %s', response.get('id'))
    except MailError as exc:
        _release(exc)
        raise
    except Exception as exc:  # unexpected - never leave a draft stuck in "sending"
        _release(exc)
        logger.exception('Unexpected error while sending draft %s', message_id)
        raise MailError(f'Unexpected error while sending: {exc}', status=500)

    with transaction.atomic():
        EmailMessage.objects.filter(gmail_message_id=response['id']).exclude(pk=message.pk).delete()
        message.state = EmailMessage.STATE_SENT
        message.direction = EmailMessage.DIRECTION_OUT
        message.gmail_message_id = response['id']
        message.gmail_thread_id = response.get('threadId')
        message.rfc_message_id = rfc_id
        message.references = refs
        message.from_email = from_header
        message.sent_by = user
        message.sent_at = timezone.now()
        message.body_html = final_html
        message.body_text = final_text
        message.snippet = make_snippet(final_html)
        message.signature_html = ''
        message.error = ''
        message.save()
        if message.student_id and message.student and not message.student.gmail_thread_id and message.gmail_thread_id:
            ProcessingStudent.objects.filter(pk=message.student_id).update(gmail_thread_id=message.gmail_thread_id)

    if message.student_id and message.student:
        log_activity(
            action='PROCESSING_STUDENT_UPDATED', entity_type='ProcessingStudent',
            entity_id=message.student_id, entity_name=message.student.name, user=user,
            description=f'Email sent to {", ".join(message.to)} from {from_header}: {message.subject}',
        )
    return message


# --------------------------------------------------------------------------- sync

def _html_from_parsed(parsed):
    if parsed['html']:
        return clean_html(parsed['html'])
    return f'<div style="white-space: pre-wrap;">{escape(parsed["text"])}</div>'


def _match_context_entities(addresses):
    """Given a list of email addresses, attempt to match a ProcessingStudent, Staff User, or Lead."""
    clean_addrs = [a.strip().lower() for a in addresses if a and '@' in a]
    if not clean_addrs:
        return None, None, None

    student = ProcessingStudent.objects.filter(email__in=clean_addrs).first()
    User = get_user_model()
    staff = User.objects.filter(email__in=clean_addrs, is_active=True).first()
    lead = None
    try:
        from leads.models import Lead
        lead = Lead.objects.filter(email__in=clean_addrs).first()
    except Exception:
        pass
    return student, staff, lead


def _import_thread(student, account, thread, default_module=''):
    imported = 0
    account_emails = {
        (account.email or '').lower(),
        (account.send_as_email or '').lower(),
    }
    if isinstance(account.custom_aliases, list):
        for al in account.custom_aliases:
            if isinstance(al, dict) and al.get('email'):
                account_emails.add(al['email'].lower())
    account_emails.discard('')

    for gmsg in thread.get('messages', []):
        parsed = gmail_client.parse_message(gmsg)
        labels = set(parsed['labels'])
        if not parsed['id'] or labels & {'DRAFT', 'TRASH', 'SPAM'}:
            continue
        if EmailMessage.objects.filter(gmail_message_id=parsed['id']).exists():
            continue
        headers = parsed['headers']
        from_addrs = [a.lower() for a in parse_header_addresses(headers.get('from'))]
        outgoing = ('SENT' in labels) or any(a in account_emails for a in from_addrs)
        to_addrs = parse_header_addresses(headers.get('to'))
        cc_addrs = parse_header_addresses(headers.get('cc'))
        html = _html_from_parsed(parsed)
        text = parsed['text'] or html_to_text(html)

        # Resolve linked entities if not explicitly passed
        matched_student = student
        matched_staff = None
        matched_lead = None
        other_addrs = to_addrs + cc_addrs if outgoing else from_addrs
        if not matched_student:
            matched_student, matched_staff, matched_lead = _match_context_entities(other_addrs)

        # Also inherit context from an earlier message in the same gmail_thread_id if present
        existing_in_thread = None
        if parsed.get('thread_id'):
            existing_in_thread = EmailMessage.objects.filter(
                gmail_thread_id=parsed['thread_id']
            ).order_by('id').first()

        context_module = default_module or account.module_scope or 'GENERAL'
        context_id = ''
        context_label = ''
        if existing_in_thread:
            matched_student = matched_student or existing_in_thread.student
            matched_staff = matched_staff or existing_in_thread.recipient_staff
            matched_lead = matched_lead or existing_in_thread.lead
            context_module = existing_in_thread.context_module or context_module
            context_id = existing_in_thread.context_id or ''
            context_label = existing_in_thread.context_label or ''

        try:
            with transaction.atomic():
                message = EmailMessage.objects.create(
                    student=matched_student,
                    recipient_staff=matched_staff,
                    lead=matched_lead,
                    context_module=context_module,
                    context_id=context_id,
                    context_label=context_label,
                    account=account,
                    direction=EmailMessage.DIRECTION_OUT if outgoing else EmailMessage.DIRECTION_IN,
                    state=EmailMessage.STATE_SENT if outgoing else EmailMessage.STATE_RECEIVED,
                    gmail_message_id=parsed['id'],
                    gmail_thread_id=parsed['thread_id'],
                    rfc_message_id=headers.get('message-id', ''),
                    references=headers.get('references', ''),
                    from_email=headers.get('from', '')[:300],
                    to=to_addrs,
                    cc=cc_addrs,
                    subject=(headers.get('subject') or '')[:500],
                    body_html=html,
                    body_text=text,
                    snippet=make_snippet(text),
                    sent_at=parsed['sent_at'],
                )
                for att in parsed['attachments']:
                    EmailAttachment.objects.create(
                        message=message,
                        filename=att['filename'][:255],
                        content_type=att['content_type'][:120],
                        size=att['size'] or 0,
                        gmail_attachment_id=att['attachment_id'],
                    )
            imported += 1
        except Exception:  # unique constraint race with a concurrent sync
            logger.info('Skipped duplicate Gmail message %s', parsed['id'])
    return imported


def sync_student(student):
    """Pull replies / messages for one student from processing-scoped connected mailboxes."""
    result = {'imported': 0, 'accounts_checked': 0, 'errors': []}
    accounts = MailAccount.objects.filter(
        is_active=True,
        status=MailAccount.STATUS_CONNECTED,
        module_scope__in=[MailAccount.SCOPE_PROCESSING, MailAccount.SCOPE_GLOBAL],
    )
    for account in accounts:
        client = GmailClient(account)
        thread_ids = set(
            student.mail_messages.filter(account=account).exclude(gmail_thread_id__isnull=True)
            .values_list('gmail_thread_id', flat=True)
        )
        try:
            if student.email:
                thread_ids.update(
                    client.search_thread_ids(f'from:{student.email} OR to:{student.email}', max_results=100)
                )
            for thread_id in thread_ids:
                try:
                    thread = client.get_thread(thread_id)
                except GmailAuthError:
                    raise
                except GmailError as exc:
                    result['errors'].append(f'{account.email}: {exc}')
                    continue
                result['imported'] += _import_thread(student, account, thread, default_module='PROCESSING')
            result['accounts_checked'] += 1
            MailAccount.objects.filter(pk=account.pk).update(last_sync_at=timezone.now())
        except GmailAuthError as exc:
            result['errors'].append(f'{account.email}: {exc}')
        except GmailError as exc:
            result['errors'].append(f'{account.email}: {exc}')

    if not student.gmail_thread_id:
        first = student.mail_messages.exclude(gmail_thread_id__isnull=True).order_by('id').first()
        if first:
            ProcessingStudent.objects.filter(pk=student.pk).update(gmail_thread_id=first.gmail_thread_id)
    return result


def sync_account_threads(account, target_email=None, max_results=35):
    """
    Sync recent threads for a connected MailAccount (e.g. Managing Director's mailbox,
    HR mailbox, or a specific target_email conversation).
    """
    result = {'imported': 0, 'errors': []}
    if not account or not account.is_active or account.status != MailAccount.STATUS_CONNECTED:
        return result

    client = GmailClient(account)
    try:
        if target_email:
            query = f'from:{target_email} OR to:{target_email}'
        else:
            query = 'in:inbox OR in:sent'
        thread_ids = set(client.search_thread_ids(query, max_results=max_results))
        # Also include existing known threads for this account
        existing_threads = EmailMessage.objects.filter(
            account=account
        ).exclude(gmail_thread_id__isnull=True).exclude(gmail_thread_id='').order_by('-created_at')[:30]
        for em in existing_threads:
            thread_ids.add(em.gmail_thread_id)

        for tid in thread_ids:
            try:
                thread = client.get_thread(tid)
                result['imported'] += _import_thread(None, account, thread, default_module=account.module_scope)
            except GmailError as exc:
                result['errors'].append(str(exc))
        MailAccount.objects.filter(pk=account.pk).update(last_sync_at=timezone.now())
    except Exception as exc:
        result['errors'].append(str(exc))
    return result


def get_gmail_attachment(attachment):
    import base64
    from django.core.files.base import ContentFile
    from .gmail_client import GmailClient

    client = GmailClient(attachment.message.account)
    res = client.get_attachment(attachment.message.gmail_message_id, attachment.gmail_attachment_id)
    data = base64.urlsafe_b64decode(res['data'])
    attachment.file.save(attachment.filename, ContentFile(data))
    attachment.save()
