from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework.permissions import IsAuthenticated
from .models import DailyReport, DailyReportAttachment
from .serializers import DailyReportSerializer
from .permissions import REPORT_REVIEWERS, IsReportReviewer, IsReportOwner
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.db.models import Case, When, Value, IntegerField
import urllib.parse
import urllib.request


class DailyReportPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 50


class DailyReportCreateView(generics.CreateAPIView):
    serializer_class = DailyReportSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            status="pending",
            company=self.request.user.company,
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
        serializer.save()

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
                Q(heading__icontains=search) | 
                Q(report_text__icontains=search)
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
                Q(heading__icontains=search) | 
                Q(report_text__icontains=search)
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
            and request.user.role not in REPORT_REVIEWERS
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
            and request.user.role not in REPORT_REVIEWERS
        ):
            return Response({"error": "Permission denied"}, status=403)

        attachments = report.attachments.all()

        if not attachments.exists():
            return Response(
                {"error": "No file attached to this report"}, status=404
            )

        attachment_data = []
        for att in attachments:
            view_url = att.attached_file.url if att.attached_file else None
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
        is_reviewer = request.user.role in REPORT_REVIEWERS
        if not (is_owner or is_reviewer):
            return Response({"error": "Permission denied"}, status=403)

        if not attachment.attached_file:
            return Response({"error": "No file found"}, status=404)

        cloudinary_url = attachment.attached_file.url
        if cloudinary_url.startswith("http://"):
            cloudinary_url = cloudinary_url.replace("http://", "https://")

        original_filename = attachment.original_filename or "download"


        try:
            req = urllib.request.Request(
                cloudinary_url,
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
