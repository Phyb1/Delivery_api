from rest_framework.permissions import BasePermission

VENDOR = "vendor"
RIDER = "rider"
ADMIN = "admin"
CLIENT_APP = "client_app"


class HasRole(BasePermission):
    """Base class: allow principals (users or client apps) whose ``role`` is listed."""

    allowed_roles = ()

    def has_permission(self, request, view):
        return getattr(request.user, "role", None) in self.allowed_roles


class CanPostDeliveries(HasRole):
    allowed_roles = (VENDOR, CLIENT_APP)


class IsRider(HasRole):
    allowed_roles = (RIDER,)


class CanCancelDeliveries(HasRole):
    allowed_roles = (VENDOR, CLIENT_APP, ADMIN)
