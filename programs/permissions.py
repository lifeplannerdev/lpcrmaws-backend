from rest_framework.permissions import BasePermission
from accounts.permissions import has_dynamic_permission


def is_prog_stud_manager(user):
    """Return True if the user can manage, create, delete, import, and assign tracker rows."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return has_dynamic_permission(user, 'processing:prog_stud_manage')


def has_prog_stud_access(user):
    """Return True if the user has either manage or assigned access to the tracker."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        has_dynamic_permission(user, 'processing:prog_stud_manage')
        or has_dynamic_permission(user, 'processing:prog_stud_assigned')
    )


class HasProgStudAccess(BasePermission):
    """Allows access to users with processing:prog_stud_manage or processing:prog_stud_assigned."""

    def has_permission(self, request, view):
        return has_prog_stud_access(request.user)


class CanManageProgStud(BasePermission):
    """Allows access only to users with processing:prog_stud_manage."""

    def has_permission(self, request, view):
        return is_prog_stud_manager(request.user)
