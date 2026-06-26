"""Tests for the site-wide moderation banner.

Covers the ``moderation_tasks`` context processor (who sees which pending items), the banner
rendering on a page, and the news-submission approve/reject views that back the inline buttons.
"""

import datetime

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import User
from calendar_app.models import Competition
from cycling_site.context_processors import moderation_tasks
from knowledge.models import DraftSubmission
from locations.models import Location, LocationProposal
from news.models import NewsArticle
from registrations.models import CompetitionRegistration


def _user(email, role):
    return User.objects.create_user(username=email, email=email, password="password123", role=role)


def _comp(title="C", status=Competition.Status.APPROVED, **kwargs):
    return Competition.objects.create(title_ru=title, date_start=datetime.date(2026, 7, 1), status=status, **kwargs)


def _submission(author, sub_type, title="S"):
    return DraftSubmission.objects.create(
        author=author, submission_type=sub_type, locale="ru", title=title, body="body text"
    )


def _kinds(user, factory):
    request = factory.get("/")
    request.user = user
    result = moderation_tasks(request)
    return result, {t["kind"] for t in result.get("moderation_tasks", [])}


class ModerationTasksContextProcessorTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_anonymous_gets_nothing(self):
        request = self.rf.get("/")
        request.user = AnonymousUser()
        self.assertEqual(moderation_tasks(request), {})

    def test_participant_sees_no_tasks_even_with_pending_items(self):
        _comp(status=Competition.Status.PENDING_APPROVAL)
        result, kinds = _kinds(_user("p@t.local", User.Role.PARTICIPANT), self.rf)
        self.assertEqual(result["moderation_tasks"], [])
        self.assertEqual(kinds, set())

    def test_organizer_sees_events_but_not_admin_only_kinds(self):
        org = _user("o@t.local", User.Role.ORGANIZER)
        _comp(status=Competition.Status.PENDING_APPROVAL)
        _submission(org, DraftSubmission.SubmissionType.NEWS)
        _submission(org, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        _, kinds = _kinds(org, self.rf)
        self.assertIn("events", kinds)
        self.assertNotIn("news", kinds)
        self.assertNotIn("articles", kinds)
        self.assertNotIn("locations", kinds)

    def test_admin_sees_events_locations_articles_news(self):
        admin = _user("a@t.local", User.Role.ADMIN)
        author = _user("auth@t.local", User.Role.PARTICIPANT)
        _comp(status=Competition.Status.PENDING_APPROVAL)
        _submission(author, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        _submission(author, DraftSubmission.SubmissionType.NEWS)
        country = Location.add_root(name_ru="KZ", name_en="KZ")
        region = country.add_child(name_ru="Region", name_en="Region")
        city = region.add_child(name_ru="City", name_en="City")
        Location.propose_venue(city, "Venue", submitted_by=author, approved=False)
        self.assertTrue(Location.objects.filter(proposal__status=LocationProposal.Status.PENDING_APPROVAL).exists())
        _, kinds = _kinds(admin, self.rf)
        self.assertEqual(kinds, {"events", "locations", "articles", "news"})

    def test_registrations_only_for_creator_organizer(self):
        creator = _user("creator@t.local", User.Role.ORGANIZER)
        other = _user("other@t.local", User.Role.ORGANIZER)
        comp = _comp(submitted_by=creator, require_approval=True)
        CompetitionRegistration.objects.create(
            competition=comp, birth_date=datetime.date(1990, 1, 1), gender="M", is_approved=False
        )

        result, _ = _kinds(creator, self.rf)
        reg_tasks = [t for t in result["moderation_tasks"] if t["kind"] == "registrations"]
        self.assertEqual(len(reg_tasks), 1)
        self.assertEqual(reg_tasks[0]["count"], 1)
        self.assertEqual(reg_tasks[0]["competition"], comp)
        self.assertEqual(reg_tasks[0]["url"], reverse("registrations:participant_list", args=[comp.pk]))

        other_result, _ = _kinds(other, self.rf)
        self.assertEqual([t for t in other_result["moderation_tasks"] if t["kind"] == "registrations"], [])

    def test_approved_or_paid_registration_is_not_counted(self):
        creator = _user("creator2@t.local", User.Role.ORGANIZER)
        comp = _comp(submitted_by=creator, require_approval=True)
        CompetitionRegistration.objects.create(
            competition=comp, birth_date=datetime.date(1990, 1, 1), gender="M", is_approved=True
        )
        result, _ = _kinds(creator, self.rf)
        self.assertEqual([t for t in result["moderation_tasks"] if t["kind"] == "registrations"], [])


class ModerationBannerRenderTests(TestCase):
    def test_banner_visible_for_admin(self):
        _comp(status=Competition.Status.PENDING_APPROVAL)
        admin = _user("a2@t.local", User.Role.ADMIN)
        self.client.force_login(admin)
        # News index links the moderate page only via the banner, so its presence proves it rendered.
        response = self.client.get(reverse("news_index"))
        self.assertTrue(response.context["moderation_tasks"])
        self.assertContains(response, reverse("calendar_moderate"))

    def test_banner_absent_for_participant(self):
        _comp(status=Competition.Status.PENDING_APPROVAL)
        participant = _user("p2@t.local", User.Role.PARTICIPANT)
        self.client.force_login(participant)
        response = self.client.get(reverse("news_index"))
        self.assertFalse(response.context.get("moderation_tasks"))
        self.assertNotContains(response, reverse("calendar_moderate"))


class NewsSubmissionModerationViewTests(TestCase):
    def setUp(self):
        self.admin = _user("newsadmin@t.local", User.Role.ADMIN)
        self.participant = _user("newsp@t.local", User.Role.PARTICIPANT)
        self.submission = DraftSubmission.objects.create(
            author=self.participant,
            submission_type=DraftSubmission.SubmissionType.NEWS,
            locale="ru",
            title="Breaking",
            body="full breaking news body",
        )

    def test_manager_sees_news_body_on_detail_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("news_submission_detail", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 200)
        # the moderator can read the full body before deciding, plus reach approve/reject from here
        self.assertContains(response, "full breaking news body")
        self.assertContains(response, reverse("news_submission_approve", args=[self.submission.pk]))
        self.assertContains(response, reverse("news_submission_reject", args=[self.submission.pk]))

    def test_participant_cannot_view_news_submission_detail(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse("news_submission_detail", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 403)

    def test_knowledge_submission_not_reachable_via_news_detail(self):
        knowledge_sub = _submission(self.participant, DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("news_submission_detail", args=[knowledge_sub.pk]))
        self.assertEqual(response.status_code, 404)

    def test_news_index_pending_title_links_to_detail(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("news_index"))
        self.assertContains(response, reverse("news_submission_detail", args=[self.submission.pk]))

    def test_manager_can_approve_news_submission(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("news_submission_approve", args=[self.submission.pk]))
        self.assertRedirects(response, reverse("news_index"))
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.APPROVED)
        self.assertTrue(NewsArticle.objects.filter(title_ru="Breaking").exists())

    def test_manager_can_reject_news_submission(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("news_submission_reject", args=[self.submission.pk]), {"note": "off topic"})
        self.assertRedirects(response, reverse("news_index"))
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.REJECTED)
        self.assertEqual(self.submission.reviewer_note, "off topic")

    def test_participant_cannot_moderate_news_submission(self):
        self.client.force_login(self.participant)
        response = self.client.post(reverse("news_submission_approve", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 403)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, DraftSubmission.Status.PENDING)

    def test_news_index_shows_pending_block_with_actions_for_manager(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("news_index"))
        self.assertContains(response, reverse("news_submission_approve", args=[self.submission.pk]))
        self.assertContains(response, reverse("news_submission_reject", args=[self.submission.pk]))

    def test_news_index_hides_pending_block_from_participant(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse("news_index"))
        self.assertNotContains(response, reverse("news_submission_approve", args=[self.submission.pk]))
