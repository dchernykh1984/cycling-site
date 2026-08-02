"""Settings for a Telegram-agent run: shared site/LLM credentials plus the optional Telegram ones."""

import pytest

from agent.config import ConfigError
from telegram_agent.config import as_agent_config, from_env, telegram_credentials_missing

_BASE = {
    "SITE_BASE_URL": "https://example.kz/",
    "AGENT_API_TOKEN": "token",
    "LLM_API_KEY": "key",
    "LLM_BASE_URL": "https://llm.example/",
}
_TELEGRAM = {
    "TELEGRAM_API_ID": "12345",
    "TELEGRAM_API_HASH": "abcdef",
    "TELEGRAM_SESSION": "1Aa...",
}


def test_the_defaults_are_the_documented_ones():
    """25 hours: the run is nightly, so a day plus an hour of overlap for a cron that fires late."""
    config = from_env({**_BASE, **_TELEGRAM})
    assert (config.max_events, config.max_per_channel) == (10, 5)
    assert (config.recent_hours, config.max_posts) == (25, 1000)
    assert config.dry_run is False
    assert config.telegram_api_id == 12345


def test_missing_site_credentials_are_an_error_naming_them_all():
    with pytest.raises(ConfigError) as caught:
        from_env({"SITE_BASE_URL": "https://example.kz/"})
    assert "AGENT_API_TOKEN" in str(caught.value)
    assert "LLM_API_KEY" in str(caught.value)


def test_missing_telegram_credentials_are_not_an_error_but_are_named():
    """Before the service account exists these are absent by design -- a skip, not a failure."""
    config = from_env(_BASE)
    assert config.telegram_session == ""
    assert telegram_credentials_missing(_BASE) == ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION"]
    assert telegram_credentials_missing({**_BASE, **_TELEGRAM}) == []


def test_the_limits_read_from_the_environment():
    """A first run digs ten days out of the channels: 250 hours, with the caps raised to match."""
    env = {
        **_BASE,
        **_TELEGRAM,
        "TELEGRAM_MAX_EVENTS": "3",
        "TELEGRAM_MAX_PER_CHANNEL": "7",
        "TELEGRAM_MAX_POSTS": "500",
        "TELEGRAM_RECENT_HOURS": "250",
    }
    config = from_env(env)
    assert (config.max_events, config.max_per_channel) == (3, 7)
    assert (config.max_posts, config.recent_hours) == (500, 250)


def test_the_per_channel_budget_reaches_the_shared_pipeline():
    """It caps what one talkative channel may contribute -- as a setting, not a constant."""
    agent_config = as_agent_config(from_env({**_BASE, **_TELEGRAM, "TELEGRAM_MAX_PER_CHANNEL": "2"}))
    assert agent_config.max_per_source == 2


def test_a_limit_that_is_not_a_number_names_itself_in_the_error():
    with pytest.raises(ConfigError, match="TELEGRAM_MAX_EVENTS"):
        from_env({**_BASE, **_TELEGRAM, "TELEGRAM_MAX_EVENTS": "many"})


def test_dry_run_reads_the_usual_spellings():
    assert from_env({**_BASE, **_TELEGRAM, "TELEGRAM_DRY_RUN": "true"}).dry_run is True
    assert from_env({**_BASE, **_TELEGRAM, "TELEGRAM_DRY_RUN": "0"}).dry_run is False


def test_the_agent_config_carries_the_llm_settings_for_the_shared_adapter():
    agent_config = as_agent_config(from_env({**_BASE, **_TELEGRAM}))
    assert agent_config.llm_base_url == "https://llm.example"
    assert agent_config.llm_model == "deepseek-chat"
