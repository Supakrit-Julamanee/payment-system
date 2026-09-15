from datetime import UTC, datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from payments.models import OrderStatus, Payment, PaymentMethod, PaymentStatus
from payments.services import (
    GATEWAY_UNREACHABLE,
    apply_charge,
    begin_webhook_event,
    create_order,
    create_pending_payment,
    find_reusable_payment,
    map_charge_status,
    mark_webhook_processed,
)

from .factories import make_charge, make_order, make_payment


def reload(obj):
    obj.refresh_from_db()
    return obj


class MapChargeStatusTests(TestCase):
    def test_mapping(self):
        cases = {
            "pending": "pending",
            "successful": "successful",
            "failed": "failed",
            "reversed": "failed",
            "expired": "expired",
            "unknown": None,
            None: None,
        }
        for charge_status, expected in cases.items():
            with self.subTest(charge_status=charge_status):
                self.assertEqual(map_charge_status(charge_status), expected)


class ApplyChargeTests(TestCase):
    def setUp(self):
        self.order = make_order()
        self.payment = make_payment(self.order)

    def test_successful_charge_marks_order_paid(self):
        charge = make_charge(self.payment, status="successful")
        apply_charge(charge)
        payment, order = reload(self.payment), reload(self.order)
        self.assertEqual(payment.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(payment.charge_id, charge["id"])  # found through metadata.payment_id
        self.assertFalse(payment.needs_refund)
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertIsNotNone(order.paid_at)

    def test_is_idempotent(self):
        charge = make_charge(self.payment, status="successful")
        apply_charge(charge)
        paid_at = reload(self.order).paid_at
        apply_charge(charge)
        self.assertEqual(reload(self.order).paid_at, paid_at)
        self.assertEqual(reload(self.payment).status, PaymentStatus.SUCCESSFUL)
        self.assertFalse(reload(self.payment).needs_refund)

    def test_failed_and_reversed_leave_order_pending(self):
        for charge_status in ("failed", "reversed"):
            with self.subTest(charge_status=charge_status):
                order = make_order()
                payment = make_payment(order)
                apply_charge(
                    make_charge(
                        payment,
                        status=charge_status,
                        failure_code="insufficient_fund",
                        failure_message="Insufficient funds",
                    )
                )
                payment, order = reload(payment), reload(order)
                self.assertEqual(payment.status, PaymentStatus.FAILED)
                self.assertEqual(payment.failure_code, "insufficient_fund")
                self.assertEqual(payment.failure_message, "Insufficient funds")
                self.assertEqual(order.status, OrderStatus.PENDING)

    def test_expired_leaves_order_pending(self):
        apply_charge(make_charge(self.payment, status="expired"))
        self.assertEqual(reload(self.payment).status, PaymentStatus.EXPIRED)
        self.assertEqual(reload(self.order).status, OrderStatus.PENDING)

    def test_pending_copies_charge_details(self):
        apply_charge(
            make_charge(
                self.payment,
                status="pending",
                authorize_uri="https://example.test/3ds",
                expires_at="2026-09-15T10:30:00Z",
            )
        )
        payment = reload(self.payment)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.authorize_uri, "https://example.test/3ds")
        self.assertEqual(payment.expires_at, datetime(2026, 9, 15, 10, 30, tzinfo=UTC))

    def test_promptpay_qr_image_url(self):
        payment = make_payment(make_order(), method=PaymentMethod.PROMPTPAY)
        source = {"scannable_code": {"image": {"download_uri": "https://example.test/qr.png"}}}
        apply_charge(make_charge(payment, source=source))
        self.assertEqual(reload(payment).qr_image_url, "https://example.test/qr.png")

    def test_amount_or_currency_mismatch_changes_nothing(self):
        for fields in ({"amount": 1}, {"currency": "usd"}, {"amount": "6000"}):
            with self.subTest(fields=fields):
                with self.assertLogs("payments.services", "ERROR"):
                    result = apply_charge(make_charge(self.payment, status="successful", **fields))
                self.assertIsNone(result)
                payment = reload(self.payment)
                self.assertEqual(payment.status, PaymentStatus.PENDING)
                self.assertIsNone(payment.charge_id)
                self.assertEqual(reload(self.order).status, OrderStatus.PENDING)

    def test_currency_case_is_ignored(self):
        apply_charge(make_charge(self.payment, status="successful", currency="THB"))
        self.assertEqual(reload(self.payment).status, PaymentStatus.SUCCESSFUL)

    def test_charge_from_outside_this_system_is_ignored(self):
        charge = make_charge(self.payment, id="chrg_test_other", status="successful", metadata={})
        with self.assertLogs("payments.services", "WARNING"):
            self.assertIsNone(apply_charge(charge))
        self.assertEqual(reload(self.payment).status, PaymentStatus.PENDING)

    def test_final_states_do_not_change(self):
        cases = [
            (PaymentStatus.SUCCESSFUL, "failed"),
            (PaymentStatus.EXPIRED, "successful"),
            (PaymentStatus.FAILED, "successful"),
        ]
        for final_status, charge_status in cases:
            with self.subTest(final_status=final_status):
                paid = final_status == PaymentStatus.SUCCESSFUL
                order = make_order(
                    status=OrderStatus.PAID if paid else OrderStatus.PENDING,
                    paid_at=timezone.now() if paid else None,
                )
                payment = make_payment(order, status=final_status, charge_id=f"chrg_test_final_{final_status}")
                apply_charge(make_charge(payment, status=charge_status))
                self.assertEqual(reload(payment).status, final_status)
                self.assertEqual(reload(order).status, order.status)

    def test_gateway_unreachable_can_become_successful(self):
        payment = make_payment(
            self.order,
            method=PaymentMethod.PROMPTPAY,
            status=PaymentStatus.FAILED,
            failure_code=GATEWAY_UNREACHABLE,
            failure_message="Gateway unreachable",
        )
        apply_charge(make_charge(payment, status="successful"))
        payment = reload(payment)
        self.assertEqual(payment.status, PaymentStatus.SUCCESSFUL)
        self.assertIsNone(payment.failure_code)
        self.assertEqual(reload(self.order).status, OrderStatus.PAID)

    def test_gateway_unreachable_keeps_its_code_while_charge_is_pending(self):
        payment = make_payment(self.order, status=PaymentStatus.FAILED, failure_code=GATEWAY_UNREACHABLE)
        apply_charge(make_charge(payment, status="pending"))
        payment = reload(payment)
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_code, GATEWAY_UNREACHABLE)

    def test_second_success_on_paid_order_needs_refund(self):
        apply_charge(make_charge(self.payment, status="successful"))
        paid_at = reload(self.order).paid_at
        second = make_payment(self.order, method=PaymentMethod.PROMPTPAY)

        with self.assertLogs("payments.services", "WARNING"):
            apply_charge(make_charge(second, status="successful"))

        second = reload(second)
        self.assertEqual(second.status, PaymentStatus.SUCCESSFUL)
        self.assertTrue(second.needs_refund)
        self.assertFalse(reload(self.payment).needs_refund)
        order = reload(self.order)
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.paid_at, paid_at)

    def test_payment_with_another_charge_is_not_overwritten(self):
        self.payment.charge_id = "chrg_test_original"
        self.payment.save()
        with self.assertLogs("payments.services", "ERROR"):
            result = apply_charge(make_charge(self.payment, id="chrg_test_other", status="successful"))
        self.assertIsNone(result)
        payment = reload(self.payment)
        self.assertEqual(payment.charge_id, "chrg_test_original")
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_unknown_charge_status_keeps_payment_status(self):
        with self.assertLogs("payments.services", "WARNING"):
            apply_charge(make_charge(self.payment, status="something_new"))
        payment = reload(self.payment)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertIsNotNone(payment.charge_id)


class OrderAndPaymentCreationTests(TestCase):
    def test_create_order_uses_catalog_price(self):
        order = create_order("cake")
        self.assertEqual((order.amount, order.currency, order.status), (12000, "thb", OrderStatus.PENDING))

    def test_create_pending_payment_copies_order_amount(self):
        order = create_order("coffee")
        payment = create_pending_payment(order, PaymentMethod.PROMPTPAY)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual((payment.amount, payment.currency), (6000, "thb"))
        self.assertIsNone(payment.charge_id)


class FindReusablePaymentTests(TestCase):
    def test_reuses_pending_payment_with_charge(self):
        order = make_order()
        future = make_payment(order, charge_id="chrg_test_1", expires_at=timezone.now() + timedelta(hours=1))
        self.assertEqual(find_reusable_payment(order, PaymentMethod.CARD), future)

    def test_payment_without_expiry_is_reusable(self):
        order = make_order()
        payment = make_payment(order, charge_id="chrg_test_1")
        self.assertEqual(find_reusable_payment(order, PaymentMethod.CARD), payment)

    def test_skips_payments_that_do_not_match(self):
        order = make_order()
        make_payment(order)  # no charge yet
        make_payment(order, method=PaymentMethod.PROMPTPAY, charge_id="chrg_test_pp")
        make_payment(order, charge_id="chrg_test_old", expires_at=timezone.now() - timedelta(minutes=1))
        make_payment(order, charge_id="chrg_test_failed", status=PaymentStatus.FAILED)
        self.assertIsNone(find_reusable_payment(order, PaymentMethod.CARD))


class WebhookEventTests(TestCase):
    def test_new_event_is_stored_unprocessed(self):
        event = begin_webhook_event("evnt_test_1", "charge.complete", {"id": "evnt_test_1"})
        self.assertIsNotNone(event)
        self.assertIsNone(reload(event).processed_at)

    def test_unprocessed_event_is_updated_on_redelivery(self):
        begin_webhook_event("evnt_test_1", "charge.create", {"v": 1})
        event = begin_webhook_event("evnt_test_1", "charge.complete", {"v": 2})
        event = reload(event)
        self.assertEqual((event.event_key, event.payload), ("charge.complete", {"v": 2}))

    def test_processed_event_is_skipped(self):
        event = begin_webhook_event("evnt_test_1", "charge.complete", {"v": 1})
        mark_webhook_processed(event)
        self.assertIsNone(begin_webhook_event("evnt_test_1", "charge.complete", {"v": 2}))
        self.assertEqual(reload(event).payload, {"v": 1})
        self.assertEqual(Payment.objects.count(), 0)
