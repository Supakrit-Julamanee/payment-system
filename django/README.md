# Payment demo: Django backend

Django REST Framework API for the learning payment system (Omise **test mode** only).
The spec is `.claude/skills/payment-architecture/references/payment-architecture.md` in the project root.

## Status

Built:
- settings, test-key guard, CORS, DRF config, the `{"error": {...}}` format, `PRODUCTS`
- PostgreSQL + pgAdmin in Docker
- models `Order`, `Payment`, `WebhookEvent` with database constraints
- `apply_charge` (spec §9), Payment reuse, webhook de-duplication
- `omise_client.py`: `create_charge` / `retrieve_charge` (spec §13)
- all four endpoints, including charging through Omise (402, 502) and webhook verification

- `sync_pending_payments` (spec §11): re-reads pending charges from Omise, and gives up on
  payments that never got a charge id after 15 minutes (`gateway_unreachable`)

Not built yet: nothing from the backend spec. What is left is manual verification through a
tunnel (webhook deliveries, PromptPay, full 3DS) and a cron entry for the sync job.

The live payment flow (card, 3DS, PromptPay) has not been run in a browser yet. Automated
tests mock the Omise client; `config/test_runner.py` fails any test that tries to reach the
real API.

## Setup

```bash
cp .env.example .env               # set DJANGO_SECRET_KEY, a skey_test_... key and DB passwords
docker compose up -d               # PostgreSQL on 127.0.0.1:5432, pgAdmin on http://localhost:5050

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

Django refuses to start unless `OMISE_SECRET_KEY` starts with `skey_test_`.

### pgAdmin

Open http://localhost:5050 and log in with `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD`.
The server "payment-system (docker)" is already registered (host `db`, user `payments`);
enter `POSTGRES_PASSWORD` the first time you open it.

`pgadmin/servers.json` is imported only on pgAdmin's first start. If you change
`POSTGRES_DB` or `POSTGRES_USER`, edit that file too, then run `docker compose down -v`
(this deletes all data) and start again.

## Tests

The tests need the database container running (Django creates a separate `test_payments` database).

```bash
python manage.py test
```

## Layout

- `docker-compose.yml`, `pgadmin/servers.json`: PostgreSQL 18 and pgAdmin 4
- `config/settings.py`: env loading, PostgreSQL, DRF (no auth, `AllowAny`, JSON only), CORS for `FRONTEND_URL`
- `config/guards.py`: `require_env`, `require_test_secret_key`
- `payments/models.py`: `Order`, `Payment`, `WebhookEvent` and their constraints
- `payments/services.py`: `apply_charge`, `map_charge_status`, `create_order`, `find_reusable_payment`, `create_pending_payment`, webhook event helpers
- `payments/serializers.py`: response bodies (never exposes `charge_id`, `metadata`, `needs_refund`)
- `payments/products.py`: `PRODUCTS` (integer satang)
- `payments/exceptions.py`: `ApiError`, DRF exception handler, JSON 404/500 handlers
- `payments/validation.py`: request parsing with the spec error codes
- `payments/views.py`, `payments/urls.py`: the four endpoints
- `payments/management/commands/sync_pending_payments.py`: the expiry sync job (run it with
  `python manage.py sync_pending_payments`)
