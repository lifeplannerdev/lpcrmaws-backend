from rest_framework.permissions import BasePermission
from accounts.models import AppPermission

def has_dynamic_permission(user, perm_name):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not hasattr(user, '_dynamic_perms_cache'):
        # Get permissions from db_roles
        db_perms = set(
            AppPermission.objects.filter(roles__users=user).values_list('name', flat=True)
        )
        # Get user-specific JSON permissions
        user_specific_perms = set(user.permissions) if isinstance(user.permissions, list) else set()
        user._dynamic_perms_cache = db_perms.union(user_specific_perms)
        
    return perm_name in user._dynamic_perms_cache


class IsManagement(BasePermission):
    """
    Management-level users who can view staff lists and details
    """
    def has_permission(self, request, view):
        return has_dynamic_permission(request.user, 'staff:read_tenant')


class IsSuperAdmin(BasePermission):
    """
    Very restricted actions like deleting staff
    """
    def has_permission(self, request, view):
        return has_dynamic_permission(request.user, 'staff:read_tenant') and has_dynamic_permission(request.user, 'tasks:edit_any')


def HasPermission(required_permission):
    """
    Factory function returning a BasePermission class that checks
    if the user's DB roles grant the required permission string.
    """
    class _HasPermission(BasePermission):
        def has_permission(self, request, view):
            return has_dynamic_permission(request.user, required_permission)

    return _HasPermission


def HasAnyPermission(*required_permissions):
    """
    Factory function returning a BasePermission class that checks
    if the user possesses at least one of the listed permissions.
    """
    class _HasAnyPermission(BasePermission):
        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            if request.user.is_superuser:
                return True
            return any(has_dynamic_permission(request.user, p) for p in required_permissions)

    return _HasAnyPermission


class CanAccessCompanyFees(BasePermission):
    """
    Checks company-scoped fee authority across FLAG, FDS, and LP.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or has_dynamic_permission(user, 'fees:accounts'):
            return True
        return any(
            has_dynamic_permission(user, p)
            for p in (
                'fees:fds', 'fees:flag', 'fees:lp', 'fees:manage',
                'fds_fees:manage', 'processing_students:manage_fees'
            )
        )


