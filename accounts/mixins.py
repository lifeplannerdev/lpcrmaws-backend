from rest_framework.exceptions import PermissionDenied

class CompanyFilterMixin:
    """
    Mixin for DRF ViewSets to automatically filter querysets by the user's company 
    or the requested company if the user has cross-company permissions.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        
        # In case this is called in a context without a request (e.g. swagger)
        if not hasattr(self, 'request') or not self.request or not self.request.user.is_authenticated:
            return qs.none()
            
        user = self.request.user
        requested_company = self.request.query_params.get('company')
        
        if requested_company:
            # Check if user is trying to access another company's data
            if requested_company != user.company:
                # The only allowed cross-company access is LP users accessing FLAG data
                if requested_company == 'FLAG' and 'access_flag' in user.permissions:
                    pass  # Access granted
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
