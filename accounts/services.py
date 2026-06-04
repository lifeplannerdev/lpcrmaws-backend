class PermissionService:
    @staticmethod
    def get_user_permissions(user):
        """
        Calculate and return the consolidated permissions dictionary for a user
        based on their role and company.
        
        Returns a dict mapping resources to a list of allowed actions.
        Example:
        {
            "leads": ["read", "create", "edit_own", "delete_own"],
            "staff": ["read"]
        }
        """
        if not user.is_authenticated:
            return {}

        if user.is_superuser:
            # Superuser gets full wildcard access
            return {"*": ["*"]}

        # Base permissions that all authenticated users get
        permissions = {
            "profile": ["read", "edit_own"],
            "dashboard": ["read"],
        }

        role = getattr(user, 'role', '')
        
        # We can eventually fetch from DB here, but for Phase 1 we fallback to hardcoded mappings
        if role in ['ADMIN', 'CEO']:
            permissions.update({
                "leads": ["read", "create", "edit_any", "delete_any"],
                "staff": ["read", "create", "edit_any", "delete_any"],
                "attendance": ["read_any", "create_any", "edit_any"],
                "penalties": ["read_any", "create", "edit_any", "delete_any"],
                "assets": ["read_any", "create", "edit_any", "delete_any"],
            })
        elif role in ['ADM_MANAGER', 'OPS', 'CM', 'BUSINESS_HEAD']:
            permissions.update({
                "leads": ["read_tenant", "create", "edit_tenant", "delete_tenant"],
                "staff": ["read_tenant", "edit_tenant"],
                "attendance": ["read_tenant", "create"],
                "penalties": ["read_tenant"],
                "assets": ["read_tenant"],
            })
        elif role in ['ADM_COUNSELLOR', 'ADM_EXEC', 'PROCESSING', 'FOE', 'BDM']:
            permissions.update({
                "leads": ["read_own", "create", "edit_own"],
                "staff": ["read_own"],
                "attendance": ["read_own", "create_own"],
                "penalties": ["read_own"],
                "assets": ["read_own"],
            })
        elif role == 'HR':
            permissions.update({
                "leads": ["read_tenant"],
                "staff": ["read_tenant", "create", "edit_tenant", "delete_tenant"],
                "attendance": ["read_tenant", "create", "edit_tenant"],
                "penalties": ["read_tenant", "create", "edit_tenant", "delete_tenant"],
                "assets": ["read_tenant", "create", "edit_tenant", "delete_tenant"],
            })
        else:
            # Default staff access for other roles
            permissions.update({
                "leads": ["read_own"],
                "staff": ["read_own"],
                "attendance": ["read_own", "create_own"],
            })

        return permissions
