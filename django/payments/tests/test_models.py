from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from payments.models import Order, OrderStatus, PaymentStatus

from .factories import make_order, make_payment


class ConstraintTests(TestCase):
    """Database-level guarantees from spec §5.4 and §6."""

    def assertIntegrityError(self, create):
        with self.assertRaises(IntegrityError), transaction.atomic():
            create()

    def test_one_effective_successful_payment_per_order(self):
        order = make_order(status=OrderStatus.PAID, paid_at=timezone.now())
        make_payment(order, status=PaymentStatus.SUCCESSFUL, charge_id="chrg_test_1")
        # A duplicate that is flagged for refund is allowed.
        make_payment(order, status=PaymentStatus.SUCCESSFUL, needs_refund=True, charge_id="chrg_test_2")
        self.assertIntegrityError(
            lambda: make_payment(order, status=PaymentStatus.SUCCESSFUL, charge_id="chrg_test_3")
        )

    def test_charge_id_is_unique_but_nullable(self):
        order = make_order()
        make_payment(order)
        make_payment(order)
        make_payment(order, charge_id="chrg_test_1")
        self.assertIntegrityError(lambda: make_payment(order, charge_id="chrg_test_1"))

    def test_paid_order_needs_paid_at(self):
        self.assertIntegrityError(lambda: make_order(status=OrderStatus.PAID))

    def test_needs_refund_only_on_successful_payment(self):
        order = make_order()
        self.assertIntegrityError(lambda: make_payment(order, status=PaymentStatus.PENDING, needs_refund=True))

    def test_status_and_method_values_are_enforced(self):
        self.assertIntegrityError(lambda: make_order(status="refunded"))
        order = make_order()
        self.assertIntegrityError(lambda: make_payment(order, status="refunded"))
        self.assertIntegrityError(lambda: make_payment(order, method="cash"))
        self.assertEqual(Order.objects.count(), 1)
