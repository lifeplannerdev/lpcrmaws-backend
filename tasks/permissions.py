from accounts.permissions import has_dynamic_permission
from rest_framework.permissions import BasePermission

TOP_MANAGEMENT = [
    "ADMIN",
    "CEO",
    "BUSINESS_HEAD",
    "MANAGING_DIRECTOR",
    "managing_director",
    "Managing Director",
    "MD",
]

OPERATIONS = [
    "OPS",
    "OPERATION",
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




def is_managing_director(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role_names = []
    if hasattr(user, 'db_roles'):
        role_names.extend(list(user.db_roles.values_list('name', flat=True)))
    role = getattr(user, 'role', '')
    if role:
        role_names.append(role)
    return any(str(r).strip().upper() in {'MANAGING_DIRECTOR', 'MANAGING DIRECTOR', 'MD', 'ADMIN'} for r in role_names)

def can_manage_all_tasks(user):
    return (
        user.is_superuser or
        has_dynamic_permission(user, 'tasks:read_all') or 
        has_dynamic_permission(user, 'tasks:read_tenant') or 
        user.db_roles.filter(name__in=TOP_MANAGEMENT).exists()
    )

def can_manage_own_assigned_tasks(user):
    return (
        has_dynamic_permission(user, 'tasks:edit_any') or 
        user.db_roles.filter(name__in=OPERATIONS).exists() or
        user.db_roles.filter(name__in=TASK_ASSIGNERS).exists()
    )

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

        if obj.assigned_to == request.user or obj.assigned_by == request.user:
            return True

        if request.user.is_superuser or has_dynamic_permission(request.user, 'tasks:edit_any'):
            return True

        return False

