"""Test runner that blocks real HTTP calls to Omise.

A test that forgets to mock the client would otherwise reach the real API with the
test secret key and create real test-mode charges. Tests that need a response patch
`payments.omise_client.create_charge` / `retrieve_charge`, or `requests.request`,
which nests over this block.
"""

from unittest.mock import patch

from django.test.runner import DiscoverRunner


def _blocked(*args, **kwargs):
    raise RuntimeError(
        "Tests must not call the Omise API. Patch payments.omise_client.create_charge / "
        "retrieve_charge (see payments/tests/test_pay_omise.py)."
    )


class NoNetworkTestRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        with patch("payments.omise_client.requests.request", side_effect=_blocked):
            return super().run_tests(*args, **kwargs)
