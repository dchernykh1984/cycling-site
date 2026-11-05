"""/api/v1/registrations/ (issue #438): entering races with one's own token, as the registration page
enters the people ticked on it -- oneself, the members one manages, the people without accounts one
added -- and listing, changing and cancelling those entries."""

import datetime
import uuid

from django.test import TestCase
from django.utils import timezone, translation
from django.utils.translation import gettext

from accounts import managing
from accounts.models import User, VirtualMember
from calendar_app.models import CompetitionInvite
from registrations.models import CompetitionRegistration
from registrations.tests import make_category, make_open_competition, make_registration, make_user


def _token(user):
    user.api_token = uuid.uuid4()
    user.save(update_fields=["api_token"])
    return {"HTTP_AUTHORIZATION": f"Bearer {user.api_token}"}


def _manage(manager, member):
    managing.ask(member, managing.issue_invite(manager).key)
    managing.accept(manager, member.pk)


class EnteringTests(TestCase):
    def setUp(self):
        self.coach = make_user(
            "coach", first_name="Ivan", last_name="Petrov", gender="M", birth_date=datetime.date(1985, 5, 5)
        )
        self.anna = make_user(
            "anna", first_name="Anna", last_name="Ivanova", gender="F", birth_date=datetime.date(2009, 4, 17)
        )
        _manage(self.coach, self.anna)
        self.kid = VirtualMember.objects.create(
            owner=self.coach, last_name="Sokolova", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
        )
        self.comp = make_open_competition(registration_mode="self_only")
        self.cat = make_category(self.comp)
        self.auth = _token(self.coach)

    def _enter(self, *entries, competition=None, auth=None):
        body = {"competition_id": (competition or self.comp).pk, "entries": list(entries)}
        return self.client.post("/api/v1/registrations/", body, content_type="application/json", **(auth or self.auth))

    def test_the_caller_their_member_and_a_person_they_added_are_entered_from_their_own_data(self):
        answer = self._enter(
            {"person": "me", "first_name": "Forged"},
            {"person": f"member:{self.anna.pk}"},
            {"person": f"virtual:{self.kid.pk}", "city": "Taraz"},
        )
        self.assertEqual(answer.status_code, 200)
        self.assertEqual([row["errors"] for row in answer.json()], [{}, {}, {}])
        entries = {
            (e.user_id, e.virtual_member_id, e.first_name, e.registered_by_id, e.city)
            for e in CompetitionRegistration.objects.all()
        }
        self.assertEqual(
            entries,
            {
                (self.coach.pk, None, "Ivan", self.coach.pk, ""),
                (self.anna.pk, None, "Anna", self.coach.pk, ""),
                (None, self.kid.pk, "Dana", self.coach.pk, "Taraz"),
            },
        )

    def test_one_refused_entry_says_why_and_the_next_one_is_still_entered(self):
        stranger = make_user("stranger", gender="M", birth_date=datetime.date(1990, 1, 1))
        other = VirtualMember.objects.create(
            owner=stranger, last_name="Z", first_name="Z", gender="M", birth_date=datetime.date(2010, 1, 1)
        )
        make_registration(self.comp, user=self.coach)
        answer = self._enter(
            {"person": "me"},
            {"person": f"member:{stranger.pk}"},
            {"person": f"virtual:{other.pk}"},
            {"person": "other", "first_name": "A", "last_name": "B", "gender": "M", "birth_year": 1990},
            {"person": f"virtual:{self.kid.pk}"},
        ).json()
        self.assertEqual([row["registration_id"] is not None for row in answer], [False, False, False, False, True])
        with translation.override("ru"):  # the API speaks the site's default language
            said = gettext("You are already registered for this competition.")
        self.assertEqual(answer[0]["errors"]["__all__"], [said])
        self.assertEqual(answer[1]["errors"], {"person": ["Not a member whose registrations you manage"]})
        self.assertEqual(answer[2]["errors"], {"person": ["Not a person you added"]})
        self.assertIn("name the person", answer[3]["errors"]["person"][0])

    def test_where_anyone_may_be_entered_another_person_is_typed_in_under_the_callers_account(self):
        free = make_open_competition(registration_mode="free")
        answer = self._enter(
            {"person": "other", "first_name": "Oleg", "last_name": "Kim", "gender": "M", "birth_year": 1995},
            competition=free,
        ).json()
        entry = CompetitionRegistration.objects.get(pk=answer[0]["registration_id"])
        self.assertEqual((entry.user, entry.first_name, entry.birth_date.year), (self.coach, "Oleg", 1995))

    def test_a_closed_or_relay_or_unseen_event_enters_nobody(self):
        closed = make_open_competition(registration_enabled=False)
        self.assertEqual(self._enter({"person": "me"}, competition=closed).status_code, 409)
        relay = make_open_competition(relay_enabled=True)
        self.assertEqual(self._enter({"person": "me"}, competition=relay).status_code, 409)
        hidden = make_open_competition(is_hidden=True)
        self.assertEqual(self._enter({"person": "me"}, competition=hidden).status_code, 404)
        self.assertFalse(CompetitionRegistration.objects.exists())

    def test_an_invite_only_event_lets_in_the_member_entered_and_no_account_for_a_person_without_one(self):
        self.comp.invite_only = True
        self.comp.save(update_fields=["invite_only"])
        CompetitionInvite.objects.create(competition=self.comp, user=self.coach)
        self._enter({"person": f"member:{self.anna.pk}"}, {"person": f"virtual:{self.kid.pk}"})
        self.assertEqual(set(CompetitionInvite.objects.values_list("user", flat=True)), {self.coach.pk, self.anna.pk})

    def test_a_person_no_category_takes_is_told_so_and_not_entered(self):
        too_old = VirtualMember.objects.create(
            owner=self.coach, last_name="Old", first_name="Ann", gender="F", birth_date=datetime.date(1950, 1, 1)
        )
        self.cat.birth_from = datetime.date(2000, 1, 1)
        self.cat.save(update_fields=["birth_from"])
        answer = self._enter({"person": f"virtual:{too_old.pk}"}).json()
        with translation.override("ru"):
            said = gettext("No open category of this event takes this gender and year of birth.")
        self.assertEqual(answer[0], {"row": 0, "registration_id": None, "errors": {"category": [said]}})
        self.assertFalse(CompetitionRegistration.objects.exists())

    def test_nobody_enters_without_a_token(self):
        body = {"competition_id": self.comp.pk, "entries": [{"person": "me"}]}
        answer = self.client.post("/api/v1/registrations/", body, content_type="application/json")
        self.assertEqual(answer.status_code, 401)


class OwnEntriesTests(TestCase):
    def setUp(self):
        self.coach = make_user("coach", gender="M", birth_date=datetime.date(1985, 5, 5))
        self.kid = VirtualMember.objects.create(
            owner=self.coach, last_name="Sokolova", first_name="Dana", gender="F", birth_date=datetime.date(2012, 3, 4)
        )
        self.comp = make_open_competition(registration_mode="self_only", require_approval=True)
        self.entry = make_registration(
            self.comp, virtual_member=self.kid, first_name="Dana", last_name="Sokolova", is_approved=True
        )
        self.own = make_registration(self.comp, user=self.coach)
        self.foreign = make_registration(self.comp, user=make_user("stranger"))
        self.auth = _token(self.coach)
        self.url = "/api/v1/registrations/{}"

    def _patch(self, pk, body):
        return self.client.patch(self.url.format(pk), body, content_type="application/json", **self.auth)

    def test_the_list_holds_the_callers_entries_and_those_of_the_people_they_enter(self):
        listed = self.client.get("/api/v1/registrations/", **self.auth).json()
        self.assertEqual(
            {(e["id"], e["person"], e["can_change"]) for e in listed},
            {(self.entry.pk, f"virtual:{self.kid.pk}", True), (self.own.pk, "me", True)},
        )

    def test_a_change_keeps_the_persons_own_data_and_sends_an_approved_entry_back_to_review(self):
        changed = self._patch(self.entry.pk, {"city": "Taraz", "team": "Junior", "first_name": "Forged"}).json()
        self.assertEqual((changed["city"], changed["team"], changed["first_name"]), ("Taraz", "Junior", "Dana"))
        self.assertFalse(changed["is_approved"])

    def test_nobody_elses_entry_is_reached_and_a_closed_race_changes_nothing(self):
        self.assertEqual(self._patch(self.foreign.pk, {"city": "X"}).status_code, 404)
        self.assertEqual(self.client.delete(self.url.format(self.foreign.pk), **self.auth).status_code, 404)
        self.comp.registration_deadline = timezone.now() - datetime.timedelta(days=1)
        self.comp.save(update_fields=["registration_deadline"])
        self.assertEqual(self._patch(self.entry.pk, {"city": "X"}).status_code, 409)
        self.assertEqual(self.client.delete(self.url.format(self.entry.pk), **self.auth).status_code, 409)

    def test_cancelling_an_entry_deletes_it(self):
        self.assertEqual(self.client.delete(self.url.format(self.entry.pk), **self.auth).status_code, 204)
        self.assertFalse(CompetitionRegistration.objects.filter(pk=self.entry.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.coach.pk).exists())
