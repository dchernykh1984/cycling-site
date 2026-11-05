"""People without accounts a member enters for starts and looks after the photos of (issue #438): how
many a member may add, what taking one off the site does to their entries, entering them, and their
albums."""

import datetime
import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts import roles, virtual_members
from accounts.models import User, VirtualMember
from calendar_app.models import CompetitionInvite
from event_photos import actions
from event_photos.models import DeclaredBib, IssuedBib
from event_photos.permissions import can_mark, can_represent, can_see_registration, declared_bib_refusal
from registrations.models import CompetitionRegistration
from registrations.tests import make_category, make_open_competition, make_registration, make_user
from tests.test_event_photos import EventPhotosTestCase, _index, _photo


def _added(owner, last="Ivanova", first="Dana", gender="F", born=datetime.date(2012, 3, 4), **more):
    return VirtualMember.objects.create(
        owner=owner, last_name=last, first_name=first, gender=gender, birth_date=born, **more
    )


def _bearer(user):
    """A personal API token for ``user``, as the profile's card makes one, in a request's header."""
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return {"HTTP_AUTHORIZATION": f"Bearer {user.api_token}"}


def _days(n):
    return timezone.localdate() + datetime.timedelta(days=n)


class LimitTests(TestCase):
    def test_how_many_people_a_member_may_add_goes_by_their_role(self):
        limits = {role: roles.virtual_members_limit(make_user(f"u-{role}", role=role)) for role in User.ROLE_HIERARCHY}
        root = User.objects.create_superuser("root", "root@example.com", "pw")
        self.assertEqual(
            limits,
            {
                User.Role.GUEST: 0,
                User.Role.PARTICIPANT: 10,
                User.Role.ORGANIZER: 1000,
                User.Role.ADMIN: None,
                User.Role.OWNER: None,
            },
        )
        self.assertIsNone(roles.virtual_members_limit(root))

    def test_the_room_left_counts_the_people_already_added(self):
        coach = make_user("coach")
        for n in range(3):
            _added(coach, first=f"Kid{n}")
        self.assertEqual(virtual_members.room(coach), 7)
        self.assertIsNone(virtual_members.room(make_user("boss", role=User.Role.ADMIN)))

    def test_consent_is_given_once_and_kept(self):
        coach = make_user("coach")
        self.assertFalse(virtual_members.consented(coach))
        virtual_members.consent(coach)
        given = User.objects.get(pk=coach.pk).virtual_members_consent_at
        virtual_members.consent(coach)
        self.assertEqual(User.objects.get(pk=coach.pk).virtual_members_consent_at, given)


class TakingSomebodyOffTests(TestCase):
    """A person taken off the site is entered in no race to come; their past races stay in the results,
    and so does a race run today or a stage race under way, whose start lists may already hold them."""

    def setUp(self):
        self.coach = make_user("coach")
        self.kid = _added(self.coach)
        self.past = make_registration(make_open_competition(date_start=_days(-20)), virtual_member=self.kid)
        self.under_way = make_registration(
            make_open_competition(date_start=_days(-1), date_end=_days(1)), virtual_member=self.kid
        )
        self.today = make_registration(make_open_competition(date_start=_days(0)), virtual_member=self.kid)
        self.to_come = make_registration(make_open_competition(date_start=_days(1)), virtual_member=self.kid)

    def _left(self):
        return set(CompetitionRegistration.objects.values_list("pk", "virtual_member_id"))

    def test_deleting_a_person_withdraws_them_from_races_to_come_and_keeps_the_rest(self):
        self.kid.delete()
        self.assertEqual(self._left(), {(self.past.pk, None), (self.under_way.pk, None), (self.today.pk, None)})

    def test_deleting_the_members_account_takes_their_people_off_too(self):
        self.coach.delete()
        self.assertFalse(VirtualMember.objects.exists())
        self.assertEqual(self._left(), {(self.past.pk, None), (self.under_way.pk, None), (self.today.pk, None)})


class EnteringTests(TestCase):
    def setUp(self):
        self.organizer = make_user("org", role=User.Role.ORGANIZER)
        self.coach = make_user(
            "coach", first_name="Ivan", last_name="Petrov", gender="M", birth_date=datetime.date(1985, 5, 5)
        )
        self.kid = _added(self.coach, city="Taraz", team="Junior")
        self.comp = make_open_competition(submitted_by=self.organizer, registration_mode="self_only")
        self.cat = make_category(self.comp)
        self.client.force_login(self.coach)

    def _url(self, name="register", *args):
        with translation.override("en"):
            return reverse(f"registrations:{name}", args=[self.comp.pk, *args])

    def _fields(self, **over):
        data = {"first_name": "Forged", "last_name": "Name", "gender": "M", "birth_year": 1990}
        data.update(over)
        return {f"pv{self.kid.pk}-{name}": value for name, value in data.items()}

    def test_a_member_with_people_added_gets_the_page_for_several_with_them_after_the_reader(self):
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, "registrations/register_many.html")
        rows = [(row.key, row.label, row.virtual) for row in response.context["rows"]]
        self.assertEqual(
            rows, [(str(self.coach.pk), "Ivan Petrov (you)", False), (f"v{self.kid.pk}", "Ivanova Dana", True)]
        )

    def test_an_event_taking_only_ones_own_data_enters_the_person_as_added_whatever_the_form_says(self):
        response = self.client.post(self._url(), {"person": [f"v{self.kid.pk}"], **self._fields(category=self.cat.pk)})
        self.assertEqual(response.status_code, 302)
        entry = CompetitionRegistration.objects.get()
        self.assertEqual(
            (entry.virtual_member, entry.user, entry.registered_by, entry.first_name, entry.last_name, entry.gender),
            (self.kid, None, self.coach, "Dana", "Ivanova", "F"),
        )
        self.assertEqual(entry.birth_date, datetime.date(2012, 3, 4))
        # entered once: the page no longer offers them
        rows = self.client.get(self._url()).context["rows"]
        self.assertNotIn(f"v{self.kid.pk}", [row.key for row in rows])

    def test_somebody_elses_person_cannot_be_ticked(self):
        other = _added(make_user("other"), first="Zoe")
        response = self.client.post(self._url(), {"person": [f"v{other.pk}"]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CompetitionRegistration.objects.exists())

    def test_an_invite_only_event_lets_in_no_account_for_a_person_without_one(self):
        self.comp.invite_only = True
        self.comp.save(update_fields=["invite_only"])
        CompetitionInvite.objects.create(competition=self.comp, user=self.coach)
        self.client.post(self._url(), {"person": [f"v{self.kid.pk}"], **self._fields(category=self.cat.pk)})
        self.assertEqual(CompetitionRegistration.objects.get().virtual_member, self.kid)
        self.assertEqual(list(CompetitionInvite.objects.values_list("user", flat=True)), [self.coach.pk])

    def test_whoever_added_the_person_edits_and_cancels_their_entry_and_nobody_else(self):
        entry = make_registration(self.comp, virtual_member=self.kid, first_name="Dana", last_name="Ivanova")
        self.assertEqual(self.client.get(self._url("edit_registration", entry.pk)).status_code, 200)
        listing = self.client.get(self._url("participant_list"))
        self.assertIn(entry.pk, listing.context["own_entries"])
        self.client.force_login(make_user("stranger"))
        self.assertEqual(self.client.get(self._url("edit_registration", entry.pk)).status_code, 403)
        self.assertEqual(self.client.post(self._url("delete_registration", entry.pk)).status_code, 403)
        self.client.force_login(self.coach)
        self.client.post(self._url("delete_registration", entry.pk))
        self.assertFalse(CompetitionRegistration.objects.exists())

    def test_the_profile_lists_the_entries_of_the_people_added(self):
        entry = make_registration(self.comp, virtual_member=self.kid, first_name="Dana", last_name="Ivanova")
        with translation.override("en"):
            response = self.client.get(reverse("account_profile"))
        self.assertIn(entry.pk, [reg.pk for reg in response.context["active_registrations"]])


class PhotoTests(EventPhotosTestCase):
    """The albums of a person without an account: whoever added them sees and marks the ones of their
    entries, and names a bib for them where the start lists give none."""

    def setUp(self):
        super().setUp()
        self.coach = make_user("coach")
        self.kid = _added(self.coach)
        self.stranger = make_user("stranger")
        self._publish(_index([_photo(1, [("7", "accepted", "ocr")]), _photo(2, [("9", "accepted", "ocr")])]))

    def _declare(self, person, bib, user=None, action="save"):
        self.client.force_login(user or self.coach)
        with translation.override("en"):
            url = reverse("event_photos:declare", args=[self.race.pk])
        return self.client.post(url, {"person": person, "bib": bib, "action": action})

    def test_whoever_added_the_person_sees_and_marks_their_entrys_album_and_nobody_else(self):
        entry = self._registration()
        entry.virtual_member = self.kid
        entry.save(update_fields=["virtual_member"])
        self.assertTrue(can_represent(self.coach, entry))
        self.assertTrue(can_mark(self.coach, entry))
        self.assertTrue(can_see_registration(self.coach, entry))
        self.assertFalse(can_represent(self.stranger, entry))
        self.assertFalse(can_see_registration(self.stranger, entry))

    def test_a_bib_named_for_the_person_finds_their_photos_for_whoever_added_them(self):
        self._declare(self.kid.pk, "7")
        declared = DeclaredBib.objects.get()
        self.assertEqual((declared.virtual_member, declared.user, declared.bib), (self.kid, None, "7"))
        self.assertEqual(declared.display_name, "Ivanova Dana")
        self.assertEqual(actions.declared_photos(declared).count(), 1)
        self._declare(self.kid.pk, "", action="remove")
        self.assertFalse(DeclaredBib.objects.exists())

    def test_nobody_names_a_bib_for_somebody_elses_person(self):
        response = self._declare(self.kid.pk, "7", user=self.stranger)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(DeclaredBib.objects.exists())

    def test_the_api_names_takes_back_and_lists_a_bib_for_the_person_as_the_page_does(self):
        url = f"/api/v1/event-photos/competitions/{self.race.pk}/my-bib"
        auth = _bearer(self.coach)
        named = self.client.put(url, {"bib": "7", "person": self.kid.pk}, content_type="application/json", **auth)
        self.assertEqual(named.status_code, 200)
        self.assertEqual(DeclaredBib.objects.get().virtual_member, self.kid)
        cards = self.client.get("/api/v1/event-photos/me/declared-bibs", **auth).json()
        self.assertEqual([(c["bib"], c["own"], c["person"], c["count"]) for c in cards], [("7", False, self.kid.pk, 1)])
        foreign = self.client.put(
            url, {"bib": "9", "person": self.kid.pk}, content_type="application/json", **_bearer(self.stranger)
        )
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(self.client.delete(f"{url}?person={self.kid.pk}", **auth).status_code, 204)
        self.assertFalse(DeclaredBib.objects.exists())

    def test_a_person_the_start_list_gives_a_bib_gets_none_named(self):
        entry = self._registration()
        entry.virtual_member = self.kid
        entry.save(update_fields=["virtual_member"])
        IssuedBib.objects.create(competition=self.race, registration=entry, bib="9")
        self.assertTrue(declared_bib_refusal(self.kid, self.race))
        self._declare(self.kid.pk, "7")
        self.assertFalse(DeclaredBib.objects.exists())


class ProfileCardTests(TestCase):
    """The profile's card: only the question until the member confirms they may handle these people's
    data, then the people, a form to add one, and each one's own page to change them."""

    def setUp(self):
        self.coach = make_user("coach")
        self.client.force_login(self.coach)

    def _url(self, name, *args):
        with translation.override("en"):
            return reverse(name, args=args)

    def _card(self):
        return self.client.get(self._url("account_profile")).context["virtual"]

    def _add(self, **over):
        data = {
            "last_name": "Ivanova",
            "first_name": "Dana",
            "gender": "F",
            "birth_date": "2012-03-04",
            "team": "Junior",
        }
        data.update(over)
        return self.client.post(self._url("account_virtual_add"), data)

    def test_nobody_is_added_before_the_member_confirms_they_may_handle_the_data(self):
        self.assertFalse(self._card()["consented"])
        self._add()
        self.assertFalse(VirtualMember.objects.exists())
        self.client.post(self._url("account_virtual_consent"))
        self.assertTrue(self._card()["consented"])
        self._add()
        self.assertEqual(list(VirtualMember.objects.values_list("owner", "last_name")), [(self.coach.pk, "Ivanova")])

    def test_the_same_person_twice_and_one_past_the_limit_come_back_with_the_reason(self):
        virtual_members.consent(self.coach)
        self._add()
        again = self._add(last_name="IVANOVA", first_name=" dana ")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.context["virtual"]["form"].errors)
        for n in range(9):
            _added(self.coach, first=f"Kid{n}")
        refused = self._add(first_name="Eleventh")
        self.assertIn("as many people as you may", " ".join(refused.context["virtual"]["form"].non_field_errors()))
        self.assertEqual(VirtualMember.objects.count(), 10)

    def test_a_member_changes_and_deletes_their_own_people_and_nobody_elses(self):
        mine = _added(self.coach)
        theirs = _added(make_user("other"), first="Zoe")
        self.assertEqual(self.client.get(self._url("account_virtual_edit", theirs.pk)).status_code, 404)
        self.assertEqual(self.client.post(self._url("account_virtual_delete", theirs.pk)).status_code, 404)
        self.client.post(
            self._url("account_virtual_edit", mine.pk),
            {"last_name": "Ivanova", "first_name": "Daria", "gender": "F", "birth_date": "2012-03-04"},
        )
        mine.refresh_from_db()
        self.assertEqual(mine.first_name, "Daria")
        self.client.post(self._url("account_virtual_delete", mine.pk))
        self.assertEqual(list(VirtualMember.objects.all()), [theirs])

    def test_a_guest_whose_address_is_not_confirmed_gets_no_card(self):
        guest = make_user("guest", role=User.Role.GUEST)
        self.client.force_login(guest)
        self.assertNotIn("virtual", self.client.get(self._url("account_profile")).context)
        self.client.post(self._url("account_virtual_consent"))
        self.assertIsNone(User.objects.get(pk=guest.pk).virtual_members_consent_at)


class ApiTests(TestCase):
    """/api/v1/virtual-members/: the profile's card over the API, with batches of many people."""

    def setUp(self):
        self.coach = make_user("coach")
        self.auth = _bearer(self.coach)

    def _post(self, path, body=None):
        return self.client.post(
            f"/api/v1/virtual-members/{path}", body or {}, content_type="application/json", **self.auth
        )

    def _row(self, n=0, **over):
        row = {"last_name": "Ivanova", "first_name": f"Kid{n}", "gender": "F", "birth_date": "2012-03-04"}
        row.update(over)
        return row

    def test_nobody_is_added_before_the_members_word_and_a_guest_cannot_give_it(self):
        self.assertEqual(self._post("", {"people": [self._row()]}).status_code, 403)
        self.assertEqual(self._post("consent").status_code, 204)
        self.assertEqual(self._post("", {"people": [self._row()]}).status_code, 200)
        guest = make_user("guest", role=User.Role.GUEST)
        refused = self.client.post("/api/v1/virtual-members/consent", **_bearer(guest))
        self.assertEqual(refused.status_code, 403)

    def test_a_batch_is_added_whole_and_a_second_send_adds_nobody_twice(self):
        virtual_members.consent(self.coach)
        batch = {"people": [self._row(n) for n in range(3)]}
        first = self._post("", batch).json()
        self.assertEqual((len(first["created"]), len(first["existing"])), (3, 0))
        again = self._post("", {"people": [self._row(0, last_name="IVANOVA"), self._row(5)]}).json()
        self.assertEqual(([p["first_name"] for p in again["created"]], len(again["existing"])), (["Kid5"], 1))
        self.assertEqual(VirtualMember.objects.count(), 4)

    def test_a_row_with_a_mistake_or_one_past_the_limit_saves_nobody(self):
        virtual_members.consent(self.coach)
        future = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        wrong = self._post("", {"people": [self._row(0), self._row(1, birth_date=future)]})
        self.assertEqual(wrong.status_code, 422)
        self.assertEqual([row["row"] for row in wrong.json()["rows"]], [1])
        too_many = self._post("", {"people": [self._row(n) for n in range(11)]})
        self.assertEqual(too_many.status_code, 422)
        self.assertFalse(VirtualMember.objects.exists())

    def test_the_names_are_kept_without_the_spaces_around_them_as_the_card_keeps_them(self):
        virtual_members.consent(self.coach)
        self._post("", {"people": [self._row(last_name="  Ivanova ", first_name=" Dana", team=" Junior ")]})
        person = VirtualMember.objects.get()
        self.assertEqual((person.last_name, person.first_name, person.team), ("Ivanova", "Dana", "Junior"))
        changed = self.client.patch(
            f"/api/v1/virtual-members/{person.pk}", {"city": " Taraz  "}, content_type="application/json", **self.auth
        )
        self.assertEqual(changed.json()["city"], "Taraz")
        blank = self._post("", {"people": [self._row(first_name="   ")]})
        self.assertEqual(blank.status_code, 422)

    def test_a_dry_run_says_what_it_would_add_and_saves_nothing(self):
        virtual_members.consent(self.coach)
        answer = self._post("", {"people": [self._row()], "dry_run": True}).json()
        self.assertEqual((answer["dry_run"], len(answer["created"])), (True, 1))
        self.assertFalse(VirtualMember.objects.exists())

    def test_the_list_says_the_limit_and_the_room_left(self):
        virtual_members.consent(self.coach)
        _added(self.coach)
        listed = self.client.get("/api/v1/virtual-members/", **self.auth).json()
        self.assertEqual((listed["consented"], listed["limit"], listed["room"]), (True, 10, 9))
        self.assertEqual([p["last_name"] for p in listed["people"]], ["Ivanova"])

    def test_a_member_changes_and_deletes_their_own_people_only(self):
        mine, other = _added(self.coach), _added(make_user("other"), first="Zoe")
        twin = _added(self.coach, first="Twin")
        url = "/api/v1/virtual-members/{}"
        changed = self.client.patch(
            url.format(mine.pk), {"city": "Taraz"}, content_type="application/json", **self.auth
        )
        self.assertEqual(changed.json()["city"], "Taraz")
        clash = self.client.patch(
            url.format(twin.pk), {"first_name": "dana"}, content_type="application/json", **self.auth
        )
        self.assertEqual(clash.status_code, 409)
        self.assertEqual(self.client.delete(url.format(other.pk), **self.auth).status_code, 404)
        self.assertEqual(self.client.delete(url.format(mine.pk), **self.auth).status_code, 204)
        self.assertEqual(set(VirtualMember.objects.all()), {other, twin})
