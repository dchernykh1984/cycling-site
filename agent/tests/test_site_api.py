"""The API client's handling of malformed responses, where a silent default would do damage."""

import pytest

from agent.pipeline import normalize_key
from agent.site_api import SiteApiClient


class _Client(SiteApiClient):
    """A client whose transport is swapped for a canned response."""

    def __init__(self, response):
        super().__init__("https://example.test", "token")
        self._response = response
        self.calls: list[tuple] = []

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return self._response


@pytest.mark.parametrize("response", [None, [], "created", {}, {"id": 0}, {"detail": "error"}])
def test_propose_place_raises_when_the_response_carries_no_id(response):
    """A missing id must stop this proposal, not hand back 0.

    The caller caches the returned id as the parent of the city it proposes next, so a falsy id
    would send every later candidate in the run to a location that does not exist.
    """
    client = _Client(response)
    with pytest.raises(RuntimeError, match="returned no id"):
        client.propose_place(7, "Kobona")


def test_propose_place_returns_the_new_id_and_posts_one_name_in_three_locales():
    client = _Client({"id": 42})
    assert client.propose_place(7, "Kobona") == 42
    _, path, payload = client.calls[0]
    assert path == "/api/v1/locations/"
    assert payload["parent_id"] == 7
    assert payload["name"] == {"ru": "Kobona", "kk": "Kobona", "en": "Kobona"}


class _ListingClient(SiteApiClient):
    """A client whose competition listings are canned per query string."""

    def __init__(self, listings: dict[str, list]):
        super().__init__("https://example.test", "token")
        self._listings = listings
        self.paths: list[str] = []

    def _request(self, method, path, payload=None):
        self.paths.append(path)
        return self._listings.get(path.partition("?")[2], [])


def _competition(title: str, date_start: str, **extra) -> dict:
    return {"title": {"ru": title, "kk": "", "en": ""}, "date_start": date_start, **extra}


def test_known_asks_for_the_deleted_competitions_of_every_status():
    client = _ListingClient({})
    client.known()
    for status in ("approved", "pending_approval", "rejected"):
        assert f"/api/v1/competitions/?status={status}&deleted=true" in client.paths


def test_a_deleted_competition_blocks_the_agent_from_proposing_it_again():
    """Deleting an event says "not this"; without this it comes straight back on the next run."""
    client = _ListingClient({"status=pending_approval&deleted=true": [_competition("Dark Race", "2026-09-26")]})
    known = client.known()
    assert normalize_key("Dark Race", "2026-09-26") in known.existing_keys


def test_a_deleted_rejection_still_carries_its_reason():
    client = _ListingClient(
        {
            "status=rejected&deleted=true": [
                _competition("Dark Race", "2026-09-26", rejection_reason="a duplicate of 343")
            ]
        }
    )
    known = client.known()
    assert [r["reason"] for r in known.rejected] == ["a duplicate of 343"]


def test_known_counts_the_deleted_events_it_folded_in():
    """The run logs this: a blocked event leaves no other trace, so the count is the only proof."""
    client = _ListingClient(
        {
            "status=approved&deleted=true": [_competition("Gone", "2026-09-26")],
            "status=rejected&deleted=true": [_competition("Also gone", "2026-10-04")],
            "status=approved": [_competition("Live", "2026-09-27")],
        }
    )
    known = client.known()
    assert known.deleted_count == 2
    assert len(known.existing) == 2  # the live one and the deleted approved one


def test_live_events_come_before_deleted_ones_in_the_prompt_list():
    client = _ListingClient(
        {
            "status=pending_approval&deleted=true": [_competition("Gone", "2026-09-26")],
            "status=pending_approval": [_competition("Live", "2026-09-27")],
        }
    )
    assert [item["title"] for item in client.known().existing] == ["Live", "Gone"]


def test_a_site_without_the_deleted_parameter_is_not_read_as_a_pile_of_deletions():
    """An older site ignores `deleted` and answers with the live list again.

    Taken at face value that fills the prompt's limited room with every event twice and reports the
    copies as blocked deletions -- a count that reads like the fix works when it is not deployed.
    """
    live = [_competition("Dark Race", "2026-09-26"), _competition("Light Race", "2026-10-04")]
    client = _ListingClient(
        {"status=approved": live, "status=approved&deleted=true": live, "status=rejected": [], "": live}
    )
    known = client.known()

    assert known.deleted_count == 0
    assert [item["title"] for item in known.existing] == ["Dark Race", "Light Race"]


def test_a_deleted_event_that_repeats_a_live_one_is_counted_once():
    same = _competition("Dark Race", "2026-09-26")
    client = _ListingClient({"status=approved": [same], "status=approved&deleted=true": [same]})
    known = client.known()
    assert (known.deleted_count, len(known.existing)) == (0, 1)
