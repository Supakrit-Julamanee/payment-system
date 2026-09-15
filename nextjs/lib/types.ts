// API shapes from spec §7. Amounts are integer satang.

export type OrderStatus = "pending" | "paid";
export type PaymentStatus = "pending" | "successful" | "failed" | "expired";
export type PaymentMethod = "card" | "promptpay";

export interface Payment {
  id: string;
  method: PaymentMethod;
  status: PaymentStatus;
  authorize_uri: string | null;
  qr_image_url: string | null;
  expires_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface Order {
  id: string;
  product_id: string;
  product_name: string;
  amount: number;
  currency: string;
  status: OrderStatus;
  paid_at?: string | null;
  latest_payment: Payment | null;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
