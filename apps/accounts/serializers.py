from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "phone")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Self-registration. Admin accounts can never be created through the API."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    role = serializers.ChoiceField(
        choices=[(User.Role.VENDOR.value, "Vendor"), (User.Role.RIDER.value, "Rider")]
    )

    class Meta:
        model = User
        fields = ("username", "password", "email", "role", "phone")

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
