"""What each kind of visitor may do, as the site answers: the table every role check is held to.

Each probe asks the site one question its role rules decide -- a page's status, a flag in a page's
context, a field of a form, an answer of the API -- as a visitor, a guest (an address not confirmed
yet), a participant, an organizer, an admin, the owner, and a superuser whose role was never set (one
``createsuperuser`` makes). The answers are pinned, so that a change to where or how roles are
compared shows here at once.

An answer is a status ("403"), flags ("yn": the first yes, the second no), or both ("200:y"); "-" is a
question with no answer for that visitor, such as the flags of a page they cannot open.
"""

import datetime
import uuid
from dataclasses import dataclass
from typing import Any

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone, translation

from accounts.access import needs_email_confirmation
from accounts.admin import UserAdmin
from accounts.models import User
from calendar_app.models import Competition, CompetitionReport
from calendar_app.visibility import can_open, can_review, can_see, listed_for, manages
from cycling_site.context_processors import moderation_tasks
from knowledge.models import DraftSubmission, KnowledgeArticle, KnowledgeIndexPage
from locations.models import Location, LocationsMapPage
from news.models import NewsArticle, NewsIndexPage, NewsPage
from registrations.wagtail_hooks import TeamViewSet

KINDS = ("visitor", "guest", "participant", "organizer", "admin", "owner", "superuser")

# fmt: off
EVENTS = {
    #                                visitor guest particip. organizer admin   owner   superuser
    "submit page":                  "302     302   200       200       200     200     200",
    # the organizer's fields, the top-event mark, the assistant
    "submit page offers":           "-       -     nnn       yny       yyy     yyy     yyy",
    # and whether it lists places awaiting review
    "moderation page":              "302     403   403       200:n     200:y   200:y   200:y",
    # and whether it offers to approve or reject
    "another's pending event":      "404     404   404       200:y     200:y   200:y   200:y",
    # comment, report, moderate, the reports, the moderation history
    "public event offers":          "nnnnn   nnnnn yynnn     yynnn     yynyy   yynyy   yynyy",
    "list: moderation link":        "n       n     n         y         y       y       y",
    "edit another's event":         "403     403   403       403       200     200     200",
    "edit own event: organizer's":  "-       n     n         y         y       y       y",
    # manages a public event, reviews and opens a pending one, sees and lists a hidden one
    "event visibility":             "nnnnn   nnnnn nnnnn     nyynn     yyyyy   yyyyy   yyyyy",
    "moderation banner":            "n       n     n         y         y       y       y",
}

EVENTS_API = {
    #                                visitor guest particip. organizer admin   owner   superuser
    # and whether the new event is approved or waits for review
    "create":                       "401     403   403       201:pend  201:appr 201:appr 403",
    "own event: top":               "-       403   403       403       200     200     200",
    "own event: hidden":            "-       403   403       403       200     200     200",
    "another's pending event":      "404     404   404       404       200     200     200",
}

NEWS_AND_KNOWLEDGE = {
    #                                visitor guest particip. organizer admin   owner   superuser
    "news list: add":               "n       n     n         n         y       y       y",
    "news create page":             "403     403   403       403       200     200     200",
    "hidden news item":             "404     404   404       404       200     200     200",
    "news item: comment":           "n       n     y         y         y       y       y",
    # comment, delete comments
    "news page offers":             "nn      nn    yn        yn        yy      yy      ny",
    "API hidden news":              "404     404   404       404       200     200     200",
    # manage, add
    "knowledge index offers":       "nn      nn    ny        ny        yy      yy      yn",
    "knowledge article: comment":   "n       n     y         y         y       y       y",
    "API new draft":                "401     403   201       201       201     201     403",
    # and whether others' drafts are listed
    "API drafts":                   "401     200:n 200:n     200:n     200:y   200:y   200:y",
}

PLACES_HOME_ACCOUNTS = {
    #                                visitor guest particip. organizer admin   owner   superuser
    # manage, add
    "places map offers":            "nn      nn    ny        ny        yy      yy      yy",
    # and manage, propose a region or a city
    "add a place page":             "302     302   200:nn    200:ny    200:yy  200:yy  200:yy",
    # and whether the venue is approved or proposed
    "API new venue":                "401     403   201:prop  201:appr  201:appr 201:appr 201:appr",
    # and whether a hidden place is listed
    "API places":                   "200:n   200:n 200:n     200:n     200:y   200:y   200:y",
    "new album page":               "302     403   403       403       200     200     200",
    "home edit page":               "302     403   403       403       403     200     403",
    "home page: edit link":         "n       n     n         n         n       y       n",
    "API new home card":            "401     403   403       403       403     201     403",
    # and its cards: contact the owners, appearance; and whether the address counts as confirmed
    "profile":                      "302     200:nnn 200:yyn 200:yyy   200:yyy 200:yyy 200:nnn",
    "needs email confirmation":     "n       y     n         n         n       n       n",
    "user admin: privileges":       "n       n     n         n         n       y       y",
    "teams in the admin":           "n       n     n         n         y       y       y",
    "API assistant on news":        "401     403   403       403       201     201     201",
}
# fmt: on


def _yn(*flags) -> str:
    return "".join("y" if flag else "n" for flag in flags)


def _with(page, *flags) -> str:
    return f"200:{_yn(*flags)}" if page.status_code == 200 else str(page.status_code)


def _member(name: str, role: str) -> User:
    person = User.objects.create_user(username=name, email=f"{name}@example.com", password="pw", role=role)
    person.api_token = uuid.uuid4()
    person.save(update_fields=["api_token"])
    return person


@dataclass
class Visitor:
    user: Any  # a member, or AnonymousUser for a visitor
    browser: Client
    program: Client
    headers: dict

    def own_event(self, site) -> Competition:
        return Competition.objects.create(
            title_ru="Own",
            status=Competition.Status.APPROVED,
            date_start=site.public.date_start,
            location=site.venue,
            submitted_by=self.user,
        )

    def post_json(self, url, body):
        return self.program.post(url, body, content_type="application/json", **self.headers)


# -- events ------------------------------------------------------------------------------------------


def submit_page(site, v):
    return str(v.browser.get("/en/calendar/submit/").status_code)


def submit_page_offers(site, v):
    page = v.browser.get("/en/calendar/submit/")
    if page.status_code != 200:
        return "-"
    form = page.context["form"]
    return _yn(
        page.context["is_organizer_plus"], "is_top" in form.fields, 'id="assistant-toggle"' in page.content.decode()
    )


def moderation_page(site, v):
    page = v.browser.get("/en/calendar/moderate/")
    return _with(page, page.status_code == 200 and "pending_locations" in page.context)


def pending_event(site, v):
    page = v.browser.get(f"/en/calendar/{site.pending.pk}/")
    return _with(page, page.status_code == 200 and page.context["can_moderate"])


def public_event_offers(site, v):
    context = v.browser.get(f"/en/calendar/{site.public.pk}/").context
    return _yn(
        context["can_comment"],
        context["can_report"],
        context["can_moderate"],
        bool(context["open_reports"]),
        context["moderation_history"] is not None,
    )


def list_moderation_link(site, v):
    page = v.browser.get("/en/calendar/list/").content.decode()
    return _yn('href="/en/calendar/moderate/" class="btn btn-outline-warning' in page)


def edit_others_event(site, v):
    return str(v.browser.get(f"/en/calendar/{site.public.pk}/edit/").status_code)


def edit_own_event(site, v):
    if not v.user.is_authenticated:
        return "-"
    page = v.browser.get(f"/en/calendar/{v.own_event(site).pk}/edit/")
    return _yn(page.context["is_organizer_plus"]) if page.status_code == 200 else str(page.status_code)


def event_visibility(site, v):
    listed = listed_for(Competition.objects.filter(pk=site.hidden.pk), v.user).exists()
    return _yn(
        manages(v.user, site.public),
        can_review(v.user, site.pending),
        can_open(v.user, site.pending),
        can_see(v.user, site.hidden),
        listed,
    )


def moderation_banner(site, v):
    request = RequestFactory().get("/")
    request.user = v.user
    return _yn(moderation_tasks(request).get("moderation_tasks"))


def api_create(site, v):
    body = {"title": {"ru": "Made"}, "date_start": str(site.public.date_start), "location_id": site.venue.pk}
    answer = v.post_json("/api/v1/competitions/", body)
    if answer.status_code != 201:
        return str(answer.status_code)
    made = Competition.objects.get(pk=answer.json()["id"])
    return "201:appr" if made.status == Competition.Status.APPROVED else "201:pend"


def api_own_event(field):
    def probe(site, v):
        if not v.user.is_authenticated:
            return "-"
        url = f"/api/v1/competitions/{v.own_event(site).pk}"
        return str(v.program.patch(url, {field: True}, content_type="application/json", **v.headers).status_code)

    return probe


def api_pending_event(site, v):
    return str(v.program.get(f"/api/v1/competitions/{site.pending.pk}", **v.headers).status_code)


# -- news and knowledge ------------------------------------------------------------------------------


def news_list_add(site, v):
    return _yn(v.browser.get("/en/news/").context["can_add"])


def news_create_page(site, v):
    return str(v.browser.get("/en/news/articles/create/").status_code)


def hidden_news(site, v):
    return str(v.browser.get(f"/en/news/articles/{site.hidden_news.pk}/").status_code)


def news_comment(site, v):
    return _yn(v.browser.get(f"/en/news/articles/{site.news.pk}/").context["can_comment"])


def news_page_offers(site, v):
    context = v.browser.get(site.news_page.url).context
    return _yn(context["can_comment"], context["user_can_delete_comment"])


def api_hidden_news(site, v):
    return str(v.program.get(f"/api/v1/news/{site.hidden_news.pk}", **v.headers).status_code)


def knowledge_index_offers(site, v):
    context = v.browser.get(site.knowledge.url).context
    return _yn(context["can_manage"], context["can_add"])


def knowledge_comment(site, v):
    return _yn(v.browser.get(f"{site.knowledge.url}{site.article.slug}/").context["can_comment"])


def api_new_draft(site, v):
    return str(
        v.post_json("/api/v1/knowledge/drafts/", {"title": "Draft", "body": "<p>Text</p>", "locale": "en"}).status_code
    )


def api_drafts(site, v):
    answer = v.program.get("/api/v1/knowledge/drafts/", **v.headers)
    if answer.status_code != 200:
        return str(answer.status_code)
    return f"200:{_yn(any(row['title'] == site.draft.title for row in answer.json()))}"


# -- places, the home page, accounts -----------------------------------------------------------------


def places_map_offers(site, v):
    context = v.browser.get(site.places_map.url).context
    return _yn(context["can_manage"], context["can_add"])


def add_place_page(site, v):
    page = v.browser.get("/en/locations/add/")
    if page.status_code != 200:
        return str(page.status_code)
    form = page.context["form"]
    return f"200:{_yn(form.can_manage, form.can_propose_place)}"


def api_new_venue(site, v):
    body = {"name": {"ru": f"Venue {v.user.pk}"}, "parent_id": site.city.pk, "lat": 43.25, "lng": 76.95}
    answer = v.post_json("/api/v1/locations/", body)
    if answer.status_code != 201:
        return str(answer.status_code)
    return "201:prop" if hasattr(Location.objects.get(pk=answer.json()["id"]), "proposal") else "201:appr"


def api_places(site, v):
    answer = v.program.get("/api/v1/locations/?include_hidden=true", **v.headers)

    def ids(nodes):
        for node in nodes:
            yield node["id"]
            yield from ids(node["children"])

    return f"{answer.status_code}:{_yn(site.catch_all.pk in set(ids(answer.json())))}"


def new_album_page(site, v):
    return str(v.browser.get("/en/gallery/albums/new/").status_code)


def home_edit_page(site, v):
    return str(v.browser.get("/en/home/edit/").status_code)


def home_edit_link(site, v):
    return _yn('href="/en/home/edit/"' in v.browser.get("/en/").content.decode())


def api_new_home_card(site, v):
    return str(v.post_json("/api/v1/home/cards/", {"title": {"ru": "Card"}}).status_code)


def profile(site, v):
    page = v.browser.get("/en/accounts/profile/")
    if page.status_code != 200:
        return str(page.status_code)
    text = page.content.decode()
    # The contact card's button, and the skin's name, which the chooser shows on the profile alone.
    contact, appearance = 'id="contact-btn"' in text, 'class="skin-name"' in text
    return f"200:{_yn(contact, appearance, page.context['has_verified_email'])}"


def needs_confirmation(site, v):
    return _yn(needs_email_confirmation(v.user))


def user_admin_privileges(site, v):
    request = RequestFactory().get("/")
    request.user = v.user
    return _yn("is_superuser" not in UserAdmin(User, admin.site).get_readonly_fields(request))


def teams_in_the_admin(site, v):
    return _yn(TeamViewSet.user_has_any_permission(None, v.user, ["view"]))


def api_assistant_on_news(site, v):
    return str(v.post_json("/api/v1/assistant/conversations", {"kind": "news"}).status_code)


@override_settings(ASSISTANT_LLM_API_KEY="sk-test")
class RoleMatrixTests(TestCase):
    people: dict[str, User]

    @classmethod
    def setUpTestData(cls):
        cls.people = {kind: _member(kind, kind) for kind in ("guest", "participant", "organizer", "admin", "owner")}
        root = User.objects.create_superuser("root", "root@example.com", "pw")
        root.api_token = uuid.uuid4()
        root.save(update_fields=["api_token"])
        cls.people["superuser"] = root
        author = _member("author", User.Role.ORGANIZER)

        country = Location.add_root(name_ru="Testland", name_kk="Testland", name_en="Testland")
        region = country.add_child(name_ru="Test Region", name_en="Test Region")
        cls.city = region.add_child(name_ru="Testville", name_en="Testville", lat=43.24, lng=76.89)
        cls.catch_all = cls.city.add_child(name_ru="Other location", name_en="Other location", is_hidden=True)
        cls.venue = cls.city.add_child(name_ru="Shop", name_en="Shop", lat=43.2389, lng=76.9453)

        start = timezone.localdate() + datetime.timedelta(days=10)
        event = {"date_start": start, "location": cls.venue, "submitted_by": author}
        cls.public = Competition.objects.create(title_ru="Public", status=Competition.Status.APPROVED, **event)
        cls.pending = Competition.objects.create(
            title_ru="Pending", status=Competition.Status.PENDING_APPROVAL, **event
        )
        cls.hidden = Competition.objects.create(
            title_ru="Hidden", status=Competition.Status.APPROVED, is_hidden=True, **event
        )
        CompetitionReport.objects.create(competition=cls.public, reported_by=author, reason="Wrong date")

        cls.news = NewsArticle.objects.create(title_ru="News", body_ru="<p>Text</p>")
        cls.hidden_news = NewsArticle.objects.create(title_ru="Hidden news", body_ru="<p>Text</p>", is_hidden=True)
        page = NewsPage(title="Probe news", slug="probe-news")
        NewsIndexPage.objects.live().get(locale__language_code="en").add_child(instance=page)
        page.save_revision().publish()
        cls.news_page = NewsPage.objects.get(pk=page.pk)

        cls.knowledge = KnowledgeIndexPage.objects.live().get(locale__language_code="en")
        cls.article = KnowledgeArticle.objects.create(title="Probe", slug="probe", locale="en", body="<p>Text</p>")
        cls.draft = DraftSubmission.objects.create(
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
            title="The author's draft",
            body="<p>Text</p>",
            locale="en",
            author=author,
        )
        cls.places_map = LocationsMapPage.objects.live().get(locale__language_code="en")

    def _check(self, probes: dict, table: dict) -> None:
        """Ask every probe as every kind of visitor -- pages by session, the API by token -- and compare."""
        answers: dict[str, list[str]] = {name: [] for name in probes}
        for kind in KINDS:
            person = self.people.get(kind)
            visitor = Visitor(person or AnonymousUser(), Client(), Client(), {})
            if person is not None:
                visitor.browser.force_login(person)
                visitor.headers = {"HTTP_AUTHORIZATION": f"Bearer {person.api_token}"}
            with translation.override("en"):
                for name, probe in probes.items():
                    answers[name].append(probe(self, visitor))
        got = {name: " ".join(row) for name, row in answers.items()}
        expected = {name: " ".join(row.split()) for name, row in table.items()}
        self.assertEqual(got, expected)

    def test_events(self):
        self._check(
            {
                "submit page": submit_page,
                "submit page offers": submit_page_offers,
                "moderation page": moderation_page,
                "another's pending event": pending_event,
                "public event offers": public_event_offers,
                "list: moderation link": list_moderation_link,
                "edit another's event": edit_others_event,
                "edit own event: organizer's": edit_own_event,
                "event visibility": event_visibility,
                "moderation banner": moderation_banner,
            },
            EVENTS,
        )

    def test_events_api(self):
        self._check(
            {
                "create": api_create,
                "own event: top": api_own_event("is_top"),
                "own event: hidden": api_own_event("is_hidden"),
                "another's pending event": api_pending_event,
            },
            EVENTS_API,
        )

    def test_news_and_knowledge(self):
        self._check(
            {
                "news list: add": news_list_add,
                "news create page": news_create_page,
                "hidden news item": hidden_news,
                "news item: comment": news_comment,
                "news page offers": news_page_offers,
                "API hidden news": api_hidden_news,
                "knowledge index offers": knowledge_index_offers,
                "knowledge article: comment": knowledge_comment,
                "API new draft": api_new_draft,
                "API drafts": api_drafts,
            },
            NEWS_AND_KNOWLEDGE,
        )

    def test_places_home_accounts(self):
        self._check(
            {
                "places map offers": places_map_offers,
                "add a place page": add_place_page,
                "API new venue": api_new_venue,
                "API places": api_places,
                "new album page": new_album_page,
                "home edit page": home_edit_page,
                "home page: edit link": home_edit_link,
                "API new home card": api_new_home_card,
                "profile": profile,
                "needs email confirmation": needs_confirmation,
                "user admin: privileges": user_admin_privileges,
                "teams in the admin": teams_in_the_admin,
                "API assistant on news": api_assistant_on_news,
            },
            PLACES_HOME_ACCOUNTS,
        )
