import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Delivery(models.Model):
    """A job posted by a vendor (or another project) for a rider to accept and complete."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        ACCEPTED = "accepted", "Accepted"
        PICKED_UP = "picked_up", "Picked up"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_deliveries",
    )
    client_app = models.ForeignKey(
        "integrations.ClientApp",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="deliveries",
    )
    rider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_deliveries",
    )
    external_reference = models.CharField(
        max_length=100, blank=True, help_text="The calling project's own order id."
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.POSTED)

    pickup_address = models.CharField(max_length=255)
    pickup_contact_name = models.CharField(max_length=100, blank=True)
    pickup_phone = models.CharField(max_length=32, blank=True)
    dropoff_address = models.CharField(max_length=255)
    dropoff_contact_name = models.CharField(max_length=100, blank=True)
    dropoff_phone = models.CharField(max_length=32, blank=True)
    item_description = models.CharField(max_length=255, blank=True)

    fee = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    currency = models.CharField(max_length=3, default="USD")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(vendor__isnull=False) | Q(client_app__isnull=False),
                name="delivery_has_an_owner",
            ),
            models.UniqueConstraint(
                fields=["client_app", "external_reference"],
                condition=~Q(external_reference=""),
                name="unique_external_reference_per_client_app",
            ),
        ]

    def __str__(self):
        return f"Delivery {self.pk} ({self.status})"


class DeliveryEvent(models.Model):
    """Append-only audit trail of every status change."""

    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name="events")
    status_from = models.CharField(max_length=12, blank=True)
    status_to = models.CharField(max_length=12)
    actor = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.delivery_id}: {self.status_from or '-'} -> {self.status_to}"
