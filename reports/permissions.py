from accounts.permissions import has_dynamic_permission
from rest_framework.permissions import BasePermission

REPORT_REVIEWERS = [
    "ADMIN",
    "CEO",
    "OPS",
    "GENERAL_MANAGER",
    "HR",
    "CM"
]

class IsReportReviewer(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            has_dynamic_permission(request.user, 'reports:read_all')
        )


class IsReportOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user

