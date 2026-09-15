"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createOrder, errorMessage } from "@/lib/api";

export default function BuyButton({ productId }: { productId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);
    try {
      const order = await createOrder(productId);
      router.push(`/checkout/${order.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <>
      <button className="button" onClick={handleClick} disabled={pending}>
        {pending ? "กำลังสร้างคำสั่งซื้อ..." : "ซื้อ"}
      </button>
      {error && <p className="alert alert-error">{error}</p>}
    </>
  );
}
