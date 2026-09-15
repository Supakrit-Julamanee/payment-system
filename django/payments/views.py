"""API views (spec §7).

Database parts are done. Steps that need the Omise client are not built yet and return
501 not_implemented; each TODO(omise) names the spec section to follow.
"""

import json

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ApiError
from .models import Order, OrderStatus
from .serializers import latest_payment_for, serialize_order
from .services import begin_webhook_event, create_order, find_reusable_payment, mark_webhook_processed
from .validation import parse_create_order, parse_order_id, parse_pay_request


def not_implemented(feature: str) -> ApiError:
    return ApiError(status.HTTP_501_NOT_IMPLEMENTED, "not_implemented", f"{feature} is not implemented yet.")


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
                return Response(serialize_order(order, reusable), status=status.HTTP_200_OK)

            # TODO(omise, §7.2 step 3): payment = create_pending_payment(order, pay_request.method)
            #   here, and let this atomic block commit before calling Omise. It is not called
            #   yet so that every click doesn't leave a Payment with charge_id null behind.

        # TODO(omise, §7.2 steps 4-5, §13.2): outside the transaction, create the charge
        #   (timeout 30 s, return_uri {FRONTEND_URL}/orders/{order_id}, metadata order_id and
        #   payment_id), then:
        #   2xx -> apply_charge(charge), 201 with serialize_order
        #   4xx -> Payment failed with Omise failure_code/message, 402 payment_failed
        #   timeout/network/5xx -> Payment stays pending, charge_id null, log, 502 gateway_unavailable
        raise not_implemented("Charging with Omise")


class OmiseWebhookView(APIView):
    """POST /api/webhooks/omise/ (spec §7.4, §10).

    No authentication. APIView.as_view() already applies csrf_exempt.
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

        # Steps 2-3.
        webhook_event = begin_webhook_event(event_id, event_key[:64], event)
        if webhook_event is None:
            return Response(status=status.HTTP_200_OK)

        # Step 4.
        data = event.get("data")
        if not isinstance(data, dict) or data.get("object") != "charge":
            mark_webhook_processed(webhook_event)
            return Response(status=status.HTTP_200_OK)

        # TODO(omise, §10 steps 5-7): never trust the body. retrieve_charge(data["id"]):
        #   404 -> mark_webhook_processed, log warning, 200 (probably a fake webhook)
        #   timeout/5xx -> 500 without marking processed, so Omise retries
        #   otherwise apply_charge(charge), mark_webhook_processed, 200
        # Until then processed_at stays null, which is the correct "not processed" state.
        raise not_implemented("Fetching the charge from Omise")
