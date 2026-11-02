import uuid

import pytest
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.deliveries import services
from apps.deliveries.exceptions import DeliveryConflict
from apps.deliveries.models import Delivery
from apps.integrations.models import WebhookEvent

pytestmark = pytest.mark.django_db


def statuses(delivery):
    return list(delivery.events.values_list("status_to", flat=True))


class TestCreate:
    def test_vendor_creates_posted_delivery(self, vendor, delivery_data):
        delivery = services.create_delivery(owner=vendor, **delivery_data)

        assert delivery.status == "posted"
        assert delivery.vendor == vendor
        assert delivery.client_app is None
        assert statuses(delivery) == ["posted"]
        assert WebhookEvent.objects.count() == 0

    def test_client_app_delivery_queues_webhook(self, client_app, delivery_data):
        delivery = services.create_delivery(owner=client_app, **delivery_data)

        assert delivery.client_app == client_app
        assert delivery.vendor is None
        event = WebhookEvent.objects.get(delivery_id=delivery.pk)
        assert event.event_type == "delivery.posted"
        assert event.payload["status"] == "posted"

    def test_duplicate_external_reference_conflicts(self, client_app, delivery_data):
        services.create_delivery(owner=client_app, external_reference="A-1", **delivery_data)

        with pytest.raises(DeliveryConflict):
            services.create_delivery(owner=client_app, external_reference="A-1", **delivery_data)
        assert Delivery.objects.count() == 1

    def test_rider_cannot_create(self, rider, delivery_data):
        with pytest.raises(PermissionDenied):
            services.create_delivery(owner=rider, **delivery_data)


class TestAccept:
    def test_rider_accepts_posted_delivery(self, rider, make_delivery):
        delivery = make_delivery()

        accepted = services.accept_delivery(delivery_id=delivery.pk, rider=rider)

        assert accepted.status == "accepted"
        assert accepted.rider == rider
        assert accepted.accepted_at is not None

    def test_only_one_rider_wins(self, rider, other_rider, make_delivery):
        delivery = make_delivery()
        services.accept_delivery(delivery_id=delivery.pk, rider=rider)

        with pytest.raises(DeliveryConflict):
            services.accept_delivery(delivery_id=delivery.pk, rider=other_rider)

        delivery.refresh_from_db()
        assert delivery.rider == rider

    def test_non_rider_cannot_accept(self, vendor, make_delivery):
        delivery = make_delivery()

        with pytest.raises(PermissionDenied):
            services.accept_delivery(delivery_id=delivery.pk, rider=vendor)

    def test_active_delivery_cap(self, rider, make_delivery, settings):
        settings.DELIVERY_MAX_ACTIVE_PER_RIDER = 1
        first, second = make_delivery(), make_delivery()
        services.accept_delivery(delivery_id=first.pk, rider=rider)

        with pytest.raises(DeliveryConflict):
            services.accept_delivery(delivery_id=second.pk, rider=rider)

    def test_unknown_delivery(self, rider):
        with pytest.raises(NotFound):
            services.accept_delivery(delivery_id=uuid.uuid4(), rider=rider)


class TestLifecycle:
    def test_full_happy_path(self, vendor, rider, delivery_data):
        delivery = services.create_delivery(owner=vendor, **delivery_data)

        services.accept_delivery(delivery_id=delivery.pk, rider=rider)
        services.mark_picked_up(delivery_id=delivery.pk, rider=rider)
        done = services.mark_delivered(delivery_id=delivery.pk, rider=rider)

        assert done.status == "delivered"
        assert done.picked_up_at is not None
        assert done.delivered_at is not None
        assert statuses(delivery) == ["posted", "accepted", "picked_up", "delivered"]

    def test_cannot_deliver_before_pickup(self, rider, make_delivery):
        delivery = make_delivery()
        services.accept_delivery(delivery_id=delivery.pk, rider=rider)

        with pytest.raises(DeliveryConflict):
            services.mark_delivered(delivery_id=delivery.pk, rider=rider)

    def test_other_rider_cannot_advance(self, rider, other_rider, make_delivery):
        delivery = make_delivery()
        services.accept_delivery(delivery_id=delivery.pk, rider=rider)

        with pytest.raises(PermissionDenied):
            services.mark_picked_up(delivery_id=delivery.pk, rider=other_rider)

    def test_client_app_gets_a_webhook_for_each_step(self, client_app, rider, delivery_data):
        delivery = services.create_delivery(owner=client_app, **delivery_data)
        services.accept_delivery(delivery_id=delivery.pk, rider=rider)

        event_types = list(
            WebhookEvent.objects.filter(delivery_id=delivery.pk).values_list(
                "event_type", flat=True
            )
        )
        assert event_types == ["delivery.posted", "delivery.accepted"]


class TestCancel:
    def test_owner_cancels_posted_delivery(self, vendor, make_delivery):
        delivery = make_delivery()

        cancelled = services.cancel_delivery(delivery_id=delivery.pk, actor=vendor)

        assert cancelled.status == "cancelled"
        assert cancelled.cancelled_at is not None

    def test_owner_cancels_after_acceptance(self, vendor, rider, make_delivery):
        delivery = make_delivery()
        services.accept_delivery(delivery_id=delivery.pk, rider=rider)

        cancelled = services.cancel_delivery(delivery_id=delivery.pk, actor=vendor)

        assert cancelled.status == "cancelled"

    def test_cannot_cancel_after_pickup(self, vendor, rider, make_delivery):
        delivery = make_delivery()
        services.accept_delivery(delivery_id=delivery.pk, rider=rider)
        services.mark_picked_up(delivery_id=delivery.pk, rider=rider)

        with pytest.raises(DeliveryConflict):
            services.cancel_delivery(delivery_id=delivery.pk, actor=vendor)

    def test_other_vendor_cannot_cancel(self, other_vendor, make_delivery):
        delivery = make_delivery()

        with pytest.raises(PermissionDenied):
            services.cancel_delivery(delivery_id=delivery.pk, actor=other_vendor)

    def test_admin_can_cancel_any_delivery(self, admin_user, make_delivery):
        delivery = make_delivery()

        cancelled = services.cancel_delivery(delivery_id=delivery.pk, actor=admin_user)

        assert cancelled.status == "cancelled"

    def test_client_app_cancels_only_its_own(self, client_app, delivery_data, make_delivery):
        own = services.create_delivery(owner=client_app, **delivery_data)
        someone_elses = make_delivery()

        services.cancel_delivery(delivery_id=own.pk, actor=client_app)
        with pytest.raises(PermissionDenied):
            services.cancel_delivery(delivery_id=someone_elses.pk, actor=client_app)
