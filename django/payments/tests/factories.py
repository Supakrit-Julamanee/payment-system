from payments.models import Order, Payment, PaymentMethod


def make_order(**fields) -> Order:
    values = {"product_id": "coffee", "amount": 6000, "currency": "thb"} | fields
    return Order.objects.create(**values)


def make_payment(order: Order, **fields) -> Payment:
    values = {"method": PaymentMethod.CARD, "amount": order.amount, "currency": order.currency} | fields
    return Payment.objects.create(order=order, **values)


def make_charge(payment: Payment, **fields) -> dict:
    """A fake Omise charge for `payment`. Only the fields apply_charge reads."""
    charge = {
        "object": "charge",
        "id": payment.charge_id or f"chrg_test_{payment.pk.hex[:16]}",
        "amount": payment.amount,
        "currency": payment.currency,
        "status": "pending",
        "authorize_uri": None,
        "expires_at": None,
        "failure_code": None,
        "failure_message": None,
        "source": None,
        "metadata": {"order_id": str(payment.order_id), "payment_id": str(payment.pk)},
    }
    charge.update(fields)
    return charge
