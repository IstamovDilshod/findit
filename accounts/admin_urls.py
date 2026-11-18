from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .admin_api import AdminStatsView, AdminUserViewSet

router = DefaultRouter()
router.register("users", AdminUserViewSet, basename="admin-user")

urlpatterns = [
    path("stats/", AdminStatsView.as_view()),
    path("", include(router.urls)),
]