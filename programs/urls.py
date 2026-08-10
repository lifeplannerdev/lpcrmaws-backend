from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProgramViewSet, ProgramCountryViewSet, ProgramUniversityViewSet, ProgramIntakeViewSet

router = DefaultRouter()
router.register(r'programs', ProgramViewSet, basename='program')
router.register(r'program-countries', ProgramCountryViewSet, basename='program-country')
router.register(r'program-universities', ProgramUniversityViewSet, basename='program-university')
router.register(r'program-intakes', ProgramIntakeViewSet, basename='program-intake')

urlpatterns = [
    path('', include(router.urls)),
]
