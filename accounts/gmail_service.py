import google.oauth2.credentials
from googleapiclient.discovery import build
from email.message import EmailMessage
import base64

def get_gmail_service(user):
    creds_data = user.gmail_credentials
    if not creds_data or not creds_data.get('token'):
        return None
    
    credentials = google.oauth2.credentials.Credentials(
        token=creds_data['token'],
        refresh_token=creds_data['refresh_token'],
        token_uri=creds_data['token_uri'],
        client_id=creds_data['client_id'],
        client_secret=creds_data['client_secret'],
        scopes=creds_data['scopes']
    )
    
    service = build('gmail', 'v1', credentials=credentials)
    return service

def create_gmail_draft(user, to, subject, body, thread_id=None):
    service = get_gmail_service(user)
    if not service:
        return None

    message = EmailMessage()
    message.set_content(body)
    message['To'] = to
    message['Subject'] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    body_data = {
        'message': {
            'raw': raw_message,
        }
    }
    
    if thread_id:
        body_data['message']['threadId'] = thread_id

    draft = service.users().drafts().create(userId='me', body=body_data).execute()
    return draft.get('message', {}).get('threadId')
