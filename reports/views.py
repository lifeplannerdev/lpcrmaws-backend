from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework.permissions import IsAuthenticated
from .models import DailyReport, DailyReportAttachment, ReportTimingSettings
from .serializers import DailyReportSerializer, ReportTimingSettingsSerializer
from .permissions import REPORT_REVIEWERS, IsReportReviewer, IsReportOwner, IsReportSettingsManager
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from accounts.permissions import has_dynamic_permission
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.db.models import Case, When, Value, IntegerField, Q
import urllib.parse
import urllib.request
from utils.pusher import save_notification, trigger_pusher
from accounts.models import User

SALES_REPORT_ROLES = ['ADM_COUNSELLOR', 'ADM_MANAGER', 'BMCO', 'FLAG COORDINATOR', 'FLAG_COORDINATOR']


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
        
        # If no agenda provided in request, check previous working day's report
        agenda_heading = data.get('agenda_heading')
        next_day_agenda = data.get('next_day_agenda')
        
        if not next_day_agenda:
            prev_report = DailyReport.objects.filter(
                user=user, 
                report_date__lt=report_date
            ).order_by('-report_date', '-created_at').first()
            if prev_report and prev_report.next_day_agenda:
                agenda_heading = prev_report.agenda_heading
                next_day_agenda = prev_report.next_day_agenda
                agenda_submitted_at = prev_report.agenda_submitted_at

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
                by=user.get_full_name() or user.username,
                related_id=report.id
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
            
        status = self.request.query_params.get("status")
        if status and status != 'all':
            qs = qs.filter(status=status)
            
        return qs.order_by("-report_date", "-created_at")

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
            elif lateness == 'late' and (r.is_report_late or r.is_agenda_late):
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
        
        if report.status == "approved" or (report.status != "pending" and report.agenda_status != "rejected" and report.report_status != "rejected"):
            raise PermissionDenied(
                "Approved reports cannot be edited."
            )
        
        # Determine timestamps based on previous state
        data = serializer.validated_data
        
        report_submitted_at = report.report_submitted_at
        if data.get('report_text') and not report.report_submitted_at:
            report_submitted_at = now()
            
        agenda_submitted_at = report.agenda_submitted_at
        if data.get('next_day_agenda') and not report.agenda_submitted_at:
            agenda_submitted_at = now()

        agenda_status = report.agenda_status
        report_status = report.report_status
        
        if report.agenda_status == 'rejected' and 'next_day_agenda' in data:
            agenda_status = 'pending'
        if report.report_status == 'rejected' and 'report_text' in data:
            report_status = 'pending'

        serializer.save(
            report_submitted_at=report_submitted_at,
            agenda_submitted_at=agenda_submitted_at,
            agenda_status=agenda_status,
            report_status=report_status
        )

        # Notify reviewers on report update
        try:
            user = self.request.user
            reviewer_users = User.objects.filter(
                db_roles__name__in=REPORT_REVIEWERS,
                is_active=True
            ).distinct()

            for reviewer in reviewer_users:
                message = f"Report updated by {user.get_full_name() or user.username}"
                save_notification.delay(
                    user_id=reviewer.id,
                    type='report',
                    message=message,
                    by=user.get_full_name() or user.username,
                    related_id=report.id
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
        except Exception:
            pass

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

        req_user = self.request.user
        if not has_dynamic_permission(req_user, 'reports:read_all') and not req_user.db_roles.filter(name__in=REPORT_REVIEWERS).exists():
            scoped_filters = Q()
            if has_dynamic_permission(req_user, 'reports:sales_all'):
                scoped_filters |= Q(user__db_roles__name__in=SALES_REPORT_ROLES)
            if has_dynamic_permission(req_user, 'reports:kochi'):
                scoped_filters |= Q(user__location__iexact="KOCHI")
            if has_dynamic_permission(req_user, 'reports:documentation'):
                scoped_filters |= Q(user__db_roles__name="DOCUMENTATION")
            
            if scoped_filters:
                qs = qs.filter(scoped_filters).distinct()
            else:
                qs = qs.none()

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
            qs = qs.filter(Q(company=company) | Q(user__company=company))
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | 
                Q(report_heading__icontains=search) | 
                Q(agenda_heading__icontains=search) | 
                Q(report_text__icontains=search) |
                Q(next_day_agenda__icontains=search)
            )

        qs = qs.order_by('-report_date', '-created_at')

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
            elif lateness == 'late' and (r.is_report_late or r.is_agenda_late):
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


from hr.models import Penalty, PenaltyType
from django.utils import timezone

class ReviewDailyReportView(APIView):
    permission_classes = [IsReportReviewer]

    def patch(self, request, pk):
        report = get_object_or_404(DailyReport, pk=pk)

        req_user = request.user
        if not has_dynamic_permission(req_user, 'reports:approval'):
            return Response({"error": "Permission denied. Missing reports:approval permission."}, status=403)

        agenda_status = request.data.get("agenda_status")
        report_status = request.data.get("report_status")
        agenda_comment = request.data.get("agenda_review_comment", "")
        report_comment = request.data.get("report_review_comment", "")
        penalty_type_ids = request.data.get("penalty_type_ids", [])

        if agenda_status:
            if agenda_status not in ["pending", "approved", "rejected"]:
                return Response({"error": "Invalid agenda_status"}, status=400)
            report.agenda_status = agenda_status
            report.agenda_review_comment = agenda_comment

        if report_status:
            if report_status not in ["pending", "approved", "rejected"]:
                return Response({"error": "Invalid report_status"}, status=400)
            report.report_status = report_status
            report.report_review_comment = report_comment

        report.reviewed_by = request.user
        report.save()

        # Handle Penalties
        if penalty_type_ids:
            for p_id in penalty_type_ids:
                try:
                    ptype = PenaltyType.objects.get(id=p_id)
                    penalty = Penalty.objects.create(
                        user=report.user,
                        company=report.company,
                        act=ptype.name,
                        amount=ptype.default_amount,
                        month=timezone.now().strftime("%B %Y"),
                        date=timezone.now().date(),
                        source_report_id=report.id
                    )
                    report.applied_penalties.add(penalty)
                except PenaltyType.DoesNotExist:
                    pass

        # Notify report owner
        by_name = request.user.get_full_name() or request.user.username
        message = f"Your daily report was reviewed by {by_name}"
        save_notification.delay(
            user_id=report.user.id,
            type='report',
            message=message,
            by=by_name,
            related_id=report.id
        )
        trigger_pusher.delay(
            channel=f"private-user-{report.user.id}",
            event="report.reviewed",
            data={
                "report_id": report.id,
                "status": report.status,
                "message": message
            }
        )

        serializer = DailyReportSerializer(
            report, context={"request": request}
        )
        return Response(serializer.data)


class MissingReportsView(APIView):
    permission_classes = [IsReportReviewer]

    def get(self, request):
        date_param = request.query_params.get("date")
        if not date_param or date_param == 'today':
            date = now().date()
        elif date_param == 'yesterday':
            date = (now() - timezone.timedelta(days=1)).date()
        else:
            from django.utils.dateparse import parse_date
            date = parse_date(date_param)
            if not date:
                date = now().date()

        users = User.objects.filter(is_active=True)
        company = request.query_params.get("company")
        if company and company != 'all':
            users = users.filter(company=company)

        req_user = request.user
        if not has_dynamic_permission(req_user, 'reports:read_all') and not req_user.db_roles.filter(name__in=REPORT_REVIEWERS).exists():
            scoped_filters = Q()
            if has_dynamic_permission(req_user, 'reports:sales_all'):
                scoped_filters |= Q(db_roles__name__in=SALES_REPORT_ROLES)
            if has_dynamic_permission(req_user, 'reports:kochi'):
                scoped_filters |= Q(location__iexact="KOCHI")
            if has_dynamic_permission(req_user, 'reports:documentation'):
                scoped_filters |= Q(db_roles__name="DOCUMENTATION")
            if scoped_filters:
                users = users.filter(scoped_filters).distinct()
            else:
                users = users.none()
            
        submitted_user_ids = DailyReport.objects.filter(report_date=date).values_list('user_id', flat=True)
        missing_users = users.exclude(id__in=submitted_user_ids)
        
        data = [
            {
                "id": u.id,
                "name": u.get_full_name() or u.username,
                "role": ", ".join([r.name for r in u.db_roles.all()]) if hasattr(u, 'db_roles') else ""
            }
            for u in missing_users
        ]
        return Response(data)


class AdminReportStatsView(APIView):
    permission_classes = [IsReportReviewer]

    def get(self, request):
        today = now()
        qs = DailyReport.objects.all()
        
        req_user = request.user
        if not has_dynamic_permission(req_user, 'reports:read_all') and not req_user.db_roles.filter(name__in=REPORT_REVIEWERS).exists():
            scoped_filters = Q()
            if has_dynamic_permission(req_user, 'reports:sales_all'):
                scoped_filters |= Q(user__db_roles__name__in=SALES_REPORT_ROLES)
            if has_dynamic_permission(req_user, 'reports:kochi'):
                scoped_filters |= Q(user__location__iexact="KOCHI")
            if has_dynamic_permission(req_user, 'reports:documentation'):
                scoped_filters |= Q(user__db_roles__name="DOCUMENTATION")
            if scoped_filters:
                qs = qs.filter(scoped_filters).distinct()
            else:
                qs = qs.none()
        
        company = request.query_params.get("company")
        user = request.query_params.get("user")
        date = request.query_params.get("date")
        search = request.query_params.get("search")

        if company and company != 'all':
            qs = qs.filter(Q(company=company) | Q(user__company=company))
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

        is_reviewer = has_dynamic_permission(request.user, 'reports:read_all') or request.user.db_roles.filter(name__in=REPORT_REVIEWERS).exists()
        is_sales_reviewer = has_dynamic_permission(request.user, 'reports:sales_all') and report.user.db_roles.filter(name__in=SALES_REPORT_ROLES).exists()
        is_kochi_reviewer = has_dynamic_permission(request.user, 'reports:kochi') and (report.user.location or "").upper() == "KOCHI"
        is_doc_reviewer = has_dynamic_permission(request.user, 'reports:documentation') and report.user.db_roles.filter(name="DOCUMENTATION").exists()

        if report.user != request.user and not (is_reviewer or is_sales_reviewer or is_kochi_reviewer or is_doc_reviewer):
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

        is_reviewer = has_dynamic_permission(request.user, 'reports:read_all') or request.user.db_roles.filter(name__in=REPORT_REVIEWERS).exists()
        is_sales_reviewer = has_dynamic_permission(request.user, 'reports:sales_all') and report.user.db_roles.filter(name__in=SALES_REPORT_ROLES).exists()
        is_kochi_reviewer = has_dynamic_permission(request.user, 'reports:kochi') and (report.user.location or "").upper() == "KOCHI"
        is_doc_reviewer = has_dynamic_permission(request.user, 'reports:documentation') and report.user.db_roles.filter(name="DOCUMENTATION").exists()

        if report.user != request.user and not (is_reviewer or is_sales_reviewer or is_kochi_reviewer or is_doc_reviewer):
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
        is_sales_reviewer = has_dynamic_permission(request.user, 'reports:sales_all') and attachment.report.user.db_roles.filter(name__in=SALES_REPORT_ROLES).exists()
        is_kochi_reviewer = has_dynamic_permission(request.user, 'reports:kochi') and (attachment.report.user.location or "").upper() == "KOCHI"
        is_doc_reviewer = has_dynamic_permission(request.user, 'reports:documentation') and attachment.report.user.db_roles.filter(name="DOCUMENTATION").exists()
        
        if not (is_owner or is_reviewer or is_sales_reviewer or is_kochi_reviewer or is_doc_reviewer):
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
        qs = DailyReport.objects.filter(user=request.user)
        
        before_date = request.query_params.get("before_date") or request.query_params.get("date")
        if before_date:
            from django.utils.dateparse import parse_date
            parsed = parse_date(before_date)
            if parsed:
                qs = qs.filter(report_date__lt=parsed)
                
        exclude_id = request.query_params.get("exclude_id")
        if exclude_id:
            try:
                qs = qs.exclude(id=int(exclude_id))
            except (ValueError, TypeError):
                pass

        latest_evening_report = qs.order_by('-report_date', '-created_at').first()

        agenda = None
        heading = None
        report_date = None
        if latest_evening_report and latest_evening_report.next_day_agenda:
            agenda = latest_evening_report.next_day_agenda
            heading = latest_evening_report.agenda_heading
            report_date = str(latest_evening_report.report_date)
            
        return Response({
            'next_day_agenda': agenda,
            'agenda_heading': heading,
            'report_date': report_date,
        })

class AdminReportSettingsListView(generics.ListCreateAPIView):
    serializer_class = ReportTimingSettingsSerializer
    permission_classes = [IsReportSettingsManager]
    
    def get_queryset(self):
        return ReportTimingSettings.objects.all().select_related('user')

class AdminReportSettingsDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReportTimingSettingsSerializer
    permission_classes = [IsReportSettingsManager]
    queryset = ReportTimingSettings.objects.all()
