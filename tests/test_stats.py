"""The owners' statistics (issue #184): who is a robot, what one page view adds, what a period sums to,
and who may read it all."""

import datetime
import uuid
from unittest import mock

from django.conf import settings
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from stats import counting
from stats.models import KEY_LENGTH, Tally
from stats.robots import OTHER, is_phone, robot

BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PHONE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
HOST = "testserver"


def _member(name: str, role: str) -> User:
    person = User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)
    person.api_token = uuid.uuid4()
    person.save(update_fields=["api_token"])
    return person


def _tallies(dimension: str) -> dict[str, int]:
    return dict(Tally.objects.filter(dimension=dimension).values_list("key", "count"))


def _at(moment: str):
    """Freeze the clock the counting reads at an instant given in ISO 8601."""
    return mock.patch("django.utils.timezone.now", return_value=datetime.datetime.fromisoformat(moment))


class RobotTests(TestCase):
    def test_a_robot_is_told_by_its_name_and_kind(self):
        cases = {
            GOOGLEBOT: ("search", "Googlebot"),
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0)": (
                "assistant",
                "ChatGPT-User",
            ),
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)": ("ai_training", "GPTBot"),
            "TelegramBot (like TwitterBot)": ("preview", "TelegramBot"),
            "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)": ("seo", "SemrushBot"),
            "curl/8.4.0": ("monitor", "curl/"),
            "Mozilla/5.0 (compatible; UniversalBicycleTeam-EventsAgent/1.0)": ("own", "UniversalBicycleTeam"),
        }
        for user_agent, expected in cases.items():
            with self.subTest(user_agent):
                self.assertEqual(robot(user_agent), expected)

    def test_a_specific_name_wins_over_a_general_one(self):
        # Claude-User fetches a page for a person who asked; ClaudeBot collects pages for training.
        agent = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +ClaudeBot)"
        self.assertEqual(robot(agent), ("assistant", "Claude-User"))

    def test_an_unknown_robot_is_named_by_what_it_calls_itself(self):
        self.assertEqual(robot("Mozilla/5.0 (compatible; SomeNewBot/2.0)"), (OTHER, "SomeNewBot"))
        self.assertEqual(robot("Java/17.0.2"), (OTHER, "Java"))

    def test_a_browser_is_no_robot(self):
        self.assertIsNone(robot(BROWSER))
        self.assertIsNone(robot(PHONE))

    def test_every_robot_the_calendar_knows_is_a_robot_here(self):
        for marker in settings.BOT_USER_AGENT_MARKERS:
            with self.subTest(marker):
                self.assertIsNotNone(robot(f"Mozilla/5.0 (compatible; {marker}/1.0)"))

    def test_a_phone_says_mobi_and_a_tablet_does_not(self):
        self.assertTrue(is_phone(PHONE))
        self.assertFalse(is_phone(BROWSER))
        self.assertFalse(is_phone("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"))


class CountingTests(TestCase):
    def _count(self, path="/ru/calendar/", referrer="", user_agent=BROWSER):
        counting.count_person(path, referrer, user_agent, HOST)

    def test_a_visit_from_another_site_is_a_view_and_a_visit(self):
        with _at("2026-11-04T10:30:00+05:00"):
            self._count(referrer="https://www.google.com/", user_agent=PHONE)
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.PEOPLE: 1})
        self.assertEqual(_tallies(Tally.Dimension.VISITS), {Tally.Audience.PEOPLE: 1})
        self.assertEqual(_tallies(Tally.Dimension.SOURCE), {"google.com": 1})
        self.assertEqual(_tallies(Tally.Dimension.DEVICE), {Tally.Device.PHONE: 1})
        self.assertEqual(_tallies(Tally.Dimension.PAGE), {"/ru/calendar/": 1})
        self.assertEqual(_tallies(Tally.Dimension.LANGUAGE), {"ru": 1})
        self.assertEqual(_tallies(Tally.Dimension.HOUR), {"10": 1})

    def test_a_page_opened_from_the_site_is_a_view_but_no_new_visit(self):
        self._count(referrer=f"https://{HOST}/ru/")
        self._count(referrer=f"https://news.{HOST}/")
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.PEOPLE: 2})
        self.assertEqual(_tallies(Tally.Dimension.VISITS), {})

    def test_a_visit_with_no_link_is_direct(self):
        self._count()
        self.assertEqual(_tallies(Tally.Dimension.SOURCE), {Tally.DIRECT: 1})
        self.assertEqual(_tallies(Tally.Dimension.DEVICE), {Tally.Device.COMPUTER: 1})

    def test_only_a_page_in_a_language_counts(self):
        for path in ("/api/v1/competitions/", "/media/a.jpg", "/rus/calendar/", "//elsewhere.example/ru/"):
            self._count(path=path)
        self.assertFalse(Tally.objects.exists())

    def test_the_same_page_again_adds_one(self):
        self._count()
        self._count()
        self.assertEqual(_tallies(Tally.Dimension.PAGE), {"/ru/calendar/": 2})

    def test_the_day_is_the_sites_whatever_zone_the_reader_is_in(self):
        # 22:30 in UTC is 03:30 the next day in the site's zone (Asia/Almaty, UTC+5).
        with _at("2026-11-04T22:30:00+00:00"), timezone.override("America/New_York"):
            self._count()
        self.assertEqual(list(Tally.objects.values_list("day", flat=True).distinct()), [datetime.date(2026, 11, 5)])
        self.assertEqual(_tallies(Tally.Dimension.HOUR), {"03": 1})

    def test_a_long_address_is_cut_to_the_column(self):
        self._count(path="/ru/" + "a" * 500)
        self.assertEqual([len(key) for key in _tallies(Tally.Dimension.PAGE)], [KEY_LENGTH])

    def test_a_day_takes_so_many_new_pages_and_still_counts_the_rest(self):
        with mock.patch.object(counting, "DAILY_KEYS", 2):
            for path in ("/ru/a/", "/ru/b/", "/ru/c/", "/ru/a/"):
                self._count(path=path)
        self.assertEqual(_tallies(Tally.Dimension.PAGE), {"/ru/a/": 2, "/ru/b/": 1})
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.PEOPLE: 4})


@override_settings(ALLOWED_HOSTS=[HOST])
class PageCountingTests(TestCase):
    """What the middleware counts as a page goes out: robots and the team, never a person's browser."""

    def test_a_robots_page_is_counted_by_its_kind(self):
        self.assertEqual(self.client.get("/ru/calendar/", HTTP_USER_AGENT=GOOGLEBOT).status_code, 200)
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.BOTS: 1})
        self.assertEqual(_tallies(Tally.Dimension.BOT), {"search:Googlebot": 1})

    def test_a_browser_is_left_to_count_itself(self):
        self.client.get("/ru/calendar/", HTTP_USER_AGENT=BROWSER)
        self.client.get("/ru/calendar/")
        self.assertFalse(Tally.objects.exists())

    def test_the_teams_pages_are_counted_apart(self):
        admin = _member("admin", User.Role.ADMIN)
        self.client.force_login(admin)
        self.client.get("/ru/calendar/", HTTP_USER_AGENT=BROWSER)
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.TEAM: 1})
        self.assertEqual(_tallies(Tally.Dimension.TEAM), {str(admin.pk): 1})

    def test_what_is_no_page_is_not_counted(self):
        self.client.get("/api/v1/competitions/", HTTP_USER_AGENT=GOOGLEBOT)
        self.client.get("/ru/calendar/999999999/", HTTP_USER_AGENT=GOOGLEBOT)
        self.client.post("/ru/calendar/", HTTP_USER_AGENT=GOOGLEBOT)
        self.assertFalse(Tally.objects.exists())

    def test_a_failed_count_never_costs_the_page(self):
        with mock.patch.object(counting, "add", side_effect=DatabaseError("down")):
            response = self.client.get("/ru/calendar/", HTTP_USER_AGENT=GOOGLEBOT)
        self.assertEqual(response.status_code, 200)
