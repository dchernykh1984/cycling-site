from urllib.error import HTTPError, URLError

import agent.check_model as check
from agent.config import DEFAULT_LLM_MODEL

_ENV = {"LLM_API_KEY": "k", "LLM_BASE_URL": "https://llm.test"}


def _serving(monkeypatch, models=None, error=None):
    def served(base_url, api_key):
        if error is not None:
            raise error
        return set(models)

    monkeypatch.setattr(check, "served_models", served)


def test_the_ids_are_read_from_the_providers_list():
    payload = {"object": "list", "data": [{"id": "deepseek-flash", "object": "model"}, {"id": "deepseek-v4-pro"}]}
    assert check.model_ids(payload) == {"deepseek-flash", "deepseek-v4-pro"}
    assert check.model_ids({"object": "list"}) == set()


def test_the_model_in_the_code_passes_while_it_is_served(monkeypatch, capsys):
    _serving(monkeypatch, {DEFAULT_LLM_MODEL, "another"})
    assert check.main(_ENV) == 0
    assert f"{DEFAULT_LLM_MODEL} is served" in capsys.readouterr().out


def test_a_model_no_longer_served_fails_and_names_what_is(monkeypatch, capsys):
    _serving(monkeypatch, {"some-new-model"})
    assert check.main(_ENV) == 1
    out = capsys.readouterr().out
    assert f"::error::{DEFAULT_LLM_MODEL} is not among" in out
    assert "some-new-model" in out


def test_a_refused_key_fails(monkeypatch, capsys):
    _serving(monkeypatch, error=HTTPError("https://llm.test/models", 401, "Unauthorized", {}, None))
    assert check.main(_ENV) == 1
    assert "HTTP 401" in capsys.readouterr().out


def test_an_unreachable_provider_does_not_hold_the_pull_request(monkeypatch, capsys):
    _serving(monkeypatch, error=URLError("timed out"))
    assert check.main(_ENV) == 0
    assert "::warning::" in capsys.readouterr().out


def test_without_the_secrets_the_check_is_skipped(capsys):
    assert check.main({}) == 0
    assert "::warning::" in capsys.readouterr().out
