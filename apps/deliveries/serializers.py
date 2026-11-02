from rest_framework import serializers

from .models import Delivery

# Riders only see where to drop off, and who to call, once the delivery is theirs.
HIDDEN_FROM_UNASSIGNED_RIDERS = ("dropoff_contact_name", "dropoff_phone")


class DeliverySerializer(serializers.ModelSerializer):
    """Read-only representation of a delivery."""

    class Meta:
        model = Delivery
        fields = (
            "id",
            "external_reference",
            "status",
            "vendor",
            "client_app",
            "rider",
            "pickup_address",
            "pickup_contact_name",
            "pickup_phone",
            "dropoff_address",
            "dropoff_contact_name",
            "dropoff_phone",
            "item_description",
            "fee",
            "currency",
            "created_at",
            "updated_at",
            "accepted_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = getattr(self.context.get("request"), "user", None)
        if getattr(user, "role", None) == "rider" and instance.rider_id != user.pk:
            for field in HIDDEN_FROM_UNASSIGNED_RIDERS:
                data.pop(field, None)
        return data


class DeliveryCreateSerializer(serializers.ModelSerializer):
    """Validates the payload for posting a new delivery."""

    class Meta:
        model = Delivery
        fields = (
            "external_reference",
            "pickup_address",
            "pickup_contact_name",
            "pickup_phone",
            "dropoff_address",
            "dropoff_contact_name",
            "dropoff_phone",
            "item_description",
            "fee",
            "currency",
        )

    def validate_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a 3-letter currency code, e.g. USD.")
        return value
