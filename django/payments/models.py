"""Data model (spec §5). Status values and transitions follow spec §6."""

import uuid

from django.db import models
from django.db.models import Q


class OrderStatus(models.TextChoices):
    PENDING = "pending"
    PAID = "paid"


class PaymentStatus(models.TextChoices):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    EXPIRED = "expired"


class PaymentMethod(models.TextChoices):
    CARD = "card"
    PROMPTPAY = "promptpay"


class Order(models.Model):
    # UUID so nobody can guess another order's id (there is no login).
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.CharField(max_length=50)
    amount = models.PositiveIntegerField()  # satang, copied from PRODUCTS
    currency = models.CharField(max_length=3, default="thb")
    status = models.CharField(max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=OrderStatus.values), name="order_status_valid"),
            models.CheckConstraint(
                condition=Q(status=OrderStatus.PENDING) | Q(paid_at__isnull=False),
                name="order_paid_has_paid_at",
            ),
        ]

    def __str__(self):
        return f"Order {self.id} ({self.status})"


class Payment(models.Model):
    """One payment attempt, backed by at most one Omise charge."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    amount = models.PositiveIntegerField()  # satang, copied from order.amount
    currency = models.CharField(max_length=3)
    # null until Omise returns a charge.
    charge_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    failure_code = models.CharField(max_length=255, null=True, blank=True)
    failure_message = models.TextField(null=True, blank=True)
    needs_refund = models.BooleanField(default=False)
    authorize_uri = models.URLField(max_length=2048, null=True, blank=True)
    qr_image_url = models.URLField(max_length=2048, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            # Used by the sync job (spec §11).
            models.Index(fields=["status", "expires_at"], name="payment_status_expires_idx"),
        ]
        constraints = [
            # Last line of defense: an order is paid by at most one payment (spec §5.4).
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status=PaymentStatus.SUCCESSFUL, needs_refund=False),
                name="one_effective_successful_payment_per_order",
            ),
            models.CheckConstraint(condition=Q(status__in=PaymentStatus.values), name="payment_status_valid"),
            models.CheckConstraint(condition=Q(method__in=PaymentMethod.values), name="payment_method_valid"),
            models.CheckConstraint(
                condition=Q(needs_refund=False) | Q(status=PaymentStatus.SUCCESSFUL),
                name="payment_refund_only_when_successful",
            ),
        ]

    def __str__(self):
        return f"Payment {self.id} ({self.method}, {self.status})"


class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=64, primary_key=True)  # evnt_...
    event_key = models.CharField(max_length=64)  # e.g. charge.complete
    payload = models.JSONField()  # raw body, for debugging only
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)  # null = not processed yet

    def __str__(self):
        return f"WebhookEvent {self.event_id}"
