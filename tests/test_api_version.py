"""The site says which commit it runs, which the nightly deploy compares with main (issue #153)."""

from django.test import TestCase, override_settings


class VersionTests(TestCase):
    @override_settings(RELEASE_COMMIT="6e9a12ae0123456789abcdef0123456789abcdef")
    def test_anyone_reads_the_commit_the_site_runs(self):
        response = self.client.get("/api/v1/version/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"commit": "6e9a12ae0123456789abcdef0123456789abcdef"})

    @override_settings(RELEASE_COMMIT="")
    def test_a_commit_the_host_does_not_name_reads_empty(self):
        self.assertEqual(self.client.get("/api/v1/version/").json(), {"commit": ""})
