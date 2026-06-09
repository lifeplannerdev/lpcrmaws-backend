from accounts.permissions import has_dynamic_permission
from rest_framework.permissions import BasePermission

TOP_MANAGEMENT = [
    "ADMIN",
    "CEO",
]

OPERATIONS = [
    "OPS",
    "GENERAL_MANAGER",
    "CM",
    "BDM",
]

HR_ROLES = [
    "HR",
]

EXECUTION_ROLES = [
    "MEDIA",
    "ADM_EXEC",
    "ADM_MANAGER",
    "ADM_COUNSELLOR",
    "PROCESSING",
    "FOE",
    "TRAINER",
    "ACCOUNTS",
    'DOCUMENTATION',
]



TASK_ASSIGNERS = TOP_MANAGEMENT + OPERATIONS + HR_ROLES
TASK_ASSIGNEES = EXECUTION_ROLES




class IsTaskAssigner(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and has_dynamic_permission(request.user, 'tasks:edit_any')
        )


class IsTaskAssignee(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated


class IsAssigneeOrTaskAssigner(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if obj.assigned_to == request.user:
            return True

        if has_dynamic_permission(request.user, 'tasks:edit_any'):
            return True

        return False

