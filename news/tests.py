import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from accounts.models import User
from news.forms import SubmitNewsForm
from news.models import Comment, NewsArticle, NewsArticleComment, NewsIndexPage, NewsPage, NewsSettings


def _get_site_root():
    site = Site.objects.filter(is_default_site=True).first()
    return site.root_page if site else Page.objects.filter(depth=1).first()


def _make_news_page(index, title="Test News", slug=None):
    page = NewsPage(title=title, slug=slug or title.lower().replace(" ", "-"))
    index.add_child(instance=page)
    page.save_revision().publish()
    return NewsPage.objects.get(pk=page.pk)


class NewsPageHierarchyTests(WagtailPageTests):
    def test_news_page_under_news_index(self):
        self.assertCanCreateAt(NewsIndexPage, NewsPage)

    def test_news_page_not_under_root(self):
        self.assertCanNotCreateAt(Page, NewsPage)


class NewsIndexPageRenderTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        self.index = NewsIndexPage(title="News", slug="news-index")
        root.add_child(instance=self.index)
        self.index.save_revision().publish()

    def test_index_returns_200(self):
        response = self.client.get(self.index.url)
        self.assertEqual(response.status_code, 200)

    def test_index_lists_news_items(self):
        _make_news_page(self.index, "Article One", "article-one")
        _make_news_page(self.index, "Article Two", "article-two")
        response = self.client.get(self.index.url)
        self.assertContains(response, "Article One")
        self.assertContains(response, "Article Two")

    def test_index_pagination(self):
        for i in range(15):
            _make_news_page(self.index, f"Article {i}", f"article-{i}")
        response = self.client.get(self.index.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("news_items", response.context)
        self.assertEqual(response.context["news_items"].paginator.num_pages, 2)

    def test_second_page_accessible(self):
        for i in range(15):
            _make_news_page(self.index, f"Article {i}", f"article-{i}")
        response = self.client.get(self.index.url + "?page=2")
        self.assertEqual(response.status_code, 200)


class NewsPageRenderTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        self.index = NewsIndexPage(title="News", slug="news-render")
        root.add_child(instance=self.index)
        self.index.save_revision().publish()
        self.news_page = _make_news_page(self.index)
        self.participant = User.objects.create_user(
            username="participant@example.com",
            email="participant@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.guest = User.objects.create_user(
            username="guest@example.com",
            email="guest@example.com",
            password="password123",
            role=User.Role.GUEST,
        )
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="password123",
            is_staff=True,
            role=User.Role.ADMIN,
        )

    def test_news_page_returns_200(self):
        response = self.client.get(self.news_page.url)
        self.assertEqual(response.status_code, 200)

    def test_news_page_shows_title(self):
        response = self.client.get(self.news_page.url)
        self.assertContains(response, self.news_page.title)

    def test_can_comment_false_for_anonymous(self):
        response = self.client.get(self.news_page.url)
        self.assertFalse(response.context["can_comment"])

    def test_can_comment_true_for_participant(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(self.news_page.url)
        self.assertTrue(response.context["can_comment"])

    def test_can_comment_false_for_guest(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.get(self.news_page.url)
        self.assertFalse(response.context["can_comment"])

    def test_user_can_delete_comment_false_for_non_staff(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(self.news_page.url)
        self.assertFalse(response.context["user_can_delete_comment"])

    def test_user_can_delete_comment_true_for_staff(self):
        self.client.login(username="staff@example.com", password="password123")
        response = self.client.get(self.news_page.url)
        self.assertTrue(response.context["user_can_delete_comment"])

    def test_approved_comments_visible_to_all(self):
        Comment.objects.create(
            page=self.news_page,
            author=self.participant,
            body="Approved comment",
            is_approved=True,
        )
        response = self.client.get(self.news_page.url)
        self.assertContains(response, "Approved comment")

    def test_unapproved_comments_hidden_from_non_staff(self):
        Comment.objects.create(
            page=self.news_page,
            author=self.participant,
            body="Pending comment",
            is_approved=False,
        )
        response = self.client.get(self.news_page.url)
        self.assertNotContains(response, "Pending comment")

    def test_unapproved_comments_visible_to_staff(self):
        Comment.objects.create(
            page=self.news_page,
            author=self.participant,
            body="Pending comment",
            is_approved=False,
        )
        self.client.login(username="staff@example.com", password="password123")
        response = self.client.get(self.news_page.url)
        self.assertContains(response, "Pending comment")


class AddCommentViewTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        self.index = NewsIndexPage(title="News", slug="news-comment")
        root.add_child(instance=self.index)
        self.index.save_revision().publish()
        self.news_page = _make_news_page(self.index)
        self.participant = User.objects.create_user(
            username="participant@example.com",
            email="participant@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.guest = User.objects.create_user(
            username="guest@example.com",
            email="guest@example.com",
            password="password123",
            role=User.Role.GUEST,
        )

    def _add_comment_url(self):
        return reverse("news_add_comment", args=[self.news_page.pk])

    def test_participant_can_post_comment(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(self._add_comment_url(), {"body": "Great article!"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comment.objects.filter(page=self.news_page).count(), 1)

    def test_comment_auto_approved_by_default(self):
        self.client.login(username="participant@example.com", password="password123")
        self.client.post(self._add_comment_url(), {"body": "Auto-approved?"})
        comment = Comment.objects.get(page=self.news_page)
        self.assertTrue(comment.is_approved)

    def test_comment_pending_when_auto_approve_off(self):
        settings = NewsSettings.load(request_or_site=None)
        settings.auto_approve_comments = False
        settings.save()
        self.client.login(username="participant@example.com", password="password123")
        self.client.post(self._add_comment_url(), {"body": "Needs review"})
        comment = Comment.objects.get(page=self.news_page)
        self.assertFalse(comment.is_approved)

    def test_anonymous_cannot_post_comment(self):
        response = self.client.post(self._add_comment_url(), {"body": "Anonymous"})
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.filter(page=self.news_page).count(), 0)

    def test_guest_cannot_post_comment(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(self._add_comment_url(), {"body": "Guest comment"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Comment.objects.filter(page=self.news_page).count(), 0)


class DeleteCommentViewTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        self.index = NewsIndexPage(title="News", slug="news-delete")
        root.add_child(instance=self.index)
        self.index.save_revision().publish()
        self.news_page = _make_news_page(self.index)
        self.participant = User.objects.create_user(
            username="participant@example.com",
            email="participant@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="password123",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.comment = Comment.objects.create(
            page=self.news_page,
            author=self.participant,
            body="A comment",
            is_approved=True,
        )

    def _delete_url(self):
        return reverse("news_delete_comment", args=[self.comment.pk])

    def test_staff_can_delete_comment(self):
        self.client.login(username="staff@example.com", password="password123")
        response = self.client.post(self._delete_url())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comment.objects.filter(pk=self.comment.pk).exists())

    def test_non_staff_cannot_delete_comment(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(self._delete_url())
        self.assertEqual(response.status_code, 403)

    def test_staff_without_admin_role_cannot_delete_comment(self):
        User.objects.create_user(
            username="staff_organizer@example.com",
            email="staff_organizer@example.com",
            password="password123",
            is_staff=True,
            role=User.Role.ORGANIZER,
        )
        self.client.login(username="staff_organizer@example.com", password="password123")
        response = self.client.post(self._delete_url())
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())

    def test_anonymous_cannot_delete_comment(self):
        response = self.client.post(self._delete_url())
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())


class SubmitNewsViewTests(TestCase):
    def setUp(self):
        self.participant = User.objects.create_user(
            username="participant@example.com",
            email="participant@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.guest = User.objects.create_user(
            username="guest@example.com",
            email="guest@example.com",
            password="password123",
            role=User.Role.GUEST,
        )

    def test_participant_can_submit(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(
            reverse("news_submit"),
            {"locale": "ru", "title": "My News", "body": "News content"},
        )
        self.assertEqual(response.status_code, 302)
        from knowledge.models import DraftSubmission

        sub = DraftSubmission.objects.get(title="My News")
        self.assertEqual(sub.submission_type, DraftSubmission.SubmissionType.NEWS)
        self.assertEqual(sub.author, self.participant)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(
            reverse("news_submit"),
            {"locale": "ru", "title": "News", "body": "body"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_guest_gets_403(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(
            reverse("news_submit"),
            {"locale": "ru", "title": "News", "body": "body"},
        )
        self.assertEqual(response.status_code, 403)

    def test_get_shows_form(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(reverse("news_submit"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], SubmitNewsForm)

    def test_submitted_news_appears_on_front_and_api_after_approval(self):
        # Full unification path: a community submission, once approved, becomes a NewsArticle that
        # shows up on the public /news/ list and in the public news API (not a stranded NewsPage).
        from knowledge.models import DraftSubmission

        self.client.login(username="participant@example.com", password="password123")
        self.client.post(
            reverse("news_submit"),
            {"locale": "ru", "title": "Community Story", "body": "<p>Reader-submitted</p>"},
        )
        sub = DraftSubmission.objects.get(title="Community Story")
        admin = User.objects.create_user(
            username="ed@example.com", email="ed@example.com", password="password123", role=User.Role.ADMIN
        )
        sub.approve(reviewer=admin)
        self.client.logout()

        page = self.client.get(reverse("news_index"))
        self.assertContains(page, "Community Story")

        api = self.client.get("/api/v1/news/")
        self.assertEqual(api.status_code, 200)
        self.assertIn("Community Story", [a["title"]["ru"] for a in api.json()])
        self.assertTrue(any("Reader-submitted" in a["body"]["ru"] for a in api.json()))

    def test_approval_fills_the_submitted_locale_columns(self):
        # Approval must populate the submission's own locale columns (not just RU) on the article.
        from knowledge.models import DraftSubmission
        from news.models import NewsArticle

        admin = User.objects.create_user(
            username="ed3@example.com", email="ed3@example.com", password="password123", role=User.Role.ADMIN
        )
        for locale in ("ru", "kk", "en"):
            with self.subTest(locale=locale):
                sub = DraftSubmission.objects.create(
                    author=self.participant,
                    submission_type=DraftSubmission.SubmissionType.NEWS,
                    locale=locale,
                    title=f"Title {locale}",
                    body=f"<p>body {locale}</p>",
                )
                sub.approve(reviewer=admin)
                article = NewsArticle.objects.get(**{f"title_{locale}": f"Title {locale}"})
                self.assertIn(f"body {locale}", getattr(article, f"body_{locale}"))


class NewsTagsTest(TestCase):
    def test_get_news_index_url_returns_none_when_no_index(self):
        from django.urls import reverse

        from news.templatetags.news_tags import get_news_index_url

        # When no Wagtail NewsIndexPage exists, the tag falls back to the Django news list URL.
        result = get_news_index_url()
        self.assertEqual(result, reverse("news_index"))

    def test_get_news_index_url_returns_url_when_index_exists(self):
        from news.templatetags.news_tags import get_news_index_url

        root = _get_site_root()
        index = NewsIndexPage(title="News", slug="news-tags")
        root.add_child(instance=index)
        index.save_revision().publish()
        result = get_news_index_url()
        self.assertIsNotNone(result)
        self.assertIn("news", result)


class NewsArticleHeroUploadTests(TestCase):
    """Frontend add-news cover upload: the hero image must save to news/hero/ and the
    stored cover must be served back (the prod scenario the user reported)."""

    def setUp(self):
        self._media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        self.admin = User.objects.create_user(
            username="news_admin",
            email="news_admin@example.com",
            password="Pass1234!",
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.admin)

    @staticmethod
    def _png(name="cover.png"):
        buf = io.BytesIO()
        PILImage.new("RGB", (32, 32), (255, 128, 0)).save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def _create_with_cover(self):
        return self.client.post(
            reverse("news_article_create"),
            {
                "title_ru": "Logo news",
                "title_kk": "",
                "title_en": "",
                "intro_ru": "",
                "intro_kk": "",
                "intro_en": "",
                "body_ru": "",
                "body_kk": "",
                "body_en": "",
                "published_at": "2026-06-17 16:51:00",
                "hero_image": self._png(),
            },
        )

    def test_create_article_saves_hero_image_file(self):
        with override_settings(MEDIA_ROOT=self._media):
            resp = self._create_with_cover()
            self.assertEqual(resp.status_code, 302)
            article = NewsArticle.objects.latest("id")
            self.assertTrue(article.hero_image.name.startswith("news/hero/"))
            self.assertTrue((Path(self._media) / article.hero_image.name).exists())

    def test_uploaded_cover_is_served_in_production(self):
        with override_settings(MEDIA_ROOT=self._media):
            self._create_with_cover()
            article = NewsArticle.objects.latest("id")
            with override_settings(DEBUG=False):
                resp = self.client.get(article.hero_image.url)
            self.assertEqual(resp.status_code, 200)


class NewsArticleSanitizeTests(TestCase):
    def test_save_sanitizes_each_locale_body(self):
        art = NewsArticle.objects.create(
            title_ru="San",
            body_ru="<p>ok</p><script>alert(1)</script>",
            body_en='<a href="javascript:evil()">x</a>',
        )
        art.refresh_from_db()
        self.assertIn("<p>ok</p>", art.body_ru)
        self.assertNotIn("<script", art.body_ru)
        self.assertNotIn("javascript:", art.body_en)

    def test_save_keeps_inline_image(self):
        art = NewsArticle.objects.create(title_ru="Img", body_ru='<p><img src="https://x.com/i.png" alt="a"></p>')
        art.refresh_from_db()
        self.assertIn("<img", art.body_ru)

    def test_found_in_search(self):
        from wagtail.search.backends import get_search_backend

        art = NewsArticle.objects.create(title_ru="SearchableNewsItem", body_ru="<p>x</p>")
        get_search_backend().add(art)
        resp = self.client.get(reverse("search") + "?query=SearchableNewsItem", HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(resp.status_code, 200)
        titles = [a.title for a in resp.context["news_results"]]
        self.assertIn("SearchableNewsItem", titles)


class NewsRichTextLimitTests(TestCase):
    """The shared rich-text size cap is enforced on every news write path (review #2)."""

    def test_submit_news_form_rejects_oversized_body(self):
        from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
        from news.forms import SubmitNewsForm

        form = SubmitNewsForm(data={"locale": "ru", "title": "T", "body": "a" * (MAX_RICH_TEXT_LENGTH + 1)})
        self.assertFalse(form.is_valid())
        self.assertIn("body", form.errors)

    def test_news_article_form_rejects_oversized_body(self):
        from cycling_site.richtext import MAX_RICH_TEXT_LENGTH
        from news.forms import NewsArticleForm

        form = NewsArticleForm(
            data={"title_ru": "T", "body_ru": "a" * (MAX_RICH_TEXT_LENGTH + 1), "published_at": "2026-01-01T00:00"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("body_ru", form.errors)

    def test_article_form_view_renders_oversized_body_error(self):
        # The hidden body field's error must be shown in the template, not silently swallowed.
        from cycling_site.richtext import MAX_RICH_TEXT_LENGTH

        admin = User.objects.create_user(
            username="ned@example.com", email="ned@example.com", password="password123", role=User.Role.ADMIN
        )
        self.client.force_login(admin)
        response = self.client.post(
            reverse("news_article_create"),
            {
                "title_ru": "T",
                "title_kk": "",
                "title_en": "",
                "intro_ru": "",
                "intro_kk": "",
                "intro_en": "",
                "body_ru": "a" * (MAX_RICH_TEXT_LENGTH + 1),
                "body_kk": "",
                "body_en": "",
                "published_at": "2026-01-01T00:00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too large")

    def test_article_form_view_renders_kk_and_en_field_errors(self):
        # KK/EN tab errors must be rendered (they sit in hidden tabs that JS auto-opens).
        from cycling_site.richtext import MAX_RICH_TEXT_LENGTH

        admin = User.objects.create_user(
            username="ned2@example.com", email="ned2@example.com", password="password123", role=User.Role.ADMIN
        )
        self.client.force_login(admin)
        response = self.client.post(
            reverse("news_article_create"),
            {
                "title_ru": "T",
                "title_kk": "",
                "title_en": "x" * 256,  # over title max_length=255
                "intro_ru": "",
                "intro_kk": "",
                "intro_en": "",
                "body_ru": "",
                "body_kk": "a" * (MAX_RICH_TEXT_LENGTH + 1),  # over the body cap
                "body_en": "",
                "published_at": "2026-01-01T00:00",
            },
            HTTP_ACCEPT_LANGUAGE="en",  # assert the English error strings deterministically
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too large")  # KK body error rendered
        self.assertContains(response, "at most 255")  # EN title error rendered

    def test_max_length_message_is_localized(self):
        # The form length error must come from the project catalog (translated for every locale),
        # not Django's built-in whose KK falls back to Russian.
        from django.utils.translation import gettext, override

        from news.forms import NewsArticleForm

        for loc in ("ru", "kk", "en"):
            with self.subTest(locale=loc), override(loc):
                form = NewsArticleForm(data={"title_ru": "a" * 256, "published_at": "2026-01-01T00:00"})
                self.assertFalse(form.is_valid())
                expected = gettext("Ensure this value has at most %(limit_value)d characters.") % {"limit_value": 255}
                self.assertEqual(form.errors["title_ru"][0], expected)


class NewsArticleCommentTests(TestCase):
    """Reader comments on a NewsArticle (mirrors calendar_app.CompetitionCommentTests)."""

    def _user(self, name, role):
        return User.objects.create_user(username=name, email=f"{name}@example.com", password="password123", role=role)

    def setUp(self):
        self.participant = self._user("news_commenter", User.Role.PARTICIPANT)
        self.other = self._user("news_other", User.Role.PARTICIPANT)
        self.admin = self._user("news_comment_admin", User.Role.ADMIN)
        self.article = NewsArticle.objects.create(title_ru="Comment News", body_ru="<p>x</p>")
        self.add_url = reverse("news_article_add_comment", args=[self.article.pk])

    def _add(self, user, body="Nice article!"):
        self.client.force_login(user)
        return self.client.post(self.add_url, {"body": body})

    def _make_comment(self, author=None, body="A comment"):
        return NewsArticleComment.objects.create(article=self.article, author=author or self.participant, body=body)

    def test_participant_can_post_comment(self):
        self._add(self.participant)
        self.assertEqual(NewsArticleComment.objects.count(), 1)
        comment = NewsArticleComment.objects.get()
        self.assertEqual(comment.author, self.participant)
        self.assertEqual(comment.article, self.article)

    def test_unauthenticated_user_redirected(self):
        response = self.client.post(self.add_url, {"body": "Hi"})
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(NewsArticleComment.objects.count(), 0)

    def test_guest_role_gets_403(self):
        guest = self._user("news_guest", User.Role.GUEST)
        self.client.force_login(guest)
        response = self.client.post(self.add_url, {"body": "Hi"})
        self.assertEqual(response.status_code, 403)

    def test_empty_body_is_rejected(self):
        response = self._add(self.participant, body="")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(NewsArticleComment.objects.count(), 0)

    def test_add_to_hidden_article_returns_404(self):
        self.article.is_hidden = True
        self.article.save(update_fields=["is_hidden"])
        response = self._add(self.participant)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(NewsArticleComment.objects.count(), 0)

    def test_detail_page_shows_comment(self):
        self._make_comment(body="Visible comment")
        response = self.client.get(reverse("news_article_detail", args=[self.article.pk]))
        self.assertContains(response, "Visible comment")

    def test_admin_can_delete_comment(self):
        comment = self._make_comment()
        self.client.force_login(self.admin)
        self.client.post(reverse("news_article_delete_comment", args=[comment.pk]))
        self.assertEqual(NewsArticleComment.objects.count(), 0)

    def test_non_manager_cannot_delete_comment(self):
        comment = self._make_comment(author=self.other)
        self.client.force_login(self.participant)
        response = self.client.post(reverse("news_article_delete_comment", args=[comment.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(NewsArticleComment.objects.count(), 1)

    def test_superuser_with_low_role_can_comment(self):
        # A superuser whose role is below participant still sees the form (display check) and must
        # be able to post it too, not get a 403.
        su = User.objects.create_user(
            username="su_news",
            email="su_news@example.com",
            password="password123",
            role=User.Role.GUEST,
            is_superuser=True,
            is_staff=True,
        )
        self.client.force_login(su)
        resp = self.client.post(self.add_url, {"body": "Admin note"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(NewsArticleComment.objects.filter(body="Admin note").exists())

    def test_anonymous_detail_does_not_expose_author_email(self):
        self._make_comment(body="Hi")  # author has no name set
        response = self.client.get(reverse("news_article_detail", args=[self.article.pk]))
        self.assertNotContains(response, self.participant.email)

    def test_detail_shows_full_name_when_set(self):
        self.participant.first_name = "Anna"
        self.participant.last_name = "Smith"
        self.participant.save()
        self._make_comment(body="Hi")
        response = self.client.get(reverse("news_article_detail", args=[self.article.pk]))
        self.assertContains(response, "Anna Smith")
        self.assertNotContains(response, self.participant.email)
