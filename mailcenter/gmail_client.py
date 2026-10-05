"""Thin wrapper around the Gmail API for one MailAccount."""
import base64
import logging
import os
from datetime import datetime, timezone as dt_timezone

from django.conf import settings

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_SECRETS_FILE = getattr(
    settings, 'GMAIL_CLIENT_SECRETS_FILE',
    os.path.join(settings.BASE_DIR, 'credentials', 'credentials.json'),
)


class GmailError(Exception):
    """Any Gmail failure that should be reported to the user."""


class GmailAuthError(GmailError):
    """The stored token is no longer valid - the mailbox must be reconnected."""


# ---------------------------------------------------------------- OAuth helpers

def build_flow(redirect_uri):
    # Scope may legitimately differ from a previous grant; don't blow up on that.
    os.environ.setdefault('OAUTHLIB_RELAX_TOKEN_SCOPE', '1')
    if redirect_uri.startswith('http://'):
        os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')  # localhost testing only

    import google_auth_oauthlib.flow as oauth_flow

    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise GmailError('Google credentials.json was not found on the server (credentials/credentials.json).')
    try:
        # Newer library versions add PKCE by default; the callback is a separate request, so turn it off.
        flow = oauth_flow.Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=SCOPES, autogenerate_code_verifier=False
        )
    except TypeError:
        flow = oauth_flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


def authorization_url(redirect_uri):
    flow = build_flow(redirect_uri)
    url, _state = flow.authorization_url(access_type='offline', prompt='consent')
    return url


def exchange_code(code, redirect_uri):
    """Exchange the OAuth code and return the credentials dict to store."""
    flow = build_flow(redirect_uri)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # oauthlib raises a variety of errors
        raise GmailError(f'Google rejected the authorization code: {exc}')
    creds = flow.credentials
    return _creds_to_dict(creds)


def _creds_to_dict(creds):
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes or SCOPES),
        'expiry': creds.expiry.replace(tzinfo=dt_timezone.utc).isoformat() if creds.expiry else None,
    }


# ------------------------------------------------------------------- Gmail client

class GmailClient:
    def __init__(self, account):
        self.account = account
        self._service = None

    # -- auth -------------------------------------------------------------
    def _credentials(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google.auth.exceptions import RefreshError

        data = self.account.credentials or {}
        if not data.get('refresh_token') and not data.get('token'):
            self._mark_reconnect('No stored Google token.')
            raise GmailAuthError('This mailbox is not connected. Reconnect it from the Mail Center.')

        expiry = None
        if data.get('expiry'):
            try:
                parsed = datetime.fromisoformat(data['expiry'])
                expiry = parsed.astimezone(dt_timezone.utc).replace(tzinfo=None)
            except ValueError:
                expiry = None

        creds = Credentials(
            token=data.get('token'),
            refresh_token=data.get('refresh_token'),
            token_uri=data.get('token_uri') or 'https://oauth2.googleapis.com/token',
            client_id=data.get('client_id'),
            client_secret=data.get('client_secret'),
            scopes=data.get('scopes') or SCOPES,
        )
        creds.expiry = expiry

        if not creds.token or creds.expired:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                self._mark_reconnect(str(exc)[:240])
                raise GmailAuthError('Google access for this mailbox expired or was revoked. Reconnect it from the Mail Center.')
            except Exception as exc:
                raise GmailError(f'Could not reach Google to refresh access: {exc}')
            merged = _creds_to_dict(creds)
            if not merged.get('refresh_token'):
                merged['refresh_token'] = data.get('refresh_token')
            self.account.credentials = merged
            self.account.save(update_fields=['credentials'])
        return creds

    def _mark_reconnect(self, message):
        self.account.status = 'needs_reconnect'
        self.account.status_message = message
        self.account.save(update_fields=['status', 'status_message'])

    @property
    def service(self):
        if self._service is None:
            from googleapiclient.discovery import build
            self._service = build('gmail', 'v1', credentials=self._credentials(), cache_discovery=False)
        return self._service

    def _execute(self, request):
        from googleapiclient.errors import HttpError
        try:
            return request.execute()
        except HttpError as exc:
            status = getattr(exc.resp, 'status', None)
            text = str(exc).lower()
            if status == 401:
                self._mark_reconnect('Gmail rejected access (401).')
                raise GmailAuthError('Gmail rejected access for this mailbox. Reconnect it from the Mail Center.')
            if status == 403 and ('insufficient' in text or 'scope' in text):
                self._mark_reconnect('Missing Gmail permissions - reconnect and accept all requested permissions.')
                raise GmailAuthError('This mailbox was connected with limited permissions. Reconnect it and accept all permissions.')
            logger.warning('Gmail API error: %s', exc)
            raise GmailError(f'Gmail error: {exc}')

    # -- API calls --------------------------------------------------------
    def profile_email(self):
        return self._execute(self.service.users().getProfile(userId='me')).get('emailAddress', '')

    def send_as_list(self):
        resp = self._execute(self.service.users().settings().sendAs().list(userId='me'))
        result = []
        for item in resp.get('sendAs', []):
            result.append({
                'email': item.get('sendAsEmail'),
                'display_name': item.get('displayName', ''),
                'signature': item.get('signature', ''),
                'is_primary': bool(item.get('isPrimary')),
                'is_default': bool(item.get('isDefault')),
            })
        return result


    def create_draft(self, raw_bytes, thread_id=None):
        message_body = {'raw': base64.urlsafe_b64encode(raw_bytes).decode('ascii')}
        if thread_id:
            message_body['threadId'] = thread_id
        body = {'message': message_body}
        return self._execute(self.service.users().drafts().create(userId='me', body=body))

    def update_draft(self, draft_id, raw_bytes, thread_id=None):
        message_body = {'raw': base64.urlsafe_b64encode(raw_bytes).decode('ascii')}
        if thread_id:
            message_body['threadId'] = thread_id
        body = {'message': message_body}
        return self._execute(self.service.users().drafts().update(userId='me', id=draft_id, body=body))
        
    def delete_draft(self, draft_id):
        return self._execute(self.service.users().drafts().delete(userId='me', id=draft_id))

    def send_raw(self, raw_bytes, thread_id=None):
        body = {'raw': base64.urlsafe_b64encode(raw_bytes).decode('ascii')}
        if thread_id:
            body['threadId'] = thread_id
        return self._execute(self.service.users().messages().send(userId='me', body=body))

    def get_message_headers(self, message_id, names=('Message-Id', 'References')):
        msg = self._execute(self.service.users().messages().get(
            userId='me', id=message_id, format='metadata', metadataHeaders=list(names)
        ))
        return {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}

    def get_thread(self, thread_id):
        return self._execute(self.service.users().threads().get(userId='me', id=thread_id, format='full'))

    def search_thread_ids(self, query, max_results=25):
        resp = self._execute(self.service.users().threads().list(userId='me', q=query, maxResults=max_results))
        return [t['id'] for t in resp.get('threads', [])]

    def get_attachment(self, message_id, attachment_id):
        resp = self._execute(self.service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=attachment_id
        ))
        return base64.urlsafe_b64decode(resp.get('data', '').encode('ascii'))


# --------------------------------------------------------------------- parsing

def _decode(data):
    if not data:
        return ''
    padded = data + '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8', errors='replace')


def parse_message(msg):
    """Flatten a Gmail 'full' message resource into the fields we store."""
    payload = msg.get('payload', {})
    headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
    html_parts, text_parts, attachments = [], [], []

    def walk(part):
        mime = part.get('mimeType', '')
        body = part.get('body', {}) or {}
        filename = part.get('filename') or ''
        if filename and body.get('attachmentId'):
            attachments.append({
                'filename': filename,
                'content_type': mime,
                'size': body.get('size', 0),
                'attachment_id': body['attachmentId'],
            })
        elif mime == 'text/html' and body.get('data'):
            html_parts.append(_decode(body['data']))
        elif mime == 'text/plain' and body.get('data'):
            text_parts.append(_decode(body['data']))
        for sub in part.get('parts', []) or []:
            walk(sub)

    walk(payload)
    internal_ms = int(msg.get('internalDate', 0) or 0)
    return {
        'id': msg.get('id'),
        'thread_id': msg.get('threadId'),
        'labels': msg.get('labelIds', []),
        'headers': headers,
        'html': '\n'.join(html_parts),
        'text': '\n'.join(text_parts),
        'attachments': attachments,
        'snippet': msg.get('snippet', ''),
        'sent_at': datetime.fromtimestamp(internal_ms / 1000, tz=dt_timezone.utc) if internal_ms else None,
    }
