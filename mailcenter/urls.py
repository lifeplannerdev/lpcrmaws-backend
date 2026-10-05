from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MailAccountViewSet, EmailSignatureViewSet, EmailTemplateViewSet, 
    EmailMessageViewSet, EmailAttachmentViewSet,
    gmail_authorize, gmail_callback
)

router = DefaultRouter()
router.register(r'accounts', MailAccountViewSet, basename='mail-account')
router.register(r'signatures', EmailSignatureViewSet, basename='mail-signature')
router.register(r'templates', EmailTemplateViewSet, basename='mail-template')
router.register(r'messages', EmailMessageViewSet, basename='mail-message')
router.register(r'attachments', EmailAttachmentViewSet, basename='mail-attachment')

urlpatterns = [
    path('authorize/', gmail_authorize, name='gmail-authorize'),
    path('callback/', gmail_callback, name='gmail-callback'),
    path('', include(router.urls)),
]
