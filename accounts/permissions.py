from rest_framework.permissions import BasePermission


class IsModerator(BasePermission):
    """Faqat moderator va admin."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_moderator)

class IsAdmin(BasePermission):
    """Faqat ADMIN roli."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "ADMIN")