from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.guards import require_test_secret_key


class TestModeGuardTests(SimpleTestCase):
    """Spec §17 scenario 14: Django refuses to start with a non-test secret key."""

    def test_accepts_test_key(self):
        self.assertEqual(require_test_secret_key("skey_test_abc"), "skey_test_abc")

    def test_rejects_live_key_without_echoing_it(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            require_test_secret_key("skey_live_secret123")
        self.assertNotIn("secret123", str(ctx.exception))

    def test_rejects_missing_key(self):
        for value in (None, ""):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                require_test_secret_key(value)

    def test_rejects_public_test_key(self):
        with self.assertRaises(ImproperlyConfigured):
            require_test_secret_key("pkey_test_abc")
