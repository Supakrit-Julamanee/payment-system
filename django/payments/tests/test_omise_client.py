from unittest.mock import patch

import requests
from django.conf import settings
from django.test import SimpleTestCase

from payments import omise_client
from payments.omise_client import OmiseError, OmiseNotFound, OmiseUnavailable


class FakeResponse:
    def __init__(self, status_code, payload=None, json_error=False):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


CHARGE = {"object": "charge", "id": "chrg_test_1", "status": "successful"}


class RequestHandlingTests(SimpleTestCase):
    def test_success_returns_body(self):
        with patch.object(requests, "request", return_value=FakeResponse(200, CHARGE)):
            self.assertEqual(omise_client.retrieve_charge("chrg_test_1"), CHARGE)

    def test_uses_secret_key_basic_auth_and_timeout(self):
        with patch.object(requests, "request", return_value=FakeResponse(200, CHARGE)) as request:
            omise_client.retrieve_charge("chrg_test_1")
        kwargs = request.call_args.kwargs
        self.assertEqual(request.call_args.args, ("GET", f"{settings.OMISE_API_BASE}/charges/chrg_test_1"))
        self.assertEqual(kwargs["auth"], (settings.OMISE_SECRET_KEY, ""))
        self.assertEqual(kwargs["timeout"], omise_client.TIMEOUT_SECONDS)

    def test_4xx_error_object_raises_omise_error(self):
        body = {"object": "error", "code": "invalid_card", "message": "Card was rejected."}
        with patch.object(requests, "request", return_value=FakeResponse(400, body)):
            with self.assertRaises(OmiseError) as ctx:
                omise_client.retrieve_charge("chrg_test_1")
        self.assertEqual((ctx.exception.code, ctx.exception.status_code), ("invalid_card", 400))
        self.assertEqual(ctx.exception.message, "Card was rejected.")

    def test_404_raises_not_found(self):
        body = {"object": "error", "code": "not_found", "message": "charge missing"}
        for response in (FakeResponse(404, body), FakeResponse(200, body)):
            with self.subTest(status_code=response.status_code):
                with patch.object(requests, "request", return_value=response):
                    with self.assertRaises(OmiseNotFound):
                        omise_client.retrieve_charge("chrg_test_missing")

    def test_5xx_and_network_errors_raise_unavailable(self):
        cases = [
            ("5xx", {"return_value": FakeResponse(502, {})}),
            ("non-json", {"return_value": FakeResponse(200, json_error=True)}),
            ("timeout", {"side_effect": requests.Timeout("timed out")}),
            ("connection", {"side_effect": requests.ConnectionError("refused")}),
        ]
        for name, kwargs in cases:
            with self.subTest(case=name):
                with patch.object(requests, "request", **kwargs):
                    with self.assertRaises(OmiseUnavailable):
                        omise_client.retrieve_charge("chrg_test_1")


class CreateChargeTests(SimpleTestCase):
    def post_data(self, **kwargs) -> dict:
        defaults = {
            "amount": 6000,
            "currency": "thb",
            "order_id": "3f6c2a8e-6f0b-4a51-9a64-0f6b8d7f2c11",
            "payment_id": "9b1d0000-0000-0000-0000-000000000001",
        }
        with patch.object(requests, "request", return_value=FakeResponse(200, CHARGE)) as request:
            omise_client.create_charge(**(defaults | kwargs))
        self.assertEqual(request.call_args.args, ("POST", f"{settings.OMISE_API_BASE}/charges"))
        return request.call_args.kwargs["data"]

    def test_card_charge_sends_token_and_return_uri(self):
        data = self.post_data(token="tokn_test_1", return_uri="http://localhost:3000/orders/1")
        self.assertEqual(data["card"], "tokn_test_1")
        self.assertEqual(data["return_uri"], "http://localhost:3000/orders/1")
        self.assertNotIn("source", data)

    def test_promptpay_charge_sends_source_without_return_uri(self):
        data = self.post_data(source="src_test_1")
        self.assertEqual(data["source"], "src_test_1")
        self.assertNotIn("card", data)
        self.assertNotIn("return_uri", data)

    def test_always_sends_amount_currency_and_metadata(self):
        data = self.post_data(token="tokn_test_1")
        self.assertEqual((data["amount"], data["currency"]), (6000, "thb"))
        self.assertEqual(data["metadata[order_id]"], "3f6c2a8e-6f0b-4a51-9a64-0f6b8d7f2c11")
        self.assertEqual(data["metadata[payment_id]"], "9b1d0000-0000-0000-0000-000000000001")
