import pytest
from django.urls import reverse

from apps.deliveries import services

pytestmark = pytest.mark.django_db


def detail_url(name, pk):
    return reverse(f"delivery-{name}", args=[pk])


@pytest.fixture
def list_url():
    return reverse("delivery-list")


class TestCreate:
    def test_vendor_posts_delivery(self, auth_client, vendor, list_url, delivery_data):
        response = auth_client(vendor).post(list_url, delivery_data, format="json")

        assert response.status_code == 201
        assert response.data["status"] == "posted"
        assert response.data["vendor"] == vendor.pk
        assert response.data["fee"] == "3.50"

    def test_rider_cannot_post(self, auth_client, rider, list_url, delivery_data):
        response = auth_client(rider).post(list_url, delivery_data, format="json")

        assert response.status_code == 403

    def test_anonymous_gets_401(self, api_client, list_url, delivery_data):
        response = api_client.post(list_url, delivery_data, format="json")

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("field", "value"),
        [("fee", "-1.00"), ("currency", "US"), ("currency", "U5D"), ("pickup_address", "")],
    )
    def test_invalid_payload_is_rejected(
        self, auth_client, vendor, list_url, delivery_data, field, value
    ):
        delivery_data[field] = value

        response = auth_client(vendor).post(list_url, delivery_data, format="json")

        assert response.status_code == 400
        assert field in response.data

    def test_currency_is_normalised(self, auth_client, vendor, list_url, delivery_data):
        delivery_data["currency"] = "zwg"

        response = auth_client(vendor).post(list_url, delivery_data, format="json")

        assert response.status_code == 201
        assert response.data["currency"] == "ZWG"

    def test_status_cannot_be_set_by_caller(self, auth_client, vendor, list_url, delivery_data):
        delivery_data["status"] = "delivered"

        response = auth_client(vendor).post(list_url, delivery_data, format="json")

        assert response.data["status"] == "posted"


class TestVisibility:
    def test_vendor_sees_only_own_deliveries(
        self, auth_client, vendor, other_vendor, make_delivery, list_url
    ):
        mine = make_delivery()
        make_delivery(vendor=other_vendor)

        response = auth_client(vendor).get(list_url)

        assert [item["id"] for item in response.data["results"]] == [str(mine.pk)]

    def test_rider_sees_posted_and_own_only(
        self, auth_client, rider, other_rider, make_delivery, list_url
    ):
        open_job = make_delivery()
        mine = make_delivery()
        services.accept_delivery(delivery_id=mine.pk, rider=rider)
        taken_by_other = make_delivery()
        services.accept_delivery(delivery_id=taken_by_other.pk, rider=other_rider)

        response = auth_client(rider).get(list_url)

        ids = {item["id"] for item in response.data["results"]}
        assert ids == {str(open_job.pk), str(mine.pk)}

    def test_rider_cannot_see_dropoff_contact_until_assigned(
        self, auth_client, rider, make_delivery
    ):
        delivery = make_delivery()
        client = auth_client(rider)

        before = client.get(detail_url("detail", delivery.pk)).data
        assert "dropoff_phone" not in before
        assert "dropoff_address" in before

        services.accept_delivery(delivery_id=delivery.pk, rider=rider)
        after = client.get(detail_url("detail", delivery.pk)).data
        assert after["dropoff_phone"] == "+263772222222"

    def test_admin_sees_everything(self, auth_client, admin_user, make_delivery, list_url):
        make_delivery()
        make_delivery()

        response = auth_client(admin_user).get(list_url)

        assert response.data["count"] == 2

    def test_status_filter(self, auth_client, vendor, make_delivery, list_url):
        make_delivery()
        cancelled = make_delivery()
        services.cancel_delivery(delivery_id=cancelled.pk, actor=vendor)

        response = auth_client(vendor).get(list_url, {"status": "cancelled"})

        assert [item["id"] for item in response.data["results"]] == [str(cancelled.pk)]

    def test_other_vendors_delivery_is_404(self, auth_client, other_vendor, make_delivery):
        delivery = make_delivery()

        response = auth_client(other_vendor).get(detail_url("detail", delivery.pk))

        assert response.status_code == 404


class TestRiderActions:
    def test_accept_pickup_deliver(self, auth_client, rider, make_delivery):
        delivery = make_delivery()
        client = auth_client(rider)

        accept = client.post(detail_url("accept", delivery.pk))
        pickup = client.post(detail_url("pickup", delivery.pk))
        deliver = client.post(detail_url("deliver", delivery.pk))

        assert accept.status_code == 200
        assert accept.data["rider"] == rider.pk
        assert pickup.data["status"] == "picked_up"
        assert deliver.data["status"] == "delivered"

    def test_second_rider_gets_409(self, auth_client, rider, other_rider, make_delivery):
        delivery = make_delivery()
        auth_client(rider).post(detail_url("accept", delivery.pk))

        response = auth_client(other_rider).post(detail_url("accept", delivery.pk))

        assert response.status_code == 409

    def test_vendor_cannot_accept(self, auth_client, vendor, make_delivery):
        delivery = make_delivery()

        response = auth_client(vendor).post(detail_url("accept", delivery.pk))

        assert response.status_code == 403

    def test_unknown_delivery_is_404(self, auth_client, rider):
        response = auth_client(rider).post(
            detail_url("accept", "11111111-1111-1111-1111-111111111111")
        )

        assert response.status_code == 404

    def test_malformed_id_is_404(self, auth_client, rider):
        response = auth_client(rider).post("/api/v1/deliveries/not-a-uuid/accept/")

        assert response.status_code == 404


class TestCancel:
    def test_vendor_cancels_own_delivery(self, auth_client, vendor, make_delivery):
        delivery = make_delivery()

        response = auth_client(vendor).post(detail_url("cancel", delivery.pk))

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"

    def test_rider_cannot_cancel(self, auth_client, rider, make_delivery):
        delivery = make_delivery()

        response = auth_client(rider).post(detail_url("cancel", delivery.pk))

        assert response.status_code == 403

    def test_cancelled_delivery_cannot_be_accepted(self, auth_client, vendor, rider, make_delivery):
        delivery = make_delivery()
        auth_client(vendor).post(detail_url("cancel", delivery.pk))

        response = auth_client(rider).post(detail_url("accept", delivery.pk))

        assert response.status_code == 409


class TestClientAppApiKey:
    def test_client_app_posts_and_lists_only_its_own(
        self, api_client, client_app_with_key, make_delivery, list_url, delivery_data
    ):
        app, raw_key = client_app_with_key
        make_delivery()  # belongs to a vendor, must stay invisible to the client app

        created = api_client.post(
            list_url,
            {**delivery_data, "external_reference": "ORDER-1"},
            format="json",
            HTTP_X_API_KEY=raw_key,
        )
        listed = api_client.get(list_url, HTTP_X_API_KEY=raw_key)

        assert created.status_code == 201
        assert created.data["client_app"] == app.pk
        assert created.data["vendor"] is None
        assert listed.data["count"] == 1

    def test_duplicate_external_reference_returns_409(
        self, api_client, client_app_with_key, list_url, delivery_data
    ):
        _, raw_key = client_app_with_key
        payload = {**delivery_data, "external_reference": "ORDER-1"}
        api_client.post(list_url, payload, format="json", HTTP_X_API_KEY=raw_key)

        response = api_client.post(list_url, payload, format="json", HTTP_X_API_KEY=raw_key)

        assert response.status_code == 409

    def test_invalid_key_is_rejected(self, api_client, list_url):
        response = api_client.get(list_url, HTTP_X_API_KEY="dk_not-a-real-key-at-all")

        assert response.status_code == 401

    def test_wrong_secret_with_valid_prefix_is_rejected(
        self, api_client, client_app_with_key, list_url
    ):
        _, raw_key = client_app_with_key

        response = api_client.get(list_url, HTTP_X_API_KEY=raw_key[:11] + "x" * 30)

        assert response.status_code == 401

    def test_inactive_client_app_is_rejected(self, api_client, client_app_with_key, list_url):
        app, raw_key = client_app_with_key
        app.is_active = False
        app.save()

        response = api_client.get(list_url, HTTP_X_API_KEY=raw_key)

        assert response.status_code == 401

    def test_client_app_can_cancel_its_delivery(
        self, api_client, client_app_with_key, list_url, delivery_data
    ):
        _, raw_key = client_app_with_key
        created = api_client.post(list_url, delivery_data, format="json", HTTP_X_API_KEY=raw_key)

        response = api_client.post(detail_url("cancel", created.data["id"]), HTTP_X_API_KEY=raw_key)

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"


def test_health_endpoint(api_client):
    response = api_client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
