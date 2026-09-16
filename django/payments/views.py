"""API views (spec §7)."""

import json
import logging

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import omise_client
from .exceptions import ApiError, error_body
from .models import Order, OrderStatus, PaymentMethod
from .omise_client import OmiseError, OmiseNotFound, OmiseUnavailable
from .serializers import latest_payment_for, serialize_order
from .services import (
    apply_charge,
    begin_webhook_event,
    create_order,
    create_pending_payment,
    find_reusable_payment,
    mark_payment_failed,
    mark_webhook_processed,
)
from .validation import parse_create_order, parse_order_id, parse_pay_request

logger = logging.getLogger(__name__)


def order_not_found() -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "order_not_found", "Order not found.")


class OrderCreateView(APIView):
    """POST /api/orders/ (spec §7.1)"""

    def post(self, request):
        product_id = parse_create_order(request.data)
        order = create_order(product_id)
        return Response(serialize_order(order, latest_payment=None), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """GET /api/orders/{order_id}/ (spec §7.3). Read-only, never calls Omise."""

    def get(self, request, order_id: str):
        order = Order.objects.filter(pk=parse_order_id(order_id)).first()
        if order is None:
            raise order_not_found()
        return Response(serialize_order(order, latest_payment_for(order)))


class OrderPayView(APIView):
    """POST /api/orders/{order_id}/pay/ (spec §7.2)"""

    def post(self, request, order_id: str):
        order_uuid = parse_order_id(order_id)

        # Hold the order lock through validation, reuse and Payment creation.
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=order_uuid).first()
            if order is None:
                raise order_not_found()
            pay_request = parse_pay_request(request.data)
            if order.status == OrderStatus.PAID:
                raise ApiError(status.HTTP_409_CONFLICT, "order_already_paid", "This order has already been paid.")

            reusable = find_reusable_payment(order, pay_request.method)
            if reusable is not None:
                # A double click reuses the charge instead of creating a second one.
                return Response(serialize_order(order, reusable), status=status.HTTP_200_OK)

            payment = create_pending_payment(order, pay_request.method)
        # The Payment is committed here, before Omise is called, so the charge is never
        # lost if this request dies (spec §7.2 step 3).

        try:
            charge = omise_client.create_charge(
                amount=payment.amount,
                currency=payment.currency,
                order_id=order.id,
                payment_id=payment.id,
                token=pay_request.token,
                source=pay_request.source,
                # 3DS sends the browser back here; that page asks Django for the result.
                return_uri=(
                    f"{settings.FRONTEND_URL}/orders/{order.id}"
                    if pay_request.method == PaymentMethod.CARD
                    else None
                ),
            )
        except OmiseError as exc:
            # 4xx: no charge was created, so this attempt failed for good.
            mark_payment_failed(payment, exc.code, exc.message)
            raise ApiError(status.HTTP_402_PAYMENT_REQUIRED, "payment_failed", exc.message) from None
        except OmiseUnavailable:
            # The charge may exist, so the Payment stays pending with charge_id null.
            # The sync job marks it gateway_unreachable after 15 minutes (§11 case C).
            logger.error("Omise unreachable while charging payment %s", payment.pk)
            raise ApiError(
                status.HTTP_502_BAD_GATEWAY,
                "gateway_unavailable",
                "The payment gateway did not respond. Check the order status before trying again.",
            ) from None

        apply_charge(charge)
        order.refresh_from_db()
        payment.refresh_from_db()
        return Response(serialize_order(order, payment), status=status.HTTP_201_CREATED)


class OmiseWebhookView(APIView):
    """POST /api/webhooks/omise/ (spec §7.4, §10).

    No authentication. APIView.as_view() already applies csrf_exempt, and the body is
    never trusted: the charge is always fetched from Omise with the secret key.
    """

    def post(self, request):
        # Step 1. Parse the raw body so a wrong Content-Type still gets 400, not 415.
        try:
            event = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_json", "Body must be JSON.") from None

        event_id = event.get("id") if isinstance(event, dict) else None
        if not isinstance(event_id, str) or not event_id or len(event_id) > 64:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_event", "Event id is missing or invalid.")
        event_key = event.get("key") if isinstance(event.get("key"), str) else ""

        # Steps 2-3: skip events already processed, otherwise store this one unprocessed.
        webhook_event = begin_webhook_event(event_id, event_key[:64], event)
        if webhook_event is None:
            return Response(status=status.HTTP_200_OK)

        # Step 4: not about a charge, so it is not ours to act on.
        data = event.get("data")
        charge_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(data, dict) or data.get("object") != "charge" or not isinstance(charge_id, str) or not charge_id:
            mark_webhook_processed(webhook_event)
            return Response(status=status.HTTP_200_OK)

        # Step 5: fetch the real charge. The body could be forged.
        try:
            charge = omise_client.retrieve_charge(charge_id)
        except OmiseNotFound:
            logger.warning("Webhook %s references unknown charge %s (possibly forged)", event_id, charge_id)
            mark_webhook_processed(webhook_event)
            return Response(status=status.HTTP_200_OK)
        except (OmiseUnavailable, OmiseError):
            # processed_at stays null and Omise retries the delivery.
            logger.error("Could not fetch charge %s for webhook %s", charge_id, event_id)
            return Response(
                error_body("gateway_unavailable", "Could not verify the charge with Omise."),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Steps 6-7.
        apply_charge(charge)
        mark_webhook_processed(webhook_event)
        return Response(status=status.HTTP_200_OK)
