"use client";

import { useEffect, useState } from "react";
import { ApiError, errorStatus, getOrder } from "./api";
import type { Order } from "./types";

export const POLL_INTERVAL_MS = 3000;
export const POLL_TIMEOUT_MS = 10 * 60 * 1000;

// Spec §12.5: stop once the order is paid or the latest payment failed/expired.
export function isFinal(order: Order | null): boolean {
  if (!order) return false;
  if (order.status === "paid") return true;
  const status = order.latest_payment?.status;
  return status === "failed" || status === "expired";
}

export interface OrderPollingState {
  order: Order | null;
  error: Error | null;
  timedOut: boolean;
}

// Polls GET /api/orders/{id}/ every 3 s. Django is the only source of the result;
// the query string Omise redirects back with is never read.
export function useOrderPolling(orderId: string): OrderPollingState {
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();

    async function tick() {
      try {
        const data = await getOrder(orderId);
        if (cancelled) return;
        setOrder(data);
        setError(null);
        // No payment yet means there is nothing to wait for.
        if (isFinal(data) || !data.latest_payment) return;
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err : new ApiError(0, "unknown_error", String(err)));
        if (errorStatus(err) === 404) return;
        // Network errors and 5xx are transient: keep polling.
      }

      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        setTimedOut(true);
        return;
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    }

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [orderId]);

  return { order, error, timedOut };
}
