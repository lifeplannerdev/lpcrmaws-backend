from rest_framework import filters
from rest_framework.exceptions import PermissionDenied

class CompanyFilterBackend(filters.BaseFilterBackend):
    """
    Filter that automatically scopes querysets to the user's company 
    or the requested company if the user has cross-company permissions.
    """
    def filter_queryset(self, request, queryset, view):
        user = request.user
        if not user or not user.is_authenticated:
            return queryset.none()
            
        requested_company = request.query_params.get('company')
        
        if requested_company:
            # Check if user is trying to access another company's data
            if requested_company != user.company:
                # The only allowed cross-company access is LP users accessing FLAG data
                if requested_company == 'FLAG' and has_dynamic_permission(user, 'staff:access_flag'):
                    pass  # Access granted
                else:
                    raise PermissionDenied(f"You do not have permission to access {requested_company} data.")
            
            # Apply the filter
            if hasattr(queryset.model, 'company'):
                return queryset.filter(company=requested_company)
            return queryset
            
        else:
            # If no company is explicitly requested, default to the user's native company
            if hasattr(queryset.model, 'company'):
                return queryset.filter(company=user.company)
            return queryset

