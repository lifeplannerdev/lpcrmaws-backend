from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CredentialViewSet, CredentialUpdateRequestViewSet, CredentialCategoryViewSet

router = DefaultRouter()
router.register(r'credentials', CredentialViewSet, basename='credential')
router.register(r'credential-requests', CredentialUpdateRequestViewSet, basename='credential-request')
router.register(r'credential-categories', CredentialCategoryViewSet, basename='credential-category')

urlpatterns = [
    path('', include(router.urls)),
]
