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


class TouchIconAtTheRootTests(TestCase):
    """iOS asks the root for the touch icon before it reads the page's own <link>.

    Both spellings were answering 404 -- a dozen a day in production's log -- and a phone saving
    the site to its home screen fell back to a screenshot of the page.
    """

    def test_both_spellings_lead_to_the_icon(self):
        for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("apple-touch-icon", response["Location"])
                self.assertTrue(response["Location"].startswith("/static/"))

    def test_the_icon_itself_is_there_to_redirect_to(self):
        from django.contrib.staticfiles import finders

        self.assertIsNotNone(finders.find("apple-touch-icon.png"))

    def test_the_root_paths_carry_no_language_prefix(self):
        """A machine-facing address, like the favicon and robots.txt -- no /ru/ in front of it."""
        response = self.client.get("/ru/apple-touch-icon.png")
        self.assertEqual(response.status_code, 404)
