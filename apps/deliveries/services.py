"""Business rules for deliveries.

Views stay thin: every state change goes through a function here, which owns the state
machine, the row locking, the audit trail and the webhook notifications.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.accounts.models import User
from apps.integrations.webhooks import enqueue_event

from .exceptions import DeliveryConflict
from .models import Delivery, DeliveryEvent

# Plain strings keep comparisons independent of enum internals.
POSTED = Delivery.Status.POSTED.value
ACCEPTED = Delivery.Status.ACCEPTED.value
PICKED_UP = Delivery.Status.PICKED_UP.value
DELIVERED = Delivery.Status.DELIVERED.value
CANCELLED = Delivery.Status.CANCELLED.value

VENDOR = User.Role.VENDOR.value
RIDER = User.Role.RIDER.value
ADMIN = User.Role.ADMIN.value
CLIENT_APP = "client_app"

TRANSITIONS = {
    POSTED: {ACCEPTED, CANCELLED},
    ACCEPTED: {PICKED_UP, CANCELLED},
    PICKED_UP: {DELIVERED},
    DELIVERED: set(),
    CANCELLED: set(),
}
TIMESTAMP_FIELDS = {
    ACCEPTED: "accepted_at",
    PICKED_UP: "picked_up_at",
    DELIVERED: "delivered_at",
    CANCELLED: "cancelled_at",
}
ACTIVE_RIDER_STATUSES = (ACCEPTED, PICKED_UP)


# --- helpers --------------------------------------------------------------
def _require_role(actor, *roles):
    if getattr(actor, "role", None) not in roles:
        raise PermissionDenied("Your account is not allowed to do this.")


def _actor_label(actor):
    name = getattr(actor, "username", None) or getattr(actor, "name", "")
    return f"{actor.role}:{name}"


def _iso(value):
    return value.isoformat() if value else None


def build_payload(delivery):
    """The JSON snapshot sent to client apps in webhooks."""
    return {
        "id": str(delivery.pk),
        "external_reference": delivery.external_reference,
        "status": str(delivery.status),
        "rider": delivery.rider.username if delivery.rider_id else None,
        "fee": str(delivery.fee),
        "currency": delivery.currency,
        "accepted_at": _iso(delivery.accepted_at),
        "picked_up_at": _iso(delivery.picked_up_at),
        "delivered_at": _iso(delivery.delivered_at),
        "cancelled_at": _iso(delivery.cancelled_at),
    }


def _record(delivery, *, from_status, to_status, actor):
    DeliveryEvent.objects.create(
        delivery=delivery,
        status_from=from_status,
        status_to=to_status,
        actor=_actor_label(actor),
    )
    if delivery.client_app_id:
        enqueue_event(
            client_app=delivery.client_app,
            delivery_id=delivery.pk,
            event_type=f"delivery.{to_status}",
            payload=build_payload(delivery),
        )


def _lock(delivery_id):
    """Fetch a delivery and lock its row until the surrounding transaction ends.

    ``of=("self",)`` is required on PostgreSQL because select_related joins nullable
    foreign keys, which cannot be locked. SQLite (used in tests) ignores row locks.
    """
    try:
        return (
            Delivery.objects.select_for_update(of=("self",))
            .select_related("client_app", "rider")
            .get(pk=delivery_id)
        )
    except Delivery.DoesNotExist as exc:
        raise NotFound("Delivery not found.") from exc


def _transition(delivery, to_status, *, actor, **changes):
    """The single place where a delivery changes status."""
    from_status = delivery.status
    if to_status not in TRANSITIONS[from_status]:
        raise DeliveryConflict(f"Cannot change a delivery from '{from_status}' to '{to_status}'.")

    timestamp_field = TIMESTAMP_FIELDS[to_status]
    delivery.status = to_status
    setattr(delivery, timestamp_field, timezone.now())
    for name, value in changes.items():
        setattr(delivery, name, value)

    delivery.save(update_fields=["status", timestamp_field, "updated_at", *changes])
    _record(delivery, from_status=from_status, to_status=to_status, actor=actor)
    return delivery


def _owns(delivery, actor):
    if actor.role == CLIENT_APP:
        return delivery.client_app_id == actor.pk
    return delivery.vendor_id == actor.pk


# --- use cases ------------------------------------------------------------
def create_delivery(*, owner, **fields):
    """Post a new delivery on behalf of a vendor or a client app."""
    _require_role(owner, VENDOR, CLIENT_APP)
    fields["client_app" if owner.role == CLIENT_APP else "vendor"] = owner

    try:
        with transaction.atomic():
            delivery = Delivery.objects.create(**fields)
            _record(delivery, from_status="", to_status=str(delivery.status), actor=owner)
    except IntegrityError as exc:
        raise DeliveryConflict("A delivery with this external reference already exists.") from exc
    return delivery


@transaction.atomic
def accept_delivery(*, delivery_id, rider):
    """A rider claims a posted delivery. Exactly one rider can win a race for it."""
    _require_role(rider, RIDER)
    # Serialise concurrent accepts by the same rider so the active-delivery cap holds.
    User.objects.select_for_update().get(pk=rider.pk)
    delivery = _lock(delivery_id)

    if delivery.status != POSTED:
        raise DeliveryConflict("This delivery is no longer available.")

    active = Delivery.objects.filter(rider=rider, status__in=ACTIVE_RIDER_STATUSES).count()
    if active >= settings.DELIVERY_MAX_ACTIVE_PER_RIDER:
        raise DeliveryConflict("You already have the maximum number of active deliveries.")

    return _transition(delivery, ACCEPTED, actor=rider, rider=rider)


@transaction.atomic
def _advance_as_assigned_rider(delivery_id, rider, to_status):
    _require_role(rider, RIDER)
    delivery = _lock(delivery_id)
    if delivery.rider_id != rider.pk:
        raise PermissionDenied("This delivery is not assigned to you.")
    return _transition(delivery, to_status, actor=rider)


def mark_picked_up(*, delivery_id, rider):
    return _advance_as_assigned_rider(delivery_id, rider, PICKED_UP)


def mark_delivered(*, delivery_id, rider):
    return _advance_as_assigned_rider(delivery_id, rider, DELIVERED)


@transaction.atomic
def cancel_delivery(*, delivery_id, actor):
    """The owner (or an admin) cancels a delivery that has not been picked up yet."""
    _require_role(actor, VENDOR, CLIENT_APP, ADMIN)
    delivery = _lock(delivery_id)
    if actor.role != ADMIN and not _owns(delivery, actor):
        raise PermissionDenied("You can only cancel your own deliveries.")
    return _transition(delivery, CANCELLED, actor=actor)
