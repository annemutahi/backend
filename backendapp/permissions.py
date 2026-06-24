from rest_framework.permissions import BasePermission, SAFE_METHODS

class CanEditSales(BasePermission):
    """Read for any authenticated user; write/edit/delete requires is_staff."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS or view.action == "create":
            return True
        return request.user.is_staff or request.user.is_superuser