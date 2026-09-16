"""The /pay/ and webhook paths with the Omise client mocked (spec §17)."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from payments.models import Order, OrderStatus, Payment, PaymentMethod, PaymentStatus, WebhookEvent
from payments.omise_client import OmiseError, OmiseNotFound, OmiseUnavailable

from .factories import make_order, make_payment

CARD_BODY = {"method": "card", "token": "tokn_test_1"}
PROMPTPAY_BODY = {"method": "promptpay", "source": "src_test_1"}
QR_URL = "https://example.test/qr.png"


def charge_builder(**overrides):
    """Build the charge Omise would return for the arguments create_charge was called with."""

    def build(
        *,
        amount,
        currency,
        order_id,
        payment_id,
        token=None,
        source=None,
        return_uri=None,
        expires_at=None,
    ):
        charge = {
            "object": "charge",
            "id": "chrg_test_1",
            "amount": amount,
            "currency": currency,
            "status": "successful",
            "authorize_uri": None,
            # Omise echoes back the expiry it was given.
            "expires_at": expires_at,
            "failure_code": None,
            "failure_message": None,
            "source": None,
            "metadata": {"order_id": str(order_id), "payment_id": str(payment_id)},
        }
        charge.update(overrides)
        return charge

    return build


class PayWithOmiseTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.order = make_order()
        self.url = f"/api/orders/{self.order.id}/pay/"

    def test_successful_card_charge_pays_the_order(self):
        with patch("payments.omise_client.create_charge", side_effect=charge_builder()) as create_charge:
            response = self.api.post(self.url, CARD_BODY, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "paid")
        self.assertEqual(body["latest_payment"]["status"], "successful")
        self.order.refresh_from_db()
        payment = Payment.objects.get()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual((payment.status, payment.charge_id), (PaymentStatus.SUCCESSFUL, "chrg_test_1"))

        kwargs = create_charge.call_args.kwargs
        # The amount comes from the order, never from the request.
        self.assertEqual((kwargs["amount"], kwargs["currency"]), (6000, "thb"))
        self.assertEqual(kwargs["token"], "tokn_test_1")
        self.assertIsNone(kwargs["source"])
        self.assertEqual(kwargs["return_uri"], f"{settings.FRONTEND_URL}/orders/{self.order.id}")
        self.assertEqual((kwargs["order_id"], kwargs["payment_id"]), (self.order.id, payment.id))

    def test_client_amount_is_ignored(self):
        with patch("payments.omise_client.create_charge", side_effect=charge_builder()) as create_charge:
            self.api.post(self.url, CARD_BODY | {"amount": 1}, format="json")
        self.assertEqual(create_charge.call_args.kwargs["amount"], 6000)

    def test_3ds_charge_returns_authorize_uri_and_leaves_order_pending(self):
        build = charge_builder(status="pending", authorize_uri="https://omise.test/3ds", expires_at="2026-09-16T10:30:00Z")
        with patch("payments.omise_client.create_charge", side_effect=build):
            response = self.api.post(self.url, CARD_BODY, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        latest = response.json()["latest_payment"]
        self.assertEqual(latest["status"], "pending")
        self.assertEqual(latest["authorize_uri"], "https://omise.test/3ds")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_promptpay_charge_returns_qr_without_return_uri(self):
        build = charge_builder(
            status="pending",
            expires_at="2026-09-16T10:30:00Z",
            source={"scannable_code": {"image": {"download_uri": QR_URL}}},
        )
        with patch("payments.omise_client.create_charge", side_effect=build) as create_charge:
            response = self.api.post(self.url, PROMPTPAY_BODY, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        latest = response.json()["latest_payment"]
        self.assertEqual((latest["method"], latest["qr_image_url"]), ("promptpay", QR_URL))
        self.assertIsNotNone(latest["expires_at"])
        kwargs = create_charge.call_args.kwargs
        self.assertEqual(kwargs["source"], "src_test_1")
        self.assertIsNone(kwargs["return_uri"])
        # Omise's own 24 h default is used unless the setting below is on.
        self.assertIsNone(kwargs["expires_at"])

    @override_settings(PROMPTPAY_EXPIRES_IN_SECONDS=10)
    def test_promptpay_expiry_can_be_shortened_for_testing(self):
        build = charge_builder(status="pending", source={"scannable_code": {"image": {"download_uri": QR_URL}}})
        with patch("payments.omise_client.create_charge", side_effect=build) as create_charge:
            self.api.post(self.url, PROMPTPAY_BODY, format="json")

        sent = create_charge.call_args.kwargs["expires_at"]
        self.assertRegex(sent, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        seconds_ahead = (
            datetime.strptime(sent, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) - timezone.now()
        ).total_seconds()
        self.assertTrue(0 < seconds_ahead <= 10, seconds_ahead)

    @override_settings(PROMPTPAY_EXPIRES_IN_SECONDS=10)
    def test_card_charge_never_gets_an_expiry(self):
        with patch("payments.omise_client.create_charge", side_effect=charge_builder()) as create_charge:
            self.api.post(self.url, CARD_BODY, format="json")
        self.assertIsNone(create_charge.call_args.kwargs["expires_at"])

    def test_omise_4xx_marks_payment_failed_and_returns_402(self):
        error = OmiseError(code="insufficient_fund", message="Insufficient funds.", status_code=402)
        with patch("payments.omise_client.create_charge", side_effect=error):
            response = self.api.post(self.url, CARD_BODY, format="json")

        self.assertEqual(response.status_code, 402, response.content)
        self.assertEqual(response.json()["error"]["code"], "payment_failed")
        payment = Payment.objects.get()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_code, "insufficient_fund")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)  # the user can retry

    def test_gateway_timeout_returns_502_and_keeps_payment_pending(self):
        with patch("payments.omise_client.create_charge", side_effect=OmiseUnavailable("timeout")):
            response = self.api.post(self.url, CARD_BODY, format="json")

        self.assertEqual(response.status_code, 502, response.content)
        self.assertEqual(response.json()["error"]["code"], "gateway_unavailable")
        payment = Payment.objects.get()
        # Not failed: the charge may exist. The sync job decides later.
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertIsNone(payment.charge_id)

    def test_double_click_creates_only_one_charge(self):
        # Spec §17 scenario 7.
        build = charge_builder(status="pending", authorize_uri="https://omise.test/3ds")
        with patch("payments.omise_client.create_charge", side_effect=build) as create_charge:
            first = self.api.post(self.url, CARD_BODY, format="json")
            second = self.api.post(self.url, CARD_BODY, format="json")

        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(create_charge.call_count, 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(first.json()["latest_payment"]["id"], second.json()["latest_payment"]["id"])

    def test_paid_order_is_not_charged_again(self):
        with patch("payments.omise_client.create_charge", side_effect=charge_builder()):
            self.api.post(self.url, CARD_BODY, format="json")
        with patch("payments.omise_client.create_charge") as create_charge:
            response = self.api.post(self.url, PROMPTPAY_BODY, format="json")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"]["code"], "order_already_paid")
        create_charge.assert_not_called()


class WebhookWithOmiseTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.order = make_order()
        self.payment = make_payment(self.order, charge_id="chrg_test_1")
        self.event = {
            "object": "event",
            "id": "evnt_test_1",
            "key": "charge.complete",
            "data": {"object": "charge", "id": "chrg_test_1"},
        }

    def post_event(self, event=None):
        return self.api.post(
            "/api/webhooks/omise/", json.dumps(event or self.event), content_type="application/json"
        )

    def charge(self, **overrides):
        charge = {
            "object": "charge",
            "id": "chrg_test_1",
            "amount": self.payment.amount,
            "currency": self.payment.currency,
            "status": "successful",
            "metadata": {"payment_id": str(self.payment.pk)},
        }
        return charge | overrides

    def test_charge_event_is_verified_with_omise_and_applied(self):
        with patch("payments.omise_client.retrieve_charge", return_value=self.charge()) as retrieve:
            response = self.post_event()

        self.assertEqual(response.status_code, 200, response.content)
        retrieve.assert_called_once_with("chrg_test_1")
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertIsNotNone(WebhookEvent.objects.get(pk="evnt_test_1").processed_at)

    def test_duplicate_delivery_is_processed_once(self):
        # Spec §17 scenario 8.
        with patch("payments.omise_client.retrieve_charge", return_value=self.charge()) as retrieve:
            first = self.post_event()
            second = self.post_event()

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(retrieve.call_count, 1)

    def test_fake_webhook_gets_200_and_changes_nothing(self):
        # Spec §17 scenario 12: Omise does not know this charge.
        with patch("payments.omise_client.retrieve_charge", side_effect=OmiseNotFound("missing")):
            response = self.post_event()

        self.assertEqual(response.status_code, 200, response.content)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)
        self.assertEqual(self.order.status, OrderStatus.PENDING)
        self.assertIsNotNone(WebhookEvent.objects.get(pk="evnt_test_1").processed_at)

    def test_gateway_failure_returns_500_so_omise_retries(self):
        with patch("payments.omise_client.retrieve_charge", side_effect=OmiseUnavailable("timeout")):
            response = self.post_event()

        self.assertEqual(response.status_code, 500, response.content)
        self.assertIsNone(WebhookEvent.objects.get(pk="evnt_test_1").processed_at)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)

    def test_charge_event_without_charge_id_is_marked_processed(self):
        event = self.event | {"data": {"object": "charge"}}
        with patch("payments.omise_client.retrieve_charge") as retrieve:
            response = self.post_event(event)
        self.assertEqual(response.status_code, 200, response.content)
        retrieve.assert_not_called()
        self.assertIsNotNone(WebhookEvent.objects.get(pk="evnt_test_1").processed_at)

    def test_amount_mismatch_is_ignored(self):
        with patch("payments.omise_client.retrieve_charge", return_value=self.charge(amount=1)):
            with self.assertLogs("payments.services", "ERROR"):
                response = self.post_event()
        self.assertEqual(response.status_code, 200, response.content)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)
        self.assertEqual(self.order.status, OrderStatus.PENDING)
        self.assertEqual(Order.objects.count(), 1)
