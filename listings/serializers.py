from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Category, Claim, FoundReport, Listing, Location, Match

from .models import Category, Claim, Listing, Location, Match


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "icon")


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ("id", "name", "type", "city", "latitude", "longitude")


class ListingSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    location_name = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="user.full_name", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = (
            "id", "type", "status", "category", "category_name", "location", "location_name",
            "title", "description", "color", "brand", "place_detail", "event_date", "image", "latitude", "longitude", "details",
            "secret_detail", "storage_place", "reject_reason", "owner_name", "is_mine", "created_at",
        )
        read_only_fields = ("status", "reject_reason", "created_at")

    def get_location_name(self, obj):
        return obj.location.name if obj.location else None

    def get_is_mine(self, obj):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.user_id == request.user.id)

    def validate_event_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Sana kelajakda bo'lishi mumkin emas.")
        return value

    def validate_category(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Bu kategoriya faol emas.")
        return value

    def validate_details(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Noto'g'ri format.")
        if len(value) > 20:
            raise serializers.ValidationError("Maydonlar juda ko'p.")
        clean = {}
        for key, val in value.items():
            val = str(val).strip()[:300]
            if val:
                clean[str(key)[:40]] = val
        return clean

    def validate(self, attrs):
        if attrs.get("type") == Listing.Type.FOUND and not attrs.get("secret_detail", "").strip():
            raise serializers.ValidationError(
                {"secret_detail": "Topilgan buyum uchun egasi biladigan yashirin belgini yozing."}
            )
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise serializers.ValidationError({"longitude": "Kenglik va uzunlik birga kiritilishi kerak."})
        return attrs

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        allowed = bool(user and user.is_authenticated and (obj.user_id == user.id or user.is_moderator))
        if not allowed:
            # Yashirin belgi va saqlash joyi faqat egasi va moderatorga ko'rinadi
            for field in ("secret_detail", "storage_place", "reject_reason"):
                data.pop(field, None)
        return data
    def get_location_name(self, obj) -> str | None:
        return obj.location.name if obj.location else None

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.user_id == request.user.id)


class MatchSerializer(serializers.ModelSerializer):
    other = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = ("id", "score", "reasons", "status", "other")

    def get_other(self, obj):
        mine = self.context["listing"]
        other = obj.found_listing if obj.lost_listing_id == mine.id else obj.lost_listing
        return ListingSerializer(other, context=self.context).data
    
    @extend_schema_field(ListingSerializer)
    def get_other(self, obj):
        mine = self.context["listing"]
        other = obj.found_listing if obj.lost_listing_id == mine.id else obj.lost_listing
        return ListingSerializer(other, context=self.context).data

class ClaimSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = Claim
        fields = ("id", "listing", "listing_title", "match", "proof_text", "status", "review_note", "created_at")
        read_only_fields = ("status", "review_note", "created_at")
        validators = []  # bir faol da'vo qoidasi create() ichida qulf bilan tekshiriladi

    def validate(self, attrs):
        user = self.context["request"].user
        listing, match = attrs["listing"], attrs.get("match")
        if listing.type != Listing.Type.FOUND:
            raise serializers.ValidationError({"listing": "Da'vo faqat topilgan (FOUND) e'longa yuboriladi."})
        if listing.user_id == user.id:
            raise serializers.ValidationError({"listing": "O'z e'loningizga da'vo qila olmaysiz."})
        if listing.status != Listing.Status.ACTIVE:
            raise serializers.ValidationError({"listing": "Bu e'lon hozir da'vo uchun ochiq emas."})
        if match and (match.found_listing_id != listing.id or match.lost_listing.user_id != user.id):
            raise serializers.ValidationError({"match": "Bu moslik sizga tegishli emas."})
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            # Bir vaqtda ikki kishi da'vo yubormasligi uchun e'lonni qulflaymiz
            listing = Listing.objects.select_for_update().get(pk=validated_data["listing"].pk)
            if listing.status != Listing.Status.ACTIVE:
                raise serializers.ValidationError({"listing": "Bu e'lon uchun da'vo allaqachon yuborilgan."})
            claim = Claim.objects.create(claimant=self.context["request"].user, **validated_data)
            listing.status = Listing.Status.IN_CLAIM
            listing.save()
        return claim

class MapPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ("id", "type", "title", "category", "latitude", "longitude", "event_date")


class ModerationClaimSerializer(serializers.ModelSerializer):
    listing = serializers.SerializerMethodField()
    claimant = serializers.SerializerMethodField()
    match_score = serializers.SerializerMethodField()
    lost_listing = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = ("id", "status", "proof_text", "review_note", "created_at",
                  "listing", "claimant", "match_score", "lost_listing")

    def get_listing(self, obj) -> dict:
        # Moderatorga yashirin belgi ham qaytadi (ListingSerializer rolni tekshiradi)
        return ListingSerializer(obj.listing, context=self.context).data

    def get_claimant(self, obj) -> dict:
        u = obj.claimant
        return {"id": u.id, "username": u.username, "full_name": u.full_name,
                "phone": u.phone, "email": u.email}

    def get_match_score(self, obj) -> float | None:
        return float(obj.match.score) if obj.match else None

    def get_lost_listing(self, obj) -> dict | None:
        if not obj.match:
            return None
        return ListingSerializer(obj.match.lost_listing, context=self.context).data


class FoundReportSerializer(serializers.ModelSerializer):
    """Topuvchi o'z arizasini yuboradi va ko'radi."""
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = FoundReport
        fields = ("id", "listing", "listing_title", "message", "current_place", "contact",
                  "status", "review_note", "created_at")
        read_only_fields = ("status", "review_note", "created_at")
        validators = []

    def validate(self, attrs):
        user = self.context["request"].user
        listing = attrs["listing"]
        if listing.type != Listing.Type.LOST:
            raise serializers.ValidationError({"listing": "Ariza faqat yo'qolgan (LOST) e'longa yuboriladi."})
        if listing.user_id == user.id:
            raise serializers.ValidationError({"listing": "O'z e'loningizga ariza yubora olmaysiz."})
        if listing.status != Listing.Status.ACTIVE:
            raise serializers.ValidationError({"listing": "Bu e'lon hozir ariza qabul qilmaydi."})
        if FoundReport.objects.filter(listing=listing, finder=user,
                                      status__in=["PENDING", "APPROVED"]).exists():
            raise serializers.ValidationError({"listing": "Siz bu e'longa allaqachon ariza yuborgansiz."})
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return FoundReport.objects.create(finder=self.context["request"].user, **validated_data)
        except IntegrityError:
            raise serializers.ValidationError({"listing": "Siz bu e'longa allaqachon ariza yuborgansiz."})


class OwnerFoundReportSerializer(serializers.ModelSerializer):
    """E'lon egasiga: faqat tasdiqlangan arizalar va topuvchi aloqa ma'lumoti."""
    finder = serializers.SerializerMethodField()

    class Meta:
        model = FoundReport
        fields = ("id", "status", "message", "current_place", "contact", "finder", "created_at")

    def get_finder(self, obj) -> dict:
        return {"full_name": obj.finder.full_name, "phone": obj.finder.phone}


class ModerationFoundReportSerializer(serializers.ModelSerializer):
    listing = serializers.SerializerMethodField()
    finder = serializers.SerializerMethodField()

    class Meta:
        model = FoundReport
        fields = ("id", "status", "message", "current_place", "contact", "review_note",
                  "created_at", "listing", "finder")

    def get_listing(self, obj) -> dict:
        return ListingSerializer(obj.listing, context=self.context).data

    def get_finder(self, obj) -> dict:
        u = obj.finder
        return {"id": u.id, "username": u.username, "full_name": u.full_name,
                "phone": u.phone, "email": u.email}