# สถานะการดำเนินงาน (progress checklist)

ไฟล์นี้บอกว่าตอนนี้ระบบทำถึงไหนแล้ว **อ่านไฟล์นี้ก่อนเริ่มงานทุกครั้ง** และอัปเดตทันทีเมื่อทำงานเสร็จ

อัปเดตล่าสุด: **2026-09-16**

## วิธีอัปเดต

1. แก้ไฟล์นี้ใน commit เดียวกับโค้ด อย่าทิ้งไว้ทีหลัง
2. ใช้สถานะ 3 แบบเท่านั้น
   - `[x]` เสร็จแล้วและตรวจแล้วว่าทำงานได้ (ระบุวิธีตรวจในช่องหมายเหตุ เช่น test ผ่าน หรือยิง API จริง)
   - `[~]` ทำบางส่วน (ต้องเขียนว่าเหลืออะไร)
   - `[ ]` ยังไม่เริ่ม
3. ห้ามติ๊ก `[x]` ถ้ายังไม่ได้รันหรือทดสอบจริง ถ้าเขียนโค้ดเสร็จแต่ยังไม่ทดสอบ ให้ใช้ `[~]` แล้วเขียนว่าค้างอะไร
4. แก้วันที่ "อัปเดตล่าสุด" ทุกครั้ง
5. ถ้าตัดสินใจต่างจาก spec ให้แก้ spec (`payment-architecture.md`) ด้วย แล้วอ้างถึงหัวข้อนั้นในหมายเหตุ อย่าบันทึกข้อตัดสินใจไว้แค่ในไฟล์นี้
6. งานที่ยังไม่ได้ทำในโค้ดควรมี `TODO(db, §...)` หรือ `TODO(omise, §...)` กำกับไว้ในไฟล์จริงด้วย

## 1. Frontend (`nextjs/`) — §12

- [x] scaffold Next.js 16 + TypeScript (strict) + pnpm — `pnpm lint`, `tsc --noEmit`, `pnpm build` ผ่าน
- [x] `lib/types.ts`, `lib/api.ts`, `lib/config.ts`, `lib/format.ts`, `lib/products.ts` — §7, §12.1
- [x] `lib/omise.ts` wrapper ของ `createToken` / `createSource` — §12.2–12.4 (ยังไม่ได้ยิงกับ Omise จริง)
- [x] `lib/useOrderPolling.ts` — §12.5
- [x] หน้า `/`, `/checkout/{orderId}`, `/orders/{orderId}` — โหลดได้ทั้ง 3 หน้า (HTTP 200)
- [x] test-mode guard ฝั่ง frontend — ทดสอบด้วย key `pkey_live_` แล้วหน้า checkout ไม่โหลด Omise.js
- [~] ทดสอบ flow จริงในเบราว์เซอร์ — 2026-09-16 ผ่าน §17 ข้อ 1 และ 3
  - ข้อ 1: บัตร `4242...` → order `paid`, payment `successful`, charge ที่ Omise ตรงทั้ง `amount`, `metadata`, `livemode: false`
  - ข้อ 3: บัตร `4111 1111 1114 0011` → payment `failed` (`insufficient_fund`) และ order ยัง `pending` จากนั้นจ่ายซ้ำด้วย `4242...` สำเร็จ ได้ Payment 2 แถวในหนึ่ง order แถวเดิมไม่ถูกแก้ และมี successful ที่ `needs_refund = false` เพียงแถวเดียว
  - PromptPay: สร้าง QR จากหน้าเว็บได้จริงแล้ว (ใน DB dev มี payment `promptpay` สถานะ `pending` พร้อม `charge_id` และ `expires_at` +24 ชม.) แต่ยังยืนยันผลการจ่ายไม่ได้เพราะยังไม่ได้ต่อ webhook
  - เหลือ: 3DS เต็มรูปแบบ (ข้อ 2), ยืนยันผล PromptPay (ข้อ 4–6), webhook ไม่มาถึง (ข้อ 9)

## 2. Backend infrastructure (`django/`) — §4, §7, §14

- [x] scaffold Django 6.1 + DRF (ไม่มี auth, `AllowAny`, JSON อย่างเดียว) — §7
- [x] โหลด `.env` ด้วย python-dotenv และ `require_env`
- [x] test-mode guard `require_test_secret_key` — §4, §17 ข้อ 14 (มี test)
- [x] CORS เฉพาะ `FRONTEND_URL` — §14 ข้อ 14 (มี test + ยิง preflight จริง)
- [x] รูปแบบ error `{"error": {...}}` รวม 404/500 นอก DRF — §7
- [x] `PRODUCTS` และการตรวจ request (`validation.py`) — §5.2, §7.1, §7.2

## 3. Database (`django/`, Docker) — §5, §6

- [x] `docker-compose.yml`: PostgreSQL 18 + pgAdmin 4 — §2, §16.2 (`docker compose up -d --wait` ผ่าน healthcheck)
- [x] models `Order`, `Payment`, `WebhookEvent` + migration แรก — §5
- [x] constraint ทั้งหมดรวม `one_effective_successful_payment_per_order` — §5.4 (มี test ระดับ DB)
- [x] pgAdmin ลงทะเบียน server จาก `pgadmin/servers.json` — ต่อ `db:5432` ได้จริง

## 4. Payment logic (`payments/services.py`) — §9

- [x] `map_charge_status` — §13.4
- [x] `apply_charge` ครบทุกขั้น (ล็อก Order ก่อน Payment, idempotent, `needs_refund`) — §9 (มี test ครอบทุก transition)
- [x] `create_order`, `find_reusable_payment`, `create_pending_payment` — §7.1, §7.2
- [x] `begin_webhook_event`, `mark_webhook_processed` (กัน event ซ้ำ) — §10

## 5. API endpoints — §7

- [x] `POST /api/orders/` — §7.1 (ยิงจริงได้ 201 และราคามาจาก `PRODUCTS`)
- [x] `GET /api/orders/{id}/` — §7.3 (ไม่คืน `charge_id` / `metadata`)
- [x] `POST /api/orders/{id}/pay/` — §7.2 ครบทุกขั้น รวมสร้าง charge, 402, 502 (มี test แบบ mock ครบทุกกรณี)
- [x] `POST /api/webhooks/omise/` — §10 ครบทุกขั้น รวมดึง charge จาก Omise, 404 → 200, timeout/5xx → 500 (มี test แบบ mock)

## 6. Omise integration — §13

- [x] `payments/omise_client.py`: `create_charge`, `retrieve_charge` (Basic auth, form-encoded, timeout 30 วิ) — §13.1–13.3 แยก error เป็น `OmiseError` / `OmiseNotFound` / `OmiseUnavailable`
- [x] ต่อเข้า `/pay/`: 2xx → `apply_charge` + 201, 4xx → 402, timeout/5xx → 502 — §7.2
- [x] ต่อเข้า webhook: 404 → 200, timeout/5xx → 500, สำเร็จ → `apply_charge` + 200 — §10
- [~] ตรวจข้อมูล Omise ตาม §18 — 2026-09-16 ตรวจแล้ว: path ของ QR, `expires_at` 24 ชม., ยอดขั้นต่ำ PromptPay ฿20, วิธีจำลองใน Dashboard, เลขบัตรทดสอบ (ดูตารางท้ายหัวข้อ 18)
  - เหลือ: ยอดขั้นต่ำของบัตร, 3DS ในบัญชีนี้, parameter ของ `Omise.createSource`, ชื่อ event ของ webhook, idempotency key
- [x] ใส่ key จริงใน `django/.env` และ `nextjs/.env.local` — 2026-09-16 ตรวจด้วย `GET https://api.omise.co/account` ได้ HTTP 200, `livemode: false`, country TH, currency THB

## 7. Expiry sync job — §11

- [x] `python manage.py sync_pending_payments` (กรณี A, B, C) — 2026-09-16 มี test 11 ข้อผ่าน และรันจริงกับ DB dev ได้ `checked=0 skipped=0 gateway_unreachable=0` (ไม่มีรายการเข้าเงื่อนไข ถูกต้องเพราะ PromptPay ที่ค้างอยู่ยังไม่หมดอายุ)
- [ ] ตั้ง cron ให้รันทุก 5 นาที — §16.4 (ตอนนี้ต้องรันด้วยมือ)

## 8. Tests — §17

- [x] test อัตโนมัติ 80 ข้อผ่านบน PostgreSQL จริง (`python manage.py test`)
- [x] test runner กันไม่ให้ test ยิง Omise จริง (`config/test_runner.py`) — ถ้าลืม mock จะ error ทันที
- [x] ครอบคลุมแล้ว: ข้อ 7 (กดจ่ายซ้ำ มี charge เดียว), 8 (webhook ซ้ำ), 10 (`needs_refund`), 11 (แก้ราคา), 12 (webhook ปลอม → 200), 13 (order ที่จ่ายแล้ว → 409), 14 (live key)
- [x] test แบบ mock Omise client: สำเร็จ, 3DS pending, PromptPay QR, 402 + payment failed, 502 + payment คง pending
- [x] test ของ sync job กรณี A/B/C รวมกฎ "Omise ยัง pending ให้คงสถานะ" และ "หนึ่งรายการพังต้องไม่หยุดรายการอื่น" — รวมทั้งชุด 91 ข้อผ่าน
- [~] ข้อ 1 และ 3 ผ่านแล้วด้วยมือ (2026-09-16) เหลือข้อ 2, 4–6 และ 9 ซึ่งต้องใช้ Dashboard, 3DS หรือ tunnel

## 9. Local development — §16

- [x] `django/.env` และ `nextjs/.env.local` ตั้งค่าครบและเชื่อมต่อกันได้ (Next.js → Django → PostgreSQL, pgAdmin → PostgreSQL)
- [x] `.gitignore` ของทุก service (ตรวจแล้วว่าไม่มี secret หลุด)
- [ ] tunnel (ngrok หรือ cloudflared) และตั้ง webhook URL ใน Omise Dashboard — §16.3

## งานที่ควรทำถัดไป

1. ตั้ง tunnel + webhook URL ใน Dashboard แล้วทดสอบ PromptPay (§16.3, §17 ข้อ 4–6, 9) — โค้ดครบหมดแล้ว เหลือแค่ต่อ webhook เข้ามาให้ถึง
2. ทดสอบ 3DS แบบกดยืนยันจริง (§17 ข้อ 2) และเก็บข้อมูล §18 ที่ยังค้าง
3. ตั้ง cron ให้ sync job รันทุก 5 นาที (§16.4)
