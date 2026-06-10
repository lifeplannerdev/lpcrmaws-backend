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

