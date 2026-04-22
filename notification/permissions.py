from rest_framework.permissions import BasePermission




class IsEmployee(BasePermission):
    def has_permission(self, request, view):
        if not request.user:
            return False
        groups = request.user.get('groups', [])
        if 'Administrator' in groups:
            return False
        return 'Employee' in groups


class IsAdminOrEmployee(BasePermission):
    def has_permission(self, request, view):
        if not request.user:
            return False
        groups = request.user.get('groups', [])
        return bool(set(groups) & {'Administrator', 'Employee'})