# Default permission templates for each role
# These are copied to a User's `permissions` JSONField upon creation or role change.

ROLE_PERMISSIONS = {
    'ADMIN': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_all', 
        'processing_students:read_any', 'processing_students:read_own', 'processing_students:edit_any', 'processing_students:edit_own', 'processing_students:manage_fees',
        'reports:read_all', 'reports:documentation', 'voxbay:read_all', 'voxbay:admin',
        'tasks:edit_any', 'penalties:edit_any', 'candidates:edit_any', 'staff:edit_any', 'staff:delete_any',
        'staff:access_flag', 'assets:read_any', 'assets:manage', 'assets:read_tenant', 'staff:edit_contact_logic',
        'credentials:view', 'credentials:manage', 'credentials:share',
        'fds:admin', 'fds:view', 'fds_fees:view',
        'flag:admin', 'flag:view', 'flag:trainer', 'flag:fees',
        'staff_analysis:admin',
    ],
    'CEO': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_all', 
        'reports:read_own', 'reports:read_all', 'voxbay:read_all',
        'tasks:edit_any', 'staff:access_flag',
        'credentials:view', 'credentials:manage', 'credentials:share',
        'fds:admin', 'fds:view', 'fds_fees:view',
        'flag:admin', 'flag:view', 'flag:trainer', 'flag:fees',
        'staff_analysis:admin',
    ],
    'BUSINESS_HEAD': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_own', 
        'tasks:read_all', 'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own',
        'fds:view', 'flag:view'
    ],
    'OPS': [
        'dashboard:read', 'leads:read_tenant', 'staff:read_tenant', 'tasks:read_all', 
        'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own',
        'tasks:edit_any',
        'fds:view', 'flag:view'
    ],
    'ADM_MANAGER': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own', 'flag:view'
    ],
    'ADM_COUNSELLOR': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own', 'flag:view'
    ],
    'ADM_EXEC': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own'
    ],
    'PROCESSING': [
        'dashboard:read', 'tasks:read_all', 'reports:read_own'
    ],
    'MEDIA': [
        'dashboard:read', 'tasks:read_all', 'reports:read_own'
    ],
    'TRAINER': [
        'dashboard:read', 'tasks:read_all', 'reports:read_own',
        'flag:trainer', 'flag:view'
    ],
    'BDM': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own',
        'tasks:edit_any'
    ],
    'CM': [
        'dashboard:read', 'staff:read_tenant', 'leads:read_tenant', 'tasks:read_all', 
        'reports:read_own', 'reports:read_all', 'voxbay:read_all', 'voxbay:admin',
        'tasks:edit_any', 'staff:access_flag', 'flag:view'
    ],
    'HR': [
        'dashboard:read', 'staff:read_tenant', 'penalties:read_any', 
        'candidates:read_any', 'tasks:read_all', 'reports:read_own', 'reports:read_all',
        'tasks:edit_any', 'penalties:edit_any', 'candidates:edit_any', 'staff:edit_any', 'staff:delete_any',
        'staff:access_flag', 'assets:read_any', 'assets:manage', 'assets:read_tenant', 'staff:edit_contact_logic',
        'flag:view'
    ],
    'FOE': [
        'dashboard:read', 'leads:read_tenant', 'tasks:read_all', 'reports:read_own', 'voxbay:read_own', 'voxbay_ai:read_own'
    ],
    'DOCUMENTATION': [
        'dashboard:read', 'tasks:read_all', 'reports:read_own'
    ],
    'ACCOUNTS': [
        'dashboard:read', 'penalties:read_any', 'tasks:read_all', 'reports:read_own',
        'penalties:edit_any',
        'fds:view', 'fds_fees:view',
        'flag:fees', 'flag:view'
    ],
}

def get_permissions_for_role(role_name):
    """Returns a list of default permissions for the given role."""
    if not role_name:
        return []
    return ROLE_PERMISSIONS.get(role_name.upper(), [])


