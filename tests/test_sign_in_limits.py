"""Sign-in limits count each visitor by their own address, which the proxy in front of the site names
in a header (CLIENT_IP_HEADER): behind a proxy the connection's address is one for everyone."""

from allauth.account.adapter import get_adapter
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

HEADER = "CF-Connecting-IP"
# allauth keeps its counters in the cache, which the test settings turn off
COUNTING = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sign-in"}}


@override_settings(CLIENT_IP_HEADER=HEADER)
class VisitorAddressTests(TestCase):
    def address(self, **headers):
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", headers=headers)
        return get_adapter(request).get_client_ip(request)

    def test_the_proxys_header_names_the_visitor(self):
        self.assertEqual(self.address(**{HEADER: "198.51.100.7"}), "198.51.100.7")
        self.assertEqual(self.address(**{HEADER: " 2001:db8::1 "}), "2001:db8::1")

    def test_without_the_header_the_connection_counts(self):
        self.assertEqual(self.address(), "10.0.0.1")

    def test_a_value_that_is_no_address_is_not_trusted(self):
        with self.assertLogs("accounts.adapters", "WARNING"):
            self.assertEqual(self.address(**{HEADER: "198.51.100.7, 203.0.113.1"}), "10.0.0.1")

    @override_settings(CLIENT_IP_HEADER="")
    def test_a_header_the_deployment_does_not_name_is_ignored(self):
        self.assertEqual(self.address(**{HEADER: "198.51.100.7"}), "10.0.0.1")


@override_settings(CLIENT_IP_HEADER=HEADER, CACHES=COUNTING)
class SignInLimitsTests(TestCase):
    def setUp(self):
        cache.clear()

    def sign_in(self, visitor, email):
        return self.client.post(
            "/en/accounts/login/", {"login": email, "password": "not-the-password"}, headers={HEADER: visitor}
        )

    def refused(self, response):
        return response.status_code == 429 or "Too many failed login attempts" in response.content.decode()

    def test_a_visitor_who_keeps_failing_holds_back_nobody_else(self):
        for n in range(10):
            self.assertFalse(self.refused(self.sign_in("198.51.100.7", f"guess{n}@example.com")), n)
        self.assertTrue(self.refused(self.sign_in("198.51.100.7", "guess10@example.com")))
        self.assertFalse(self.refused(self.sign_in("203.0.113.9", "member@example.com")))
