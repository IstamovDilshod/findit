from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
import secrets

from rest_framework.decorators import action
from listings.models import Claim, Listing, Match

from .models import Role, User
from .permissions import IsAdmin
from .serializers import AdminUserSerializer


def grouped(qs, field):
    """{qiymat: soni} ko'rinishida guruhlaydi."""
    return {r[field]: r["n"] for r in qs.order_by().values(field).annotate(n=Count("id"))}


class AdminStatsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        today = timezone.localdate()
        since = today - timedelta(days=29)

        roles = {r: 0 for r in Role.values}
        roles.update(grouped(User.objects.all(), "role"))
        statuses = {s: 0 for s in Listing.Status.values}
        statuses.update(grouped(Listing.objects.all(), "status"))
        types = {t: 0 for t in Listing.Type.values}
        types.update(grouped(Listing.objects.all(), "type"))
        claim_statuses = {s: 0 for s in Claim.Status.values}
        claim_statuses.update(grouped(Claim.objects.all(), "status"))

        by_category = [
            {"name": r["category__name"], "count": r["n"]}
            for r in Listing.objects.order_by().values("category__name")
            .annotate(n=Count("id")).order_by("-n")[:8]
        ]
        by_location = [
            {"name": r["location__name"], "count": r["n"]}
            for r in Listing.objects.filter(location__isnull=False).order_by()
            .values("location__name").annotate(n=Count("id")).order_by("-n")[:5]
        ]

        created = {
            r["d"]: r["n"]
            for r in Listing.objects.filter(created_at__date__gte=since)
            .annotate(d=TruncDate("created_at")).order_by().values("d").annotate(n=Count("id"))
        }
        closed = {
            r["d"]: r["n"]
            for r in Listing.objects.filter(closed_at__date__gte=since)
            .annotate(d=TruncDate("closed_at")).order_by().values("d").annotate(n=Count("id"))
        }
        daily = []
        for i in range(30):
            d = since + timedelta(days=i)
            daily.append({"date": d.isoformat(), "created": created.get(d, 0), "closed": closed.get(d, 0)})

        # Tasdiqlangan e'lonlar ichida egasiga qaytarilganlar ulushi
        approved = sum(v for k, v in statuses.items() if k not in ("PENDING", "REJECTED"))
        return_rate = round(statuses["CLOSED"] / approved * 100, 1) if approved else None

        pairs = Listing.objects.filter(status=Listing.Status.CLOSED, closed_at__isnull=False) \
            .values_list("created_at", "closed_at")[:1000]
        days = [(c - a).total_seconds() / 86400 for a, c in pairs]
        avg_days = round(sum(days) / len(days), 1) if days else None

        return Response({
            "users": {
                "total": sum(roles.values()),
                "by_role": roles,
                "blocked": User.objects.filter(is_active=False).count(),
                "new_7d": User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count(),
            },
            "listings": {
                "total": sum(statuses.values()),
                "by_status": statuses,
                "by_type": types,
                "by_category": by_category,
                "by_location": by_location,
                "return_rate": return_rate,
                "avg_days_to_close": avg_days,
            },
            "claims": {"total": sum(claim_statuses.values()), "by_status": claim_statuses},
            "matches": {"total": Match.objects.count()},
            "daily": daily,
        })


class AdminUserViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Foydalanuvchilar ro'yxati; admin rol berishi va bloklashi mumkin."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        qs = User.objects.annotate(
            listings_count=Count("listings", distinct=True),
            claims_count=Count("claims", distinct=True),
        ).order_by("-date_joined")
        p = self.request.query_params
        if p.get("role") in Role.values:
            qs = qs.filter(role=p["role"])
        if p.get("q"):
            q = p["q"]
            qs = qs.filter(
                Q(username__icontains=q) | Q(full_name__icontains=q)
                | Q(email__icontains=q) | Q(phone__icontains=q)
            )
        return qs

    def perform_update(self, serializer):
        # O'zini admin'likdan tushirib yoki bloklab qo'ymasligi uchun
        if serializer.instance.pk == self.request.user.pk:
            raise ValidationError("O'zingizning rolingiz yoki holatingizni o'zgartira olmaysiz.")
        serializer.save()
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Vaqtinchalik parol beradi (email kiritmagan foydalanuvchilar uchun)."""
        user = self.get_object()
        if user.pk == request.user.pk:
            raise ValidationError("O'z parolingizni profil sahifasidan o'zgartiring.")
        password = secrets.token_urlsafe(9)
        user.set_password(password)
        user.save()
        return Response({"password": password})