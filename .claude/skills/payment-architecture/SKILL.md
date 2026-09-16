---
name: payment-architecture
description: Architecture spec and implementation guide for this project's learning payment system — Next.js (App Router) frontend + Django REST Framework backend + Omise (Opn Payments) in test mode, with card (3D Secure) and PromptPay QR. Use this skill whenever working in this project on anything payment-related, even if the user doesn't mention the spec: scaffolding django/ or nextjs/ (TypeScript), the PostgreSQL + pgAdmin Docker setup, writing Order/Payment/WebhookEvent models, the /api/orders/, /pay/ or /api/webhooks/omise/ endpoints, apply_charge, the sync_pending_payments command, Omise.js tokenization or createSource, checkout/polling pages, test-mode key guards, env vars, ngrok/cloudflared webhook setup, writing tests for payment scenarios, or reviewing existing payment code for correctness and security. Also use for questions about how the flow, state machine, duplicate payments, retries or refunds are supposed to work, and whenever the user asks what is already built, what is left, or what to do next — `references/progress.md` is the project's progress checklist.
---

# Payment Architecture (Next.js + Django REST + Omise test mode)

The full spec lives in `references/payment-architecture.md` (written in Thai, 19 sections). It is the source of truth. This file tells you how to use it and which rules matter most, so you don't have to hold all 950 lines in your head for a small task.

`references/progress.md` is the progress checklist: what is built, what is half-built, and what is left. The spec says what the system should be; the checklist says where it is now.

## How to work

1. **Read `references/progress.md` first**, so you know what already exists and don't rebuild it or assume a missing piece is there. **Update it in the same turn you finish a piece of work** (status, notes, and the "อัปเดตล่าสุด" date), and tell the user what you changed. Only mark `[x]` after you ran or tested it; use `[~]` with a note about what is left when code is written but unproven. The checklist tracks status only: decisions and rules belong in the spec.
2. **Identify the task type**, then read only the spec sections it needs (see the map below). For anything that touches payment state, always also read §6 (state machine) and §9 (`apply_charge`), because every status change flows through them.
3. **Follow the spec exactly** for names, fields, status values, error codes, HTTP statuses and paths. Other code in the project (frontend, sync job, tests) depends on these matching. If the spec seems wrong or incomplete, say so and propose a change rather than silently deviating.
4. **Don't invent Omise facts.** §18 lists things that must be checked against Omise's official docs: test card numbers, minimum amounts, 3DS behavior, how to simulate PromptPay, webhook event names, the QR field path, and idempotency key support. If code depends on one of these, point to the docs (https://docs.omise.co — the old docs.opn.ooo domain no longer resolves) or mark it clearly as `TODO: verify with Omise docs`. Don't guess a number.
5. **Stay in scope** (§1, §15). There's no login, no cart, no refund API and no live mode. If the user asks for one of these, point out that it's outside the spec and confirm before building it.
6. Respond in the language the user writes in. Code identifiers stay in English as in the spec.
7. **Project layout and tooling.** The backend lives in `django/` and the frontend in `nextjs/`. The frontend is TypeScript (strict) on Next.js 16 with pnpm: write `.ts`/`.tsx`, never `.js`. Keep TypeScript on 6.0.x until typescript-eslint supports 7. Next.js 16 changed APIs (for example, `params` is a Promise), so read `nextjs/node_modules/next/dist/docs/` before using a Next.js API you're unsure about. API response types live in `nextjs/lib/types.ts` and must stay in sync with §7.
8. **Database.** PostgreSQL 18 and pgAdmin run in Docker from `django/docker-compose.yml`, reading `django/.env` (§4, §16). Django runs on the host and connects to `localhost:5432`. Start Docker Desktop and `docker compose up -d --wait` before `migrate` or tests. Change the schema only through models plus `makemigrations`, and keep the constraints listed in §5.4.

## Spec section map

| Task | Read |
|---|---|
| "What's done / what's next?" / updating status | `references/progress.md` |
| Project scaffolding / folder layout | §19, §2, §4, §16 |
| Env vars, settings, test-key guard | §4, §7 (DRF defaults), §14 |
| Django models & migrations | §5, §6 |
| Docker PostgreSQL / pgAdmin | §2, §4, §16.2 |
| `POST /api/orders/`, `GET /api/orders/{id}/` | §7.1, §7.3, §5.2 |
| `POST /api/orders/{id}/pay/` | §7.2, §13.1–13.2, §9 |
| `apply_charge` / status mapping | §9, §6.1, §13.4 |
| Webhook endpoint | §10, §7.4, §9 |
| `sync_pending_payments` command | §11, §9 |
| Omise HTTP client | §13 |
| Next.js pages, Omise.js, polling | §12, §8 |
| Writing tests | §17, plus the section for the code under test |
| Security / code review | §14, then check against §6, §7.2, §9, §10 |
| Local dev, tunnel, webhook setup | §16 |
| "Is X in scope?" / production hardening | §1, §15 |

## Invariants that must not break

These are the rules that stop money problems. Bugs here cause double charges, fake "paid" orders or leaked keys, so check every change against them, and treat a violation as a blocking issue in reviews.

**Money and trust**
- Amounts are integer satang (60.00 THB = `6000`). Never use floats. Prices come only from backend `PRODUCTS`, so any `amount` the client sends is ignored. This stops users from editing prices in the browser.
- Omise is the source of truth. Django copies status from a charge it fetched itself with the secret key. It never decides a charge succeeded on its own, never trusts a webhook body, and never trusts the 3DS redirect query string. Webhooks and redirects can be forged.
- Before changing anything, `apply_charge` checks that `charge.amount` and `charge.currency` match the Payment.

**Keys and card data**
- `skey_test_` lives only in `django/.env`. Django raises `ImproperlyConfigured` at startup if the key doesn't start with `skey_test_`. The checkout page refuses to load if the public key isn't `pkey_test_`. This makes real charges impossible even if someone pastes the wrong key.
- Card data goes from the browser straight to Omise.js. It never reaches Django, is never logged or put in `localStorage`, and is cleared from state right after tokenization. Tokens and secret keys are never logged either.

**Concurrency and idempotency**
- There is one path for status changes: `apply_charge(charge)`, called from `/pay`, the webhook and the sync job. Running it twice with the same charge must give the same result.
- `apply_charge` runs inside `transaction.atomic()` with `select_for_update()`, and always locks **Order before Payment** to avoid deadlocks.
- `/pay` locks the order and reuses an existing Payment that is pending, has the same method, has a `charge_id`, and hasn't expired. It creates a new Payment only when none matches, and commits that Payment **before** calling Omise. This prevents a double-click from charging twice and prevents losing track of a charge if the request dies.
- If Omise times out or returns 5xx during `/pay`, the Payment stays `pending` with `charge_id = null` and the API returns `502`. It is not marked failed, because the charge may have actually been created. The sync job marks it `gateway_unreachable` after 15 minutes, and that is the only `failed` status that can later become `successful`.
- Webhooks are deduplicated by `event_id` using `processed_at`. If fetching the charge fails, return `500` so Omise retries. If Omise returns `404` (likely a fake webhook), return `200`. Omise does not guarantee retries, and an expiring PromptPay charge emits no event at all, so the sync job — not the webhook — is the real backstop (§11, §18).
- The database enforces `UniqueConstraint(fields=["order"], condition=Q(status="successful", needs_refund=False))` as the last line of defense.

**State rules**
- Payment statuses: `pending`, `successful`, `failed`, `expired`. Order statuses: `pending`, `paid`. `successful`, `expired` and `paid` are final.
- A second successful payment on an already-paid order becomes `successful` with `needs_refund=True` and logs a warning. It never raises an error or rejects the payment, because the money has already moved.
- A `failed` Payment with `failure_code = gateway_unreachable` can only become `successful`. Until then `apply_charge` keeps that status and failure code instead of copying them from the charge. `apply_charge` never overwrites a Payment's existing, different `charge_id`.
- A failed or expired Payment leaves the Order `pending` so the user can retry. A retry creates a new Payment row and needs a new token or source (they can only be used once).
- The sync job never marks a payment expired on its own. It fetches the charge and lets `apply_charge` decide. Each payment is processed independently, so one failure doesn't stop the rest.

**API surface**
- All paths end with `/`. Errors always use the format `{"error": {"code": ..., "message": ...}}`.
- Responses never expose `charge_id`, `metadata` or other internal fields.
- DRF uses no authentication classes and `AllowAny`. IDs are UUIDs, because without login, guessable IDs would expose other people's orders.

## Reviewing existing code

When asked to review or audit, go through the invariants above plus §14's 15 rules and the 14 scenarios in §17. For each problem, give the file and line, the rule it breaks, a concrete way it could fail (for example, "two `/pay` requests at the same time create two charges because there is no `select_for_update`"), and a fix. List money and security problems before style issues.

## Writing tests

§17 lists the required scenarios. Automated backend tests should mock the Omise HTTP client (`omise_client.create_charge` / `retrieve_charge`) instead of calling the network, and cover at least: price tampering is ignored, reuse on double `/pay`, `409` on a paid order, duplicate webhook processed once, fake webhook `404` → `200` with no state change, `needs_refund` on a double success, gateway timeout → `502` + pending, sync job cases A/B/C, and the live-key guard. Scenarios that need the Omise Dashboard (1, 3–6, 9) are manual checks in test mode. Scenario 2 (real 3DS page) is excluded because the Omise test account does not have 3DS enabled (see the note under the §17 table); keep the 3DS code path and its mocked tests.

Backend tests use Django `TestCase` against the Docker PostgreSQL (Django creates `test_payments`), so the `db` container must be running. Build rows with `payments/tests/factories.py` (`make_order`, `make_payment`, `make_charge`). Use `SimpleTestCase` only for code that never touches the database.
