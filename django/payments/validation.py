"""Request parsing for the payments API (spec §7.1, §7.2).

Each parser returns clean values or raises ApiError with the error code from the spec.
"""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from rest_framework import status

from .exceptions import ApiError
from .products import PRODUCTS

PaymentMethod = Literal["card", "promptpay"]


def parse_order_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise ApiError(status.HTTP_404_NOT_FOUND, "order_not_found", "Order not found.") from None


def parse_create_order(data: object) -> str:
    """Return a valid product_id. Every other field, including `amount`, is ignored on purpose."""
    product_id = data.get("product_id") if isinstance(data, dict) else None
    if not isinstance(product_id, str) or product_id not in PRODUCTS:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_product", "Unknown product.")
    return product_id


@dataclass(frozen=True)
class PayRequest:
    method: PaymentMethod
    # Kept out of repr so a logged PayRequest never leaks a token or source.
    token: str | None = field(default=None, repr=False)
    source: str | None = field(default=None, repr=False)


def parse_pay_request(data: object) -> PayRequest:
    body = data if isinstance(data, dict) else {}
    method = body.get("method")

    if method == "card":
        token = body.get("token")
        if not isinstance(token, str) or not token.startswith("tokn_"):
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "invalid_token",
                "A card payment needs a token that starts with tokn_.",
            )
        return PayRequest(method="card", token=token)

    if method == "promptpay":
        source = body.get("source")
        if not isinstance(source, str) or not source.startswith("src_"):
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "invalid_source",
                "A PromptPay payment needs a source that starts with src_.",
            )
        return PayRequest(method="promptpay", source=source)

    raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_method", "method must be card or promptpay.")
