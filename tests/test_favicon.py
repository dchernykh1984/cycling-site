from django.test import TestCase
from django.urls import reverse


class FaviconTests(TestCase):
    def test_favicon_ico_redirects_to_static(self):
        resp = self.client.get("/favicon.ico")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("favicon", resp["Location"])

    def test_base_template_links_favicon(self):
        resp = self.client.get(reverse("calendar_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'rel="icon"')
        self.assertContains(resp, "favicon.ico")
