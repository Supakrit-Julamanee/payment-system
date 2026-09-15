"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { errorStatus } from "@/lib/api";
import { formatAmount, formatCountdown } from "@/lib/format";
import type { Order, Payment } from "@/lib/types";
import { useOrderPolling } from "@/lib/useOrderPolling";

function useSecondsLeft(expiresAt: string | null): number | null {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  if (!expiresAt) return null;
  return Math.max(0, Math.floor((Date.parse(expiresAt) - now) / 1000));
}

function RetryLink({ orderId }: { orderId: string }) {
  return (
    <Link className="button" href={`/checkout/${orderId}`}>
      ลองอีกครั้ง
    </Link>
  );
}

function PromptPayQr({ orderId, payment }: { orderId: string; payment: Payment }) {
  const secondsLeft = useSecondsLeft(payment.expires_at);

  // Spec §12.4 step 5: hide the QR once expires_at passes, even if the backend
  // still says pending.
  if (secondsLeft === 0) {
    return (
      <div className="card center">
        <p className="alert alert-warning">QR หมดอายุ</p>
        <RetryLink orderId={orderId} />
      </div>
    );
  }

  return (
    <div className="card center">
      <p>สแกน QR เพื่อชำระเงิน</p>
      {/* External image from Omise, so a plain <img> instead of next/image. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="qr" src={payment.qr_image_url ?? ""} alt="PromptPay QR code" />
      {secondsLeft !== null && (
        <p className="countdown">หมดอายุใน {formatCountdown(secondsLeft)}</p>
      )}
      <p className="muted">กำลังตรวจสอบการชำระเงิน...</p>
    </div>
  );
}

interface StatusBodyProps {
  orderId: string;
  order: Order;
  timedOut: boolean;
}

function StatusBody({ orderId, order, timedOut }: StatusBodyProps) {
  const payment = order.latest_payment;

  if (order.status === "paid") {
    return <p className="alert alert-success">ชำระเงินสำเร็จ</p>;
  }

  if (!payment) {
    return (
      <div className="card center">
        <p>ยังไม่มีการชำระเงินสำหรับคำสั่งซื้อนี้</p>
        <Link className="button" href={`/checkout/${orderId}`}>
          ไปหน้าชำระเงิน
        </Link>
      </div>
    );
  }

  if (payment.status === "failed") {
    return (
      <div className="card center">
        <p className="alert alert-error">
          {payment.failure_message || "การชำระเงินไม่สำเร็จ"}
        </p>
        <RetryLink orderId={orderId} />
      </div>
    );
  }

  if (payment.status === "expired") {
    return (
      <div className="card center">
        <p className="alert alert-warning">QR หมดอายุ</p>
        <RetryLink orderId={orderId} />
      </div>
    );
  }

  // pending
  if (timedOut) {
    return <p className="alert alert-warning">ยังไม่ได้รับผล กรุณารีเฟรชภายหลัง</p>;
  }

  if (payment.method === "promptpay" && payment.qr_image_url) {
    return <PromptPayQr orderId={orderId} payment={payment} />;
  }

  return (
    <div className="card center">
      <div className="spinner" aria-hidden="true" />
      <p>กำลังตรวจสอบการชำระเงิน...</p>
    </div>
  );
}

export default function OrderStatusClient({ orderId }: { orderId: string }) {
  const { order, error, timedOut } = useOrderPolling(orderId);

  if (errorStatus(error) === 404) {
    return (
      <main className="container">
        <h1>สถานะคำสั่งซื้อ</h1>
        <p className="alert alert-error">ไม่พบคำสั่งซื้อ</p>
        <Link href="/">กลับหน้าแรก</Link>
      </main>
    );
  }

  return (
    <main className="container">
      <h1>สถานะคำสั่งซื้อ</h1>

      {error && <p className="alert alert-warning">{error.message} กำลังลองใหม่...</p>}

      {!order ? (
        <p className="muted">กำลังโหลด...</p>
      ) : (
        <>
          <section className="card summary">
            <div>
              <div className="muted">สินค้า</div>
              <div className="summary-name">{order.product_name}</div>
            </div>
            <div className="summary-amount">{formatAmount(order.amount, order.currency)}</div>
          </section>
          <StatusBody orderId={orderId} order={order} timedOut={timedOut} />
        </>
      )}

      <p>
        <Link href="/">กลับหน้าแรก</Link>
      </p>
    </main>
  );
}
