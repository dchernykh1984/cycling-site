"""Invite-only events (issue #313).

An invite-only event is published, but only to the people who may edit it -- its author while an
organizer, admins, owners -- and to everybody who opened its invitation link while signed in. To
them it shows up everywhere an ordinary event does; to everyone else it does not exist, and the
channels read by machines (sitemap, feeds, search engines, the API) never carry it at all.
"""

import datetime
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import Competition, CompetitionFavorite, CompetitionInvite
from protocols.models import Protocol


def _user(name, role):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)


def _event(title, **kwargs):
    defaults = {
        "title_ru": title,
        "date_start": timezone.localdate() + datetime.timedelta(days=5),
        "status": Competition.Status.APPROVED,
        "approved_at": timezone.now(),
    }
    defaults.update(kwargs)
    return Competition.objects.create(**defaults)


class _Cast(TestCase):
    """Everyone the rules talk about, and one invite-only event by an organizer."""

    @classmethod
    def setUpTestData(cls):
        cls.author = _user("author", User.Role.ORGANIZER)
        cls.other_organizer = _user("other_org", User.Role.ORGANIZER)
        cls.admin = _user("admin", User.Role.ADMIN)
        cls.invitee = _user("invitee", User.Role.PARTICIPANT)
        cls.stranger = _user("stranger", User.Role.PARTICIPANT)
        cls.private = _event("Private ride", submitted_by=cls.author, invite_only=True)
        CompetitionInvite.objects.create(competition=cls.private, user=cls.invitee)
        cls.public = _event("Public race", submitted_by=cls.author)

    def as_(self, user):
        if user is None:
            self.client.logout()
        else:
            self.client.force_login(user)


class InviteKeyTests(_Cast):
    def test_a_key_is_issued_when_an_event_becomes_invite_only(self):
        self.assertIsNotNone(self.private.invite_key)
        self.assertIsNone(self.public.invite_key)
        self.public.invite_only = True
        self.public.save(update_fields=["invite_only"])
        self.public.refresh_from_db()
        self.assertIsNotNone(self.public.invite_key)

    def test_every_event_gets_its_own_key(self):
        """One key shared by events would open each of them with another's link."""
        other = _event("Another private", submitted_by=self.author, invite_only=True)
        self.assertNotEqual(other.invite_key, self.private.invite_key)


class WhoSeesTheEventTests(_Cast):
    def _list(self):
        return self.client.get(reverse("calendar_list")).content.decode()

    def _calendar_json(self):
        today = timezone.localdate()
        params = {"start": f"{today:%Y-%m-%d}", "end": f"{today + datetime.timedelta(days=30):%Y-%m-%d}"}
        return json.dumps(self.client.get(reverse("calendar_events_api"), params).json())

    def test_the_people_let_in_see_it_in_the_list_and_the_calendar(self):
        for user in (self.author, self.admin, self.invitee):
            with self.subTest(user=user.username):
                self.as_(user)
                self.assertIn("Private ride", self._list())
                self.assertIn("Private ride", self._calendar_json())

    def test_everyone_else_does_not(self):
        for user in (self.other_organizer, self.stranger, None):
            with self.subTest(user=getattr(user, "username", "anonymous")):
                self.as_(user)
                self.assertNotIn("Private ride", self._list())
                self.assertNotIn("Private ride", self._calendar_json())
                self.assertIn("Public race", self._list())

    def test_the_event_page_follows_the_same_rule(self):
        url = reverse("competition_detail", args=[self.private.pk])
        for user, status in (
            (self.author, 200),
            (self.admin, 200),
            (self.invitee, 200),
            (self.other_organizer, 404),
            (self.stranger, 404),
            (None, 404),
        ):
            with self.subTest(user=getattr(user, "username", "anonymous")):
                self.as_(user)
                self.assertEqual(self.client.get(url).status_code, status)

    def test_the_page_asks_not_to_be_indexed(self):
        self.as_(self.invitee)
        response = self.client.get(reverse("competition_detail", args=[self.private.pk]))
        self.assertEqual(response["X-Robots-Tag"], "noindex")

    def test_only_its_managers_are_shown_the_invitation_link(self):
        link = reverse("competition_invite", args=[self.private.pk, self.private.invite_key])
        url = reverse("competition_detail", args=[self.private.pk])
        self.as_(self.author)
        self.assertContains(self.client.get(url), link)
        self.as_(self.invitee)
        self.assertNotContains(self.client.get(url), link)

    def test_taking_it_down_hides_it_from_invitees_too(self):
        self.private.is_hidden = True
        self.private.save(update_fields=["is_hidden"])
        self.as_(self.invitee)
        self.assertNotIn("Private ride", self._list())
        self.assertEqual(self.client.get(reverse("competition_detail", args=[self.private.pk])).status_code, 404)


class RegisteredRidersTests(_Cast):
    """An event can turn invite-only after people signed up for it while it was public."""

    def _register(self, user, **kwargs):
        from registrations.models import CompetitionRegistration

        return CompetitionRegistration.objects.create(
            competition=self.public,
            user=user,
            first_name="Rider",
            last_name="Test",
            birth_date=datetime.date(1990, 1, 1),
            gender="M",
            **kwargs,
        )

    def _go_private(self):
        self.public.invite_only = True
        self.public.save(update_fields=["invite_only"])

    def test_a_registered_rider_keeps_the_page_and_the_list_row(self):
        self._register(self.stranger)
        self._go_private()
        self.as_(self.stranger)
        self.assertEqual(self.client.get(reverse("competition_detail", args=[self.public.pk])).status_code, 200)
        self.assertIn("Public race", self.client.get(reverse("calendar_list")).content.decode())

    def test_a_rejected_registration_lets_nobody_in(self):
        self._register(self.stranger, is_rejected=True)
        self._go_private()
        self.as_(self.stranger)
        self.assertEqual(self.client.get(reverse("competition_detail", args=[self.public.pk])).status_code, 404)


class MapTests(_Cast):
    """The calendar map pins an event the same way the list shows it."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from locations.models import add_location_child

        country = add_location_child(None, name="Kazakhstan", name_ru="Kazakhstan")
        region = add_location_child(country, name="Almaty", name_ru="Almaty")
        city = add_location_child(region, name="Almaty city", name_ru="Almaty city")
        venue = add_location_child(city, name="Medeu", name_ru="Medeu", lat="43.157800", lng="77.057000")
        cls.private.location = venue
        cls.private.save(update_fields=["location"])

    def _map(self):
        return json.dumps(self.client.get(reverse("calendar_map_api")).json())

    def test_pinned_for_an_invitee(self):
        self.as_(self.invitee)
        self.assertIn("Private ride", self._map())

    def test_not_pinned_for_anyone_else(self):
        for user in (self.stranger, None):
            with self.subTest(user=getattr(user, "username", "anonymous")):
                self.as_(user)
                self.assertNotIn("Private ride", self._map())


class UpcomingRowsTests(_Cast):
    """The rows under the calendar grid: the reader's invitations, never a taken-down event."""

    def _rows(self):
        return self.client.get(reverse("calendar")).context["upcoming"]

    def test_an_invitee_finds_the_event_there(self):
        self.as_(self.invitee)
        self.assertIn(self.private, self._rows())

    def test_a_hidden_event_stays_out_even_for_an_admin(self):
        self.public.is_hidden = True
        self.public.save(update_fields=["is_hidden"])
        self.as_(self.admin)
        self.assertNotIn(self.public, self._rows())


class InvitationLinkTests(_Cast):
    def _link(self, key=None):
        return reverse("competition_invite", args=[self.private.pk, key or self.private.invite_key])

    def test_signing_in_comes_first(self):
        response = self.client.get(self._link())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])
        self.assertIn("next=", response["Location"])

    def test_opening_it_lets_the_reader_in_and_drops_the_key_from_the_address(self):
        self.as_(self.stranger)
        response = self.client.get(self._link())
        self.assertRedirects(response, reverse("competition_detail", args=[self.private.pk]))
        self.assertTrue(CompetitionInvite.objects.filter(competition=self.private, user=self.stranger).exists())
        self.assertIn("Private ride", self.client.get(reverse("calendar_list")).content.decode())

    def test_a_wrong_key_says_nothing(self):
        import uuid

        self.as_(self.stranger)
        self.assertEqual(self.client.get(self._link(uuid.uuid4())).status_code, 404)
        self.assertFalse(CompetitionInvite.objects.filter(user=self.stranger).exists())

    def test_a_new_link_shuts_the_old_one_but_keeps_the_people_already_in(self):
        old_key = self.private.invite_key
        self.as_(self.author)
        self.client.post(reverse("competition_regenerate_invite", args=[self.private.pk]))
        self.private.refresh_from_db()
        self.assertNotEqual(self.private.invite_key, old_key)
        self.as_(self.stranger)
        self.assertEqual(self.client.get(self._link(old_key)).status_code, 404)
        self.as_(self.invitee)
        self.assertEqual(self.client.get(reverse("competition_detail", args=[self.private.pk])).status_code, 200)

    def test_only_its_managers_may_replace_the_link(self):
        for user in (self.invitee, self.other_organizer):
            with self.subTest(user=user.username):
                self.as_(user)
                response = self.client.post(reverse("competition_regenerate_invite", args=[self.private.pk]))
                self.assertEqual(response.status_code, 403)

    def test_the_link_of_an_ordinary_event_just_opens_it(self):
        self.as_(self.stranger)
        import uuid

        response = self.client.get(reverse("competition_invite", args=[self.public.pk, uuid.uuid4()]))
        self.assertRedirects(response, reverse("competition_detail", args=[self.public.pk]))


class MachineChannelsTests(_Cast):
    """Read by crawlers, feed readers and calendar apps -- never carry an invite-only event."""

    def test_sitemap(self):
        body = self.client.get(reverse("sitemap_section", args=["competitions"])).content.decode()
        self.assertIn(f"/calendar/{self.public.pk}/", body, "the sitemap lists nothing at all")
        self.assertNotIn(f"/calendar/{self.private.pk}/", body)

    def test_rss(self):
        body = self.client.get(reverse("calendar_rss")).content.decode()
        self.assertIn("Public race", body, "the feed carries nothing at all")
        self.assertNotIn("Private ride", body)

    def test_ics_subscription_even_for_an_invitee(self):
        self.as_(self.invitee)
        body = self.client.get(reverse("calendar_ics")).content.decode()
        self.assertIn("Public race", body, "the calendar carries nothing at all")
        self.assertNotIn("Private ride", body)

    def test_public_api_even_for_an_invitee(self):
        self.as_(self.invitee)
        listing = self.client.get("/api/v1/competitions/").content.decode()
        self.assertIn("Public race", listing, "the API lists nothing at all")
        self.assertNotIn("Private ride", listing)
        self.assertEqual(self.client.get(f"/api/v1/competitions/{self.private.pk}/").status_code, 404)

    def test_landing_pages_skip_it(self):
        from calendar_app.listing_seo import landing_filters

        regions, places, kinds = landing_filters()
        self.assertFalse(any("Private ride" in str(item) for item in [*regions, *places, *kinds]))


class SearchTests(_Cast):
    def _search(self):
        return self.client.get(reverse("search"), {"query": "Private"}).content.decode()

    def test_found_by_the_people_let_in(self):
        self.as_(self.invitee)
        self.assertIn("Private ride", self._search())

    def test_not_found_by_anyone_else(self):
        self.as_(self.stranger)
        self.assertNotIn("Private ride", self._search())


class ModerationTests(_Cast):
    """Any organizer moderates, but an invite-only event waits for admins."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.waiting = _event(
            "Private waiting", submitted_by=cls.author, invite_only=True, status=Competition.Status.PENDING_APPROVAL
        )

    def test_the_queue(self):
        self.as_(self.other_organizer)
        self.assertNotContains(self.client.get(reverse("calendar_moderate")), "Private waiting")
        self.as_(self.admin)
        self.assertContains(self.client.get(reverse("calendar_moderate")), "Private waiting")

    def test_the_page_while_it_waits(self):
        url = reverse("competition_detail", args=[self.waiting.pk])
        for user, status in ((self.other_organizer, 404), (self.author, 200), (self.admin, 200)):
            with self.subTest(user=user.username):
                self.as_(user)
                self.assertEqual(self.client.get(url).status_code, status)

    def test_another_organizer_cannot_approve_it(self):
        self.as_(self.other_organizer)
        self.client.post(reverse("competition_approve", args=[self.waiting.pk]))
        self.waiting.refresh_from_db()
        self.assertEqual(self.waiting.status, Competition.Status.PENDING_APPROVAL)

    def test_the_task_counter_counts_what_the_moderator_may_act_on(self):
        from django.test import RequestFactory

        from cycling_site.context_processors import moderation_tasks

        request = RequestFactory().get("/")
        request.user = self.other_organizer
        counts = {t["kind"]: t["count"] for t in moderation_tasks(request).get("moderation_tasks", [])}
        self.assertNotIn("events", counts)


class WhatHangsOffTheEventTests(_Cast):
    """Registration, results, favorites: as private as the page."""

    def test_registration(self):
        self.private.registration_enabled = True
        self.private.save(update_fields=["registration_enabled"])
        url = reverse("registrations:register", args=[self.private.pk])
        self.as_(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.as_(self.invitee)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_participant_list(self):
        url = reverse("registrations:participant_list", args=[self.private.pk])
        self.as_(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.as_(self.invitee)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_results(self):
        protocol = Protocol.objects.create(competition=self.private, protocol_type="absolute", is_live=False)
        url = reverse("protocol_detail", args=[protocol.pk])
        self.as_(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.as_(self.invitee)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_favorites(self):
        self.as_(self.stranger)
        self.client.post(reverse("competition_toggle_favorite", args=[self.private.pk]))
        self.assertFalse(CompetitionFavorite.objects.filter(user=self.stranger).exists())


class FormTests(_Cast):
    def _payload(self, **extra):
        payload = {
            "title_ru": "Form ride",
            "date_start": f"{timezone.localdate() + datetime.timedelta(days=9):%Y-%m-%d}",
            "invite_only": "on",
        }
        payload.update(extra)
        return payload

    def test_an_organizer_can_make_an_event_invite_only(self):
        self.as_(self.author)
        self.client.post(reverse("calendar_submit"), self._payload())
        self.assertTrue(Competition.objects.get(title_ru="Form ride").invite_only)

    def test_a_participant_cannot(self):
        self.as_(self.stranger)
        self.client.post(reverse("calendar_submit"), self._payload())
        self.assertFalse(Competition.objects.get(title_ru="Form ride").invite_only)

    def _edit(self, user, event, **extra):
        self.as_(user)
        payload = {"title_ru": f"{event.title_ru} edited", "date_start": f"{event.date_start:%Y-%m-%d}"}
        payload.update(extra)
        self.client.post(reverse("competition_edit", args=[event.pk]), payload)
        event.refresh_from_db()
        # The edit must have gone through, or the flag assertion below would pass for nothing.
        self.assertTrue(event.title_ru.endswith(" edited"), "the edit was refused")
        return event

    def test_an_organizer_can_open_an_event_up_again(self):
        self.assertFalse(self._edit(self.author, self.private).invite_only)

    def test_a_participant_author_cannot_change_it(self):
        own = _event("Participant ride", submitted_by=self.stranger)
        self.assertFalse(self._edit(self.stranger, own, invite_only="on").invite_only)

    def test_the_tick_is_offered_to_organizers_only(self):
        self.as_(self.author)
        self.assertContains(self.client.get(reverse("calendar_submit")), 'name="invite_only"')
        self.as_(self.stranger)
        self.assertNotContains(self.client.get(reverse("calendar_submit")), 'name="invite_only"')


class TranslationTests(TestCase):
    MSGIDS = (
        "Invite-only event",
        "Only the people who may edit it, and everyone who opens its invitation link while signed in, will see "
        "it. The link appears on the event page once it is saved.",
        "This event is by invitation: only the people its organizer invited can see it.",
        "Invitation link",
        "Replace the invitation link? The current link will stop working; people already invited keep access.",
        "Replace link",
        "Anyone who opens this link while signed in will see the event everywhere on the site. Send it only to "
        "the people you invite.",
        "By invitation",
        "Invitation link replaced. The old link no longer works; people already invited keep access.",
    )

    def test_every_new_string_is_translated(self):
        from django.utils.translation import gettext, override

        for msgid in self.MSGIDS:
            for lang in ("ru", "kk"):
                with self.subTest(msgid=msgid[:30], lang=lang), override(lang):
                    self.assertNotEqual(gettext(msgid), msgid)
