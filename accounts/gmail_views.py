import os
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.urls import reverse
import google.oauth2.credentials
import google_auth_oauthlib.flow

# Path to the credentials file downloaded from Google Cloud
CREDENTIALS_PATH = os.path.join(settings.BASE_DIR, 'credentials', 'credentials.json')

class GmailAuthorizeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not os.path.exists(CREDENTIALS_PATH):
            return Response({"error": "Google API credentials.json not found in backend/credentials folder."}, status=500)
        
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=['https://www.googleapis.com/auth/gmail.compose']
        )
        
        # The redirect_uri must match exactly what is in Google Cloud Console
        # Let frontend pass the redirect_uri it wants to use (e.g. http://localhost:5173/gmail-callback)
        redirect_uri = request.query_params.get('redirect_uri', 'http://localhost:8000/api/accounts/gmail/oauth2callback/')
        
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        flow.redirect_uri = redirect_uri

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return Response({"authorization_url": authorization_url})


class GmailOAuth2CallbackAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get('code')
        redirect_uri = request.data.get('redirect_uri')
        
        if not code:
            return Response({"error": "Authorization code not provided."}, status=400)
            
        if not os.path.exists(CREDENTIALS_PATH):
            return Response({"error": "Google API credentials.json not found."}, status=500)
            
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

        try:
            flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/gmail.compose']
            )
            flow.redirect_uri = redirect_uri
            
            # Exchange authorization code for access token
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            creds_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            
            request.user.gmail_credentials = creds_data
            request.user.save()
            
            return Response({"message": "Gmail connected successfully!"})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

class GmailStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        has_creds = bool(request.user.gmail_credentials and request.user.gmail_credentials.get('token'))
        return Response({"connected": has_creds})
