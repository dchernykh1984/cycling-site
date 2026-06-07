from django.test import TestCase
from django.urls import reverse
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTests

from accounts.models import User
from news.forms import SubmitNewsForm
from news.models import Comment, NewsIndexPage, NewsPage, NewsSettings


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
        self.index = NewsIndexPage(title="News", slug="news")
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


class NewsTagsTest(TestCase):
    def test_get_news_index_url_returns_none_when_no_index(self):
        from news.templatetags.news_tags import get_news_index_url

        result = get_news_index_url()
        self.assertIsNone(result)

    def test_get_news_index_url_returns_url_when_index_exists(self):
        from news.templatetags.news_tags import get_news_index_url

        root = _get_site_root()
        index = NewsIndexPage(title="News", slug="news-tags")
        root.add_child(instance=index)
        index.save_revision().publish()
        result = get_news_index_url()
        self.assertIsNotNone(result)
        self.assertIn("news", result)
