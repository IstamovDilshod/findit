from django.contrib import admin, messages

from .matching import run_matching
from .models import Category, Claim, FoundReport, Listing, Location, Match

class ModeratorMixin:
    """Moderator va admin ko'ra/o'zgartira oladi; o'chirish faqat admin."""

    def _ok(self, request):
        return request.user.is_active and getattr(request.user, "is_moderator", False)

    def has_module_permission(self, request):
        return self._ok(request)

    def has_view_permission(self, request, obj=None):
        return self._ok(request)

    def has_change_permission(self, request, obj=None):
        return self._ok(request)

    def has_add_permission(self, request):
        return False  # e'lon va da'volar faqat API orqali yaratiladi

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.role == "ADMIN"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "city", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("name",)


@admin.register(Listing)
class ListingAdmin(ModeratorMixin, admin.ModelAdmin):
    list_display = ("id", "type", "title", "category", "status", "user", "event_date", "created_at")
    list_filter = ("status", "type", "category")
    search_fields = ("title", "description", "user__username")
    readonly_fields = ("user", "type", "created_at", "closed_at")
    actions = ["approve_listings"]

    @admin.action(description="Tanlangan e'lonlarni tasdiqlash")
    def approve_listings(self, request, queryset):
        count = 0
        for listing in queryset.filter(status=Listing.Status.PENDING):
            listing.status = Listing.Status.ACTIVE
            listing.save()
            run_matching(listing)
            count += 1
        self.message_user(request, f"{count} ta e'lon tasdiqlandi.", messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        was_pending = change and "status" in form.changed_data and form.initial.get("status") == Listing.Status.PENDING
        super().save_model(request, obj, form, change)
        if was_pending and obj.status == Listing.Status.ACTIVE:
            run_matching(obj)  # formadan tasdiqlanganda ham matching ishlaydi


@admin.register(Claim)
class ClaimAdmin(ModeratorMixin, admin.ModelAdmin):
    list_display = ("id", "listing", "claimant", "status", "created_at")
    list_filter = ("status",)
    fields = ("listing", "claimant", "proof_text", "listing_secret", "match",
              "review_note", "status", "reviewed_by", "reviewed_at", "created_at")
    readonly_fields = ("listing", "claimant", "proof_text", "listing_secret", "match",
                       "status", "reviewed_by", "reviewed_at", "created_at")
    actions = ["approve_claims", "reject_claims"]

    @admin.display(description="Topuvchi yozgan yashirin belgi")
    def listing_secret(self, obj):
        return obj.listing.secret_detail or "-"

    @admin.action(description="Da'voni tasdiqlash (buyum egasiga topshirildi)")
    def approve_claims(self, request, queryset):
        count = 0
        for claim in queryset.filter(status=Claim.Status.PENDING):
            claim.approve(request.user)
            count += 1
        self.message_user(request, f"{count} ta da'vo tasdiqlandi, e'lonlar yopildi.", messages.SUCCESS)

    @admin.action(description="Da'voni rad etish")
    def reject_claims(self, request, queryset):
        count = 0
        for claim in queryset.filter(status=Claim.Status.PENDING):
            claim.reject(request.user)
            count += 1
        self.message_user(request, f"{count} ta da'vo rad etildi.", messages.WARNING)


@admin.register(Match)
class MatchAdmin(ModeratorMixin, admin.ModelAdmin):
    list_display = ("id", "lost_listing", "found_listing", "score", "status")
    list_filter = ("status",)


@admin.register(FoundReport)
class FoundReportAdmin(ModeratorMixin, admin.ModelAdmin):
    list_display = ("id", "listing", "finder", "status", "created_at")
    list_filter = ("status",)
