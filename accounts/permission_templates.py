# Default permission templates for each role
# These are copied to a User's `permissions` JSONField upon creation or role change.

ROLE_PERMISSIONS = {
    'ADMIN': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_all', 
        'students:read_tenant', 'students:edit_any', 'fees:read_tenant', 'fees:manage', 'fees:restructure',
        'fees:partial_payment', 'fees:issue_notice', 'fees:view_reports',
        'reports:read_all', 'voxbay:read_all', 'voxbay:admin',
        'tasks:edit_any', 'penalties:edit_any', 'candidates:edit_any', 'staff:edit_any', 'staff:delete_any',
        'staff:access_flag', 'assets:read_any', 'assets:manage', 'assets:read_tenant', 'staff:edit_contact_logic',
        'credentials:view', 'credentials:manage', 'credentials:share'
    ],
    'CEO': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_all', 
        'students:read_tenant', 'students:edit_any', 'fees:read_tenant', 'fees:manage', 'fees:view_reports',
        'reports:read_own', 'reports:read_all', 'voxbay:read_all',
        'tasks:edit_any', 'staff:access_flag',
        'credentials:view', 'credentials:manage', 'credentials:share'
    ],
    'BUSINESS_HEAD': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_own', 
        'tasks:read_all', 'reports:read_own', 'voxbay:read_own'
    ],
    'OPS': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_all', 
        'reports:read_own', 'voxbay:read_own',
        'tasks:edit_any'
    ],
    'ADM_MANAGER': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own'
    ],
    'ADM_COUNSELLOR': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own'
    ],
    'ADM_EXEC': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own'
    ],
    'PROCESSING': [
        # Based on default logic or fallback
        'dashboard:read', 'tasks:read_all', 'reports:read_own'
    ],
    'MEDIA': [
        'dashboard:read', 'tasks:read_all', 'reports:read_own'
    ],
    'TRAINER': [
        'dashboard:read', 'students:read_tenant', 'fees:read_tenant', 'attendance:mark', 
        'tasks:read_all', 'reports:read_own'
    ],
    'BDM': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own',
        'tasks:edit_any'
    ],
    'CM': [
        'dashboard:read', 'staff:read_tenant', 'leads:read_tenant', 'tasks:read_all', 
        'reports:read_own', 'reports:read_all', 'voxbay:read_all', 'voxbay:admin',
        'tasks:edit_any', 'staff:access_flag'
    ],
    'HR': [
        'dashboard:read', 'staff:read_tenant', 'penalties:read_any', 'attendance:view_docs', 'fees:read_tenant',
        'candidates:read_any', 'tasks:read_all', 'reports:read_own', 'reports:read_all',
        'tasks:edit_any', 'penalties:edit_any', 'candidates:edit_any', 'staff:edit_any', 'staff:delete_any',
        'staff:access_flag', 'assets:read_any', 'assets:manage', 'assets:read_tenant', 'staff:edit_contact_logic'
    ],
    'FOE': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own'
    ],
    'DOCUMENTATION': [
        'dashboard:read', 'tasks:read_all', 'reports:read_own'
    ],
    'ACCOUNTS': [
        'dashboard:read', 'penalties:read_any', 'tasks:read_all', 'reports:read_own',
        'fees:read_tenant', 'fees:manage', 'fees:restructure', 'fees:partial_payment',
        'fees:issue_notice', 'fees:view_reports', 'penalties:edit_any'
    ],
}

def get_permissions_for_role(role_name):
    """Returns a list of default permissions for the given role."""
    if not role_name:
        return []
    return ROLE_PERMISSIONS.get(role_name.upper(), [])

