from django.urls import path
from .views import (
    NotificationListView, 
    MarkNotificationsReadView, 
    ClearNotificationsView,
    RegisterDeviceTokenView
)

urlpatterns = [
    path('notifications/', NotificationListView.as_view()),
    path('notifications/mark-read/', MarkNotificationsReadView.as_view()),
    path('notifications/clear/', ClearNotificationsView.as_view()),
    path('notifications/devices/', RegisterDeviceTokenView.as_view()),
]