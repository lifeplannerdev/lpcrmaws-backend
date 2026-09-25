from django.urls import path
from .views import (
    TaskStatsAPIView,
    EmployeeListAPIView,
    TaskListCreateAPIView,
    TaskDetailAPIView,
    TaskUpdateListCreateAPIView,
    TasksAssignedByMeAPIView,
    TaskStatusUpdateAPIView,
    TaskApproveAPIView,
    TaskRejectAPIView,
    UpcomingTasksAPIView,
    PendingTasksAPIView,
)

urlpatterns = [
    path('tasks/stats/',         TaskStatsAPIView.as_view(),       name='task-stats'),
    path('tasks/assigned-by-me/', TasksAssignedByMeAPIView.as_view(), name='tasks-assigned-by-me'),
    path('tasks/pending/',       PendingTasksAPIView.as_view(),    name='pending-tasks'),

    # ── Collection endpoints ─────────────────────────────────────────────────
    path('tasks/',               TaskListCreateAPIView.as_view(),  name='task-list-create'),
    path('employees/list/',      EmployeeListAPIView.as_view(),    name='employee-list'),
    path('upcoming/',            UpcomingTasksAPIView.as_view(),   name='upcoming-tasks'),

    # ── Parameterised endpoints ────────────────────
    path('tasks/<int:pk>/',              TaskDetailAPIView.as_view(),          name='task-detail'),
    path('tasks/<int:pk>/status/',       TaskStatusUpdateAPIView.as_view(),    name='task-status-update'),
    path('tasks/<int:pk>/approve/',      TaskApproveAPIView.as_view(),         name='task-approve'),
    path('tasks/<int:pk>/reject/',       TaskRejectAPIView.as_view(),          name='task-reject'),
    path('tasks/<int:task_id>/updates/', TaskUpdateListCreateAPIView.as_view(), name='task-updates'),
]