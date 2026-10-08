# Default permission templates for each role
# These are no longer used. We rely solely on the DB role structure.

ROLE_PERMISSIONS = {}

def get_permissions_for_role(role_name):
    """Returns a list of default permissions for the given role."""
    if not role_name:
        return []
    return ROLE_PERMISSIONS.get(role_name.upper(), [])
