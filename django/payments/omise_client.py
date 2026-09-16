"""HTTP client for the Omise API (spec §13).

Only this module talks to Omise. The secret key never leaves it, and tokens,
sources and keys are never logged.

Callers must handle three failures differently (spec §7.2, §10):
- OmiseError: Omise rejected the request with a 4xx, so no charge was created.
- OmiseNotFound: the charge does not exist (probably a fake webhook).
- OmiseUnavailable: timeout, network error or 5xx, so the charge may or may not exist.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class OmiseError(Exception):
    """Omise replied with an error object (4xx). No charge was created."""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class OmiseNotFound(Exception):
    """Omise returned 404 for this object."""


class OmiseUnavailable(Exception):
    """Timeout, network error or 5xx. The charge may still have been created."""


def _request(method: str, path: str, data: dict | None = None) -> dict:
    url = f"{settings.OMISE_API_BASE}{path}"
    try:
        # HTTP Basic auth: secret key as the username, empty password (spec §13.1).
        response = requests.request(
            method,
            url,
            auth=(settings.OMISE_SECRET_KEY, ""),
            data=data,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error("Omise %s %s failed: %s", method, path, type(exc).__name__)
        raise OmiseUnavailable(f"{type(exc).__name__} calling Omise") from exc

    if response.status_code >= 500:
        logger.error("Omise %s %s returned %s", method, path, response.status_code)
        raise OmiseUnavailable(f"Omise returned {response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        logger.error("Omise %s %s returned a non-JSON body (%s)", method, path, response.status_code)
        raise OmiseUnavailable("Omise returned a non-JSON body") from exc

    if not isinstance(body, dict):
        logger.error("Omise %s %s returned an unexpected body type", method, path)
        raise OmiseUnavailable("Omise returned an unexpected body")

    if body.get("object") == "error" or response.status_code >= 400:
        code = str(body.get("code") or "unknown_error")
        message = str(body.get("message") or f"Omise returned {response.status_code}")
        if response.status_code == 404 or code == "not_found":
            raise OmiseNotFound(message)
        logger.warning("Omise %s %s rejected: %s (%s)", method, path, code, response.status_code)
        raise OmiseError(code=code, message=message, status_code=response.status_code)

    return body


def create_charge(
    *,
    amount: int,
    currency: str,
    order_id,
    payment_id,
    token: str | None = None,
    source: str | None = None,
    return_uri: str | None = None,
) -> dict:
    """POST /charges (spec §13.2). `amount` is satang and comes from the Payment.

    TODO: verify with Omise docs (spec §18) whether POST /charges accepts an idempotency
    key. It would add a second layer of protection on top of the reuse rule in §7.2.
    """
    data: dict[str, object] = {
        "amount": amount,
        "currency": currency,
        "metadata[order_id]": str(order_id),
        "metadata[payment_id]": str(payment_id),
    }
    if token:
        data["card"] = token
    if source:
        data["source"] = source
    if return_uri:
        data["return_uri"] = return_uri
    return _request("POST", "/charges", data=data)


def retrieve_charge(charge_id: str) -> dict:
    """GET /charges/{charge_id} (spec §13.3). The only trustworthy source of charge status."""
    return _request("GET", f"/charges/{charge_id}")
