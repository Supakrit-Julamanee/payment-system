import OrderStatusClient from "./OrderStatusClient";

// Also the 3DS return_uri. The query string Omise appends is ignored on purpose:
// the result always comes from GET /api/orders/{id}/ (spec §12.5, §14 rule 13).
export default async function OrderPage({ params }: PageProps<"/orders/[orderId]">) {
  const { orderId } = await params;
  return <OrderStatusClient orderId={orderId} />;
}
