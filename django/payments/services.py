"""Database-side payment logic (spec §6, §7, §9, §10).

apply_charge is the only function that changes Payment or Order status based on a charge.
It never calls Omise: callers pass a charge they fetched with the secret key.
"""

import logging
import uuid
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Order, OrderStatus, Payment, PaymentStatus, WebhookEvent
from .products import CURRENCY, PRODUCTS

logger = logging.getLogger(__name__)

GATEWAY_UNREACHABLE = "gateway_unreachable"

# Spec §13.4. Any other charge status leaves the payment unchanged.
CHARGE_STATUS_TO_PAYMENT_STATUS = {
    "pending": PaymentStatus.PENDING,
    "successful": PaymentStatus.SUCCESSFUL,
    "failed": PaymentStatus.FAILED,
    "reversed": PaymentStatus.FAILED,
    "expired": PaymentStatus.EXPIRED,
}


def map_charge_status(charge_status: object) -> str | None:
    if not isinstance(charge_status, str):
        return None
    return CHARGE_STATUS_TO_PAYMENT_STATUS.get(charge_status)


# --- Orders and payments (spec §7.1, §7.2) ---


def create_order(product_id: str) -> Order:
    """product_id must already be validated. The amount always comes from PRODUCTS."""
    return Order.objects.create(
        product_id=product_id,
        amount=PRODUCTS[product_id]["amount"],
        currency=CURRENCY,
        status=OrderStatus.PENDING,
    )


def find_reusable_payment(order: Order, method: str) -> Payment | None:
    """Spec §7.2 step 2. Call while holding the order lock."""
    return (
        order.payments.filter(status=PaymentStatus.PENDING, method=method, charge_id__isnull=False)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .order_by("-created_at")
        .first()
    )


def create_pending_payment(order: Order, method: str) -> Payment:
    """Spec §7.2 step 3. Call while holding the order lock, and let that transaction
    commit before calling Omise so the Payment survives if the request dies."""
    return Payment.objects.create(
        order=order,
        method=method,
        amount=order.amount,
        currency=order.currency,
        status=PaymentStatus.PENDING,
    )


def mark_payment_failed(payment: Payment, failure_code: str, failure_message: str) -> Payment:
    """Spec §7.2: Omise rejected the request with a 4xx, so no charge exists.

    This is the only status change that does not come from a charge. A Payment that is
    no longer pending is left alone, so a late webhook always wins.
    """
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status != PaymentStatus.PENDING:
            return locked
        locked.status = PaymentStatus.FAILED
        locked.failure_code = failure_code[:255]
        locked.failure_message = failure_message
        locked.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
    return locked


# --- apply_charge (spec §9) ---


def _str_or_none(value: object, max_length: int | None = None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:max_length] if max_length else value


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_datetime(value)
    except ValueError:
        return None


def _qr_image_url(charge: dict) -> str | None:
    # Verified 2026-09-16 against https://docs.omise.co/promptpay: the QR image lives at
    # charge.source.scannable_code.image.download_uri.
    try:
        url = charge["source"]["scannable_code"]["image"]["download_uri"]
    except (KeyError, TypeError):
        return None
    return _str_or_none(url)


def _find_payment(charge_id: str, charge: dict) -> Payment | None:
    payment = Payment.objects.filter(charge_id=charge_id).first()
    if payment is not None:
        return payment

    metadata = charge.get("metadata")
    payment_id = metadata.get("payment_id") if isinstance(metadata, dict) else None
    try:
        payment_uuid = uuid.UUID(str(payment_id))
    except ValueError:
        return None
    return Payment.objects.filter(pk=payment_uuid).first()


def apply_charge(charge: dict) -> Payment | None:
    """Copy an Omise charge into Payment/Order. Idempotent.

    Returns the Payment it updated, or None when the charge was ignored.
    """
    charge_id = charge.get("id")
    if not isinstance(charge_id, str) or not charge_id:
        logger.warning("apply_charge: charge without an id was ignored")
        return None

    # Step 1: find the Payment.
    found = _find_payment(charge_id, charge)
    if found is None:
        logger.warning("apply_charge: no payment matches charge %s", charge_id)
        return None

    # Step 2: amount and currency must match.
    currency = charge.get("currency")
    if charge.get("amount") != found.amount or not isinstance(currency, str) or currency.lower() != found.currency:
        logger.error("apply_charge: amount/currency mismatch for charge %s (payment %s)", charge_id, found.pk)
        return None

    # Step 3: lock Order before Payment, always, to avoid deadlocks.
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=found.order_id)
        payment = Payment.objects.select_for_update().get(pk=found.pk)

        if payment.charge_id is None:
            payment.charge_id = charge_id
        elif payment.charge_id != charge_id:
            # Found through metadata, but this payment already belongs to another charge.
            logger.error(
                "apply_charge: payment %s already has a different charge; charge %s was ignored",
                payment.pk,
                charge_id,
            )
            return None

        new_status = map_charge_status(charge.get("status"))
        was_gateway_unreachable = (
            payment.status == PaymentStatus.FAILED and payment.failure_code == GATEWAY_UNREACHABLE
        )
        is_final = payment.status in (PaymentStatus.SUCCESSFUL, PaymentStatus.EXPIRED) or (
            payment.status == PaymentStatus.FAILED and not was_gateway_unreachable
        )
        # Step 6 (spec §6.1): gateway_unreachable may only move to successful.
        can_transition = (
            new_status is not None
            and new_status != payment.status
            and not is_final
            and (not was_gateway_unreachable or new_status == PaymentStatus.SUCCESSFUL)
        )

        # Step 4: copy charge details.
        payment.authorize_uri = _str_or_none(charge.get("authorize_uri"), 2048)
        payment.qr_image_url = _str_or_none(_qr_image_url(charge), 2048)
        payment.expires_at = _parse_datetime(charge.get("expires_at"))
        # Keep gateway_unreachable until the payment actually succeeds, otherwise the
        # exception in §6.1 would be lost the first time a pending charge is applied.
        if not was_gateway_unreachable or can_transition:
            payment.failure_code = _str_or_none(charge.get("failure_code"), 255)
            payment.failure_message = _str_or_none(charge.get("failure_message"))

        if new_status is None:
            logger.warning("apply_charge: unknown status %r on charge %s", charge.get("status"), charge_id)

        # Step 7: change status.
        order_changed = False
        if can_transition:
            payment.status = new_status
            if new_status == PaymentStatus.SUCCESSFUL:
                if order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.PAID
                    order.paid_at = timezone.now()
                    order_changed = True
                else:
                    # The money has already moved, so record it instead of rejecting it.
                    payment.needs_refund = True
                    logger.warning(
                        "Order %s was already paid; payment %s (charge %s) also succeeded and needs a manual refund",
                        order.pk,
                        payment.pk,
                        charge_id,
                    )

        if order_changed:
            order.save(update_fields=["status", "paid_at", "updated_at"])
        payment.save()
        # Step 8: commit when the atomic block exits.

    return payment


# --- Webhook events (spec §10) ---


def begin_webhook_event(event_id: str, event_key: str, payload: dict) -> WebhookEvent | None:
    """Steps 2-3: return None if the event was already processed, otherwise store it
    (processed_at stays null). Concurrent deliveries are safe because apply_charge is idempotent."""
    with transaction.atomic():
        event, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={"event_key": event_key, "payload": payload},
        )
        if event.processed_at is not None:
            return None
        if not created:
            event.event_key = event_key
            event.payload = payload
            event.save(update_fields=["event_key", "payload"])
        return event


def mark_webhook_processed(event: WebhookEvent) -> None:
    event.processed_at = timezone.now()
    event.save(update_fields=["processed_at"])
