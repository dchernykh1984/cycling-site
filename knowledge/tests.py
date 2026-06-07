import json

from django.test import Client, TestCase
from django.urls import reverse
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

    def test_index_renders(self):
        response = self.client.get(self.index.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Article")

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

    def test_search_page_returns_200(self):
        response = self.client.get(reverse("search") + "?query=Almaty")
        self.assertEqual(response.status_code, 200)

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
