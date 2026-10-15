from django.urls import path
from .views import (
    ReminderListCreateAPIView,
    ReminderDetailAPIView,
    ReminderSubmitCompletionAPIView,
    ReminderApproveAPIView,
    ReminderRejectAPIView,
    ReminderUpdateListCreateAPIView,
    ReminderChecklistToggleAPIView,
    ReminderBriefingToggleAPIView,
    ReminderStatsAPIView,
    ReminderAlertsAPIView,
    ReminderStaffListAPIView,
    ReminderStudentsListAPIView,
    ReminderNotificationSettingAPIView,
    ReminderNotificationTestAPIView,
)

urlpatterns = [
    path('', ReminderListCreateAPIView.as_view(), name='reminder_list_create'),
    path('stats/', ReminderStatsAPIView.as_view(), name='reminder_stats'),
    path('alerts/', ReminderAlertsAPIView.as_view(), name='reminder_alerts'),
    path('staff/', ReminderStaffListAPIView.as_view(), name='reminder_staff_list'),
    path('students/', ReminderStudentsListAPIView.as_view(), name='reminder_students_list'),
    path('<int:pk>/', ReminderDetailAPIView.as_view(), name='reminder_detail'),
    path('<int:pk>/notification-settings/', ReminderNotificationSettingAPIView.as_view(), name='reminder_notification_settings'),
    path('<int:pk>/notification-settings/test/', ReminderNotificationTestAPIView.as_view(), name='reminder_notification_test'),
    path('<int:pk>/submit-completion/', ReminderSubmitCompletionAPIView.as_view(), name='reminder_submit_completion'),
    path('<int:pk>/approve/', ReminderApproveAPIView.as_view(), name='reminder_approve'),
    path('<int:pk>/reject/', ReminderRejectAPIView.as_view(), name='reminder_reject'),
    path('<int:pk>/updates/', ReminderUpdateListCreateAPIView.as_view(), name='reminder_updates'),
    path('<int:pk>/checklist/toggle/', ReminderChecklistToggleAPIView.as_view(), name='reminder_checklist_toggle'),
    path('<int:pk>/briefing/toggle/', ReminderBriefingToggleAPIView.as_view(), name='reminder_briefing_toggle'),
]
