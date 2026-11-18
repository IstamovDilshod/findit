from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "username", "full_name", "email", "phone", "password")

    def validate_phone(self, value):
        return value or None

    def create(self, validated_data):
        # Rol har doim USER; moderator/adminni faqat admin tayinlaydi
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "full_name", "phone", "role")
        read_only_fields = ("id", "username", "role")

    def validate_phone(self, value):
        return value or None

class AdminUserSerializer(serializers.ModelSerializer):
    listings_count = serializers.IntegerField(read_only=True)
    claims_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "full_name", "email", "phone", "role", "is_active",
                  "date_joined", "listings_count", "claims_count")
        # Admin faqat rol va faollik (bloklash) maydonlarini o'zgartira oladi
        read_only_fields = ("id", "username", "full_name", "email", "phone", "date_joined")

class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(attrs["uid"])), is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"token": "Havola noto'g'ri yoki eskirgan."})
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Havola noto'g'ri yoki eskirgan."})
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Joriy parol noto'g'ri.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value