from rest_framework.permissions import BasePermission
from accounts.permissions import has_dynamic_permission


def is_reminders_admin(user):
    """
    Returns True if user has administrative control over all reminders.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return has_dynamic_permission(user, 'processing:reminders_admin')


def is_reminders_user(user):
    """
    Returns True if user can access reminders (either admin or user permission).
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        has_dynamic_permission(user, 'processing:reminders_admin') or
        has_dynamic_permission(user, 'processing:reminders_users')
    )


class HasRemindersAccess(BasePermission):
    """
    Requires the user to have either processing:reminders_admin or processing:reminders_users.
    """
    def has_permission(self, request, view):
        return is_reminders_user(request.user)


class HasRemindersAdminAccess(BasePermission):
    """
    Requires the user to have processing:reminders_admin.
    """
    def has_permission(self, request, view):
        return is_reminders_admin(request.user)
