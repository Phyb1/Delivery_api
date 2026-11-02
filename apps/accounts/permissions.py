from rest_framework.permissions import BasePermission

from .models import User


class IsUserAccount(BasePermission):
    """Allow human accounts only; client-app API keys are rejected."""

    def has_permission(self, request, view):
        return isinstance(request.user, User)
