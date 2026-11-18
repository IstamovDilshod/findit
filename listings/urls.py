from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (CategoryListView, ClaimViewSet, DismissMatchView, FoundReportViewSet,
                    ListingViewSet, LocationListView, ModerationClaimViewSet,
                    ModerationFoundReportViewSet, ModerationListingViewSet, ModerationSummaryView)

router = DefaultRouter()
router.register("listings", ListingViewSet, basename="listing")
router.register("claims", ClaimViewSet, basename="claim")
router.register("found-reports", FoundReportViewSet, basename="found-report")
router.register("moderation/listings", ModerationListingViewSet, basename="moderation-listing")
router.register("moderation/claims", ModerationClaimViewSet, basename="moderation-claim")
router.register("moderation/found-reports", ModerationFoundReportViewSet, basename="moderation-found-report")

urlpatterns = [
    path("categories/", CategoryListView.as_view()),
    path("locations/", LocationListView.as_view()),
    path("matches/<int:pk>/dismiss/", DismissMatchView.as_view()),
    path("moderation/summary/", ModerationSummaryView.as_view()),
    path("", include(router.urls)),
]