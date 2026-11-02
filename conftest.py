"""Shared pytest fixtures."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.deliveries.models import Delivery
from apps.integrations.models import ClientApp

PASSWORD = "S7r0ng-Passw0rd!x"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client():
    """Factory returning an APIClient authenticated as the given user (or client app)."""

    def _make(principal):
        client = APIClient()
        client.force_authenticate(user=principal)
        return client

    return _make


def _create_user(username, role):
    return User.objects.create_user(
        username=username, password=PASSWORD, role=role, phone="+263771000000"
    )


@pytest.fixture
def vendor(db):
    return _create_user("vendor1", User.Role.VENDOR)


@pytest.fixture
def other_vendor(db):
    return _create_user("vendor2", User.Role.VENDOR)


@pytest.fixture
def rider(db):
    return _create_user("rider1", User.Role.RIDER)


@pytest.fixture
def other_rider(db):
    return _create_user("rider2", User.Role.RIDER)


@pytest.fixture
def admin_user(db):
    return _create_user("admin1", User.Role.ADMIN)


@pytest.fixture
def client_app_with_key(db):
    """A client app with a webhook, plus its raw API key."""
    return ClientApp.issue(name="Demo Shop", webhook_url="https://shop.example.com/hooks")


@pytest.fixture
def client_app(client_app_with_key):
    return client_app_with_key[0]


@pytest.fixture
def delivery_data():
    """A valid payload for posting a delivery."""
    return {
        "pickup_address": "12 Main Street, Mvurwi",
        "pickup_contact_name": "Tendai",
        "pickup_phone": "+263771111111",
        "dropoff_address": "4 Church Road, Mvurwi",
        "dropoff_contact_name": "Rudo",
        "dropoff_phone": "+263772222222",
        "item_description": "Two boxes",
        "fee": "3.50",
        "currency": "USD",
    }


@pytest.fixture
def make_delivery(vendor, delivery_data):
    """Factory creating a delivery directly in the database (bypasses services)."""

    def _make(**overrides):
        fields = {**delivery_data, "fee": Decimal("3.50"), "vendor": vendor, **overrides}
        return Delivery.objects.create(**fields)

    return _make
