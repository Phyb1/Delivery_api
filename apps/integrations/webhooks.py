"""Outbound webhooks using a database outbox.

Deliveries enqueue a ``WebhookEvent`` inside the same transaction as the state change, so a
notification is never lost. ``process_pending`` (run by the ``send_webhooks`` command, cron or
a scheduled AWS job) sends due events, signs them, and retries with exponential backoff.
"""

import hashlib
import hmac
import json
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from .models import WebhookEvent

SIGNATURE_HEADER = "X-Webhook-Signature"
EVENT_HEADER = "X-Webhook-Event"
BACKOFF_BASE_SECONDS = 30


def sign(secret, body):
    """HMAC-SHA256 hex digest receivers use to verify a webhook came from us."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_body(event):
    document = {
        "id": event.pk,
        "type": event.event_type,
        "created_at": event.created_at.isoformat(),
        "data": event.payload,
    }
    return json.dumps(document, separators=(",", ":"), sort_keys=True).encode()


def default_sender(url, body, headers, timeout):
    """POST ``body`` and return the HTTP status code. Network errors raise OSError."""
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Unsupported webhook URL scheme.")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status


def enqueue_event(*, client_app, delivery_id, event_type, payload):
    """Queue a notification. Returns ``None`` when the client has no webhook configured."""
    if not client_app.webhook_url:
        return None
    return WebhookEvent.objects.create(
        client_app=client_app,
        delivery_id=delivery_id,
        event_type=event_type,
        payload=payload,
    )


def dispatch_event(event, *, sender=None):
    """Attempt one send. Returns True on success; updates the outbox row either way."""
    sender = sender or default_sender
    app = event.client_app
    body = build_body(event)
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign(app.webhook_secret, body),
        EVENT_HEADER: event.event_type,
    }

    event.attempts += 1
    try:
        status_code = sender(app.webhook_url, body, headers, settings.WEBHOOK_TIMEOUT_SECONDS)
        succeeded = 200 <= status_code < 300
        error = "" if succeeded else f"HTTP {status_code}"
    except (OSError, ValueError) as exc:
        succeeded = False
        error = str(exc)[:500]

    now = timezone.now()
    if succeeded:
        event.status = WebhookEvent.Status.SENT
        event.sent_at = now
    elif event.attempts >= settings.WEBHOOK_MAX_ATTEMPTS:
        event.status = WebhookEvent.Status.FAILED
    else:
        delay = BACKOFF_BASE_SECONDS * 2 ** (event.attempts - 1)
        event.next_attempt_at = now + timedelta(seconds=delay)
    event.last_error = error
    event.save(update_fields=["attempts", "status", "sent_at", "next_attempt_at", "last_error"])
    return succeeded


def process_pending(*, limit=100, sender=None):
    """Send every due pending event. Returns the number sent successfully."""
    due = WebhookEvent.objects.select_related("client_app").filter(
        status=WebhookEvent.Status.PENDING, next_attempt_at__lte=timezone.now()
    )[:limit]
    return sum(1 for event in due if dispatch_event(event, sender=sender))
