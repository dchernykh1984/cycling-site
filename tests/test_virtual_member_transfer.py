"""Handing a person without an account over to an account of their own (issue #438): the manager's link,
the account's request, the manager's answer, and what moves -- on the pages and through the API."""

import datetime
from http import HTTPStatus

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts import transfers, virtual_members
from accounts.models import ManagedMember, User, VirtualMember, VirtualMemberTransfer
from calendar_app.visibility import can_see, listed_events
from event_photos import actions
from event_photos.models import DeclaredBib
from registrations.models import CompetitionRegistration
from registrations.tests import make_open_competition, make_registration, make_user
from registrations.views import can_self_edit
from tests.test_virtual_members import _bearer

API = "/api/v1/virtual-members"


def _url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs)


class HandOverTests(TestCase):
    def setUp(self):
        self.coach = make_user("coach", first_name="Anna", last_name="Coach")
        virtual_members.consent(self.coach)
        self.kid = VirtualMember.objects.create(
            owner=self.coach,
            last_name="Kim",
            first_name="Dana",
            gender="F",
            birth_date=datetime.date(2012, 3, 4),
            team="Tuzy jol",
            city="Almaty",
            sports_achievements="KMS",
        )
        self.rider = make_user("dana", first_name="Dana", last_name="Kim", city="Taraz")

    def _ask(self, keep_manager=False, account=None):
        link = transfers.issue(self.kid)
        self.client.force_login(account or self.rider)
        self.client.post(_url("account_virtual_claim", key=link.key), {"keep_manager": "on"} if keep_manager else {})
        link.refresh_from_db()
        return link

    def _confirm(self):
        self.client.force_login(self.coach)
        return self.client.post(_url("account_virtual_transfer_confirm", pk=self.kid.pk))

    def test_every_field_and_every_link_of_a_person_is_handed_over_or_left_on_purpose(self):
        """A field or a table added to people without accounts later is not left behind unseen."""
        fields = {field.name for field in VirtualMember._meta.concrete_fields}
        self.assertEqual(fields, {*transfers.PROFILE_FIELDS, *transfers.NOT_HANDED_OVER})
        links = {relation.get_accessor_name() for relation in VirtualMember._meta.related_objects}
        self.assertEqual(links, {*transfers.HANDED_OVER, *transfers.GONE_WITH_THE_PERSON})

    def test_opening_the_link_changes_nothing_and_the_request_waits_for_the_manager(self):
        entry = make_registration(make_open_competition(), virtual_member=self.kid)
        link = transfers.issue(self.kid)
        self.client.force_login(self.rider)
        page = self.client.get(_url("account_virtual_claim", key=link.key))
        self.assertContains(page, "Take Kim Dana into your account?")
        # The fields of the profile that get filled, by name: the manager has confirmed nothing yet
        self.assertContains(page, "Gender, Date of birth, Team, Sports achievements.")
        self.assertNotContains(page, "2012")
        link.refresh_from_db()
        self.assertIsNone(link.claimed_by)

        answer = self.client.post(_url("account_virtual_claim", key=link.key))
        self.assertRedirects(answer, _url("account_profile"), fetch_redirect_response=False)
        link.refresh_from_db()
        self.assertEqual((link.claimed_by, link.keep_manager), (self.rider, False))
        entry.refresh_from_db()
        self.assertEqual((entry.virtual_member, entry.user), (self.kid, None))

    def test_once_the_manager_confirms_the_entries_bibs_and_empty_fields_move_and_the_person_goes(self):
        to_come = make_open_competition(title="To come")
        both = make_open_competition(title="Both entered")
        own = make_registration(to_come, virtual_member=self.kid, registered_by=self.coach)
        kids = make_registration(both, virtual_member=self.kid, registered_by=self.coach)
        riders = make_registration(both, user=self.rider)
        same, two, one = (make_open_competition(title=title) for title in ("Same bib", "Two bibs", "One bib"))
        for competition, bib in ((same, "7"), (two, "12"), (one, "5")):
            DeclaredBib.objects.create(competition=competition, virtual_member=self.kid, bib=bib)
        for competition, bib in ((same, "7"), (two, "34")):
            DeclaredBib.objects.create(competition=competition, user=self.rider, bib=bib)

        self._ask(keep_manager=True)
        answer = self._confirm()

        self.assertRedirects(answer, f"{_url('account_profile')}#virtual-members", fetch_redirect_response=False)
        self.assertFalse(VirtualMember.objects.filter(pk=self.kid.pk).exists())
        # An event both were entered for keeps both entries; a race to come is not withdrawn
        for entry in (own, kids, riders):
            entry.refresh_from_db()
            self.assertEqual((entry.user, entry.virtual_member), (self.rider, None))
        self.assertEqual(CompetitionRegistration.objects.filter(competition=both).count(), 2)
        self.assertEqual(own.registered_by, self.coach)
        named = DeclaredBib.objects.filter(user=self.rider)
        self.assertEqual(sorted(named.filter(competition=same).values_list("bib", flat=True)), ["7"])
        self.assertEqual(sorted(named.filter(competition=two).values_list("bib", flat=True)), ["12", "34"])
        self.assertEqual(list(named.filter(competition=one).values_list("bib", flat=True)), ["5"])
        self.rider.refresh_from_db()
        # Only what the profile had empty: the city the rider typed in stays
        self.assertEqual(
            (self.rider.city, self.rider.gender, self.rider.birth_date, self.rider.team),
            ("Taraz", "F", datetime.date(2012, 3, 4), "Tuzy jol"),
        )
        self.assertEqual(self.rider.sports_achievements, "KMS")
        self.assertTrue(ManagedMember.objects.filter(manager=self.coach, member=self.rider, accepted_at__isnull=False))
        self.assertTrue(can_self_edit(self.coach, to_come, own))

    def test_an_invite_only_event_the_person_was_entered_for_opens_to_the_account_once_handed_over(self):
        race = make_open_competition(invite_only=True)
        make_registration(race, virtual_member=self.kid, first_name="Dana", last_name="Kim")
        self.assertFalse(can_see(self.rider, race))
        self._ask()
        self._confirm()
        # the entry is the account's now, and an entry lets its rider in as the invitation would
        self.assertTrue(can_see(self.rider, race))
        self.assertIn(race, listed_events(self.rider))
        self.client.force_login(self.rider)
        self.assertEqual(self.client.get(race.get_absolute_url()).status_code, HTTPStatus.OK)

    def test_without_the_box_ticked_the_manager_keeps_nothing_of_the_person(self):
        competition = make_open_competition()
        entry = make_registration(competition, virtual_member=self.kid, registered_by=self.coach)
        self._ask()
        self._confirm()
        entry.refresh_from_db()
        self.assertFalse(ManagedMember.objects.filter(manager=self.coach, member=self.rider).exists())
        self.assertFalse(can_self_edit(self.coach, competition, entry))
        self.assertTrue(can_self_edit(self.rider, competition, entry))

    def test_a_link_takes_one_request_lasts_a_week_and_a_new_one_stops_the_old(self):
        stranger = make_user("stranger", first_name="Ivan", last_name="Petrov")
        link = self._ask(account=stranger)
        self.assertEqual(link.claimed_by, stranger)
        self.client.force_login(self.rider)
        used = self.client.post(_url("account_virtual_claim", key=link.key))
        self.assertEqual(used.status_code, HTTPStatus.NOT_FOUND)
        link.refresh_from_db()
        self.assertEqual(link.claimed_by, stranger)

        fresh = transfers.issue(self.kid)
        self.assertNotEqual(fresh.key, link.key)
        self.assertIsNone(fresh.claimed_by)  # the request through the old link is dropped
        self.assertEqual(self.client.get(_url("account_virtual_claim", key=link.key)).status_code, 404)
        VirtualMemberTransfer.objects.filter(pk=fresh.pk).update(created_at=timezone.now() - datetime.timedelta(days=8))
        self.assertEqual(self.client.get(_url("account_virtual_claim", key=fresh.key)).status_code, 404)

    def test_the_manager_is_told_to_send_their_own_link_and_an_unconfirmed_account_only_looks(self):
        link = transfers.issue(self.kid)
        self.client.force_login(self.coach)
        with translation.override("en"):
            self.assertContains(self.client.get(_url("account_virtual_claim", key=link.key)), "send it to the owner")
            self.client.post(_url("account_virtual_claim", key=link.key))
        guest = make_user("guest", role=User.Role.GUEST)
        self.client.force_login(guest)
        self.assertContains(self.client.get(_url("account_virtual_claim", key=link.key)), "confirm your e-mail address")
        self.client.post(_url("account_virtual_claim", key=link.key))
        link.refresh_from_db()
        self.assertIsNone(link.claimed_by)

    def test_rejecting_drops_the_request_with_its_link_and_keeps_the_person(self):
        entry = make_registration(make_open_competition(), virtual_member=self.kid)
        self._ask()
        self.client.force_login(self.coach)
        self.client.post(_url("account_virtual_transfer_reject", pk=self.kid.pk))
        self.assertFalse(VirtualMemberTransfer.objects.exists())
        entry.refresh_from_db()
        self.assertEqual(entry.virtual_member, self.kid)

    def test_nobody_but_the_manager_links_or_answers_for_a_person(self):
        self._ask()
        other = make_user("other", first_name="Other", last_name="Member")
        self.client.force_login(other)
        for name in ("account_virtual_transfer", "account_virtual_transfer_confirm", "account_virtual_transfer_reject"):
            self.assertEqual(self.client.post(_url(name, pk=self.kid.pk)).status_code, HTTPStatus.NOT_FOUND)
        self.assertTrue(VirtualMember.objects.filter(pk=self.kid.pk).exists())

    def test_the_card_offers_the_link_then_shows_it_then_the_request_to_answer(self):
        self.client.force_login(self.coach)
        with translation.override("en"):
            # Every row has these buttons: a screen reader hears whose each one is, as with "Edit" and "Delete"
            page = self.client.get(_url("account_profile"))
            self.assertContains(page, 'aria-label="Hand over to a mentor: Kim Dana"')
            self.assertContains(page, 'aria-label="Hand over to the owner: Kim Dana"')
            self.assertNotContains(page, "Make a new link?")
            self.client.post(_url("account_virtual_transfer", pk=self.kid.pk), {"to": VirtualMemberTransfer.To.OWNER})
            link = VirtualMemberTransfer.objects.get(person=self.kid)
            page = self.client.get(_url("account_profile"))
        self.assertContains(page, _url("account_virtual_claim", key=link.key))
        self.assertContains(page, "Send this link to the owner of the account the data of Kim Dana moves to")
        # Pressed again while the link is live, either button makes a new link, of its kind, and says so first
        self.assertContains(page, 'aria-label="Hand over to a mentor: Kim Dana"')
        self.assertContains(page, "Make a new link? This one will stop working.", count=2)
        self._ask(keep_manager=True)
        self.client.force_login(self.coach)
        with translation.override("en"):
            page = self.client.get(_url("account_profile"))
        self.assertContains(page, "Dana Kim asks to take Kim Dana into their account.")
        self.assertContains(page, "They let you go on managing their registrations and photos.")
        self.assertContains(page, 'aria-label="Confirm: Kim Dana"')
        self.assertContains(page, 'aria-label="Reject: Kim Dana"')
        self.assertNotContains(page, "Hand over to the owner: Kim Dana")

    def test_a_manager_without_a_name_is_asked_for_one_before_a_link(self):
        """Whoever opens the link must see who hands the person over, as with a manager's own link."""
        nameless = make_user("nameless")
        virtual_members.consent(nameless)
        person = VirtualMember.objects.create(
            owner=nameless, last_name="Kim", first_name="Arman", gender="M", birth_date=datetime.date(2011, 1, 2)
        )
        self.client.force_login(nameless)
        with translation.override("en"):
            answer = self.client.post(_url("account_virtual_transfer", pk=person.pk), follow=True)
        self.assertContains(answer, "Add your first and last name to your profile first")
        self.assertFalse(VirtualMemberTransfer.objects.filter(person=person).exists())
        refused = self.client.post(f"{API}/{person.pk}/transfer", content_type="application/json", **_bearer(nameless))
        self.assertEqual(refused.status_code, HTTPStatus.CONFLICT)

    def test_naming_a_bib_again_leaves_one_where_a_hand_over_brought_two(self):
        competition = make_open_competition()
        first = DeclaredBib.objects.create(competition=competition, user=self.rider, bib="12")
        DeclaredBib.objects.create(competition=competition, user=self.rider, bib="34")
        named = actions.declare_bib(self.rider, competition, "9")
        self.assertEqual(named.pk, first.pk)
        self.assertEqual(list(DeclaredBib.objects.filter(user=self.rider).values_list("bib", flat=True)), ["9"])


class HandOverApiTests(TestCase):
    def setUp(self):
        self.coach = make_user("coach", first_name="Anna", last_name="Coach")
        virtual_members.consent(self.coach)
        self.kid = VirtualMember.objects.create(
            owner=self.coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
        )
        self.rider = make_user("dana", first_name="Dana", last_name="Kim", birth_date=datetime.date(2012, 3, 4))
        self.as_coach, self.as_rider = _bearer(self.coach), _bearer(self.rider)

    def _post(self, path, auth, data=None):
        return self.client.post(f"{API}{path}", data or {}, content_type="application/json", **auth)

    def test_the_link_the_request_and_the_answer_go_through_the_api_as_on_the_pages(self):
        made = self._post(f"/{self.kid.pk}/transfer", self.as_coach)
        self.assertEqual(made.status_code, HTTPStatus.CREATED)
        link = VirtualMemberTransfer.objects.get(person=self.kid)
        self.assertIn(f"/virtual-members/take/{link.key}/", made.json()["url"])
        listed = self.client.get(f"{API}/", **self.as_coach).json()["people"][0]["transfer"]
        self.assertEqual((listed["url"], listed["claimed_by"]), (made.json()["url"], None))

        own = self._post("/transfers/claim", self.as_coach, {"key": str(link.key)})
        self.assertEqual(own.status_code, HTTPStatus.CONFLICT)
        asked = self._post("/transfers/claim", self.as_rider, {"key": str(link.key), "keep_manager": True})
        self.assertEqual(asked.status_code, HTTPStatus.CREATED)
        self.assertEqual(asked.json(), {"person": "Kim Dana", "manager": "Anna Coach", "to": "owner"})
        again = self._post("/transfers/claim", self.as_rider, {"key": str(link.key)})
        self.assertEqual(again.status_code, HTTPStatus.NOT_FOUND)
        waiting = self.client.get(f"{API}/", **self.as_coach).json()["people"][0]["transfer"]
        self.assertEqual(waiting["url"], "")
        self.assertEqual(waiting["claimed_by"], {"user_id": self.rider.pk, "name": "Dana Kim", "birth_year": 2012})
        self.assertTrue(waiting["keep_manager"])

        self.assertEqual(self._post(f"/{self.kid.pk}/transfer/confirm", self.as_rider).status_code, 404)
        self.assertEqual(self._post(f"/{self.kid.pk}/transfer/confirm", self.as_coach).status_code, 204)
        self.assertFalse(VirtualMember.objects.filter(pk=self.kid.pk).exists())
        self.assertTrue(ManagedMember.objects.filter(manager=self.coach, member=self.rider).exists())

    def test_answering_where_no_request_waits_is_not_found_and_rejecting_one_drops_it(self):
        for answer in ("confirm", "reject"):
            self.assertEqual(self._post(f"/{self.kid.pk}/transfer/{answer}", self.as_coach).status_code, 404)
        link = transfers.issue(self.kid)
        self._post("/transfers/claim", self.as_rider, {"key": str(link.key)})
        self.assertEqual(self._post(f"/{self.kid.pk}/transfer/reject", self.as_coach).status_code, 204)
        self.assertFalse(VirtualMemberTransfer.objects.exists())
        self.assertTrue(VirtualMember.objects.filter(pk=self.kid.pk).exists())


MENTOR = VirtualMemberTransfer.To.MENTOR


class HandToMentorTests(TestCase):
    """Handing a person over to another mentor: they stay a person without an account, in that member's list."""

    def setUp(self):
        self.coach = make_user("coach", first_name="Anna", last_name="Coach")
        virtual_members.consent(self.coach)
        self.kid = VirtualMember.objects.create(
            owner=self.coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
        )
        self.mentor = make_user("mentor", first_name="Olga", last_name="Mentor", city="Taraz")

    def _ask(self, consent=True):
        link = transfers.issue(self.kid, MENTOR)
        self.client.force_login(self.mentor)
        answer = self.client.post(_url("account_virtual_claim", key=link.key), {"consent": "on"} if consent else {})
        link.refresh_from_db()
        return link, answer

    def _confirm(self):
        self.client.force_login(self.coach)
        with translation.override("en"):
            return self.client.post(_url("account_virtual_transfer_confirm", pk=self.kid.pk), follow=True)

    def _fill_up(self, account, count):
        VirtualMember.objects.bulk_create(
            VirtualMember(owner=account, last_name=f"Pupil{n}", first_name="X", gender="M", birth_date="2012-01-01")
            for n in range(count)
        )

    def test_the_mentor_gives_their_word_on_the_page_and_the_request_waits_for_the_manager(self):
        link = transfers.issue(self.kid, MENTOR)
        self.client.force_login(self.mentor)
        with translation.override("en"):
            page = self.client.get(_url("account_virtual_claim", key=link.key))
            self.assertContains(page, "Become the mentor of Kim Dana?")
            self.assertContains(page, "Anna Coach hands Kim Dana (Female, born on 04.03.2012) over to you")
            self.assertContains(page, 'name="consent"')
            self.assertNotContains(page, 'name="keep_manager"')
            refused = self.client.post(_url("account_virtual_claim", key=link.key))
        self.assertContains(refused, "Confirm first that you may handle the personal data of Kim Dana")
        link.refresh_from_db()
        self.assertIsNone(link.claimed_by)
        self.assertFalse(virtual_members.consented(self.mentor))

        link, answer = self._ask()
        self.assertRedirects(answer, _url("account_profile"), fetch_redirect_response=False)
        self.assertEqual(link.claimed_by, self.mentor)
        self.mentor.refresh_from_db()
        self.assertTrue(virtual_members.consented(self.mentor))
        self.kid.refresh_from_db()
        self.assertEqual(self.kid.owner, self.coach)
        self.client.force_login(self.coach)
        with translation.override("en"):
            self.assertContains(
                self.client.get(_url("account_profile")), "Olga Mentor asks to become the mentor of Kim Dana."
            )

    def test_once_confirmed_the_person_with_their_entries_and_bibs_is_in_the_mentors_list(self):
        competition = make_open_competition()
        entry = make_registration(competition, virtual_member=self.kid, registered_by=self.coach)
        bib = DeclaredBib.objects.create(
            competition=make_open_competition(title="Bib"), virtual_member=self.kid, bib="7"
        )
        self._ask()
        answer = self._confirm()
        self.assertContains(answer, "Kim Dana is now in the list of Olga Mentor.")
        self.kid.refresh_from_db()
        self.assertEqual(self.kid.owner, self.mentor)
        self.assertFalse(VirtualMemberTransfer.objects.exists())
        entry.refresh_from_db()
        bib.refresh_from_db()
        self.assertEqual((entry.virtual_member, entry.user, entry.registered_by), (self.kid, None, self.coach))
        self.assertEqual((bib.virtual_member, bib.user), (self.kid, None))
        self.assertTrue(can_self_edit(self.mentor, competition, entry))
        self.assertFalse(can_self_edit(self.coach, competition, entry))
        # Nothing of an account's: no profile filled, nobody managed
        self.mentor.refresh_from_db()
        self.assertEqual((self.mentor.city, self.mentor.birth_date), ("Taraz", None))
        self.assertFalse(ManagedMember.objects.exists())

    def test_the_mentor_sees_the_invite_only_events_their_person_is_entered_for(self):
        race = make_open_competition(invite_only=True)
        make_registration(race, virtual_member=self.kid, first_name="Dana", last_name="Kim")
        self.assertFalse(can_see(self.mentor, race))
        self._ask()
        self._confirm()
        self.assertTrue(can_see(self.mentor, race))
        self.assertIn(race, listed_events(self.mentor))
        self.client.force_login(self.mentor)
        self.assertEqual(self.client.get(race.get_absolute_url()).status_code, HTTPStatus.OK)

    def test_a_full_list_or_a_copy_of_the_person_keeps_them_with_their_manager(self):
        virtual_members.consent(self.mentor)
        self._fill_up(self.mentor, virtual_members.room(self.mentor))
        link = transfers.issue(self.kid, MENTOR)
        self.client.force_login(self.mentor)
        with translation.override("en"):
            self.assertContains(
                self.client.get(_url("account_virtual_claim", key=link.key)), "is full", status_code=200
            )
        VirtualMember.objects.filter(owner=self.mentor).delete()
        VirtualMember.objects.create(
            owner=self.mentor, last_name="KIM", first_name="dana", gender="F", birth_date=self.kid.birth_date
        )
        with translation.override("en"):
            page = self.client.get(_url("account_virtual_claim", key=link.key))
        self.assertContains(page, "You already have Kim Dana, born on 04.03.2012, in your list")
        self.client.post(_url("account_virtual_claim", key=link.key), {"consent": "on"})
        link.refresh_from_db()
        self.assertIsNone(link.claimed_by)

        # Room when asked, none left when the manager answers: the person stays, and so does the request
        VirtualMember.objects.filter(owner=self.mentor).delete()
        link, _answer = self._ask()
        self._fill_up(self.mentor, virtual_members.room(self.mentor))
        answer = self._confirm()
        self.assertContains(answer, "Olga Mentor has no room left for people without an account")
        self.kid.refresh_from_db()
        self.assertEqual(self.kid.owner, self.coach)
        self.assertTrue(VirtualMemberTransfer.objects.filter(pk=link.pk, claimed_by=self.mentor).exists())

    def test_either_button_makes_a_link_of_its_kind_in_place_of_the_last(self):
        self.client.force_login(self.coach)
        transfer = _url("account_virtual_transfer", pk=self.kid.pk)
        self.client.post(transfer, {"to": MENTOR})
        first = VirtualMemberTransfer.objects.get(person=self.kid)
        self.assertTrue(first.to_mentor)
        with translation.override("en"):
            page = self.client.get(_url("account_profile"))
            self.assertContains(page, "Send this link to the mentor who takes Kim Dana over")
            self.assertContains(self.client.get(_url("account_virtual_claim", key=first.key)), "send it to the mentor")
        self.client.post(transfer, {"to": VirtualMemberTransfer.To.OWNER})
        second = VirtualMemberTransfer.objects.get(person=self.kid)
        self.assertEqual((second.to_mentor, second.pk == first.pk), (False, True))
        self.assertNotEqual(second.key, first.key)
        self.assertEqual(self.client.post(transfer, {"to": "nobody"}).status_code, HTTPStatus.BAD_REQUEST)


class HandToMentorApiTests(TestCase):
    def setUp(self):
        self.coach = make_user("coach", first_name="Anna", last_name="Coach")
        virtual_members.consent(self.coach)
        self.kid = VirtualMember.objects.create(
            owner=self.coach, last_name="Kim", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
        )
        self.mentor = make_user("mentor", first_name="Olga", last_name="Mentor")
        self.as_coach, self.as_mentor = _bearer(self.coach), _bearer(self.mentor)

    def _post(self, path, auth, data=None):
        return self.client.post(f"{API}{path}", data or {}, content_type="application/json", **auth)

    def test_the_mentor_link_the_word_the_request_and_the_answer_go_through_the_api(self):
        made = self._post(f"/{self.kid.pk}/transfer?to=mentor", self.as_coach)
        self.assertEqual(made.status_code, HTTPStatus.CREATED)
        self.assertEqual(made.json()["to"], "mentor")
        key = str(VirtualMemberTransfer.objects.get(person=self.kid).key)

        unsaid = self._post("/transfers/claim", self.as_mentor, {"key": key})
        self.assertEqual(unsaid.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(self._post("/consent", self.as_mentor).status_code, HTTPStatus.NO_CONTENT)
        asked = self._post("/transfers/claim", self.as_mentor, {"key": key, "keep_manager": True})
        self.assertEqual(asked.status_code, HTTPStatus.CREATED)
        self.assertEqual(asked.json(), {"person": "Kim Dana", "manager": "Anna Coach", "to": "mentor"})
        waiting = self.client.get(f"{API}/", **self.as_coach).json()["people"][0]["transfer"]
        self.assertEqual(
            (waiting["to"], waiting["claimed_by"]["name"], waiting["keep_manager"]), ("mentor", "Olga Mentor", False)
        )

        self.assertEqual(
            self._post(f"/{self.kid.pk}/transfer/confirm", self.as_coach).status_code, HTTPStatus.NO_CONTENT
        )
        people = self.client.get(f"{API}/", **self.as_mentor).json()["people"]
        self.assertEqual([(p["id"], p["transfer"]) for p in people], [(self.kid.pk, None)])
        self.assertEqual(self.client.get(f"{API}/", **self.as_coach).json()["people"], [])

    def test_a_mentor_whose_list_filled_up_since_asking_is_refused_at_the_answer(self):
        virtual_members.consent(self.mentor)
        link = transfers.issue(self.kid, MENTOR)
        self._post("/transfers/claim", self.as_mentor, {"key": str(link.key)})
        VirtualMember.objects.bulk_create(
            VirtualMember(owner=self.mentor, last_name=f"Pupil{n}", first_name="X", gender="M", birth_date="2012-01-01")
            for n in range(virtual_members.room(self.mentor))
        )
        refused = self._post(f"/{self.kid.pk}/transfer/confirm", self.as_coach)
        self.assertEqual(refused.status_code, HTTPStatus.CONFLICT)
        self.kid.refresh_from_db()
        self.assertEqual(self.kid.owner, self.coach)
        self.assertEqual(self._post(f"/{self.kid.pk}/transfer?to=nobody", self.as_coach).status_code, 422)
