"""Expiry sync job (spec §11).

Webhooks can be missed: the tunnel may be down, or Omise may give up retrying. This
command re-reads charges from Omise and lets apply_charge decide. It never marks a
payment expired on its own (§11), and each payment is processed independently so one
failure does not stop the rest.

Run it every 5 minutes with cron, or by hand:

    python manage.py sync_pending_payments
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments import omise_client
from payments.omise_client import OmiseError, OmiseNotFound, OmiseUnavailable
from payments.services import (
    GATEWAY_UNREACHABLE,
    apply_charge,
    mark_payment_failed,
    payments_awaiting_charge_check,
    payments_without_charge,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-read pending payments from Omise and give up on ones that never got a charge."

    def handle(self, *args, **options):
        now = timezone.now()
        checked = 0
        skipped = 0
        given_up = 0

        # Cases A and B: ask Omise what really happened to the charge.
        for payment in payments_awaiting_charge_check(now):
            try:
                charge = omise_client.retrieve_charge(payment.charge_id)
            except OmiseNotFound:
                # Omise does not know this charge; leave the payment alone for a human.
                logger.warning("Sync: Omise has no charge for payment %s", payment.pk)
                skipped += 1
                continue
            except (OmiseUnavailable, OmiseError):
                logger.error("Sync: could not fetch the charge for payment %s", payment.pk)
                skipped += 1
                continue

            try:
                apply_charge(charge)
            except Exception:  # noqa: BLE001 - one bad payment must not stop the others
                logger.exception("Sync: apply_charge failed for payment %s", payment.pk)
                skipped += 1
                continue
            checked += 1

        # Case C: /pay never got a charge id back, so the charge probably never existed.
        for payment in payments_without_charge(now):
            mark_payment_failed(
                payment,
                GATEWAY_UNREACHABLE,
                "The payment gateway could not be reached, so this attempt was given up on.",
            )
            given_up += 1

        summary = f"checked={checked} skipped={skipped} gateway_unreachable={given_up}"
        logger.info("Sync finished: %s", summary)
        self.stdout.write(self.style.SUCCESS(summary))
