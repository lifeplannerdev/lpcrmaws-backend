"""Business logic: drafting, sending (always an explicit action) and Gmail synchronisation."""
import logging
import mimetypes
import re
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, getaddresses, parseaddr

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
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
    qs = student.mail_messages.filter(state__in=[EmailMessage.STATE_SENT, EmailMessage.STATE_RECEIVED])
    if account is not None:
        qs = qs.filter(account=account)
    return qs.annotate(_t=_effective_time_ordering()).order_by('-_t', '-id').first()


def default_account():
    return (
        MailAccount.objects.filter(is_active=True, status=MailAccount.STATUS_CONNECTED, is_default=True).first()
        or MailAccount.objects.filter(is_active=True, status=MailAccount.STATUS_CONNECTED).first()
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
    message.body_text = html_to_text(message.body_html)
    message.snippet = make_snippet(message.body_html)
    return message


@transaction.atomic
def create_draft(student, user, data):
    message = EmailMessage(student=student, created_by=user, state=EmailMessage.STATE_DRAFT, direction=EmailMessage.DIRECTION_OUT)
    data = dict(data or {})
    if not data.get('to') and student.email:
        data['to'] = [student.email]
    if not data.get('account'):
        account = default_account()
        data['account'] = account.pk if account else None
    apply_draft_data(message, data, user)
    if not message.subject and not message.new_thread:
        last = last_thread_message(student)
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
        payloads.append((att.filename, att.content_type or mimetypes.guess_type(att.filename)[0] or 'application/octet-stream', data))
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
        msg.add_attachment(data, maintype=maintype or 'application', subtype=subtype or 'octet-stream', filename=filename)
    return msg.as_bytes()


def _threading_for(message):
    """Decide Gmail threadId + RFC headers for a draft about to be sent."""
    student = message.student
    if message.new_thread:
        return None, '', ''
    last_any = last_thread_message(student)
    if not last_any:
        return None, '', ''
    last_same_account = last_thread_message(student, message.account) if message.account_id else None
    in_reply_to = last_any.rfc_message_id or ''
    references = ' '.join(filter(None, [last_any.references, last_any.rfc_message_id]))
    references = ' '.join(references.split()[-10:])
    thread_id = None
    if last_same_account and last_same_account.gmail_thread_id:
        thread_id = last_same_account.gmail_thread_id
        if last_same_account.pk != last_any.pk:  # use headers from the same mailbox' thread
            in_reply_to = last_same_account.rfc_message_id or in_reply_to
            references = ' '.join(filter(None, [last_same_account.references, last_same_account.rfc_message_id]))
            references = ' '.join(references.split()[-10:])
    return thread_id, in_reply_to, references



def sync_draft_to_gmail(message):
    if message.state != EmailMessage.STATE_DRAFT or not message.account:
        return
    final_html = _compose_final_html(message)
    final_text = html_to_text(final_html)
    from email.utils import formataddr
    from_header = formataddr((message.account.display_name or '', message.account.email))
    thread_id, in_reply_to, references = _threading_for(message)
    raw = build_mime(
        from_header, message.to, message.cc, message.bcc, message.subject or '(no subject)',
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

def send_draft(message_id, user, force=False):
    """Send a draft through Gmail. Never called automatically - only from the explicit Send action."""
    claimed = EmailMessage.objects.filter(pk=message_id, state=EmailMessage.STATE_DRAFT).update(state=EmailMessage.STATE_SENDING)
    if not claimed:
        raise MailError('This message was already sent or is being sent.', status=409)
    message = EmailMessage.objects.select_related('student', 'account').get(pk=message_id)

    def _release(error):
        EmailMessage.objects.filter(pk=message_id).update(state=EmailMessage.STATE_DRAFT, error=str(error)[:490])

    try:
        account = message.account
        if not account or not account.is_active:
            raise MailError('Choose a sender account (From) before sending.')
        if account.status != MailAccount.STATUS_CONNECTED:
            raise MailError('This sender account needs to be reconnected in the Mail Center.', status=409)
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
        from_header = formataddr((account.display_name or '', account.email))
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
            raise MailError('This sender account needs to be reconnected in the Mail Center.', status=409)
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
        # A concurrent sync may already have imported this very message - keep one row only.
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
        if not message.student.gmail_thread_id and message.gmail_thread_id:
            ProcessingStudent.objects.filter(pk=message.student_id).update(gmail_thread_id=message.gmail_thread_id)

    log_activity(
        action='PROCESSING_STUDENT_UPDATED', entity_type='ProcessingStudent',
        entity_id=message.student_id, entity_name=message.student.name, user=user,
        description=f'Email sent to {", ".join(message.to)} from {account.email}: {message.subject}',
    )
    return message


# --------------------------------------------------------------------------- sync

def _html_from_parsed(parsed):
    if parsed['html']:
        return clean_html(parsed['html'])
    return f'<div style="white-space: pre-wrap;">{escape(parsed["text"])}</div>'


def _import_thread(student, account, thread):
    imported = 0
    for gmsg in thread.get('messages', []):
        parsed = gmail_client.parse_message(gmsg)
        labels = set(parsed['labels'])
        if not parsed['id'] or labels & {'DRAFT', 'TRASH', 'SPAM'}:
            continue
        if EmailMessage.objects.filter(gmail_message_id=parsed['id']).exists():
            continue
        headers = parsed['headers']
        outgoing = 'SENT' in labels
        html = _html_from_parsed(parsed)
        text = parsed['text'] or html_to_text(html)
        try:
            with transaction.atomic():
                message = EmailMessage.objects.create(
                    student=student, account=account,
                    direction=EmailMessage.DIRECTION_OUT if outgoing else EmailMessage.DIRECTION_IN,
                    state=EmailMessage.STATE_SENT if outgoing else EmailMessage.STATE_RECEIVED,
                    gmail_message_id=parsed['id'], gmail_thread_id=parsed['thread_id'],
                    rfc_message_id=headers.get('message-id', ''), references=headers.get('references', ''),
                    from_email=headers.get('from', '')[:300],
                    to=parse_header_addresses(headers.get('to')),
                    cc=parse_header_addresses(headers.get('cc')),
                    subject=(headers.get('subject') or '')[:500],
                    body_html=html, body_text=text, snippet=make_snippet(text),
                    sent_at=parsed['sent_at'],
                )
                for att in parsed['attachments']:
                    EmailAttachment.objects.create(
                        message=message, filename=att['filename'][:255], content_type=att['content_type'][:120],
                        size=att['size'] or 0, gmail_attachment_id=att['attachment_id'],
                    )
            imported += 1
        except Exception:  # unique constraint race with a concurrent sync
            logger.info('Skipped duplicate Gmail message %s', parsed['id'])
    return imported


def sync_student(student):
    """Pull replies / messages for one student from every connected mailbox."""
    result = {'imported': 0, 'accounts_checked': 0, 'errors': []}
    accounts = MailAccount.objects.filter(is_active=True, status=MailAccount.STATUS_CONNECTED)
    for account in accounts:
        client = GmailClient(account)
        thread_ids = set(
            student.mail_messages.filter(account=account).exclude(gmail_thread_id__isnull=True)
            .values_list('gmail_thread_id', flat=True)
        )
        try:
            if student.email:
                thread_ids.update(client.search_thread_ids(f'from:{student.email} OR to:{student.email}', max_results=25))
            for thread_id in thread_ids:
                try:
                    thread = client.get_thread(thread_id)
                except GmailAuthError:
                    raise
                except GmailError as exc:
                    result['errors'].append(f'{account.email}: {exc}')
                    continue
                result['imported'] += _import_thread(student, account, thread)
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


def get_gmail_attachment(attachment):
    import base64
    from django.core.files.base import ContentFile
    from .gmail_client import GmailClient
    
    client = GmailClient(attachment.message.account)
    res = client.get_attachment(attachment.message.gmail_message_id, attachment.gmail_attachment_id)
    data = base64.urlsafe_b64decode(res['data'])
    attachment.file.save(attachment.filename, ContentFile(data))
    attachment.save()
