"""sync_pending_payments, cases A/B/C from spec §11, with the Omise client mocked."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from payments.models import OrderStatus, Payment, PaymentMethod, PaymentStatus
from payments.omise_client import OmiseUnavailable
from payments.services import GATEWAY_UNREACHABLE

from .factories import make_charge, make_order, make_payment


def backdate(payment: Payment, minutes: int) -> Payment:
    """created_at uses auto_now_add, so it can only be changed with an UPDATE."""
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
    payment.refresh_from_db()
    return payment


def run_sync() -> str:
    out = StringIO()
    call_command("sync_pending_payments", stdout=out)
    return out.getvalue()


class SyncCaseATests(TestCase):
    """charge_id is set and expires_at has passed."""

    def setUp(self):
        self.order = make_order()
        self.payment = make_payment(
            self.order,
            method=PaymentMethod.PROMPTPAY,
            charge_id="chrg_test_1",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

    def test_expired_charge_expires_the_payment(self):
        charge = make_charge(self.payment, status="expired")
        with patch("payments.omise_client.retrieve_charge", return_value=charge) as retrieve:
            run_sync()

        retrieve.assert_called_once_with("chrg_test_1")
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.EXPIRED)
        # A failed or expired payment leaves the order open for a retry.
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_charge_paid_after_expiry_still_pays_the_order(self):
        # Spec §17 scenario 9: the webhook never arrived, but the money moved.
        charge = make_charge(self.payment, status="successful")
        with patch("payments.omise_client.retrieve_charge", return_value=charge):
            run_sync()

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(self.order.status, OrderStatus.PAID)

    def test_omise_still_pending_keeps_the_payment_pending(self):
        # Django never decides on its own that a charge expired (§11).
        charge = make_charge(self.payment, status="pending")
        with patch("payments.omise_client.retrieve_charge", return_value=charge):
            run_sync()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)

    def test_gateway_failure_leaves_the_payment_for_the_next_run(self):
        with patch("payments.omise_client.retrieve_charge", side_effect=OmiseUnavailable("timeout")):
            with self.assertLogs("payments.management.commands.sync_pending_payments", "ERROR"):
                output = run_sync()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)
        self.assertIsNotNone(self.payment.charge_id)
        self.assertIn("skipped=1", output)


class SyncCaseBTests(TestCase):
    """charge_id is set, no expiry, and the payment is older than 15 minutes."""

    def test_old_payment_without_expiry_is_checked(self):
        order = make_order()
        payment = backdate(make_payment(order, charge_id="chrg_test_1"), minutes=20)

        charge = make_charge(payment, status="failed", failure_code="failed_processing")
        with patch("payments.omise_client.retrieve_charge", return_value=charge) as retrieve:
            run_sync()

        retrieve.assert_called_once_with("chrg_test_1")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_code, "failed_processing")

    def test_recent_payment_is_left_alone(self):
        order = make_order()
        make_payment(order, charge_id="chrg_test_1")  # created just now, no expiry

        with patch("payments.omise_client.retrieve_charge") as retrieve:
            output = run_sync()

        retrieve.assert_not_called()
        self.assertIn("checked=0", output)

    def test_payment_expiring_in_the_future_is_left_alone(self):
        order = make_order()
        make_payment(
            order,
            method=PaymentMethod.PROMPTPAY,
            charge_id="chrg_test_1",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        with patch("payments.omise_client.retrieve_charge") as retrieve:
            run_sync()

        retrieve.assert_not_called()


class SyncCaseCTests(TestCase):
    """No charge_id: the call to Omise never came back."""

    def test_old_payment_without_charge_is_given_up_on(self):
        order = make_order()
        payment = backdate(make_payment(order), minutes=20)

        with patch("payments.omise_client.retrieve_charge") as retrieve:
            output = run_sync()

        retrieve.assert_not_called()
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_code, GATEWAY_UNREACHABLE)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertIn("gateway_unreachable=1", output)

    def test_recent_payment_without_charge_is_left_alone(self):
        order = make_order()
        payment = make_payment(order)

        run_sync()

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_given_up_payment_is_not_checked_again(self):
        # Once it is failed it is no longer pending, and it has no charge_id to ask about.
        # Only a later webhook can still move it to successful (§6.1), which
        # test_services.ApplyChargeTests covers.
        order = make_order()
        payment = backdate(make_payment(order), minutes=20)
        run_sync()
        payment.refresh_from_db()
        self.assertEqual(payment.failure_code, GATEWAY_UNREACHABLE)

        with patch("payments.omise_client.retrieve_charge") as retrieve:
            output = run_sync()

        retrieve.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_code, GATEWAY_UNREACHABLE)
        self.assertIn("gateway_unreachable=0", output)


class SyncIndependenceTests(TestCase):
    """One broken payment must not stop the others (§11)."""

    def test_one_failure_does_not_stop_the_rest(self):
        broken = make_payment(
            make_order(),
            charge_id="chrg_test_broken",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        good_order = make_order()
        good = make_payment(
            good_order,
            charge_id="chrg_test_good",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        def retrieve(charge_id):
            if charge_id == "chrg_test_broken":
                raise OmiseUnavailable("timeout")
            return make_charge(good, status="successful")

        with patch("payments.omise_client.retrieve_charge", side_effect=retrieve):
            with self.assertLogs("payments.management.commands.sync_pending_payments", "ERROR"):
                output = run_sync()

        broken.refresh_from_db()
        good.refresh_from_db()
        good_order.refresh_from_db()
        self.assertEqual(broken.status, PaymentStatus.PENDING)
        self.assertEqual(good.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(good_order.status, OrderStatus.PAID)
        self.assertIn("checked=1", output)
        self.assertIn("skipped=1", output)
