
with open('mailcenter/gmail_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

methods = '''
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
'''

content = content.replace('    def send_raw', methods + '\n    def send_raw')

with open('mailcenter/gmail_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

