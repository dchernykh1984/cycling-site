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
