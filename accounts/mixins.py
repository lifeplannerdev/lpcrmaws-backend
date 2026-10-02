from accounts.permissions import has_dynamic_permission
from rest_framework.exceptions import PermissionDenied

# Maps branch-level company keys to their parent company
BRANCH_TO_COMPANY = {
    'LP_HQ':    'LP',
    'LP_KOCHI': 'LP',
    'FLAG_KOCHI': 'FLAG',
    'FDS_KOCHI':  'FDS',
}

class CompanyFilterMixin:
    """
    Mixin for DRF ViewSets to automatically filter querysets by the user's company 
    or the requested company if the user has cross-company permissions.
    Supports branch-level keys: LP_HQ, LP_KOCHI, FLAG_KOCHI, FDS_KOCHI.
    """
    def get_cross_company_permissions(self):
        # Allow viewsets to specify which permissions grant cross-company access
        return getattr(self, 'cross_company_permissions', ['staff:access_flag'])

    def has_cross_company_access(self, user):
        if user.is_superuser:
            return True
        for perm in self.get_cross_company_permissions():
            if has_dynamic_permission(user, perm):
                return True
        return False

    def get_queryset(self):
        qs = super().get_queryset()
        
        # In case this is called in a context without a request (e.g. swagger)
        if not hasattr(self, 'request') or not self.request or not self.request.user.is_authenticated:
            return qs.none()
            
        user = self.request.user
        requested_company = self.request.query_params.get('company')
        
        if requested_company:
            if requested_company.lower() == 'all':
                if self.has_cross_company_access(user):
                    return qs
                else:
                    if hasattr(qs.model, 'company'):
                        return qs.filter(company=user.company)
                    return qs
                    
            # Determine the parent company for branch-level keys
            parent_company = BRANCH_TO_COMPANY.get(requested_company, requested_company)
            user_parent_company = BRANCH_TO_COMPANY.get(user.company, user.company)

            # Check if user is trying to access another company's data
            if parent_company != user_parent_company:
                # Allow cross-company access if they have the right permission
                if parent_company in ['FLAG', 'FDS'] and self.has_cross_company_access(user):
                    pass  # Access granted
                elif self.has_cross_company_access(user):
                    pass  # Access granted generically if they have cross-company perms
                else:
                    raise PermissionDenied(f"You do not have permission to access {requested_company} data.")
            
            # Apply the filter
            if hasattr(qs.model, 'company'):
                return qs.filter(company=requested_company)
            return qs
            
        else:
            # If no company is explicitly requested, default to the user's native company
            if hasattr(qs.model, 'company'):
                return qs.filter(company=user.company)
            return qs

