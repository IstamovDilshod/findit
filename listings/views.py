from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsModerator

from .matching import run_matching
from .models import Category, Claim, FoundReport, Listing, Location, Match
from .serializers import (CategorySerializer, ClaimSerializer, FoundReportSerializer,
                          ListingSerializer, LocationSerializer, MapPointSerializer,
                          MatchSerializer, ModerationClaimSerializer,
                          ModerationFoundReportSerializer, OwnerFoundReportSerializer)
class CategoryListView(ListAPIView):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    pagination_class = None
    permission_classes = [permissions.AllowAny]


class LocationListView(ListAPIView):
    queryset = Location.objects.filter(is_active=True)
    serializer_class = LocationSerializer
    pagination_class = None
    permission_classes = [permissions.AllowAny]

@extend_schema_view(
    list=extend_schema(parameters=[
        OpenApiParameter("type", str, enum=["LOST", "FOUND"]),
        OpenApiParameter("category", int, description="Kategoriya ID"),
        OpenApiParameter("location", int, description="Joy ID"),
        OpenApiParameter("color", str),
        OpenApiParameter("q", str, description="Sarlavha, tavsif yoki brend bo'yicha qidiruv"),
        OpenApiParameter("date_from", str, description="YYYY-MM-DD"),
        OpenApiParameter("date_to", str, description="YYYY-MM-DD"),
    ]),
)

class ListingViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = Listing.objects.select_related("category", "location", "user")
        user = self.request.user

        if self.action in ("list", "map"):
            qs = qs.filter(status=Listing.Status.ACTIVE)
            p = self.request.query_params
            if p.get("type") in (Listing.Type.LOST, Listing.Type.FOUND):
                qs = qs.filter(type=p["type"])
            if p.get("category"):
                qs = qs.filter(category_id=p["category"])
            if p.get("location"):
                qs = qs.filter(location_id=p["location"])
            if p.get("color"):
                qs = qs.filter(color__icontains=p["color"])
            if p.get("date_from"):
                qs = qs.filter(event_date__gte=p["date_from"])
            if p.get("date_to"):
                qs = qs.filter(event_date__lte=p["date_to"])
            if p.get("q"):
                q = p["q"]
                qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(brand__icontains=q))
            if p.get("bbox"):
                try:
                    min_lng, min_lat, max_lng, max_lat = [float(x) for x in p["bbox"].split(",")]
                except ValueError:
                    raise ValidationError({"bbox": "Format: min_lng,min_lat,max_lng,max_lat"})
                qs = qs.filter(longitude__gte=min_lng, longitude__lte=max_lng,
                               latitude__gte=min_lat, latitude__lte=max_lat)
            if self.action == "map":
                qs = qs.filter(latitude__isnull=False, longitude__isnull=False)
            return qs

        if self.action == "retrieve":
            if user.is_authenticated and user.is_moderator:
                return qs
            cond = Q(status__in=[Listing.Status.ACTIVE, Listing.Status.IN_CLAIM, Listing.Status.CLOSED])
            if user.is_authenticated:
                cond |= Q(user=user)
            return qs.filter(cond)

        # destroy, mine, matches: faqat o'z e'lonlari
        return qs.filter(user=user)
    
    def create(self, request, *args, **kwargs):
        # Admin e'lon bera olmaydi: u faqat boshqaradi
        if request.user.role == "ADMIN":
            raise PermissionDenied("Admin e'lon bera olmaydi.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)  # status avtomatik PENDING

    def perform_destroy(self, instance):
        if instance.status in (Listing.Status.IN_CLAIM, Listing.Status.CLOSED):
            raise ValidationError("Da'vo jarayonidagi yoki yopilgan e'lonни o'chirib bo'lmaydi.")
        instance.delete()
        
    @extend_schema(responses=MapPointSerializer(many=True))
    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def map(self, request):
        """Xaritadagi nuqtalar (koordinatasi bor faol e'lonlar, eng ko'pi bilan 500 ta)."""
        qs = self.get_queryset()[:500]
        return Response(MapPointSerializer(qs, many=True).data)

    @extend_schema(responses=ListingSerializer(many=True))
    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def mine(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(responses=OwnerFoundReportSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="found-reports",
            permission_classes=[permissions.IsAuthenticated])
    def found_reports(self, request, pk=None):
        listing = self.get_object()  # faqat o'z e'loni
        qs = listing.found_reports.filter(status__in=["APPROVED", "COMPLETED"]).select_related("finder")
        return Response(OwnerFoundReportSerializer(qs, many=True).data)
    
    @extend_schema(responses=MatchSerializer(many=True))
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def matches(self, request, pk=None):
        listing = self.get_object()
        qs = (
            Match.objects.filter(
                Q(lost_listing=listing, found_listing__status=Listing.Status.ACTIVE)
                | Q(found_listing=listing, lost_listing__status=Listing.Status.ACTIVE)
            )
            .exclude(status=Match.Status.DISMISSED)
            .select_related("lost_listing__category", "lost_listing__location", "lost_listing__user",
                            "found_listing__category", "found_listing__location", "found_listing__user")
            .order_by("-score")
        )
        data = MatchSerializer(qs, many=True, context={"request": request, "listing": listing}).data
        return Response(data)


class DismissMatchView(APIView):
    """Foydalanuvchi mos emas deb hisoblagan moslikni yashiradi."""
    permission_classes = [permissions.IsAuthenticated]
    @extend_schema(request=None, responses={204: None})
    def post(self, request, pk):
        match = get_object_or_404(
            Match.objects.filter(Q(lost_listing__user=request.user) | Q(found_listing__user=request.user)), pk=pk
        )
        match.status = Match.Status.DISMISSED
        match.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClaimViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ClaimSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.claims.select_related("listing")

class ModerationListingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Moderator uchun e'lonlar navbati. Standart: tekshiruvdagi (PENDING) e'lonlar."""
    serializer_class = ListingSerializer
    permission_classes = [IsModerator]

    def get_queryset(self):
        qs = Listing.objects.select_related("category", "location", "user")
        if self.action == "list":
            wanted = self.request.query_params.get("status", Listing.Status.PENDING)
            if wanted != "ALL":
                qs = qs.filter(status=wanted)
            return qs.order_by("created_at" if wanted == Listing.Status.PENDING else "-created_at")
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        listing = self.get_object()
        if listing.status != Listing.Status.PENDING:
            raise ValidationError("Faqat tekshiruvdagi e'lonni tasdiqlash mumkin.")
        listing.status = Listing.Status.ACTIVE
        listing.save()
        run_matching(listing)
        return Response(self.get_serializer(listing).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        listing = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        if listing.status != Listing.Status.PENDING:
            raise ValidationError("Faqat tekshiruvdagi e'lonni rad etish mumkin.")
        if not reason:
            raise ValidationError({"reason": "Rad etish sababini yozing."})
        listing.status = Listing.Status.REJECTED
        listing.reject_reason = reason
        listing.save()
        return Response(self.get_serializer(listing).data)


class ModerationClaimViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Moderator uchun da'volar navbati. Standart: kutilayotgan (PENDING) da'volar."""
    serializer_class = ModerationClaimSerializer
    permission_classes = [IsModerator]

    def get_queryset(self):
        qs = Claim.objects.select_related(
            "listing__category", "listing__location", "listing__user", "claimant",
            "match__lost_listing__category", "match__lost_listing__location", "match__lost_listing__user",
        )
        if self.action == "list":
            wanted = self.request.query_params.get("status", Claim.Status.PENDING)
            if wanted != "ALL":
                qs = qs.filter(status=wanted)
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        claim = self.get_object()
        if claim.status != Claim.Status.PENDING:
            raise ValidationError("Bu da'vo allaqachon ko'rib chiqilgan.")
        claim.review_note = (request.data.get("note") or "").strip()
        claim.approve(request.user)
        return Response(self.get_serializer(claim).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        claim = self.get_object()
        note = (request.data.get("note") or "").strip()
        if claim.status != Claim.Status.PENDING:
            raise ValidationError("Bu da'vo allaqachon ko'rib chiqilgan.")
        if not note:
            raise ValidationError({"note": "Rad etish sababini yozing."})
        claim.review_note = note
        claim.reject(request.user)
        return Response(self.get_serializer(claim).data)


class ModerationSummaryView(APIView):
    permission_classes = [IsModerator]

    def get(self, request):
        return Response({
            "pending_listings": Listing.objects.filter(status=Listing.Status.PENDING).count(),
            "pending_claims": Claim.objects.filter(status=Claim.Status.PENDING).count(),
            "pending_reports": FoundReport.objects.filter(status=FoundReport.Status.PENDING).count(),
        })


class FoundReportViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Topuvchi: ariza yuboradi va o'z arizalarini ko'radi. E'lon egasi: tasdiqlaydi yoki rad etadi."""
    serializer_class = FoundReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = FoundReport.objects.select_related("listing")
        if self.action in ("confirm", "dispute"):
            return qs.filter(listing__user=self.request.user)
        return qs.filter(finder=self.request.user)

    @extend_schema(request=None, responses={200: OwnerFoundReportSerializer})
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        report = self.get_object()
        if report.status != FoundReport.Status.APPROVED:
            raise ValidationError("Bu ariza hozir tasdiqlashga tayyor emas.")
        report.complete()
        return Response(OwnerFoundReportSerializer(report).data)

    @extend_schema(request=None, responses={200: OwnerFoundReportSerializer})
    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        report = self.get_object()
        if report.status != FoundReport.Status.APPROVED:
            raise ValidationError("Bu ariza hozir rad etishga tayyor emas.")
        report.dispute()
        return Response(OwnerFoundReportSerializer(report).data)


class ModerationFoundReportViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Moderator uchun topilma arizalari navbati (standart: kutilayotganlar)."""
    serializer_class = ModerationFoundReportSerializer
    permission_classes = [IsModerator]

    def get_queryset(self):
        qs = FoundReport.objects.select_related(
            "listing__category", "listing__location", "listing__user", "finder")
        if self.action == "list":
            wanted = self.request.query_params.get("status", FoundReport.Status.PENDING)
            if wanted != "ALL":
                qs = qs.filter(status=wanted)
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        report = self.get_object()
        if report.status != FoundReport.Status.PENDING:
            raise ValidationError("Bu ariza allaqachon ko'rib chiqilgan.")
        if report.listing.status != Listing.Status.ACTIVE:
            raise ValidationError("E'lon endi faol emas, arizani tasdiqlab bo'lmaydi.")
        report.review_note = (request.data.get("note") or "").strip()
        report.approve(request.user)
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        report = self.get_object()
        note = (request.data.get("note") or "").strip()
        if report.status != FoundReport.Status.PENDING:
            raise ValidationError("Bu ariza allaqachon ko'rib chiqilgan.")
        if not note:
            raise ValidationError({"note": "Rad etish sababini yozing."})
        report.review_note = note
        report.reject(request.user)
        return Response(self.get_serializer(report).data)