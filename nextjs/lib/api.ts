import { API_BASE_URL } from "./config";
import type { ApiErrorBody, Order } from "./types";

// Error shape from Django: { "error": { "code": ..., "message": ... } } (spec §7).
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ";
}

export function errorStatus(err: unknown): number | null {
  return err instanceof ApiError ? err.status : null;
}

function isApiErrorBody(data: unknown): data is ApiErrorBody {
  return typeof data === "object" && data !== null && "error" in data;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
}

async function request<T>(path: string, { method = "GET", body }: RequestOptions = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้");
  }

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    // Non-JSON body; handled below.
  }

  if (!res.ok) {
    const apiError = isApiErrorBody(data) ? data.error : null;
    throw new ApiError(
      res.status,
      apiError?.code ?? "unknown_error",
      apiError?.message ?? `เกิดข้อผิดพลาด (${res.status})`,
    );
  }
  return data as T;
}

const orderPath = (orderId: string) => `/api/orders/${encodeURIComponent(orderId)}/`;

// The client only sends product_id. The price always comes from the backend.
export function createOrder(productId: string): Promise<Order> {
  return request<Order>("/api/orders/", { method: "POST", body: { product_id: productId } });
}

export function getOrder(orderId: string): Promise<Order> {
  return request<Order>(orderPath(orderId));
}

export function payWithCard(orderId: string, token: string): Promise<Order> {
  return request<Order>(`${orderPath(orderId)}pay/`, {
    method: "POST",
    body: { method: "card", token },
  });
}

export function payWithPromptPay(orderId: string, source: string): Promise<Order> {
  return request<Order>(`${orderPath(orderId)}pay/`, {
    method: "POST",
    body: { method: "promptpay", source },
  });
}
