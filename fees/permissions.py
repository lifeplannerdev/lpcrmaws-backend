from accounts.permissions import has_dynamic_permission
from rest_framework.permissions import BasePermission


def _has_perm(user, perm):
    return user.is_authenticated and has_dynamic_permission(user, perm)


def is_trainer_user(user):
    """
    Returns True if user has the TRAINER role (or flag:trainer permission)
    and does NOT possess administrative / finance override permissions
    (flag:admin, fees:manage, or superuser).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return False
    if _has_perm(user, 'flag:admin') or _has_perm(user, 'fees:manage'):
        return False
    if hasattr(user, 'db_roles') and user.db_roles.filter(name__iexact='TRAINER').exists():
        return True
    if _has_perm(user, 'flag:trainer'):
        return True
    return False


EXECUTIVE_ROLES = {'MANAGING_DIRECTOR', 'MANAGING DIRECTOR', 'MD', 'DIRECTOR', 'CEO', 'BUSINESS_HEAD', 'ADMIN'}


def has_global_fee_access(user):
    """
    Returns True if user has global fee authority across all companies (FLAG, FDS, LP).
    Granted to superusers, users with 'fees:accounts' permission, or executive roles.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if _has_perm(user, 'fees:accounts'):
        return True
    user_roles = set()
    if hasattr(user, 'db_roles'):
        user_roles.update(user.db_roles.values_list('name', flat=True))
    if hasattr(user, 'role') and user.role:
        user_roles.add(user.role)
    if any(str(r).strip().upper() in EXECUTIVE_ROLES for r in user_roles):
        return True
    return False


def get_allowed_fee_companies(user, action='view'):
    """
    Returns a list of companies ('FLAG', 'FDS', 'LP') the user is permitted to access.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    if has_global_fee_access(user):
        return ['FLAG', 'FDS', 'LP']

    allowed = []

    # 1. FLAG
    if is_trainer_user(user):
        if action == 'view':
            allowed.append('FLAG')
    else:
        can_flag_write = (
            _has_perm(user, 'fees:flag') or
            _has_perm(user, 'flag:admin') or
            _has_perm(user, 'flag:fees') or
            _has_perm(user, 'fees:manage') or
            _has_perm(user, 'fees:partial_payment')
        )
        if can_flag_write:
            allowed.append('FLAG')
        elif action == 'view' and (
            _has_perm(user, 'fees:read_tenant') or
            _has_perm(user, 'fees:view_reports') or
            _has_perm(user, 'fees:read_own') or
            _has_perm(user, 'flag:view')
        ):
            allowed.append('FLAG')

    # 2. FDS
    can_fds_write = (
        _has_perm(user, 'fees:fds') or
        _has_perm(user, 'fds:admin') or
        _has_perm(user, 'fds_fees:manage')
    )
    if can_fds_write:
        allowed.append('FDS')
    elif action == 'view' and (
        _has_perm(user, 'fds_fees:view') or
        _has_perm(user, 'fds:view') or
        _has_perm(user, 'fds:management')
    ):
        allowed.append('FDS')

    # 3. LP
    can_lp_write = (
        _has_perm(user, 'fees:lp') or
        _has_perm(user, 'processing_students:manage_fees')
    )
    if can_lp_write:
        allowed.append('LP')
    elif action == 'view' and (
        _has_perm(user, 'processing_students:read_any') or
        _has_perm(user, 'processing_students:read_own')
    ):
        allowed.append('LP')

    return allowed


def can_access_company_receipts(user, company, action='view'):
    if not company:
        return False
    return company.upper() in get_allowed_fee_companies(user, action=action)


def can_manage_company_receipt_settings(user, company):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if is_trainer_user(user):
        return False
    if has_global_fee_access(user):
        return True
    c = (company or 'FLAG').upper()
    if c == 'FDS':
        return _has_perm(user, 'fees:fds') or _has_perm(user, 'fds:admin') or _has_perm(user, 'fds_fees:manage')
    if c == 'LP':
        return _has_perm(user, 'fees:lp') or _has_perm(user, 'processing_students:manage_fees')
    if c == 'FLAG':
        return _has_perm(user, 'fees:flag') or _has_perm(user, 'flag:admin') or _has_perm(user, 'flag:fees') or _has_perm(user, 'fees:manage')
    return False


class CanViewFees(BasePermission):
    def has_permission(self, request, view):
        if has_global_fee_access(request.user):
            return True
        allowed = get_allowed_fee_companies(request.user, action='view')
        if len(allowed) > 0:
            return True
        return (
            _has_perm(request.user, 'fees:read_tenant') or 
            _has_perm(request.user, 'fees:manage') or 
            _has_perm(request.user, 'fees:view_reports') or 
            _has_perm(request.user, 'fees:read_own') or
            _has_perm(request.user, 'flag:admin') or
            _has_perm(request.user, 'flag:fees') or
            _has_perm(request.user, 'flag:view') or
            (hasattr(request.user, 'db_roles') and request.user.db_roles.filter(name__iexact='TRAINER').exists())
        )


class CanManageFees(BasePermission):
    def has_permission(self, request, view):
        if has_global_fee_access(request.user):
            return True
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return CanViewFees().has_permission(request, view)
        return (
            _has_perm(request.user, 'fees:manage') or
            _has_perm(request.user, 'fees:flag') or
            _has_perm(request.user, 'fees:fds') or
            _has_perm(request.user, 'fees:lp')
        )


class CanRestructureFees(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:restructure') or _has_perm(request.user, 'fees:manage') or has_global_fee_access(request.user)


class CanRecordPartialPayment(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:partial_payment') or _has_perm(request.user, 'fees:manage') or has_global_fee_access(request.user)


class CanIssueFeeNotice(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:issue_notice') or _has_perm(request.user, 'fees:manage') or has_global_fee_access(request.user)


def _can_manage_receipt_admin_actions(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if is_trainer_user(user):
        return False
    if has_global_fee_access(user):
        return True
    return (
        _has_perm(user, 'fees:manage') or
        _has_perm(user, 'fees:flag') or
        _has_perm(user, 'fees:fds') or
        _has_perm(user, 'fees:lp') or
        _has_perm(user, 'flag:admin') or
        _has_perm(user, 'flag:fees') or
        _has_perm(user, 'fds:admin') or
        _has_perm(user, 'fds_fees:manage') or
        _has_perm(user, 'processing_students:manage_fees')
    )


def _can_view_fee_account(user, account):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if (
        getattr(user, 'is_superuser', False) or
        has_global_fee_access(user) or
        _has_perm(user, 'fees:read_tenant') or
        _has_perm(user, 'fees:view_reports') or
        _has_perm(user, 'fees:manage') or
        _has_perm(user, 'fees:flag') or
        _has_perm(user, 'flag:admin') or
        _has_perm(user, 'flag:fees')
    ):
        return True
    if not account:
        return False
    student = getattr(account, 'student', None)
    if not student:
        return False
    if getattr(student, 'trainer_id', None) == user.id:
        return True
    batch = getattr(student, 'batch', None)
    if batch and getattr(batch, 'trainer_id', None) == user.id:
        return True
    return hasattr(user, 'trainer_profile') and student.trainer_id == user.trainer_profile.id


class CanManageReceipts(BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return CanViewFees().has_permission(request, view)

        # WRITE actions (create, edit, update, delete, void) are strictly denied for trainers
        if is_trainer_user(request.user):
            return False

        if has_global_fee_access(request.user):
            return True

        allowed_write_companies = get_allowed_fee_companies(request.user, action='write')
        if len(allowed_write_companies) > 0:
            return True

        return (
            _can_manage_receipt_admin_actions(request.user) or
            _has_perm(request.user, 'fees:partial_payment')
        )
