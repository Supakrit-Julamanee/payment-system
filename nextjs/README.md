# Payment demo: Next.js frontend

The frontend for the learning payment system (Next.js App Router + Django REST + Omise **test mode**).
The spec is `.claude/skills/payment-architecture/references/payment-architecture.md` in the project root (§12).

## Setup

```bash
cp .env.example .env.local   # put your pkey_test_... here
pnpm install
pnpm dev                     # http://localhost:3000
```

The Django API must be running at `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)
with CORS allowing `http://localhost:3000`.

## Routes

| Route | Purpose |
|---|---|
| `/` | Product list. "ซื้อ" calls `POST /api/orders/` and goes to checkout |
| `/checkout/[orderId]` | Shows the amount from Django, card form (Omise.js `createToken`) or PromptPay (`createSource`) |
| `/orders/[orderId]` | Result page and 3DS `return_uri`. Shows the PromptPay QR and countdown, polls `GET /api/orders/{id}/` every 3 s |

## Files

TypeScript (strict), pnpm, TypeScript 6.0.x (typescript-eslint does not support 7 yet).

- `lib/types.ts`: API response types (`Order`, `Payment`, status unions), matching spec §7
- `lib/config.ts`: env vars and the `pkey_test_` guard
- `lib/api.ts`: Django API calls (`createOrder`, `getOrder`, `payWithCard`, `payWithPromptPay`) and `ApiError`
- `lib/omise.ts`: Omise.js promise wrappers and the `window.Omise` type
- `lib/useOrderPolling.ts`: polling hook (stops on paid / failed / expired, gives up after 10 min)
- `lib/products.ts`: product ids and names for the home page (no prices; Django owns them)
- `lib/format.ts`: satang formatting with integer math

Type-check with `pnpm exec tsc --noEmit` (run `pnpm exec next typegen` first so `PageProps` exists).

## Rules this code keeps

- Never sends an amount to Django. The PromptPay source amount comes from the Django order response.
- Card fields are uncontrolled inputs read once on submit. The form is reset right after tokenization, and card data is never logged or stored.
- Checkout refuses to load Omise.js unless the public key starts with `pkey_test_`.
- The result page ignores the redirect query string and only trusts Django.
- Pay buttons are disabled while a request is in flight.
