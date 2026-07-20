from django.urls import path
from .views import (
    DailyReportCreateView,
    MyDailyReportsView,
    MyDailyReportUpdateView,
    AllDailyReportsView,
    ReviewDailyReportView,
    AdminReportStatsView,
    DailyReportDetailView,
    ViewReportFileView,
    DownloadAttachmentView,
    PreviousEveningAgendaView,
    AdminReportSettingsListView,
    AdminReportSettingsDetailView,
    MissingReportsView,
)

urlpatterns = [
    path("reports/next-day-agenda/", PreviousEveningAgendaView.as_view(), name="next-day-agenda"),
    path("reports/create/",DailyReportCreateView.as_view(),name="report-create"),
    path("reports/my/",MyDailyReportsView.as_view(),name="my-reports"),
    path("reports/<int:pk>/edit/",MyDailyReportUpdateView.as_view(),name="report-update"),
    path("reports/<int:pk>/",DailyReportDetailView.as_view(),name="report-detail"),
    path("reports/attachments/<int:pk>/download/",DownloadAttachmentView.as_view(), name="attachment-download"), 
    path("admin/reports/",AllDailyReportsView.as_view(),name="all-reports"),
    path("admin/reports/missing/",MissingReportsView.as_view(),name="missing-reports"),
    path("admin/reports/settings/", AdminReportSettingsListView.as_view(), name="report-settings-list"),
    path("admin/reports/settings/<int:pk>/", AdminReportSettingsDetailView.as_view(), name="report-settings-detail"),
    path("admin/reports/<int:pk>/review/", ReviewDailyReportView.as_view(),name="report-review"),
    path("admin/reports/stats/",AdminReportStatsView.as_view(),name="report-stats"),
    path("admin/reports/<int:pk>/view-file/",ViewReportFileView.as_view(),name="report-file"),
]
