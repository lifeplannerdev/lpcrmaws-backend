from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CredentialViewSet, CredentialUpdateRequestViewSet

router = DefaultRouter()
router.register(r'credentials', CredentialViewSet, basename='credential')
router.register(r'credential-requests', CredentialUpdateRequestViewSet, basename='credential-request')

urlpatterns = [
    path('', include(router.urls)),
]
