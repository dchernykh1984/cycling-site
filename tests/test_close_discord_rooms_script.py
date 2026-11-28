"""The nightly cron's call that closes the Discord rooms of the virtual races that are over."""

import io
import json

from scripts import close_discord_rooms as script


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_it_asks_the_site_and_says_how_many_rooms_closed(capsys):
    asked = []

    def opener(request, timeout):
        asked.append((request.full_url, request.get_method()))
        return _Answer(json.dumps({"closed": 2}).encode())

    assert script.run("https://site.test/", opener) == 0
    assert asked == [("https://site.test/api/v1/virtual-ride/discord-rooms/close-due", "POST")]
    assert "closed: 2" in capsys.readouterr().out


def test_a_site_that_does_not_answer_is_said_and_fails_the_step_only(capsys):
    def opener(request, timeout):
        raise OSError("down")

    assert script.run("https://site.test", opener) == 1
    assert "did not close" in capsys.readouterr().out
