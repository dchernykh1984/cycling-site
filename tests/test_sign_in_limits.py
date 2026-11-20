"""Sign-in limits count each visitor by their own address, which the proxy in front of the site names
in a header (CLIENT_IP_HEADER): behind a proxy the connection's address is one for everyone."""

from allauth.account.adapter import get_adapter
from django.core import mail
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from accounts.models import User

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
        self.assertEqual(self.address(**{HEADER: "::ffff:198.51.100.7"}), "198.51.100.7")

    def test_an_ipv6_visitor_is_their_whole_64(self):
        # a subscriber is handed a /64 and could take a new address from it for every try
        self.assertEqual(self.address(**{HEADER: " 2001:db8:1:2::1 "}), self.address(**{HEADER: "2001:db8:1:2:ab::9"}))
        self.assertNotEqual(self.address(**{HEADER: "2001:db8:1:2::1"}), self.address(**{HEADER: "2001:db8:1:3::1"}))

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

    def test_an_account_is_guarded_across_visitors(self):
        for n in range(5):
            self.assertFalse(self.refused(self.sign_in(f"198.51.100.{n + 1}", "member@example.com")), n)
        self.assertTrue(self.refused(self.sign_in("203.0.113.9", "member@example.com")))

    def test_people_signing_up_from_one_address_each_get_an_account_and_a_confirmation_mail(self):
        # one place's network -- a club's, a race village's -- serves many people at once, each on a phone
        for n in range(6):
            response = Client().post(
                "/en/accounts/signup/",
                {
                    "email": f"rider{n}@example.com",
                    "password1": "a long pass phrase 2026",
                    "password2": "a long pass phrase 2026",
                    "privacy": "on",
                },
                headers={HEADER: "198.51.100.7"},
            )
            self.assertEqual(response.status_code, 302, n)
        self.assertEqual(User.objects.filter(email__startswith="rider").count(), 6)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), [f"rider{n}@example.com" for n in range(6)])
