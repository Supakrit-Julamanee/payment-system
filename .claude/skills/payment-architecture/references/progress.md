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
- [x] `lib/omise.ts` wrapper ของ `createToken` / `createSource` — §12.2–12.4 ใช้งานจริงในเบราว์เซอร์แล้วทั้งบัตร (§17 ข้อ 1, 3) และ PromptPay (ข้อ 4–6)
- [x] `lib/useOrderPolling.ts` — §12.5
- [x] หน้า `/`, `/checkout/{orderId}`, `/orders/{orderId}` — โหลดได้ทั้ง 3 หน้า (HTTP 200)
- [x] test-mode guard ฝั่ง frontend — ทดสอบด้วย key `pkey_live_` แล้วหน้า checkout ไม่โหลด Omise.js
- [x] ทดสอบ flow จริงในเบราว์เซอร์ — 2026-09-16 ผ่าน §17 ข้อ 1, 3, 4, 5, 6 และ 9 ส่วนข้อ 2 (3DS) ตัดออกจากการทดสอบตามที่บันทึกไว้ใต้ตารางหัวข้อ 17
  - ข้อ 1: บัตร `4242...` → order `paid`, payment `successful`, charge ที่ Omise ตรงทั้ง `amount`, `metadata`, `livemode: false`
  - ข้อ 3: บัตร `4111 1111 1114 0011` → payment `failed` (`insufficient_fund`) และ order ยัง `pending` จากนั้นจ่ายซ้ำด้วย `4242...` สำเร็จ ได้ Payment 2 แถวในหนึ่ง order แถวเดิมไม่ถูกแก้ และมี successful ที่ `needs_refund = false` เพียงแถวเดียว
  - ข้อ 4 (PromptPay สำเร็จ): สร้าง QR จากหน้าเว็บ → กด Mark as successful ใน Dashboard → Omise ส่ง event `charge.complete` เข้า tunnel → Django ดึง charge มาตรวจแล้ว payment เป็น `successful`, order เป็น `paid` และหน้าเว็บเปลี่ยนเองจาก polling นี่คือการพิสูจน์เส้นทาง webhook จริงครั้งแรก
  - ข้อ 5 (PromptPay ล้มเหลว): กด Mark as failed → payment เป็น `failed` พร้อม `failure_code = failed_processing` ส่วน order ยัง `pending` ให้ลองใหม่ได้ (webhook 3 event ที่เข้ามาถูกประมวลผลครบทุกตัว)
  - ข้อ 6 (QR หมดอายุ): ตั้ง `PROMPTPAY_EXPIRES_IN_SECONDS=10` แล้วสร้าง QR 2 ใบโดยไม่จ่าย พอรัน `sync_pending_payments` ได้ `checked=2` และ payment ทั้งสองเป็น `expired` ส่วน order ยัง `pending` — Django ไม่ได้ตัดสินเอง แต่ถาม Omise แล้วคัดลอกสถานะมา
  - ข้อ 9 (webhook ไม่มาถึง): ปิด tunnel แล้วตั้งอายุ QR 180 วินาที ลำดับเวลา: สร้าง charge 14:12:58 → Mark as successful ที่ Omise 14:13:57 → หมดอายุ 14:15:58 → sync job อัปเดต 14:16:49 ผลคือ payment `successful`, order `paid` ตรงกับ charge ที่ Omise หลักฐานว่า webhook ไม่มาถึงจริง: Omise สร้าง event `charge.create` และ `charge.complete` ของ charge นี้ แต่ตาราง `payments_webhookevent` ยังมี 6 แถวเท่าเดิม
  - ข้อ 2 (3DS): ตัดออกจากการทดสอบ 2026-09-16 เพราะบัญชีทดสอบไม่ได้เปิด 3DS (เอกสาร 3 หน้ายืนยัน และ `authorize_uri` เป็น `?acs=false` ที่ข้ามหน้ายืนยันตัวตน) โค้ดรองรับ 3DS ยังอยู่ครบ

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
  - 2026-09-16 ตรวจเพิ่ม: บัตรทดสอบ 3DS ใช้ได้เฉพาะบัญชีที่เปิด 3DS (ต้องขอ `support@omise.co`), event ที่ส่งจริงมี `charge.create` และ `charge.complete`, event `charge.expire` มีในเอกสารแต่ใช้กับ Barcode Alipay เท่านั้น (PromptPay หมดอายุแล้วเงียบ ตรวจซ้ำด้วย `GET /events` แล้ว) และ Omise ไม่รับประกันการส่ง webhook ซ้ำ
  - เหลือ: ยอดขั้นต่ำของบัตร, parameter ของ `Omise.createSource`, idempotency key
- [x] ใส่ key จริงใน `django/.env` และ `nextjs/.env.local` — 2026-09-16 ตรวจด้วย `GET https://api.omise.co/account` ได้ HTTP 200, `livemode: false`, country TH, currency THB
- [x] `PROMPTPAY_EXPIRES_IN_SECONDS` (ตัวเลือก ใช้ทดสอบเท่านั้น) ส่ง `expires_at` ตอนสร้าง charge ของ PromptPay — 2026-09-16 ยิงจริงกับ Omise พบว่า 10 วินาทีใช้ได้ และ charge เปลี่ยนเป็น `expired` เองเมื่อเลยเวลา ทำให้ทดสอบ §17 ข้อ 6 และ 9 ได้โดยไม่ต้องรอ 24 ชม.

## 7. Expiry sync job — §11

- [x] `python manage.py sync_pending_payments` (กรณี A, B, C) — 2026-09-16 มี test 11 ข้อผ่าน และรันจริงได้ผลถูกต้องทั้งตอนไม่มีรายการเข้าเงื่อนไข (`checked=0`) และตอนมี QR หมดอายุ 2 ใบ (`checked=2` แล้ว payment เป็น `expired`)
- [x] ตั้ง cron ให้รันทุก 5 นาที — §16.4 ทดสอบ 2026-09-16: ตั้งเป็นทุก 1 นาทีชั่วคราวก่อน cron รันจริงและเขียน `Sync finished` ลง `django/sync_pending_payments.log` (macOS ไม่ได้บล็อกการเข้าถึง Desktop) แล้วเปลี่ยนเป็น `*/5`
  - ดู/ลบได้ด้วย `crontab -l` และ `crontab -r` (บรรทัดมี comment `payment-system` กำกับ) Docker ต้องรันอยู่ ไม่งั้น job จะ log error แล้วรอรอบถัดไป

## 8. Tests — §17

- [x] test อัตโนมัติ 94 ข้อผ่านบน PostgreSQL จริง (`python manage.py test`)
- [x] test runner กันไม่ให้ test ยิง Omise จริง (`config/test_runner.py`) — ถ้าลืม mock จะ error ทันที
- [x] ครอบคลุมแล้ว: ข้อ 7 (กดจ่ายซ้ำ มี charge เดียว), 8 (webhook ซ้ำ), 10 (`needs_refund`), 11 (แก้ราคา), 12 (webhook ปลอม → 200), 13 (order ที่จ่ายแล้ว → 409), 14 (live key)
- [x] test แบบ mock Omise client: สำเร็จ, 3DS pending, PromptPay QR, 402 + payment failed, 502 + payment คง pending
- [x] test ของ sync job กรณี A/B/C รวมกฎ "Omise ยัง pending ให้คงสถานะ" และ "หนึ่งรายการพังต้องไม่หยุดรายการอื่น"
- [x] ข้อ 1, 3, 4, 5, 6 และ 9 ผ่านแล้วด้วยมือ (2026-09-16) ข้อ 2 (3DS) ตัดออกจากการทดสอบ

## 9. Local development — §16

- [x] `django/.env` และ `nextjs/.env.local` ตั้งค่าครบและเชื่อมต่อกันได้ (Next.js → Django → PostgreSQL, pgAdmin → PostgreSQL)
- [x] `.gitignore` ของทุก service (ตรวจแล้วว่าไม่มี secret หลุด)
- [x] tunnel (cloudflared quick tunnel) และตั้ง webhook URL ใน Omise Dashboard — §16.3 ทดสอบ 2026-09-16: ยิงจากภายนอกเข้า `/api/webhooks/omise/` ผ่าน tunnel ได้ และ Omise ส่ง event `charge.complete` เข้ามาจริง
  - URL ของ quick tunnel เปลี่ยนทุกครั้งที่เปิดใหม่ ต้องกลับไปแก้ใน Dashboard ทุกครั้ง

## งานที่ควรทำถัดไป

1. เก็บข้อมูล §18 ที่ค้าง: ยอดขั้นต่ำของบัตร, parameter ของ `Omise.createSource`, idempotency key (ไม่กระทบการใช้งานปัจจุบัน)
