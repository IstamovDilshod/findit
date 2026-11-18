from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)
    list_display = ("username", "full_name", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("username", "full_name", "email", "phone")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Ma'lumotlar", {"fields": ("full_name", "email", "phone", "role", "is_active")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "full_name", "role", "password1", "password2")}),
    )
    # Bloklash: "is_active" ni o'chirish yetarli