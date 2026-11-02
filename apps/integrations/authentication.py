import hmac

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import KEY_PREFIX_LENGTH, ClientApp


class ClientAppAuthentication(BaseAuthentication):
    """Authenticate another project via the ``X-API-Key`` header."""

    header = "HTTP_X_API_KEY"

    def authenticate(self, request):
        raw_key = request.META.get(self.header)
        if not raw_key:
            return None  # let other authenticators try

        try:
            app = ClientApp.objects.get(key_prefix=raw_key[:KEY_PREFIX_LENGTH], is_active=True)
        except ClientApp.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid API key.") from exc

        if not hmac.compare_digest(app.key_hash, ClientApp.hash_key(raw_key)):
            raise AuthenticationFailed("Invalid API key.")
        return (app, raw_key)

    def authenticate_header(self, request):
        return "X-API-Key"
