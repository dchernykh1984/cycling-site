import importlib
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from wagtail.models import Locale, Page, Site

from accounts.models import User
from knowledge.models import DraftSubmission, KnowledgeArticle, KnowledgeIndexPage

_MIG_0008 = "knowledge.migrations.0008_populate_knowledgearticle"


def _get_site_root():
    site = Site.objects.filter(is_default_site=True).first()
    return site.root_page if site else Page.objects.filter(depth=1).first()


def _ru_index():
    ru = Locale.objects.get(language_code="ru")
    return KnowledgeIndexPage.objects.live().filter(locale=ru).first()


def _make_user(email, role, **kwargs):
    return User.objects.create_user(username=email, email=email, password="password123", role=role, **kwargs)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class KnowledgeArticleModelTests(TestCase):
    def test_save_sanitizes_body(self):
        art = KnowledgeArticle.objects.create(
            title="Sanitize me",
            locale="ru",
            body='<p>Hi <strong>x</strong></p><a href="https://x.com">l</a><script>alert(1)</script>',
        )
        art.refresh_from_db()
        self.assertIn("<strong>x</strong>", art.body)
        self.assertIn('href="https://x.com"', art.body)
        self.assertNotIn("<script", art.body)

    def test_save_keeps_inline_image(self):
        art = KnowledgeArticle.objects.create(
            title="Img", locale="ru", body='<p><img src="https://x.com/i.png" alt="a"></p>'
        )
        art.refresh_from_db()
        self.assertIn("<img", art.body)

    def test_autoslug_from_title_is_ascii_and_unique(self):
        a1 = KnowledgeArticle.objects.create(title="Hello World", locale="en")
        a2 = KnowledgeArticle.objects.create(title="Hello World", locale="en")
        self.assertEqual(a1.slug, "hello-world")
        self.assertEqual(a2.slug, "hello-world-1")

    def test_cyrillic_title_falls_back_to_ascii_slug(self):
        # Cyrillic small 'a' x5 -> slugify(allow_unicode=False) == "" -> "article" base.
        art = KnowledgeArticle.objects.create(title=chr(0x0430) * 5, locale="ru")
        self.assertTrue(art.slug)
        self.assertRegex(art.slug, r"^[a-z0-9-]+$")

    def test_get_absolute_url_uses_index_and_slug(self):
        art = KnowledgeArticle.objects.create(title="Url Article", locale="en")
        self.assertTrue(art.get_absolute_url().endswith(f"{art.slug}/"))


class KnowledgeMigrationHelperTests(TestCase):
    """The 0008 data migration's pure helpers (body extraction + tag re-link)."""

    def test_body_from_blocks_concatenates_only_text_blocks(self):
        mig = importlib.import_module(_MIG_0008)
        raw = json.dumps(
            [
                {"type": "text", "value": "<p>a</p>"},
                {"type": "image", "value": 1},
                {"type": "text", "value": "<p>b</p>"},
            ]
        )
        self.assertEqual(mig._body_from_blocks(raw), "<p>a</p><p>b</p>")

    def test_attach_tags_recreates_taggit_links(self):
        from django.contrib.contenttypes.models import ContentType
        from taggit.models import Tag, TaggedItem

        mig = importlib.import_module(_MIG_0008)
        art = KnowledgeArticle.objects.create(title="Tagged Migrate", locale="ru")
        t1 = Tag.objects.create(name="alpha", slug="alpha")
        t2 = Tag.objects.create(name="beta", slug="beta")
        ct = ContentType.objects.get_for_model(KnowledgeArticle)
        mig._attach_tags(TaggedItem, ct, art.pk, [t1.pk, t2.pk])
        self.assertEqual(set(art.tags.names()), {"alpha", "beta"})

    def test_data_migrations_are_irreversible(self):
        # Reversing would silently lose data, so the destructive data migrations must refuse
        # to roll back rather than recreate empty tables.
        for name in (_MIG_0008, "knowledge.migrations.0009_delete_knowledge_pages_data"):
            mig = importlib.import_module(name)
            self.assertFalse(mig.Migration.operations[0].reversible, name)


# ---------------------------------------------------------------------------
# Public views (index listing + slug detail routed via KnowledgeIndexPage)
# ---------------------------------------------------------------------------


class KnowledgeArticleViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("kv_admin@example.com", User.Role.ADMIN)
        self.article = KnowledgeArticle.objects.create(
            title="Cycling Routes in Almaty",
            locale="ru",
            body="<p>Great <strong>routes</strong> here</p>",
            category="Routes",
        )

    def test_index_lists_article(self):
        resp = self.client.get(_ru_index().url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cycling Routes in Almaty")
        self.assertContains(resp, self.article.get_absolute_url())

    def test_detail_renders_body_as_html(self):
        resp = self.client.get(self.article.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "<strong>routes</strong>", html=False)
        self.assertNotContains(resp, "&lt;strong&gt;")

    def test_unknown_slug_returns_404(self):
        resp = self.client.get(_ru_index().url + "no-such-article-xyz/")
        self.assertEqual(resp.status_code, 404)

    def test_hidden_article_404_for_anon_but_200_for_admin(self):
        self.article.is_hidden = True
        self.article.save(update_fields=["is_hidden"])
        self.assertEqual(self.client.get(self.article.get_absolute_url()).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.article.get_absolute_url()).status_code, 200)

    def test_deleted_article_404(self):
        self.article.is_deleted = True
        self.article.save(update_fields=["is_deleted"])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.article.get_absolute_url()).status_code, 404)

    def test_edit_link_is_on_site_not_wagtail(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.article.get_absolute_url())
        self.assertContains(resp, reverse("knowledge_article_edit", args=[self.article.pk]))
        self.assertNotContains(resp, "/admin/pages/")


class KnowledgeForeignLocaleBannerTests(TestCase):
    def setUp(self):
        self.article = KnowledgeArticle.objects.create(
            title="Foreign Locale Banner Article", locale="ru", body="<p>Original body content</p>"
        )

    def test_same_locale_serves_without_banner(self):
        resp = self.client.get(self.article.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Original body content")
        with translation.override("ru"):
            self.assertNotContains(resp, _("Search for a similar article in your language"))

    def test_foreign_locale_serves_original_with_banner(self):
        resp = self.client.get(self.article.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Original body content")
        self.assertContains(resp, "shown in its original language")
        self.assertContains(resp, reverse("search"))


# ---------------------------------------------------------------------------
# DraftSubmission model + participant submit
# ---------------------------------------------------------------------------


class DraftSubmissionModelTests(TestCase):
    def setUp(self):
        self.user = _make_user("dsm_participant@example.com", User.Role.PARTICIPANT)

    def test_create_submission_defaults_to_pending(self):
        sub = DraftSubmission.objects.create(
            author=self.user,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="My Article",
            body="Article body text",
        )
        self.assertEqual(sub.status, DraftSubmission.Status.PENDING)

    def test_str_representation(self):
        sub = DraftSubmission(
            author=self.user,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            title="My Article",
        )
        self.assertIn("My Article", str(sub))


class SubmissionFormViewTests(TestCase):
    def setUp(self):
        self.participant = _make_user("sf_participant@example.com", User.Role.PARTICIPANT)
        self.guest = _make_user("sf_guest@example.com", User.Role.GUEST)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("knowledge_submit"))
        self.assertRedirects(resp, f"/accounts/login/?next={reverse('knowledge_submit')}")

    def test_guest_gets_403(self):
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(reverse("knowledge_submit")).status_code, 403)

    def test_participant_can_view_form_with_quill_editor(self):
        self.client.force_login(self.participant)
        resp = self.client.get(reverse("knowledge_submit"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="quill-body"')
        self.assertContains(resp, "vendor/quill/quill.min.js")

    def test_participant_can_submit(self):
        self.client.force_login(self.participant)
        resp = self.client.post(
            reverse("knowledge_submit"),
            {"locale": "ru", "title": "New Article", "body": "<p>Article content</p>", "category": "Routes"},
        )
        self.assertRedirects(resp, reverse("account_profile"))
        sub = DraftSubmission.objects.get(title="New Article")
        self.assertEqual(sub.author, self.participant)
        self.assertEqual(sub.status, DraftSubmission.Status.PENDING)

    def test_guest_post_does_not_create_submission(self):
        self.client.force_login(self.guest)
        resp = self.client.post(
            reverse("knowledge_submit"),
            {"locale": "ru", "title": "Sneaky", "body": "<p>x</p>", "category": ""},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(DraftSubmission.objects.count(), 0)


# ---------------------------------------------------------------------------
# DraftSubmission.approve / reject
# ---------------------------------------------------------------------------


class DraftSubmissionApproveRejectTests(TestCase):
    def setUp(self):
        self.staff = _make_user("ar_staff@example.com", User.Role.ADMIN, is_staff=True)
        self.participant = _make_user("ar_participant@example.com", User.Role.PARTICIPANT)
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="Approved Article",
            body="<p>Article body content</p>",
            category="Routes",
        )

    def test_approve_creates_knowledge_article(self):
        self.submission.approve(reviewer=self.staff)
        art = KnowledgeArticle.objects.get(title="Approved Article")
        self.assertEqual(art.locale, "ru")
        self.assertEqual(art.category, "Routes")
        self.assertEqual(art.published_by, self.participant)

    def test_approve_sets_status_and_reviewed_by(self):
        self.submission.approve(reviewer=self.staff)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)
        self.assertEqual(self.submission.reviewed_by, self.staff)

    def test_reject_sets_status_note_and_reviewed_by(self):
        self.submission.reject(reviewer=self.staff, note="Not relevant content")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "Not relevant content")
        self.assertEqual(self.submission.reviewed_by, self.staff)

    def test_approve_strips_dangerous_html(self):
        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="XSS Test Article",
            body='<p onclick="evil()">hi</p><script>alert(\'xss\')</script><a href="javascript:evil()">l</a>',
        )
        sub.approve(reviewer=self.staff)
        art = KnowledgeArticle.objects.get(title="XSS Test Article")
        self.assertNotIn("<script", art.body)
        self.assertNotIn("onclick", art.body)
        self.assertNotIn("javascript:", art.body)
        self.assertIn("hi", art.body)
        self.assertEqual(self.client.get(art.get_absolute_url()).status_code, 200)

    def test_approve_keeps_rich_html_body(self):
        body = "<h2>Section</h2><p>Intro with <strong>bold</strong>.</p><ul><li>first</li></ul>"
        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="Rich Body Article",
            body=body,
        )
        sub.approve(reviewer=self.staff)
        art = KnowledgeArticle.objects.get(title="Rich Body Article")
        self.assertIn("<h2>Section</h2>", art.body)
        self.assertIn("<li>first</li>", art.body)
        self.assertNotIn("&lt;h2&gt;", art.body)

    def test_double_approve_raises_error(self):
        self.submission.approve(reviewer=self.staff)
        with self.assertRaises(ValueError):
            self.submission.approve(reviewer=self.staff)
        self.assertEqual(KnowledgeArticle.objects.filter(title=self.submission.title).count(), 1)

    def test_approve_reads_db_status_not_memory_status(self):
        DraftSubmission.objects.filter(pk=self.submission.pk).update(status=DraftSubmission.Status.APPROVED)
        stale = DraftSubmission.objects.get(pk=self.submission.pk)
        stale.status = DraftSubmission.Status.PENDING
        with self.assertRaises(ValueError):
            stale.approve(reviewer=self.staff)
        self.assertEqual(KnowledgeArticle.objects.filter(title=self.submission.title).count(), 0)

    def test_reject_after_approve_raises_error(self):
        self.submission.approve(reviewer=self.staff)
        with self.assertRaises(ValueError):
            self.submission.reject(reviewer=self.staff, note="oops")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)

    def test_news_submission_creates_news_page_not_article(self):
        from news.models import NewsIndexPage, NewsPage

        news_index = NewsIndexPage(title="News", slug="news-approve")
        _get_site_root().add_child(instance=news_index)
        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.NEWS,
            locale="ru",
            title="Breaking News",
            body="<p>News body</p>",
        )
        sub.approve(reviewer=self.staff)
        self.assertEqual(NewsPage.objects.filter(title="Breaking News").count(), 1)
        self.assertEqual(KnowledgeArticle.objects.filter(title="Breaking News").count(), 0)


# ---------------------------------------------------------------------------
# Manager add / edit (on-site Quill)
# ---------------------------------------------------------------------------


class AddArticleViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("aa_admin@example.com", User.Role.ADMIN)
        self.participant = _make_user("aa_participant@example.com", User.Role.PARTICIPANT)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("knowledge_add"))
        self.assertRedirects(resp, f"/accounts/login/?next={reverse('knowledge_add')}")

    def test_participant_gets_403(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(reverse("knowledge_add")).status_code, 403)

    def test_admin_can_view_form_with_quill(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("knowledge_add"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="quill-body"')

    def test_admin_post_creates_article_directly(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("knowledge_add"),
            {"locale": "ru", "title": "Published Article", "body": "<p>Body</p>", "category": "Routes"},
        )
        self.assertEqual(resp.status_code, 302)
        art = KnowledgeArticle.objects.get(title="Published Article")
        self.assertEqual(art.published_by, self.admin)
        # No moderation draft is created for the manager add path.
        self.assertEqual(DraftSubmission.objects.count(), 0)

    def test_admin_post_sanitizes_body(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("knowledge_add"),
            {"locale": "ru", "title": "Add XSS", "body": "<p>ok</p><script>alert(1)</script>", "category": ""},
        )
        art = KnowledgeArticle.objects.get(title="Add XSS")
        self.assertNotIn("<script", art.body)

    def test_admin_post_saves_tags(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("knowledge_add"),
            {"locale": "ru", "title": "Tagged Add", "body": "<p>x</p>", "category": "", "tags": "alpha, beta"},
        )
        art = KnowledgeArticle.objects.get(title="Tagged Add")
        self.assertEqual(set(art.tags.names()), {"alpha", "beta"})


class EditArticleViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("ea_admin@example.com", User.Role.ADMIN)
        self.participant = _make_user("ea_participant@example.com", User.Role.PARTICIPANT)
        self.article = KnowledgeArticle.objects.create(title="Editable", locale="ru", body="<p>old</p>")

    def test_participant_gets_403(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get(reverse("knowledge_article_edit", args=[self.article.pk])).status_code, 403)

    def test_admin_can_view_edit_form_prefilled(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("knowledge_article_edit", args=[self.article.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="quill-body"')
        self.assertContains(resp, "Editable")

    def test_admin_edit_updates_and_sanitizes(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("knowledge_article_edit", args=[self.article.pk]),
            {"locale": "ru", "title": "Editable", "body": "<p>new</p><script>x</script>", "category": ""},
        )
        self.assertEqual(resp.status_code, 302)
        self.article.refresh_from_db()
        self.assertIn("<p>new</p>", self.article.body)
        self.assertNotIn("<script", self.article.body)

    def test_admin_can_hide_and_unhide(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("knowledge_article_hide", args=[self.article.pk]))
        self.article.refresh_from_db()
        self.assertTrue(self.article.is_hidden)
        self.client.post(reverse("knowledge_article_hide", args=[self.article.pk]))
        self.article.refresh_from_db()
        self.assertFalse(self.article.is_hidden)

    def test_admin_can_delete(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("knowledge_article_delete", args=[self.article.pk]))
        self.assertEqual(resp.status_code, 302)
        self.article.refresh_from_db()
        self.assertTrue(self.article.is_deleted)

    def test_edit_form_prefills_tags(self):
        self.article.tags.add("existing")
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("knowledge_article_edit", args=[self.article.pk]))
        self.assertContains(resp, "existing")

    def test_admin_edit_updates_tags(self):
        self.article.tags.add("old")
        self.client.force_login(self.admin)
        self.client.post(
            reverse("knowledge_article_edit", args=[self.article.pk]),
            {"locale": "ru", "title": "Editable", "body": "<p>x</p>", "category": "", "tags": "new1, new2"},
        )
        self.article.refresh_from_db()
        self.assertEqual(set(self.article.tags.names()), {"new1", "new2"})


# ---------------------------------------------------------------------------
# Submission moderation views (DraftSubmission)
# ---------------------------------------------------------------------------


class SubmissionDetailViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("sd_admin@example.com", User.Role.ADMIN)
        self.participant = _make_user("sd_participant@example.com", User.Role.PARTICIPANT)
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="Pending Article Detail",
            body="<p>Body</p>",
        )

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_participant_gets_403(self):
        self.client.force_login(self.participant)
        self.assertEqual(
            self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk])).status_code, 403
        )

    def test_admin_can_view_detail(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pending Article Detail")

    def test_news_submission_returns_404_on_detail(self):
        news_sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.NEWS,
            locale="ru",
            title="News Detail 404",
            body="<p>Body</p>",
        )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("knowledge_submission_detail", args=[news_sub.pk]))
        self.assertEqual(resp.status_code, 404)


class ApproveSubmissionViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("av_admin@example.com", User.Role.ADMIN)
        self.participant = _make_user("av_participant@example.com", User.Role.PARTICIPANT)
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="To Be Approved Via View",
            body="<p>Body</p>",
        )

    def test_admin_approve_creates_article(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertEqual(resp.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)
        self.assertEqual(KnowledgeArticle.objects.filter(title="To Be Approved Via View").count(), 1)

    def test_participant_cannot_approve(self):
        self.client.force_login(self.participant)
        resp = self.client.post(reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertEqual(resp.status_code, 403)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.PENDING)

    def test_double_approve_redirects_to_detail(self):
        self.submission.approve(reviewer=self.admin)
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertRedirects(resp, reverse("knowledge_submission_detail", args=[self.submission.pk]))


class RejectSubmissionViewTests(TestCase):
    def setUp(self):
        self.admin = _make_user("rv_admin@example.com", User.Role.ADMIN)
        self.participant = _make_user("rv_participant@example.com", User.Role.PARTICIPANT)
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="To Be Rejected Via View",
            body="<p>Body</p>",
        )

    def test_admin_reject_with_note(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("knowledge_submission_reject", args=[self.submission.pk]), {"note": "Not suitable content"}
        )
        self.assertEqual(resp.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "Not suitable content")

    def test_participant_cannot_reject(self):
        self.client.force_login(self.participant)
        resp = self.client.post(reverse("knowledge_submission_reject", args=[self.submission.pk]), {"note": "Sneaky"})
        self.assertEqual(resp.status_code, 403)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.PENDING)


# ---------------------------------------------------------------------------
# Localization of the on-site forms
# ---------------------------------------------------------------------------


class AddArticleFormLocalizationTests(TestCase):
    def setUp(self):
        self.admin = _make_user("loc_admin@example.com", User.Role.ADMIN)
        self.client.force_login(self.admin)
        self.url = reverse("knowledge_add")

    def test_field_labels_in_russian(self):
        resp = self.client.get(self.url)
        with translation.override("ru"):
            for label in ("Locale", "Title", "Body", "Category"):
                self.assertContains(resp, _(label))

    def test_locale_choices_in_russian(self):
        resp = self.client.get(self.url)
        with translation.override("ru"):
            for label in ("Russian", "Kazakh", "English"):
                self.assertContains(resp, _(label))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchReturnsKnowledgeArticleTests(TestCase):
    def setUp(self):
        self.article = KnowledgeArticle.objects.create(
            title="Cycling Routes in Almaty", locale="ru", body="<p>routes</p>"
        )

    def test_search_page_returns_200(self):
        self.assertEqual(self.client.get(reverse("search") + "?query=Almaty").status_code, 200)

    def test_search_finds_article_by_title(self):
        from wagtail.search.backends import get_search_backend

        get_search_backend().add(self.article)
        resp = self.client.get(reverse("search") + "?query=Almaty", HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Almaty")
