# Payment demo: Django backend

Django REST Framework API for the learning payment system (Omise **test mode** only).
The spec is `.claude/skills/payment-architecture/references/payment-architecture.md` in the project root.

## Status

Built:
- settings, test-key guard, CORS, DRF config, the `{"error": {...}}` format, `PRODUCTS`
- PostgreSQL + pgAdmin in Docker
- models `Order`, `Payment`, `WebhookEvent` with database constraints
- `apply_charge` (spec §9), Payment reuse, webhook de-duplication
- `POST /api/orders/` and `GET /api/orders/{id}/` fully
- `POST /api/orders/{id}/pay/` up to the point where Omise is called (404, 400, 409, reuse)
- `POST /api/webhooks/omise/` up to the point where the charge is fetched from Omise

Not built yet: the Omise client (`omise_client.py`) and `sync_pending_payments`. Those steps
return `501 not_implemented`; the `TODO(omise, ...)` comments in `payments/views.py` point at
the spec section for each one.

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
