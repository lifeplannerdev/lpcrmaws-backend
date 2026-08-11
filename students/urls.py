from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AcademicGradeViewSet, AcademicPackageViewSet, AcademicBatchViewSet,
    StudentViewSet, ExamResultViewSet, BatchAttendanceViewSet, DailyRemarkViewSet
)

router = DefaultRouter()
router.register(r'grades', AcademicGradeViewSet)
router.register(r'packages', AcademicPackageViewSet)
router.register(r'batches', AcademicBatchViewSet)
router.register(r'students', StudentViewSet)
router.register(r'exam-results', ExamResultViewSet)
router.register(r'attendances', BatchAttendanceViewSet)
router.register(r'remarks', DailyRemarkViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
