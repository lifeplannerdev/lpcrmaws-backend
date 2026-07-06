from django.urls import path
from .views import (
    VoxbayWebhookView,
    CallLogListView,
    CallLogDetailView,
    CallStatsView,
    ClickToCallView,
    VoxbayAgentListView,
    VoxbayAgentDetailView,
    UnassignedMissedCallsView,
    AssignMissedCallView,
    CallAgentStatsView,
)

urlpatterns = [
    # Webhook
    path("voxbay/webhook/",                     VoxbayWebhookView.as_view()),
    path("voxbay/call-logs/",                   CallLogListView.as_view()),
    path("voxbay/call-logs/<int:pk>/",           CallLogDetailView.as_view()),
    path("voxbay/call-logs/uuid/<str:uuid>/",    CallLogDetailView.as_view()),
    path("voxbay/stats/",                        CallStatsView.as_view()),
    path("voxbay/click-to-call/",               ClickToCallView.as_view()),
    path("voxbay/agents/",                       VoxbayAgentListView.as_view()),
    path("voxbay/agents/<int:pk>/",              VoxbayAgentDetailView.as_view()),
    path("voxbay/agent-stats/",                  CallAgentStatsView.as_view()),
    path("voxbay/unassigned-missed/",            UnassignedMissedCallsView.as_view()),
    path("voxbay/unassigned-missed/<str:call_uuid>/assign/", AssignMissedCallView.as_view()),
]