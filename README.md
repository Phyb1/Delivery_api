# Delivery Dispatch API

A small, reusable Django REST API. **Vendors (or other projects) post deliveries, riders accept
them**, and every status change is audited and can be pushed to the calling project by webhook.

> **Status:** the code was linted (`ruff`) and byte-compiled, but the test suite has **not been
> run yet**. Run it first (see Quick start) and fix anything it finds.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
make install                 # pip install -r requirements/dev.txt
cp .env.example .env         # then set SECRET_KEY

make migrations              # generate migrations once, then commit them
make migrate
python manage.py createsuperuser   # gets the "admin" role automatically
make test                    # pytest
make run
```

`make check` runs what CI runs: lint, "migrations are up to date", and the tests.

## Concepts

| Principal | How it authenticates | Can do |
|-----------|---------------------|--------|
| **Vendor** | `Authorization: Token <token>` | Post deliveries, see and cancel their own |
| **Rider** | `Authorization: Token <token>` | See open deliveries + their own, accept, pick up, deliver |
| **Client app** (another project) | `X-API-Key: <key>` | Post deliveries, see and cancel its own, receive webhooks |
| **Admin** | Token | See and cancel everything (also Django admin at `/admin/`) |

Delivery status machine (enforced in `apps/deliveries/services.py`, tested):

```
posted -> accepted -> picked_up -> delivered
   \          \
    +----------+--> cancelled      (owner/admin, only before pickup)
```

## Endpoints (`/api/v1/`)

| Method | Path | Notes |
|--------|------|-------|
| POST | `auth/register/` | Vendor or rider only; returns a token |
| POST | `auth/token/` | Log in (rate limited) |
| GET | `auth/me/` | Current user |
| GET | `deliveries/?status=posted` | Scoped to the caller; paginated |
| POST | `deliveries/` | Vendor or client app |
| GET | `deliveries/<uuid>/` | |
| POST | `deliveries/<uuid>/accept/` | Rider. `409` if someone else got it first |
| POST | `deliveries/<uuid>/pickup/` | Assigned rider |
| POST | `deliveries/<uuid>/deliver/` | Assigned rider |
| POST | `deliveries/<uuid>/cancel/` | Owner or admin |
| GET | `/health/` | Liveness check for load balancers |

```bash
curl -X POST localhost:8000/api/v1/deliveries/ \
  -H "X-API-Key: dk_..." -H "Content-Type: application/json" \
  -d '{"external_reference":"ORDER-17","pickup_address":"12 Main St",
       "dropoff_address":"4 Church Rd","fee":"3.50","currency":"USD"}'
```

## Plugging another project in

```bash
python manage.py create_client_app "My Shop" --webhook-url https://myshop.example/hooks
```

The API key is printed **once** (only a hash is stored). The other project then:

1. Calls `POST /api/v1/deliveries/` with `X-API-Key`, sending its own order id as
   `external_reference` (unique per client app, so retries cannot double-post).
2. Receives `delivery.posted|accepted|picked_up|delivered|cancelled` webhooks. Verify the
   `X-Webhook-Signature` header: it is the HMAC-SHA256 hex digest of the raw body using the
   signing secret printed by the command.

Webhooks are written to an outbox table in the same transaction as the status change and sent
by `python manage.py send_webhooks` (run it every minute from cron or a scheduled job).
Failures retry with exponential backoff, up to `WEBHOOK_MAX_ATTEMPTS`.

## Layout

```
config/settings/{base,dev,prod,test}.py   split settings; secrets via python-decouple
apps/accounts/       custom User (role, phone), register/login/me
apps/deliveries/     models, services (business rules), serializers, views, permissions
apps/integrations/   client-app API keys, webhook outbox, management commands
conftest.py          shared fixtures; tests live beside each app in tests/
```

Design rules: views are thin, every state change goes through `services.py`, row locks make
"two riders accept at once" safe on PostgreSQL, and tests cover services, API and webhooks.

## Settings

| Env var | Default | Meaning |
|---------|---------|---------|
| `SECRET_KEY` | dev default; **required** in prod | |
| `DATABASE_URL` | local SQLite | e.g. `postgres://user:pass@host/db` |
| `ALLOWED_HOSTS` | localhost | comma-separated; required in prod |
| `DELIVERY_MAX_ACTIVE_PER_RIDER` | 3 | accepted + picked-up cap |
| `WEBHOOK_MAX_ATTEMPTS` / `WEBHOOK_TIMEOUT_SECONDS` | 5 / 5 | |

Run with `DJANGO_SETTINGS_MODULE=config.settings.prod` and `requirements/prod.txt` in production
(`gunicorn config.wsgi`).

## Known limits and next steps

- Migrations are not committed yet; generate them with `make migrations` and commit.
- The row-lock race test only proves the logic on SQLite. Verify concurrency on PostgreSQL.
- `send_webhooks` assumes a single worker; add `select_for_update(skip_locked=True)` if you
  run several.
- Rider location tracking, pricing and payments are out of scope.
- AWS path: containerise, RDS PostgreSQL, S3 (proof-of-delivery photos), SQS/SNS in place of
  the polling webhook sender, CloudWatch logs and alarms, CI/CD.
