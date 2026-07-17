from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework.permissions import IsAuthenticated
from .models import DailyReport, DailyReportAttachment, ReportTimingSettings
from .serializers import DailyReportSerializer, ReportTimingSettingsSerializer
from .permissions import REPORT_REVIEWERS, IsReportReviewer, IsReportOwner
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from accounts.permissions import has_dynamic_permission
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.db.models import Case, When, Value, IntegerField
import urllib.parse
import urllib.request
from utils.pusher import save_notification, trigger_pusher
from accounts.models import User


class DailyReportPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 50


class DailyReportCreateView(generics.CreateAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        data = serializer.validated_data
        
        # Determine timestamps
        report_submitted_at = now() if data.get('report_text') else None
        agenda_submitted_at = now() if data.get('next_day_agenda') else None
        
        # Auto-carryover logic
        user = self.request.user
        report_date = data.get('report_date', now().date())
        
        # If no agenda provided in request, check yesterday's report
        agenda_heading = data.get('agenda_heading')
        next_day_agenda = data.get('next_day_agenda')
        
        if not next_day_agenda:
            from datetime import timedelta
            yesterday = report_date - timedelta(days=1)
            yesterday_report = DailyReport.objects.filter(user=user, report_date=yesterday).order_by('-created_at').first()
            if yesterday_report and yesterday_report.next_day_agenda:
                agenda_heading = yesterday_report.agenda_heading
                next_day_agenda = yesterday_report.next_day_agenda
                agenda_submitted_at = yesterday_report.agenda_submitted_at

        report = serializer.save(
            user=user,
            status="pending",
            company=user.company,
            report_submitted_at=report_submitted_at,
            agenda_submitted_at=agenda_submitted_at,
            agenda_heading=agenda_heading,
            next_day_agenda=next_day_agenda
        )

        # Notify reviewers
        reviewer_users = User.objects.filter(
            db_roles__name__in=REPORT_REVIEWERS,
            is_active=True
        ).distinct()

        for reviewer in reviewer_users:
            message = f"New report submitted by {user.get_full_name() or user.username}"
            save_notification.delay(
                user_id=reviewer.id,
                type='report',
                message=message,
                by=user.get_full_name() or user.username
            )
            trigger_pusher.delay(
                channel=f"private-user-{reviewer.id}",
                event="report.submitted",
                data={
                    "report_id": report.id,
                    "user_name": user.get_full_name() or user.username,
                    "message": message
                }
            )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class MyDailyReportsView(generics.ListAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DailyReportPagination

    def get_queryset(self):
        qs = DailyReport.objects.filter(user=self.request.user).select_related("user", "reviewed_by").prefetch_related("attachments")
        
        company = self.request.query_params.get("company")
        if company:
            qs = qs.filter(user__company=company)
            
        return qs.order_by("-report_date")

    def filter_lateness(self, queryset):
        lateness = self.request.query_params.get("lateness")
        if not lateness or lateness == 'all':
            return queryset
        
        results = []
        for r in queryset:
            if lateness == 'late_agenda' and r.is_agenda_late:
                results.append(r)
            elif lateness == 'late_report' and r.is_report_late:
                results.append(r)
            elif lateness == 'on_time' and not r.is_report_late and not r.is_agenda_late and r.completion_percentage == 100:
                results.append(r)
            elif lateness == 'incomplete' and r.completion_percentage < 100:
                results.append(r)
        return results

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        lateness = request.query_params.get("lateness")
        if lateness and lateness != 'all':
            queryset = self.filter_lateness(queryset)
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
            
        return super().list(request, *args, **kwargs)


class MyDailyReportUpdateView(generics.UpdateAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated, IsReportOwner]
    queryset = DailyReport.objects.all()

    def perform_update(self, serializer):
        report = self.get_object()
        if report.status != "pending":
            raise PermissionDenied(
                "Approved or rejected reports cannot be edited."
            )
        
        # Determine timestamps based on previous state
        data = serializer.validated_data
        
        report_submitted_at = report.report_submitted_at
        if data.get('report_text') and not report.report_submitted_at:
            report_submitted_at = now()
            
        agenda_submitted_at = report.agenda_submitted_at
        if data.get('next_day_agenda') and not report.agenda_submitted_at:
            agenda_submitted_at = now()

        serializer.save(
            report_submitted_at=report_submitted_at,
            agenda_submitted_at=agenda_submitted_at
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class AllDailyReportsView(generics.ListAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsReportReviewer]
    pagination_class = DailyReportPagination

    def get_queryset(self):
        qs = DailyReport.objects.select_related(
            "user", "reviewed_by"
        ).prefetch_related("attachments")

        status = self.request.query_params.get("status")
        user = self.request.query_params.get("user")
        date = self.request.query_params.get("date")
        company = self.request.query_params.get("company")
        search = self.request.query_params.get("search")

        if status and status != 'all':
            qs = qs.filter(status=status)
        if user and user != 'all':
            qs = qs.filter(user__id=user)
        if date and date != 'all':
            if date == 'today':
                qs = qs.filter(report_date=now().date())
            elif date == 'yesterday':
                qs = qs.filter(report_date=(now() - timezone.timedelta(days=1)).date())
            else:
                qs = qs.filter(report_date=date)
        if company and company != 'all':
            qs = qs.filter(user__company=company)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search) | 
                Q(report_heading__icontains=search) | 
                Q(agenda_heading__icontains=search) | 
                Q(report_text__icontains=search) |
                Q(next_day_agenda__icontains=search)
            )

        qs = qs.annotate(
            status_order=Case(
                When(status="pending", then=Value(0)),
                When(status="rejected", then=Value(1)),
                When(status="approved", then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by("status_order", "-report_date", "-created_at")

        return qs

    def filter_lateness(self, queryset):
        lateness = self.request.query_params.get("lateness")
        if not lateness or lateness == 'all':
            return queryset
        
        results = []
        for r in queryset:
            if lateness == 'late_agenda' and r.is_agenda_late:
                results.append(r)
            elif lateness == 'late_report' and r.is_report_late:
                results.append(r)
            elif lateness == 'on_time' and not r.is_report_late and not r.is_agenda_late and r.completion_percentage == 100:
                results.append(r)
            elif lateness == 'incomplete' and r.completion_percentage < 100:
                results.append(r)
        return results

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        lateness = request.query_params.get("lateness")
        if lateness and lateness != 'all':
            queryset = self.filter_lateness(queryset)
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
            
        return super().list(request, *args, **kwargs)


class ReviewDailyReportView(APIView):
    permission_classes = [IsReportReviewer]

    def patch(self, request, pk):
        report = get_object_or_404(DailyReport, pk=pk)

        status_value = request.data.get("status")
        comment = request.data.get("review_comment", "")

        if status_value not in ["approved", "rejected"]:
            return Response({"error": "Invalid status"}, status=400)

        report.status = status_value
        report.review_comment = comment
        report.reviewed_by = request.user
        report.save()

        # Notify report owner
        by_name = request.user.get_full_name() or request.user.username
        message = f"Your daily report was {status_value} by {by_name}"
        save_notification.delay(
            user_id=report.user.id,
            type='report',
            message=message,
            by=by_name
        )
        trigger_pusher.delay(
            channel=f"private-user-{report.user.id}",
            event="report.reviewed",
            data={
                "report_id": report.id,
                "status": status_value,
                "message": message
            }
        )

        serializer = DailyReportSerializer(
            report, context={"request": request}
        )
        return Response(serializer.data)


class AdminReportStatsView(APIView):
    permission_classes = [IsReportReviewer]

    def get(self, request):
        today = now()
        qs = DailyReport.objects.all()
        
        company = request.query_params.get("company")
        user = request.query_params.get("user")
        date = request.query_params.get("date")
        search = request.query_params.get("search")

        if company and company != 'all':
            qs = qs.filter(user__company=company)
        if user and user != 'all':
            qs = qs.filter(user__id=user)
        if date and date != 'all':
            if date == 'today':
                qs = qs.filter(report_date=now().date())
            elif date == 'yesterday':
                qs = qs.filter(report_date=(now() - timezone.timedelta(days=1)).date())
            else:
                qs = qs.filter(report_date=date)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search) | 
                Q(report_heading__icontains=search) | 
                Q(agenda_heading__icontains=search) | 
                Q(report_text__icontains=search) |
                Q(next_day_agenda__icontains=search)
            )

        return Response(
            {
                "total": qs.count(),
                "today": qs.filter(report_date=today.date()).count(),
                "this_month": qs.filter(
                    report_date__year=today.year,
                    report_date__month=today.month,
                ).count(),
                "approved": qs.filter(status="approved").count(),
                "pending": qs.filter(status="pending").count(),
                "rejected": qs.filter(status="rejected").count(),
            }
        )


class DailyReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(
            DailyReport.objects.select_related("user", "reviewed_by").prefetch_related("attachments"), pk=pk
        )

        if (
            report.user != request.user
            and not (has_dynamic_permission(request.user, 'reports:read_all') or request.user.db_roles.filter(name__in=REPORT_REVIEWERS).exists())
        ):
            return Response({"error": "Permission denied"}, status=403)

        serializer = DailyReportSerializer(
            report, context={"request": request}
        )
        return Response(serializer.data)


class ViewReportFileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(
            DailyReport.objects.prefetch_related("attachments"), pk=pk
        )

        if (
            report.user != request.user
            and not (has_dynamic_permission(request.user, 'reports:read_all') or request.user.db_roles.filter(name__in=REPORT_REVIEWERS).exists())
        ):
            return Response({"error": "Permission denied"}, status=403)

        attachments = report.attachments.all()

        if not attachments.exists():
            return Response(
                {"error": "No file attached to this report"}, status=404
            )

        attachment_data = []
        for att in attachments:
            view_url = att.get_download_url()
            if view_url and view_url.startswith("http://"):
                view_url = view_url.replace("http://", "https://")

            attachment_data.append(
                {
                    "id": att.id,
                    "file_name": att.original_filename,
                    "view_url": view_url,
                    "download_url": att.get_download_url(),
                }
            )

        first = attachment_data[0]

        return JsonResponse(
            {
                "file_name": first["file_name"],
                "view_url": first["view_url"],
                "attachments": attachment_data,
                "report_name": report.name,
            }
        )


class DownloadAttachmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        attachment = get_object_or_404(
            DailyReportAttachment.objects.select_related("report__user"),
            pk=pk,
        )

        is_owner    = attachment.report.user == request.user
        is_reviewer = has_dynamic_permission(request.user, 'reports:read_all') or request.user.db_roles.filter(name__in=REPORT_REVIEWERS).exists()
        if not (is_owner or is_reviewer):
            return Response({"error": "Permission denied"}, status=403)

        if not attachment.attached_file:
            return Response({"error": "No file found"}, status=404)

        file_url = attachment.get_download_url()
        if file_url and file_url.startswith('/'):
            file_url = request.build_absolute_uri(file_url)

        original_filename = attachment.original_filename or "download"

        try:
            req = urllib.request.Request(
                file_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            remote = urllib.request.urlopen(req, timeout=30)
            content_type = remote.headers.get(
                "Content-Type", "application/octet-stream"
            )
        except Exception as exc:
            return Response(
                {"error": f"Could not fetch file: {exc}"}, status=502
            )

        ascii_name   = original_filename.replace(" ", "_").encode(
            "ascii", errors="replace"
        ).decode("ascii")
        encoded_name = urllib.parse.quote(original_filename, safe="")

        content_disposition = (
            f"attachment; "
            f'filename="{ascii_name}"; '
            f"filename*=UTF-8''{encoded_name}"
        )

        response = StreamingHttpResponse(
            streaming_content=remote,
            content_type=content_type,
        )
        response["Content-Disposition"] = content_disposition
        response["Cache-Control"]        = "no-store"

        content_length = remote.headers.get("Content-Length")
        if content_length:
            response["Content-Length"] = content_length

        return response


class PreviousEveningAgendaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest_evening_report = DailyReport.objects.filter(
            user=request.user, 
            report_type='EVENING'
        ).order_by('-created_at').first()

        agenda = None
        if latest_evening_report and latest_evening_report.next_day_agenda:
            agenda = latest_evening_report.next_day_agenda
            
        return Response({'next_day_agenda': agenda})

class AdminReportSettingsListView(generics.ListCreateAPIView):
    serializer_class = ReportTimingSettingsSerializer
    permission_classes = [IsReportReviewer]
    
    def get_queryset(self):
        return ReportTimingSettings.objects.all().select_related('user')

class AdminReportSettingsDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReportTimingSettingsSerializer
    permission_classes = [IsReportReviewer]
    queryset = ReportTimingSettings.objects.all()
