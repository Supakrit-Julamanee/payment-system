"""Response bodies (spec §7.1–7.3). Never expose charge_id, metadata or needs_refund."""

from rest_framework import serializers

from .models import Order, OrderStatus, Payment, PaymentStatus
from .products import PRODUCTS


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "status",
            "authorize_uri",
            "qr_image_url",
            "expires_at",
            "failure_code",
            "failure_message",
        ]
        read_only_fields = fields


def latest_payment_for(order: Order) -> Payment | None:
    """Spec §7.3: a paid order shows its effective successful payment, otherwise the newest one."""
    if order.status == OrderStatus.PAID:
        return order.payments.filter(status=PaymentStatus.SUCCESSFUL, needs_refund=False).first()
    return order.payments.order_by("-created_at").first()


def serialize_order(order: Order, latest_payment: Payment | None) -> dict:
    product = PRODUCTS.get(order.product_id)
    return {
        "id": str(order.id),
        "product_id": order.product_id,
        "product_name": product["name"] if product else order.product_id,
        "amount": order.amount,
        "currency": order.currency,
        "status": order.status,
        "paid_at": serializers.DateTimeField().to_representation(order.paid_at) if order.paid_at else None,
        "latest_payment": PaymentSerializer(latest_payment).data if latest_payment else None,
    }
