import hashlib
import secrets

from django.db import models
from django.utils import timezone

KEY_PREFIX = "dk_"
KEY_PREFIX_LENGTH = 11  # "dk_" + 8 characters; used to look a key up without storing it


class ClientApp(models.Model):
    """Another project (shop, ordering site...) that plugs into this API.

    It authenticates with an API key sent in the ``X-API-Key`` header. Only a hash of
    the key is stored, so the raw key is shown once when it is issued.
    """

    name = models.CharField(max_length=100, unique=True)
    key_prefix = models.CharField(max_length=KEY_PREFIX_LENGTH, unique=True, editable=False)
    key_hash = models.CharField(max_length=64, editable=False)
    webhook_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=64, blank=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # DRF accepts any object with these attributes as an authenticated principal, and
    # ``role`` lets permission code treat users and client apps uniformly.
    role = "client_app"
    is_authenticated = True
    is_anonymous = False

    def __str__(self):
        return self.name

    @staticmethod
    def hash_key(raw_key):
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def issue(cls, *, name, webhook_url=""):
        """Create a client app and return ``(app, raw_key)``. The raw key is not stored."""
        raw_key = f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"
        app = cls.objects.create(
            name=name,
            key_prefix=raw_key[:KEY_PREFIX_LENGTH],
            key_hash=cls.hash_key(raw_key),
            webhook_url=webhook_url,
            webhook_secret=secrets.token_hex(32),
        )
        return app, raw_key


class WebhookEvent(models.Model):
    """Outbox row: a notification waiting to be (re)sent to a client app."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    client_app = models.ForeignKey(
        ClientApp, on_delete=models.CASCADE, related_name="webhook_events"
    )
    delivery_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self):
        return f"{self.event_type} -> {self.client_app} ({self.status})"
