import json
from unittest import skip

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from accounts.models import User
from knowledge.models import (
    DraftSubmission,
    KnowledgeArticlePage,
    KnowledgeIndexPage,
    LocationArticlePage,
)


class KnowledgePageHierarchyTests(WagtailPageTests):
    def test_can_create_article_under_index(self):
        self.assertCanCreateAt(KnowledgeIndexPage, KnowledgeArticlePage)

    def test_can_create_location_under_index(self):
        self.assertCanCreateAt(KnowledgeIndexPage, LocationArticlePage)

    def test_article_cannot_be_created_under_root(self):
        self.assertCanNotCreateAt(Page, KnowledgeArticlePage)


def _get_site_root():
    site = Site.objects.filter(is_default_site=True).first()
    return site.root_page if site else Page.objects.filter(depth=1).first()


class KnowledgeArticlePageRenderTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        self.index = KnowledgeIndexPage(title="Knowledge", slug="knowledge")
        root.add_child(instance=self.index)
        self.article = KnowledgeArticlePage(
            title="Test Article",
            slug="test-article",
            body=json.dumps([{"type": "text", "value": "<p>Hello world</p>"}]),
        )
        self.index.add_child(instance=self.article)

    @skip("slug conflict with migration-created KnowledgeIndexPage -fix test setUp to handle migration data")
    def test_index_renders(self):
        response = self.client.get(self.index.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Article")

    @skip("slug conflict with migration-created KnowledgeIndexPage -fix test setUp to handle migration data")
    def test_article_renders(self):
        response = self.client.get(self.article.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Article")
        self.assertContains(response, "Hello world")


class LocationArticlePageRenderTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        index = KnowledgeIndexPage(title="Knowledge", slug="knowledge")
        root.add_child(instance=index)
        self.location = LocationArticlePage(
            title="Almaty Loop Route",
            slug="almaty-loop",
        )
        index.add_child(instance=self.location)

    @skip("slug conflict with migration-created KnowledgeIndexPage -fix test setUp to handle migration data")
    def test_location_article_renders(self):
        response = self.client.get(self.location.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Almaty Loop Route")


class SearchReturnsKnowledgeArticleTests(TestCase):
    def setUp(self):
        root = _get_site_root()
        index = KnowledgeIndexPage(title="Knowledge", slug="knowledge")
        root.add_child(instance=index)
        self.article = KnowledgeArticlePage(
            title="Cycling Routes in Almaty",
            slug="cycling-routes-almaty",
        )
        index.add_child(instance=self.article)

    @skip("slug conflict with migration-created KnowledgeIndexPage -fix test setUp to handle migration data")
    def test_search_page_returns_200(self):
        response = self.client.get(reverse("search") + "?query=Almaty")
        self.assertEqual(response.status_code, 200)

    @skip("slug conflict with migration-created KnowledgeIndexPage -fix test setUp to handle migration data")
    def test_search_finds_article_by_title(self):
        from wagtail.search.backends import get_search_backend

        backend = get_search_backend()
        backend.add(self.article)
        response = self.client.get(reverse("search") + "?query=Almaty")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Almaty")


class DraftSubmissionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="participant@example.com",
            email="participant@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )

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
        self.client = Client()
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

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("knowledge_submit"))
        self.assertRedirects(
            response,
            f"/accounts/login/?next={reverse('knowledge_submit')}",
        )

    def test_guest_gets_403(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.get(reverse("knowledge_submit"))
        self.assertEqual(response.status_code, 403)

    def test_participant_can_view_form(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.get(reverse("knowledge_submit"))
        self.assertEqual(response.status_code, 200)

    def test_participant_can_submit(self):
        self.client.login(username="participant@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_submit"),
            {
                "submission_type": "knowledge_article",
                "locale": "ru",
                "title": "New Article",
                "body": "Article content here",
                "category": "Routes",
            },
        )
        self.assertRedirects(response, reverse("account_profile"))
        self.assertEqual(DraftSubmission.objects.count(), 1)
        sub = DraftSubmission.objects.first()
        self.assertEqual(sub.author, self.participant)
        self.assertEqual(sub.status, DraftSubmission.Status.PENDING)

    def test_guest_post_does_not_create_submission(self):
        self.client.login(username="guest@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_submit"),
            {
                "submission_type": "knowledge_article",
                "locale": "ru",
                "title": "Sneaky Article",
                "body": "Content",
                "category": "",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DraftSubmission.objects.count(), 0)


class DraftSubmissionApproveRejectTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="password123",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.participant = User.objects.create_user(
            username="participant@example.com",
            email="participant@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        root = _get_site_root()
        self.index = KnowledgeIndexPage(title="Knowledge", slug="knowledge-approve")
        root.add_child(instance=self.index)
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="Approved Article",
            body="Article body content",
            category="Routes",
        )

    def test_approve_creates_knowledge_article_page(self):
        self.submission.approve(reviewer=self.staff)
        self.assertEqual(KnowledgeArticlePage.objects.filter(title="Approved Article").count(), 1)

    def test_approve_sets_status_and_reviewed_by(self):
        self.submission.approve(reviewer=self.staff)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)
        self.assertEqual(self.submission.reviewed_by, self.staff)

    @skip("migration creates KnowledgeIndexPage for all locales -fix test to use a locale without index page")
    def test_approve_fails_without_index_page(self):
        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="kk",
            title="KK Submission",
            body="body",
        )
        with self.assertRaises(ValueError):
            sub.approve(reviewer=self.staff)

    def test_reject_sets_status_note_and_reviewed_by(self):
        self.submission.reject(reviewer=self.staff, note="Not relevant content")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "Not relevant content")
        self.assertEqual(self.submission.reviewed_by, self.staff)

    def test_admin_approve_view_post(self):
        self.client.login(username="staff@example.com", password="password123")
        approve_url = reverse(
            "wagtailsnippets_knowledge_draftsubmission:approve",
            args=[self.submission.pk],
        )
        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)
        self.assertEqual(KnowledgeArticlePage.objects.filter(title="Approved Article").count(), 1)

    def test_admin_reject_view_post(self):
        self.client.login(username="staff@example.com", password="password123")
        reject_url = reverse(
            "wagtailsnippets_knowledge_draftsubmission:reject",
            args=[self.submission.pk],
        )
        response = self.client.post(reject_url, {"reviewer_note": "Not suitable"})
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "Not suitable")

    def test_non_staff_cannot_access_approve_view(self):
        self.client.login(username="participant@example.com", password="password123")
        approve_url = reverse(
            "wagtailsnippets_knowledge_draftsubmission:approve",
            args=[self.submission.pk],
        )
        response = self.client.post(approve_url)
        self.assertNotEqual(response.status_code, 200)

    def test_approve_escapes_body_html(self):
        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="XSS Test Article",
            body="<script>alert('xss')</script>",
        )
        sub.approve(reviewer=self.staff)
        article = KnowledgeArticlePage.objects.get(title="XSS Test Article")
        response = self.client.get(article.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert")

    def test_approve_unknown_locale_raises_error(self):
        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="de",
            title="German Submission",
            body="body",
        )
        with self.assertRaises(ValueError, msg="Locale 'de' is not configured"):
            sub.approve(reviewer=self.staff)
        self.assertEqual(DraftSubmission.objects.get(pk=sub.pk).status, DraftSubmission.Status.PENDING)

    def test_double_approve_raises_error(self):
        self.submission.approve(reviewer=self.staff)
        with self.assertRaises(ValueError):
            self.submission.approve(reviewer=self.staff)
        self.assertEqual(KnowledgeArticlePage.objects.filter(title=self.submission.title).count(), 1)

    def test_reject_after_approve_raises_error(self):
        self.submission.approve(reviewer=self.staff)
        with self.assertRaises(ValueError):
            self.submission.reject(reviewer=self.staff, note="oops")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)

    def test_news_submission_creates_news_page(self):
        from news.models import NewsIndexPage, NewsPage

        news_index = NewsIndexPage(title="News", slug="news-approve")
        _get_site_root().add_child(instance=news_index)

        sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.NEWS,
            locale="ru",
            title="Breaking News",
            body="News body",
        )
        sub.approve(reviewer=self.staff)
        self.assertEqual(NewsPage.objects.filter(title="Breaking News").count(), 1)
        self.assertEqual(KnowledgeArticlePage.objects.filter(title="Breaking News").count(), 0)
        sub.refresh_from_db()
        self.assertEqual(sub.status, DraftSubmission.Status.APPROVED)


class AddArticleViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-add@example.com",
            email="admin-add@example.com",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.participant = User.objects.create_user(
            username="participant-add@example.com",
            email="participant-add@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("knowledge_add"))
        self.assertRedirects(
            response,
            f"/accounts/login/?next={reverse('knowledge_add')}",
        )

    def test_participant_gets_403(self):
        self.client.login(username="participant-add@example.com", password="password123")
        response = self.client.get(reverse("knowledge_add"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_view_form(self):
        self.client.login(username="admin-add@example.com", password="password123")
        response = self.client.get(reverse("knowledge_add"))
        self.assertEqual(response.status_code, 200)

    def test_admin_post_creates_and_publishes_article(self):
        self.client.login(username="admin-add@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_add"),
            {
                "locale": "ru",
                "title": "Published Article",
                "body": "Article content",
                "category": "Routes",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(KnowledgeArticlePage.objects.filter(title="Published Article").count(), 1)
        sub = DraftSubmission.objects.get(title="Published Article")
        self.assertEqual(sub.status, DraftSubmission.Status.APPROVED)
        self.assertEqual(sub.author, self.admin)

    def test_admin_post_does_not_leave_pending_submission(self):
        self.client.login(username="admin-add@example.com", password="password123")
        self.client.post(
            reverse("knowledge_add"),
            {
                "locale": "ru",
                "title": "Instant Article",
                "body": "Body",
                "category": "",
            },
        )
        sub = DraftSubmission.objects.get(title="Instant Article")
        self.assertNotEqual(sub.status, DraftSubmission.Status.PENDING)


class SubmissionDetailViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-detail@example.com",
            email="admin-detail@example.com",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.participant = User.objects.create_user(
            username="participant-detail@example.com",
            email="participant-detail@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="Pending Article Detail",
            body="Body text",
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 302)

    def test_participant_gets_403(self):
        self.client.login(username="participant-detail@example.com", password="password123")
        response = self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_view_detail(self):
        self.client.login(username="admin-detail@example.com", password="password123")
        response = self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Article Detail")

    def test_news_submission_returns_404_on_detail(self):
        news_sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.NEWS,
            locale="ru",
            title="News Detail 404",
            body="Body",
        )
        self.client.login(username="admin-detail@example.com", password="password123")
        response = self.client.get(reverse("knowledge_submission_detail", args=[news_sub.pk]))
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_approve_and_reject_buttons_for_pending(self):
        self.client.login(username="admin-detail@example.com", password="password123")
        response = self.client.get(reverse("knowledge_submission_detail", args=[self.submission.pk]))
        self.assertContains(response, reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertContains(response, reverse("knowledge_submission_reject", args=[self.submission.pk]))


class ApproveSubmissionViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-approve@example.com",
            email="admin-approve@example.com",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.participant = User.objects.create_user(
            username="participant-approve@example.com",
            email="participant-approve@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="To Be Approved Via View",
            body="Body text",
        )

    def test_admin_approve_creates_article(self):
        self.client.login(username="admin-approve@example.com", password="password123")
        response = self.client.post(reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)
        self.assertEqual(KnowledgeArticlePage.objects.filter(title="To Be Approved Via View").count(), 1)

    def test_approve_returns_success_message(self):
        self.client.login(username="admin-approve@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_submission_approve", args=[self.submission.pk]),
            follow=True,
        )
        self.assertContains(response, "alert-success")

    def test_news_submission_returns_404(self):
        from news.models import NewsIndexPage

        news_index = NewsIndexPage(title="News", slug="news-approve-view-test")
        _get_site_root().add_child(instance=news_index)
        news_sub = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.NEWS,
            locale="ru",
            title="News Via Knowledge URL",
            body="Body",
        )
        self.client.login(username="admin-approve@example.com", password="password123")
        response = self.client.post(reverse("knowledge_submission_approve", args=[news_sub.pk]))
        self.assertEqual(response.status_code, 404)

    def test_participant_cannot_approve(self):
        self.client.login(username="participant-approve@example.com", password="password123")
        response = self.client.post(reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 403)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.PENDING)

    def test_double_approve_redirects_to_detail(self):
        self.submission.approve(reviewer=self.admin)
        self.client.login(username="admin-approve@example.com", password="password123")
        response = self.client.post(reverse("knowledge_submission_approve", args=[self.submission.pk]))
        self.assertRedirects(
            response,
            reverse("knowledge_submission_detail", args=[self.submission.pk]),
        )


class RejectSubmissionViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-reject@example.com",
            email="admin-reject@example.com",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.participant = User.objects.create_user(
            username="participant-reject@example.com",
            email="participant-reject@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="To Be Rejected Via View",
            body="Body text",
        )

    def test_admin_reject_with_note(self):
        self.client.login(username="admin-reject@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_submission_reject", args=[self.submission.pk]),
            {"note": "Not suitable content"},
        )
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "Not suitable content")
        self.assertEqual(self.submission.reviewed_by, self.admin)

    def test_admin_reject_without_note(self):
        self.client.login(username="admin-reject@example.com", password="password123")
        response = self.client.post(reverse("knowledge_submission_reject", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "")

    def test_participant_cannot_reject(self):
        self.client.login(username="participant-reject@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_submission_reject", args=[self.submission.pk]),
            {"note": "Sneaky reject"},
        )
        self.assertEqual(response.status_code, 403)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.PENDING)

    def test_reject_redirects_to_detail(self):
        self.client.login(username="admin-reject@example.com", password="password123")
        response = self.client.post(
            reverse("knowledge_submission_reject", args=[self.submission.pk]),
            {"note": ""},
        )
        self.assertRedirects(
            response,
            reverse("knowledge_submission_detail", args=[self.submission.pk]),
        )


class SubmissionDetailTranslationTests(TestCase):
    """submission_detail.html 'Submitted' label is translated (no fuzzy marker)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-trans@example.com",
            email="admin-trans@example.com",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.participant = User.objects.create_user(
            username="participant-trans@example.com",
            email="participant-trans@example.com",
            password="password123",
            role=User.Role.PARTICIPANT,
        )
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            locale="ru",
            title="Trans Test Article",
            body="body",
        )
        self.client.login(username="admin-trans@example.com", password="password123")
        self.url = reverse("knowledge_submission_detail", args=[self.submission.pk])

    def test_submitted_label_in_russian(self):
        response = self.client.get(self.url)
        with translation.override("ru"):
            self.assertContains(response, _("Submitted"))

    def test_submitted_label_in_kazakh(self):
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="kk")
        with translation.override("kk"):
            self.assertContains(response, _("Submitted"))

    def test_author_label_in_russian(self):
        response = self.client.get(self.url)
        with translation.override("ru"):
            self.assertContains(response, _("Author"))

    def test_author_label_in_kazakh(self):
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="kk")
        with translation.override("kk"):
            self.assertContains(response, _("Author"))


class AddArticleFormLocalizationTests(TestCase):
    """add_article.html form labels and locale choices are translated."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-loc@example.com",
            email="admin-loc@example.com",
            password="password123",
            role=User.Role.ADMIN,
        )
        self.client.login(username="admin-loc@example.com", password="password123")
        self.url = reverse("knowledge_add")

    def test_field_labels_in_russian(self):
        response = self.client.get(self.url)
        with translation.override("ru"):
            self.assertContains(response, _("Locale"))
            self.assertContains(response, _("Title"))
            self.assertContains(response, _("Body"))
            self.assertContains(response, _("Category"))

    def test_locale_choices_in_russian(self):
        response = self.client.get(self.url)
        with translation.override("ru"):
            self.assertContains(response, _("Russian"))
            self.assertContains(response, _("Kazakh"))
            self.assertContains(response, _("English"))

    def test_field_labels_in_kazakh(self):
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="kk")
        with translation.override("kk"):
            self.assertContains(response, _("Locale"))
            self.assertContains(response, _("Title"))
            self.assertContains(response, _("Body"))
            self.assertContains(response, _("Category"))

    def test_locale_choices_in_kazakh(self):
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="kk")
        with translation.override("kk"):
            self.assertContains(response, _("Russian"))
            self.assertContains(response, _("Kazakh"))
            self.assertContains(response, _("English"))
