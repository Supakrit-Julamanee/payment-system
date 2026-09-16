import json
import uuid

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from payments.models import Order, OrderStatus, Payment, PaymentMethod, PaymentStatus, WebhookEvent
from payments.products import PRODUCTS
from payments.validation import PayRequest

from .factories import make_order, make_payment

CARD_BODY = {"method": "card", "token": "tokn_test_1"}
PAYMENT_FIELDS = {
    "id",
    "method",
    "status",
    "authorize_uri",
    "qr_image_url",
    "expires_at",
    "failure_code",
    "failure_message",
}
ORDER_FIELDS = {"id", "product_id", "product_name", "amount", "currency", "status", "paid_at", "latest_payment"}


class ApiTestCase(TestCase):
    def setUp(self):
        self.api = APIClient()

    def assertError(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(body["error"]["code"], code)
        self.assertIsInstance(body["error"]["message"], str)


class CreateOrderTests(ApiTestCase):
    url = "/api/orders/"

    def test_creates_pending_order_with_catalog_price(self):
        # Spec §17 scenario 11: the amount sent by the client is ignored.
        response = self.api.post(self.url, {"product_id": "coffee", "amount": 1}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(
            body,
            {
                "id": body["id"],
                "product_id": "coffee",
                "product_name": "Coffee",
                "amount": 6000,
                "currency": "thb",
                "status": "pending",
                "paid_at": None,
                "latest_payment": None,
            },
        )
        self.assertEqual(Order.objects.get(pk=body["id"]).amount, 6000)

    def test_unknown_product(self):
        self.assertError(self.api.post(self.url, {"product_id": "car"}, format="json"), 400, "invalid_product")

    def test_missing_or_non_string_product(self):
        for body in ({}, {"product_id": None}, {"product_id": ["coffee"]}):
            with self.subTest(body=body):
                self.assertError(self.api.post(self.url, body, format="json"), 400, "invalid_product")
        self.assertEqual(Order.objects.count(), 0)

    def test_malformed_json(self):
        self.assertError(self.api.post(self.url, "{", content_type="application/json"), 400, "invalid_json")

    def test_get_not_allowed(self):
        self.assertError(self.api.get(self.url), 405, "method_not_allowed")


class OrderDetailTests(ApiTestCase):
    def test_unknown_order(self):
        for order_id in ("123", str(uuid.uuid4())):
            with self.subTest(order_id=order_id):
                self.assertError(self.api.get(f"/api/orders/{order_id}/"), 404, "order_not_found")

    def test_pending_order_returns_newest_payment(self):
        order = make_order()
        make_payment(order, status=PaymentStatus.FAILED, charge_id="chrg_test_1")
        newest = make_payment(
            order, method=PaymentMethod.PROMPTPAY, charge_id="chrg_test_2", qr_image_url="https://example.test/qr.png"
        )
        body = self.api.get(f"/api/orders/{order.id}/").json()
        self.assertEqual(body["latest_payment"]["id"], str(newest.id))
        self.assertEqual(body["latest_payment"]["qr_image_url"], "https://example.test/qr.png")

    def test_paid_order_returns_effective_successful_payment(self):
        order = make_order(status=OrderStatus.PAID, paid_at=timezone.now())
        effective = make_payment(order, status=PaymentStatus.SUCCESSFUL, charge_id="chrg_test_1")
        make_payment(
            order,
            method=PaymentMethod.PROMPTPAY,
            status=PaymentStatus.SUCCESSFUL,
            needs_refund=True,
            charge_id="chrg_test_2",
        )
        body = self.api.get(f"/api/orders/{order.id}/").json()
        self.assertEqual(body["status"], "paid")
        self.assertIsNotNone(body["paid_at"])
        self.assertEqual(body["latest_payment"]["id"], str(effective.id))

    def test_response_hides_internal_fields(self):
        order = make_order()
        make_payment(order, charge_id="chrg_test_secret")
        response = self.api.get(f"/api/orders/{order.id}/")
        body = response.json()
        self.assertEqual(set(body), ORDER_FIELDS)
        self.assertEqual(set(body["latest_payment"]), PAYMENT_FIELDS)
        self.assertNotIn(b"chrg_test_secret", response.content)


class PayTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.order = make_order()
        self.url = f"/api/orders/{self.order.id}/pay/"

    def test_unknown_order(self):
        for order_id in ("123", str(uuid.uuid4())):
            with self.subTest(order_id=order_id):
                response = self.api.post(f"/api/orders/{order_id}/pay/", CARD_BODY, format="json")
                self.assertError(response, 404, "order_not_found")

    def test_invalid_method(self):
        for body in ({}, {"method": "bitcoin"}, {"method": None}):
            with self.subTest(body=body):
                self.assertError(self.api.post(self.url, body, format="json"), 400, "invalid_method")

    def test_card_needs_token(self):
        for token in (None, "", "src_test_1", 123):
            with self.subTest(token=token):
                response = self.api.post(self.url, {"method": "card", "token": token}, format="json")
                self.assertError(response, 400, "invalid_token")

    def test_promptpay_needs_source(self):
        for source in (None, "", "tokn_test_1"):
            with self.subTest(source=source):
                response = self.api.post(self.url, {"method": "promptpay", "source": source}, format="json")
                self.assertError(response, 400, "invalid_source")

    def test_paid_order_conflict(self):
        # Spec §17 scenario 13.
        order = make_order(status=OrderStatus.PAID, paid_at=timezone.now())
        response = self.api.post(f"/api/orders/{order.id}/pay/", CARD_BODY, format="json")
        self.assertError(response, 409, "order_already_paid")

    def test_body_validation_comes_before_paid_check(self):
        order = make_order(status=OrderStatus.PAID, paid_at=timezone.now())
        response = self.api.post(f"/api/orders/{order.id}/pay/", {"method": "bitcoin"}, format="json")
        self.assertError(response, 400, "invalid_method")

    def test_reuses_pending_payment(self):
        # Spec §17 scenario 7 (the database part).
        payment = make_payment(self.order, charge_id="chrg_test_1", authorize_uri="https://example.test/3ds")
        response = self.api.post(self.url, CARD_BODY, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        latest = response.json()["latest_payment"]
        self.assertEqual(latest["id"], str(payment.id))
        self.assertEqual(latest["authorize_uri"], "https://example.test/3ds")
        self.assertEqual(Payment.objects.count(), 1)

    def test_pay_request_repr_hides_token_and_source(self):
        text = repr(PayRequest(method="card", token="tokn_test_secret")) + repr(
            PayRequest(method="promptpay", source="src_test_secret")
        )
        self.assertNotIn("secret", text)


class WebhookTests(ApiTestCase):
    url = "/api/webhooks/omise/"

    def post_event(self, event):
        body = event if isinstance(event, str) else json.dumps(event)
        return self.api.post(self.url, body, content_type="application/json")

    def test_non_json_body(self):
        self.assertEqual(self.post_event("not json").status_code, 400)

    def test_missing_or_invalid_event_id(self):
        for body in ('{"key": "charge.complete"}', "[]", '{"id": ""}', json.dumps({"id": "e" * 65})):
            with self.subTest(body=body[:30]):
                self.assertEqual(self.post_event(body).status_code, 400)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_non_charge_event_is_marked_processed(self):
        response = self.post_event({"id": "evnt_test_1", "key": "customer.create", "data": {"object": "customer"}})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(WebhookEvent.objects.get(pk="evnt_test_1").processed_at)

    def test_processed_event_is_not_processed_again(self):
        # Spec §17 scenario 8 (the database part).
        event = {"id": "evnt_test_1", "key": "customer.create", "data": {"object": "customer"}}
        self.post_event(event)
        processed_at = WebhookEvent.objects.get(pk="evnt_test_1").processed_at
        response = self.post_event(event | {"key": "changed"})
        self.assertEqual(response.status_code, 200)
        stored = WebhookEvent.objects.get(pk="evnt_test_1")
        self.assertEqual((stored.processed_at, stored.event_key), (processed_at, "customer.create"))


class ProductCatalogTests(TestCase):
    def test_amounts_are_positive_integers(self):
        for product_id, product in PRODUCTS.items():
            with self.subTest(product_id=product_id):
                self.assertIs(type(product["amount"]), int)
                self.assertGreater(product["amount"], 0)


class CorsAndErrorFormatTests(ApiTestCase):
    def test_preflight_allows_frontend_origin(self):
        response = self.api.options(
            "/api/orders/", HTTP_ORIGIN=settings.FRONTEND_URL, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST"
        )
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), settings.FRONTEND_URL)

    def test_preflight_rejects_other_origin(self):
        response = self.api.options(
            "/api/orders/", HTTP_ORIGIN="https://evil.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST"
        )
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_unknown_path_uses_error_format(self):
        self.assertError(self.api.get("/api/does-not-exist/"), 404, "not_found")
