# Default permission templates for each role
# These are copied to a User's `permissions` JSONField upon creation or role change.

ROLE_PERMISSIONS = {
    'ADMIN': [
        'view_overview', 'view_leads', 'view_staff', 'view_all_tasks', 
        'view_students', 'edit_students', 'view_fees', 'manage_fees', 'restructure_fees',
        'record_partial_payment', 'issue_fee_notice', 'view_fee_reports',
        'view_staff_reports', 'view_voxbay',
        'edit_tasks', 'edit_penalties', 'edit_candidates', 'edit_staff', 'delete_staff',
        'access_flag', 'view_asset', 'manage_asset', 'view_staff_assets', 'edit_staff_contact_logic'
    ],
    'CEO': [
        'view_overview', 'view_leads', 'view_staff', 'view_all_tasks', 
        'view_students', 'edit_students', 'view_fees', 'manage_fees', 'view_fee_reports',
        'view_my_reports', 'view_staff_reports', 'view_voxbay',
        'edit_tasks', 'access_flag'
    ],
    'BUSINESS_HEAD': [
        'view_overview', 'view_leads', 'view_staff', 'view_my_tasks', 
        'view_all_tasks', 'view_my_reports'
    ],
    'OPS': [
        'view_overview', 'view_leads', 'view_staff', 'view_all_tasks', 
        'view_my_reports',
        'edit_tasks'
    ],
    'ADM_MANAGER': [
        'view_overview', 'view_leads', 'view_all_tasks', 'view_my_reports'
    ],
    'ADM_COUNSELLOR': [
        'view_overview', 'view_leads', 'view_all_tasks', 'view_my_reports'
    ],
    'ADM_EXEC': [
        'view_overview', 'view_leads', 'view_all_tasks', 'view_my_reports'
    ],
    'PROCESSING': [
        # Based on default logic or fallback
        'view_overview', 'view_all_tasks', 'view_my_reports'
    ],
    'MEDIA': [
        'view_overview', 'view_all_tasks', 'view_my_reports'
    ],
    'TRAINER': [
        'view_overview', 'view_students', 'view_fees', 'mark_attendance', 
        'view_all_tasks', 'view_my_reports'
    ],
    'BDM': [
        'view_overview', 'view_leads', 'view_all_tasks', 'view_my_reports',
        'edit_tasks'
    ],
    'CM': [
        'view_overview', 'view_staff', 'view_leads', 'view_all_tasks', 
        'view_my_reports', 'view_staff_reports',
        'edit_tasks', 'access_flag'
    ],
    'HR': [
        'view_overview', 'view_staff', 'view_penalties', 'view_attendance_docs', 'view_fees',
        'view_candidates', 'view_all_tasks', 'view_my_reports', 'view_staff_reports',
        'edit_tasks', 'edit_penalties', 'edit_candidates', 'edit_staff', 'delete_staff',
        'access_flag', 'view_asset', 'manage_asset', 'view_staff_assets', 'edit_staff_contact_logic'
    ],
    'FOE': [
        'view_overview', 'view_leads', 'view_all_tasks', 'view_my_reports'
    ],
    'DOCUMENTATION': [
        'view_overview', 'view_all_tasks', 'view_my_reports'
    ],
    'ACCOUNTS': [
        'view_overview', 'view_penalties', 'view_all_tasks', 'view_my_reports',
        'view_fees', 'manage_fees', 'restructure_fees', 'record_partial_payment',
        'issue_fee_notice', 'view_fee_reports', 'edit_penalties'
    ],
}

def get_permissions_for_role(role_name):
    """Returns a list of default permissions for the given role."""
    if not role_name:
        return []
    return ROLE_PERMISSIONS.get(role_name.upper(), [])
