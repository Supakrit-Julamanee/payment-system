import Link from "next/link";
import { getPublicKeyError } from "@/lib/config";
import CheckoutClient from "./CheckoutClient";

export default async function CheckoutPage({ params }: PageProps<"/checkout/[orderId]">) {
  const { orderId } = await params;

  // Test-mode guard: with a missing or non-test key, Omise.js is never loaded.
  const keyError = getPublicKeyError();
  if (keyError) {
    return (
      <main className="container">
        <h1>ชำระเงิน</h1>
        <p className="alert alert-error">{keyError}</p>
        <Link href="/">กลับหน้าแรก</Link>
      </main>
    );
  }

  return <CheckoutClient orderId={orderId} />;
}
