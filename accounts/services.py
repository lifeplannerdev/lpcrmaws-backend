class PermissionService:
    @staticmethod
    def get_user_permissions(user):
        """
        Calculate and return the consolidated permissions dictionary for a user
        based on their dynamically assigned db_roles.
        
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

        permissions_dict = {}

        # Pre-load permissions via db_roles
        for role in user.db_roles.prefetch_related('permissions').all():
            for perm in role.permissions.all():
                if ':' in perm.name:
                    resource, action = perm.name.split(':', 1)
                    if resource not in permissions_dict:
                        permissions_dict[resource] = set()
                    permissions_dict[resource].add(action)

        # Include user-specific JSON permissions
        user_specific_perms = user.permissions if isinstance(user.permissions, list) else []
        for perm in user_specific_perms:
            if isinstance(perm, str) and ':' in perm:
                resource, action = perm.split(':', 1)
                if resource not in permissions_dict:
                    permissions_dict[resource] = set()
                permissions_dict[resource].add(action)

        # Convert sets to lists
        for resource in permissions_dict:
            permissions_dict[resource] = list(permissions_dict[resource])

        return permissions_dict
