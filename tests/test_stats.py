"""The owners' statistics (issue #184): who is a robot, what one page view adds, what a period sums to,
and who may read it all."""

import datetime
import uuid
from unittest import mock

from django.conf import settings
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from calendar_app.models import Competition
from locations.models import Location
from stats import counting, report
from stats.models import KEY_LENGTH, Tally
from stats.robots import KINDS, OTHER, is_phone, robot
from stats.views import KIND_NAMES, PERIOD_NAMES

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


@override_settings(ALLOWED_HOSTS=[HOST])
class HitTests(TestCase):
    """POST /api/v1/stats/hit: a page of the site, opened in a person's browser, says so."""

    def _hit(self, client=None, path="/ru/calendar/", **headers):
        headers.setdefault("HTTP_USER_AGENT", BROWSER)
        headers.setdefault("HTTP_SEC_FETCH_SITE", "same-origin")
        return (client or self.client).post(
            "/api/v1/stats/hit", {"path": path, "referrer": ""}, content_type="application/json", **headers
        )

    def test_a_persons_page_is_counted(self):
        self.assertEqual(self._hit(HTTP_ORIGIN=f"http://{HOST}").status_code, 204)
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.PEOPLE: 1})

    def test_what_is_not_a_person_on_our_page_is_dropped_without_a_word(self):
        admin = Client()
        admin.force_login(_member("admin", User.Role.ADMIN))
        for answer in (
            self._hit(HTTP_SEC_FETCH_SITE="cross-site"),
            self._hit(HTTP_ORIGIN="https://elsewhere.example"),
            self._hit(HTTP_USER_AGENT=GOOGLEBOT),
            self._hit(HTTP_USER_AGENT=""),
            self._hit(admin),
        ):
            self.assertEqual(answer.status_code, 204)
        self.assertFalse(Tally.objects.exists())

    def test_a_signed_in_reader_below_the_team_is_counted_with_no_csrf_token(self):
        # The page sends no token, and the test client skips the check unless it is asked to make it.
        organizer = Client(enforce_csrf_checks=True)
        organizer.force_login(_member("organizer", User.Role.ORGANIZER))
        self.assertEqual(self._hit(organizer).status_code, 204)
        self.assertEqual(_tallies(Tally.Dimension.VIEWS), {Tally.Audience.PEOPLE: 1})


class ReportTests(TestCase):
    today = datetime.date(2026, 11, 4)

    def _tally(self, day, dimension, key, count):
        Tally.objects.create(day=day, dimension=dimension, key=key, count=count)

    def _build(self, period):
        with _at(f"{self.today.isoformat()}T12:00:00+05:00"):
            return report.build(period)

    def test_each_period_ends_today(self):
        self._tally(datetime.date(2024, 3, 1), Tally.Dimension.VIEWS, Tally.Audience.PEOPLE, 1)
        spans = {period: (self._build(period)["start"], self._build(period)["bucket"]) for period in report.PERIODS}
        self.assertEqual(
            spans,
            {
                "today": (self.today, "hour"),
                "week": (datetime.date(2026, 10, 29), "day"),
                "month": (datetime.date(2026, 10, 6), "day"),
                "quarter": (datetime.date(2026, 8, 7), "day"),
                "ytd": (datetime.date(2026, 1, 1), "week"),
                "year": (datetime.date(2025, 11, 5), "week"),
                "all": (datetime.date(2024, 3, 1), "month"),
            },
        )
        self.assertEqual(self._build("all")["end"], self.today)

    def test_an_unknown_period_reads_as_the_default(self):
        self.assertEqual(self._build("decade")["period"], report.DEFAULT_PERIOD)

    def test_a_period_sums_its_days_and_shows_the_empty_ones_as_zero(self):
        self._tally(self.today, Tally.Dimension.VIEWS, Tally.Audience.PEOPLE, 5)
        self._tally(self.today, Tally.Dimension.VISITS, Tally.Audience.PEOPLE, 2)
        self._tally(self.today - datetime.timedelta(days=6), Tally.Dimension.VIEWS, Tally.Audience.PEOPLE, 3)
        self._tally(self.today - datetime.timedelta(days=7), Tally.Dimension.VIEWS, Tally.Audience.PEOPLE, 100)
        self._tally(self.today, Tally.Dimension.VIEWS, Tally.Audience.BOTS, 40)
        people = self._build("week")["people"]
        self.assertEqual((people["views"], people["visits"], people["views_per_visit"]), (8, 2, 4.0))
        self.assertEqual([point["views"] for point in people["series"]], [3, 0, 0, 0, 0, 0, 5])

    def test_today_is_drawn_by_the_hour(self):
        self._tally(self.today, Tally.Dimension.HOUR, "09", 4)
        series = self._build("today")["people"]["series"]
        self.assertEqual(len(series), 24)
        self.assertEqual(series[9], {"at": "09:00", "views": 4})

    def test_a_page_is_listed_by_the_title_of_what_it_shows(self):
        country = Location.add_root(name_ru="Testland", name_en="Testland")
        venue = country.add_child(name_ru="R").add_child(name_ru="C").add_child(name_ru="V")
        event = Competition.objects.create(
            title_ru="Race", status=Competition.Status.APPROVED, date_start=self.today, location=venue
        )
        self._tally(self.today, Tally.Dimension.PAGE, f"/ru/calendar/{event.pk}/", 3)
        self._tally(self.today, Tally.Dimension.PAGE, "/ru/calendar/", 7)
        pages = self._build("week")["people"]["pages"]
        self.assertEqual(
            pages,
            [
                {"path": "/ru/calendar/", "title": "", "views": 7},
                {"path": f"/ru/calendar/{event.pk}/", "title": "Race", "views": 3},
            ],
        )

    def test_robots_are_summed_by_kind(self):
        self._tally(self.today, Tally.Dimension.VIEWS, Tally.Audience.BOTS, 11)
        self._tally(self.today, Tally.Dimension.BOT, "search:Googlebot", 5)
        self._tally(self.today, Tally.Dimension.BOT, "search:YandexBot", 2)
        self._tally(self.today, Tally.Dimension.BOT, "seo:AhrefsBot", 4)
        bots = self._build("week")["bots"]
        self.assertEqual(bots["views"], 11)
        self.assertEqual(bots["kinds"], [{"kind": "search", "views": 7}, {"kind": "seo", "views": 4}])
        self.assertEqual(bots["names"][0], {"kind": "search", "name": "Googlebot", "views": 5})

    def test_the_robots_total_counts_those_past_the_days_names(self):
        with mock.patch.object(counting, "DAILY_KEYS", 1), _at(f"{self.today.isoformat()}T12:00:00+05:00"):
            for robot_name in ("Googlebot", "YandexBot"):
                counting.add(
                    (Tally.Dimension.VIEWS, Tally.Audience.BOTS), (Tally.Dimension.BOT, f"search:{robot_name}")
                )
        bots = self._build("week")["bots"]
        self.assertEqual((bots["views"], len(bots["names"])), (2, 1))

    def test_the_team_is_every_admin_and_owner_with_their_pages_and_changes(self):
        admin = _member("admin", User.Role.ADMIN)
        owner = _member("owner", User.Role.OWNER)
        _member("organizer", User.Role.ORGANIZER)
        self._tally(self.today, Tally.Dimension.TEAM, str(admin.pk), 6)
        with _at(f"{self.today.isoformat()}T12:00:00+05:00"):
            AuditLog.objects.create(
                user=owner, action=AuditLog.ACTION_UPDATED, object_type="competition", object_id="1", object_repr="x"
            )
            team = report.build("week")["team"]
        self.assertEqual(
            team["members"],
            [
                {"name": "admin@example.com", "views": 6, "actions": 0},
                {"name": "owner@example.com", "views": 0, "actions": 1},
            ],
        )
        self.assertEqual((team["views"], team["actions"]), (6, 1))

    def test_newcomers_are_the_members_who_joined_in_the_period(self):
        joined = _member("newcomer", User.Role.PARTICIPANT)
        old = _member("old", User.Role.PARTICIPANT)
        User.objects.filter(pk=old.pk).update(date_joined=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))
        User.objects.filter(pk=joined.pk).update(date_joined=datetime.datetime(2026, 11, 3, tzinfo=datetime.UTC))
        site = self._build("week")["site"]
        self.assertEqual((site["members"], site["new_members"]), (2, 1))
        self.assertEqual([row["name"] for row in site["newcomers"]], ["newcomer@example.com"])


@override_settings(ALLOWED_HOSTS=[HOST])
class DashboardTests(TestCase):
    def test_an_owner_sees_the_period_they_chose(self):
        self.client.force_login(_member("owner", User.Role.OWNER))
        Tally.objects.create(day=counting.now().date(), dimension=Tally.Dimension.VIEWS, key="people", count=3)
        page = self.client.get("/en/stats/?period=week")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '<option value="week" selected>')
        charts = page.context["charts"]
        self.assertEqual(charts["people"]["names"], ["Visits", "Page views"])
        self.assertEqual(charts["people"]["points"][-1]["values"], [0, 3])

    def test_every_period_and_every_kind_of_robot_has_a_name(self):
        self.assertEqual(set(PERIOD_NAMES), set(report.PERIODS))
        self.assertEqual(set(KIND_NAMES), {kind for kind, _names in KINDS} | {OTHER})

    def test_nobody_below_an_owner_opens_it(self):
        self.client.force_login(_member("admin", User.Role.ADMIN))
        self.assertEqual(self.client.get("/en/stats/").status_code, 403)

    def test_a_visitor_is_asked_to_sign_in(self):
        self.assertEqual(self.client.get("/en/stats/").status_code, 302)


class StatisticsApiTests(TestCase):
    def _get(self, person=None, query=""):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {person.api_token}"} if person else {}
        return self.client.get(f"/api/v1/stats/{query}", **headers)

    def test_an_owner_reads_the_numbers_of_the_page(self):
        answer = self._get(_member("owner", User.Role.OWNER), "?period=today")
        self.assertEqual(answer.status_code, 200)
        body = answer.json()
        self.assertEqual((body["period"], body["bucket"]), ("today", "hour"))
        self.assertEqual(set(body), {"period", "start", "end", "bucket", "people", "bots", "team", "site"})

    def test_an_admin_does_not(self):
        answer = self._get(_member("admin", User.Role.ADMIN))
        self.assertEqual(answer.status_code, 403)

    def test_nobody_without_a_token_does(self):
        self.assertEqual(self._get().status_code, 401)
