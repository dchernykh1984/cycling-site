"""The API client's handling of malformed responses, where a silent default would do damage."""

import pytest

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
