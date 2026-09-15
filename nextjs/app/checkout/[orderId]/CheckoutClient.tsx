"use client";

import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import {
  errorMessage,
  errorStatus,
  getOrder,
  payWithCard,
  payWithPromptPay,
} from "@/lib/api";
import { OMISE_PUBLIC_KEY } from "@/lib/config";
import { formatAmount } from "@/lib/format";
import {
  OMISE_JS_URL,
  createPromptPaySource,
  createToken,
  initOmise,
  type OmiseCardInput,
} from "@/lib/omise";
import type { Order, PaymentMethod } from "@/lib/types";

function isHttpsUrl(value: string): boolean {
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

function readField(fields: FormData, name: string): string {
  const value = fields.get(name);
  return typeof value === "string" ? value : "";
}

export default function CheckoutClient({ orderId }: { orderId: string }) {
  const router = useRouter();
  const [order, setOrder] = useState<Order | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [omiseReady, setOmiseReady] = useState(false);
  const [omiseError, setOmiseError] = useState<string | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("card");
  const [submitting, setSubmitting] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const resultPath = `/orders/${orderId}`;

  useEffect(() => {
    let cancelled = false;
    getOrder(orderId)
      .then((data) => {
        if (cancelled) return;
        if (data.status === "paid") {
          router.replace(resultPath);
          return;
        }
        setOrder(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err ?? new Error("unknown"));
      });
    return () => {
      cancelled = true;
    };
  }, [orderId, resultPath, router]);

  // Where to go after a successful POST /pay/ (spec §12.3 step 5).
  function goToResult(data: Order) {
    const payment = data.latest_payment;
    if (payment?.status === "pending" && payment.authorize_uri) {
      if (!isHttpsUrl(payment.authorize_uri)) {
        setPayError("ลิงก์ยืนยันตัวตนไม่ถูกต้อง");
        setSubmitting(false);
        return;
      }
      window.location.assign(payment.authorize_uri);
      return;
    }
    router.push(resultPath);
  }

  async function handlePayError(err: unknown) {
    const status = errorStatus(err);
    if (status === 409) {
      router.replace(resultPath);
      return;
    }
    if (status === 402) {
      // Re-read the order so the message comes from the stored Payment.
      try {
        const data = await getOrder(orderId);
        setOrder(data);
        setPayError(data.latest_payment?.failure_message || errorMessage(err));
      } catch {
        setPayError(errorMessage(err));
      }
      return;
    }
    if (status === 502) {
      // The charge may have been created anyway, so warn before a retry.
      setPayError(
        "ระบบชำระเงินไม่ตอบกลับ การชำระเงินอาจสำเร็จแล้ว กรุณาตรวจสอบสถานะคำสั่งซื้อก่อนลองอีกครั้ง",
      );
      return;
    }
    setPayError(errorMessage(err));
  }

  async function handleCardSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    // Card data is read from the uncontrolled form, so it never enters React state.
    const form = event.currentTarget;
    const fields = new FormData(form);
    const card: OmiseCardInput = {
      name: readField(fields, "name").trim(),
      number: readField(fields, "number").replace(/\s+/g, ""),
      expiration_month: Number(readField(fields, "expiration_month")),
      expiration_year: Number(readField(fields, "expiration_year")),
      security_code: readField(fields, "security_code"),
    };

    setSubmitting(true);
    setPayError(null);

    let token: string;
    try {
      token = await createToken(card);
    } catch (err) {
      setPayError(errorMessage(err));
      setSubmitting(false);
      return;
    } finally {
      // Clear card data right after tokenization, whatever the result.
      form.reset();
    }

    try {
      const data = await payWithCard(orderId, token);
      goToResult(data);
    } catch (err) {
      await handlePayError(err);
      setSubmitting(false);
    }
  }

  async function handlePromptPay(current: Order) {
    if (submitting) return;
    setSubmitting(true);
    setPayError(null);
    try {
      const source = await createPromptPaySource(current.amount, current.currency);
      await payWithPromptPay(orderId, source);
      // The result page shows the QR, the countdown and polls for the result.
      router.push(resultPath);
    } catch (err) {
      await handlePayError(err);
      setSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <main className="container">
        <h1>ชำระเงิน</h1>
        <p className="alert alert-error">
          {errorStatus(loadError) === 404 ? "ไม่พบคำสั่งซื้อ" : errorMessage(loadError)}
        </p>
        <Link href="/">กลับหน้าแรก</Link>
      </main>
    );
  }

  if (!order) {
    return (
      <main className="container">
        <p className="muted">กำลังโหลด...</p>
      </main>
    );
  }

  const lastPayment = order.latest_payment;
  const canPay = omiseReady && !submitting;

  return (
    <main className="container">
      <Script
        src={OMISE_JS_URL}
        strategy="afterInteractive"
        onReady={() => {
          try {
            initOmise(OMISE_PUBLIC_KEY);
            setOmiseReady(true);
          } catch (err) {
            setOmiseError(errorMessage(err));
          }
        }}
        onError={() => setOmiseError("โหลด Omise.js ไม่สำเร็จ")}
      />

      <h1>ชำระเงิน</h1>

      <section className="card summary">
        <div>
          <div className="muted">สินค้า</div>
          <div className="summary-name">{order.product_name}</div>
        </div>
        <div className="summary-amount">{formatAmount(order.amount, order.currency)}</div>
      </section>

      {lastPayment?.status === "failed" && !payError && (
        <p className="alert alert-error">
          ครั้งก่อนไม่สำเร็จ: {lastPayment.failure_message || "การชำระเงินไม่สำเร็จ"}
        </p>
      )}
      {lastPayment?.status === "expired" && !payError && (
        <p className="alert alert-warning">QR ครั้งก่อนหมดอายุ กรุณาทำรายการใหม่</p>
      )}

      {omiseError && <p className="alert alert-error">{omiseError}</p>}
      {!omiseReady && !omiseError && <p className="muted">กำลังโหลด Omise.js...</p>}

      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={method === "card"}
          className={`tab ${method === "card" ? "tab-active" : ""}`}
          onClick={() => setMethod("card")}
          disabled={submitting}
        >
          บัตรเครดิต/เดบิต
        </button>
        <button
          role="tab"
          aria-selected={method === "promptpay"}
          className={`tab ${method === "promptpay" ? "tab-active" : ""}`}
          onClick={() => setMethod("promptpay")}
          disabled={submitting}
        >
          PromptPay
        </button>
      </div>

      {payError && (
        <div className="alert alert-error">
          <p>{payError}</p>
          <Link href={resultPath}>ตรวจสอบสถานะคำสั่งซื้อ</Link>
        </div>
      )}

      {method === "card" ? (
        <form className="card form" onSubmit={handleCardSubmit} autoComplete="on">
          <label>
            ชื่อบนบัตร
            <input name="name" autoComplete="cc-name" required />
          </label>
          <label>
            หมายเลขบัตร
            <input
              name="number"
              inputMode="numeric"
              autoComplete="cc-number"
              pattern="[\d ]{12,23}"
              required
            />
          </label>
          <div className="row">
            <label>
              เดือนหมดอายุ
              <input
                name="expiration_month"
                inputMode="numeric"
                autoComplete="cc-exp-month"
                placeholder="MM"
                pattern="\d{1,2}"
                required
              />
            </label>
            <label>
              ปีหมดอายุ
              <input
                name="expiration_year"
                inputMode="numeric"
                autoComplete="cc-exp-year"
                placeholder="YYYY"
                pattern="\d{4}"
                required
              />
            </label>
            <label>
              CVV
              <input
                name="security_code"
                inputMode="numeric"
                autoComplete="cc-csc"
                pattern="\d{3,4}"
                required
              />
            </label>
          </div>
          <button className="button" type="submit" disabled={!canPay}>
            {submitting ? "กำลังดำเนินการ..." : `จ่าย ${formatAmount(order.amount, order.currency)}`}
          </button>
          <p className="muted small">
            ข้อมูลบัตรส่งตรงไปที่ Omise ไม่ผ่านเซิร์ฟเวอร์ของเรา (test mode ไม่มีการตัดเงินจริง)
          </p>
        </form>
      ) : (
        <div className="card form">
          <p>สร้าง QR PromptPay แล้วสแกนจ่ายภายในเวลาที่กำหนด</p>
          <button className="button" onClick={() => handlePromptPay(order)} disabled={!canPay}>
            {submitting ? "กำลังสร้าง QR..." : "สร้าง QR PromptPay"}
          </button>
        </div>
      )}
    </main>
  );
}
