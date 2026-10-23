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

def get_user_task_locations(user):
    """
    Returns set of location names ('kochi', 'kottayam') that the user
    has permission to manage tasks for via tasks:kochi / tasks:kottayam.
    """
    if not user or not user.is_authenticated:
        return set()
    locs = set()
    if has_dynamic_permission(user, 'tasks:kochi'):
        locs.add('kochi')
    if has_dynamic_permission(user, 'tasks:kottayam'):
        locs.add('kottayam')
    return locs


def can_approve_task(user, task):
    """
    Determines if a user can approve or reject a task.
    - Managing Director / Superuser: can approve/reject.
    - Users with tasks:kochi / tasks:kottayam: can approve/reject tasks
      assigned to staff in their location, BUT cannot approve/reject their own task.
    - Users with tasks:documentation: can approve/reject tasks assigned to staff with
      DOCUMENTATION role, BUT cannot approve/reject their own task.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    # "see approving own task is not possible for them"
    if task.assigned_to == user:
        return False
    if is_managing_director(user):
        return True
    task_locations = get_user_task_locations(user)
    if task_locations:
        assignee_loc = (task.assigned_to.location or "").strip().lower()
        if assignee_loc in task_locations:
            return True
    if has_dynamic_permission(user, 'tasks:documentation'):
        if task.assigned_to and task.assigned_to.db_roles.filter(name='DOCUMENTATION').exists():
            return True
    return False


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
            and (
                has_dynamic_permission(request.user, 'tasks:edit_any')
                or has_dynamic_permission(request.user, 'tasks:kochi')
                or has_dynamic_permission(request.user, 'tasks:kottayam')
                or has_dynamic_permission(request.user, 'tasks:documentation')
            )
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

        task_locations = get_user_task_locations(request.user)
        if task_locations:
            assignee_loc = (obj.assigned_to.location or "").strip().lower()
            if assignee_loc in task_locations:
                return True

        if has_dynamic_permission(request.user, 'tasks:documentation'):
            if obj.assigned_to and obj.assigned_to.db_roles.filter(name='DOCUMENTATION').exists():
                return True

        return False
