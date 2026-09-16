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
- [ ] ทดสอบ flow จริงในเบราว์เซอร์ (บัตร, 3DS, PromptPay) — รอ Omise client ฝั่ง backend และ key จริง

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
- [~] `POST /api/orders/{id}/pay/` — §7.2 ทำถึงล็อก order, 404, ตรวจ body, 409 และ reuse แล้ว
  - เหลือ: เรียก `create_pending_payment` แล้วสร้าง charge ตอนนี้ตอบ `501 not_implemented`
- [~] `POST /api/webhooks/omise/` — §10 ทำถึงบันทึก event, กันซ้ำ และ event ที่ไม่ใช่ charge แล้ว
  - เหลือ: ดึง charge จาก Omise แล้วเรียก `apply_charge` ตอนนี้ตอบ `501`

## 6. Omise integration — §13

- [ ] `payments/omise_client.py`: `create_charge`, `retrieve_charge` (Basic auth, form-encoded, timeout 30 วิ) — §13.1–13.3
- [ ] ต่อเข้า `/pay/`: 2xx → `apply_charge` + 201, 4xx → 402, timeout/5xx → 502 — §7.2
- [ ] ต่อเข้า webhook: 404 → 200, timeout/5xx → 500, สำเร็จ → `apply_charge` + 200 — §10
- [ ] ตรวจข้อมูล Omise ตาม §18 (ยอดขั้นต่ำ, บัตรทดสอบ, 3DS, วิธีจำลอง PromptPay, path ของ QR, ชื่อ event, idempotency key)
- [ ] ใส่ key จริงใน `django/.env` และ `nextjs/.env.local` (ตอนนี้เป็น placeholder ทั้งคู่)

## 7. Expiry sync job — §11

- [ ] `python manage.py sync_pending_payments` (กรณี A, B, C)
- [ ] ตั้ง cron หรือรันด้วยมือ — §16.4

## 8. Tests — §17

- [x] test อัตโนมัติ 60 ข้อผ่านบน PostgreSQL จริง (`python manage.py test`)
- [x] ครอบคลุมแล้ว: ข้อ 11 (แก้ราคา), 13 (จ่าย order ที่จ่ายแล้ว), 14 (live key), 10 (`needs_refund` ผ่าน `apply_charge`)
- [~] ข้อ 7 (กดจ่ายซ้ำ) และ 8 (webhook ซ้ำ) — ทดสอบเฉพาะส่วน DB เหลือส่วนที่ต้อง mock Omise client
- [ ] ข้อ 12 (webhook ปลอม → 404 → 200) — รอ Omise client
- [ ] test ที่ mock `omise_client.create_charge` / `retrieve_charge`: 402, 502 + payment คง pending, sync job A/B/C
- [ ] ข้อ 1–6 และ 9 — ต้องทดสอบด้วยมือใน test mode (Dashboard, 3DS, tunnel)

## 9. Local development — §16

- [x] `django/.env` และ `nextjs/.env.local` ตั้งค่าครบและเชื่อมต่อกันได้ (Next.js → Django → PostgreSQL, pgAdmin → PostgreSQL)
- [x] `.gitignore` ของทุก service (ตรวจแล้วว่าไม่มี secret หลุด)
- [ ] tunnel (ngrok หรือ cloudflared) และตั้ง webhook URL ใน Omise Dashboard — §16.3

## งานที่ควรทำถัดไป

1. `payments/omise_client.py` (§13) แล้วต่อเข้า `/pay/` และ webhook (§7.2, §10)
2. test ที่ mock Omise client (§17)
3. `sync_pending_payments` (§11)
4. ตั้ง tunnel + webhook แล้วทดสอบด้วยมือข้อ 1–6, 9 (§16.3, §17)
