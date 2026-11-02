import hmac
import re
import uuid
from datetime import timedelta
from hashlib import sha256
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from apps.integrations import webhooks
from apps.integrations.models import ClientApp, WebhookEvent

pytestmark = pytest.mark.django_db


def queue_event(app, **overrides):
    return webhooks.enqueue_event(
        client_app=app,
        delivery_id=overrides.pop("delivery_id", uuid.uuid4()),
        event_type="delivery.posted",
        payload={"status": "posted"},
    )


class TestClientApp:
    def test_raw_key_is_not_stored(self):
        app, raw_key = ClientApp.issue(name="Acme")

        assert raw_key.startswith("dk_")
        assert raw_key not in (app.key_hash, app.key_prefix)
        assert app.key_hash == sha256(raw_key.encode()).hexdigest()
        assert raw_key.startswith(app.key_prefix)

    def test_each_app_gets_a_unique_key_and_secret(self):
        first, first_key = ClientApp.issue(name="One")
        second, second_key = ClientApp.issue(name="Two")

        assert first_key != second_key
        assert first.webhook_secret != second.webhook_secret

    def test_principal_attributes(self, client_app):
        assert client_app.is_authenticated is True
        assert client_app.role == "client_app"


class TestWebhookQueue:
    def test_no_event_without_webhook_url(self):
        app, _ = ClientApp.issue(name="No Hook")

        assert queue_event(app) is None
        assert WebhookEvent.objects.count() == 0

    def test_event_is_queued_with_webhook_url(self, client_app):
        event = queue_event(client_app)

        assert event.status == "pending"
        assert event.attempts == 0


class TestDispatch:
    def test_success_marks_event_sent_and_signs_body(self, client_app):
        event = queue_event(client_app)
        sender = Mock(return_value=200)

        assert webhooks.dispatch_event(event, sender=sender) is True

        event.refresh_from_db()
        assert event.status == "sent"
        assert event.attempts == 1
        assert event.sent_at is not None
        url, body, headers, _timeout = sender.call_args.args
        assert url == client_app.webhook_url
        expected = hmac.new(client_app.webhook_secret.encode(), body, sha256).hexdigest()
        assert headers[webhooks.SIGNATURE_HEADER] == expected
        assert headers[webhooks.EVENT_HEADER] == "delivery.posted"

    def test_http_error_schedules_a_retry_with_backoff(self, client_app):
        event = queue_event(client_app)

        assert webhooks.dispatch_event(event, sender=Mock(return_value=500)) is False

        event.refresh_from_db()
        assert event.status == "pending"
        assert event.last_error == "HTTP 500"
        assert event.next_attempt_at > timezone.now() + timedelta(seconds=20)

    def test_network_error_is_recorded(self, client_app):
        event = queue_event(client_app)

        webhooks.dispatch_event(event, sender=Mock(side_effect=OSError("connection refused")))

        event.refresh_from_db()
        assert event.status == "pending"
        assert "connection refused" in event.last_error

    def test_gives_up_after_max_attempts(self, client_app, settings):
        settings.WEBHOOK_MAX_ATTEMPTS = 2
        event = queue_event(client_app)
        sender = Mock(return_value=500)

        webhooks.dispatch_event(event, sender=sender)
        webhooks.dispatch_event(event, sender=sender)

        event.refresh_from_db()
        assert event.status == "failed"
        assert event.attempts == 2

    def test_default_sender_rejects_non_http_urls(self):
        with pytest.raises(ValueError, match="scheme"):
            webhooks.default_sender("file:///etc/passwd", b"{}", {}, 1)


class TestProcessPending:
    def test_only_due_pending_events_are_sent(self, client_app):
        due = queue_event(client_app)
        later = queue_event(client_app)
        later.next_attempt_at = timezone.now() + timedelta(hours=1)
        later.save()
        sender = Mock(return_value=200)

        sent = webhooks.process_pending(sender=sender)

        assert sent == 1
        due.refresh_from_db()
        later.refresh_from_db()
        assert (due.status, later.status) == ("sent", "pending")

    def test_command_sends_pending_events(self, client_app, monkeypatch):
        event = queue_event(client_app)
        monkeypatch.setattr(webhooks, "default_sender", lambda *args: 200)
        out = StringIO()

        call_command("send_webhooks", stdout=out)

        event.refresh_from_db()
        assert event.status == "sent"
        assert "Sent 1" in out.getvalue()


class TestCreateClientAppCommand:
    def test_prints_a_working_key_once(self, api_client):
        out = StringIO()

        call_command(
            "create_client_app", "Acme", "--webhook-url", "https://acme.test/h", stdout=out
        )

        raw_key = re.search(r"dk_[\w-]+", out.getvalue()).group(0)
        app = ClientApp.objects.get(name="Acme")
        assert app.webhook_url == "https://acme.test/h"
        assert raw_key not in app.key_hash
        response = api_client.get(reverse("delivery-list"), HTTP_X_API_KEY=raw_key)
        assert response.status_code == 200

    def test_duplicate_name_is_an_error(self):
        call_command("create_client_app", "Acme", stdout=StringIO())

        with pytest.raises(CommandError):
            call_command("create_client_app", "Acme", stdout=StringIO())
