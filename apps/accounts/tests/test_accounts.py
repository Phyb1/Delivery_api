import pytest
from django.urls import reverse

from apps.accounts.models import User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def register_payload(**overrides):
    return {
        "username": "newuser",
        "password": "Tr1cky-horse-staple",
        "email": "new@example.com",
        "role": "vendor",
        "phone": "+263771000000",
        **overrides,
    }


class TestRegister:
    @pytest.mark.parametrize("role", ["vendor", "rider"])
    def test_register_returns_user_and_token(self, api_client, role):
        response = api_client.post(reverse("register"), register_payload(role=role), format="json")

        assert response.status_code == 201
        assert response.data["user"]["role"] == role
        assert response.data["token"]
        assert "password" not in response.data["user"]

    def test_admin_role_cannot_be_self_assigned(self, api_client):
        response = api_client.post(
            reverse("register"), register_payload(role="admin"), format="json"
        )

        assert response.status_code == 400
        assert not User.objects.filter(username="newuser").exists()

    def test_weak_password_is_rejected(self, api_client):
        response = api_client.post(
            reverse("register"), register_payload(password="password"), format="json"
        )

        assert response.status_code == 400
        assert "password" in response.data

    def test_duplicate_username_is_rejected(self, api_client, vendor):
        response = api_client.post(
            reverse("register"), register_payload(username=vendor.username), format="json"
        )

        assert response.status_code == 400

    def test_password_is_hashed(self, api_client):
        api_client.post(reverse("register"), register_payload(), format="json")

        user = User.objects.get(username="newuser")
        assert user.password != "Tr1cky-horse-staple"
        assert user.check_password("Tr1cky-horse-staple")


class TestLogin:
    def test_valid_credentials_return_token(self, api_client, vendor):
        response = api_client.post(
            reverse("token"), {"username": vendor.username, "password": PASSWORD}, format="json"
        )

        assert response.status_code == 200
        assert response.data["token"]

    def test_wrong_password_is_rejected(self, api_client, vendor):
        response = api_client.post(
            reverse("token"), {"username": vendor.username, "password": "nope"}, format="json"
        )

        assert response.status_code == 400

    def test_token_authenticates_requests(self, api_client, vendor):
        token = api_client.post(
            reverse("token"), {"username": vendor.username, "password": PASSWORD}, format="json"
        ).data["token"]

        response = api_client.get(reverse("me"), HTTP_AUTHORIZATION=f"Token {token}")

        assert response.status_code == 200
        assert response.data["username"] == vendor.username


class TestMe:
    def test_requires_authentication(self, api_client):
        assert api_client.get(reverse("me")).status_code == 401

    def test_client_app_key_is_not_a_user(self, api_client, client_app_with_key):
        _, raw_key = client_app_with_key

        response = api_client.get(reverse("me"), HTTP_X_API_KEY=raw_key)

        assert response.status_code == 403


class TestSuperuser:
    def test_superuser_gets_admin_role(self, db):
        user = User.objects.create_superuser(username="root", password=PASSWORD)

        assert user.role == "admin"
        assert user.is_superuser
