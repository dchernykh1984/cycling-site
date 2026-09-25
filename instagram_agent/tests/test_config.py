"""Settings: its own limits, the same credentials as the web agent."""

import pytest

from agent.config import ConfigError
from instagram_agent.config import DEFAULT_GRAPH_VERSION, as_agent_config, from_env

_BASE = {
    "SITE_BASE_URL": "https://s/",
    "AGENT_API_TOKEN": "t",
    "LLM_API_KEY": "k",
    "LLM_BASE_URL": "https://llm/",
}


def test_defaults_hold_a_nightly_run_to_a_reviewable_size():
    config = from_env(dict(_BASE))
    assert config.max_events == 10
    assert config.max_posts == 10
    assert config.recent_days == 21
    assert config.dry_run is False
    assert config.site_base_url == "https://s"


def test_every_limit_can_be_raised_for_a_one_off_run():
    config = from_env(
        {
            **_BASE,
            "INSTAGRAM_MAX_EVENTS": "100",
            "INSTAGRAM_MAX_POSTS": "50",
            "INSTAGRAM_RECENT_DAYS": "365",
            "INSTAGRAM_DRY_RUN": "true",
        }
    )
    assert (config.max_events, config.max_posts, config.recent_days) == (100, 50, 365)
    assert config.dry_run is True


def test_a_missing_credential_is_named():
    with pytest.raises(ConfigError, match="AGENT_API_TOKEN"):
        from_env({**_BASE, "AGENT_API_TOKEN": ""})


def test_a_limit_that_is_not_a_number_is_refused_rather_than_ignored():
    with pytest.raises(ConfigError, match="INSTAGRAM_MAX_EVENTS"):
        from_env({**_BASE, "INSTAGRAM_MAX_EVENTS": "ten"})


def test_the_shared_api_adapter_gets_the_same_model_and_key():
    config = from_env({**_BASE, "LLM_MODEL": "deepseek-v4-flash"})
    shared = as_agent_config(config)
    assert shared.llm_model == "deepseek-v4-flash"
    assert shared.llm_api_key == "k"


def test_a_run_can_be_pointed_at_one_account():
    """Each account gets a job of its own, so a refused address costs that account and no other."""
    assert from_env({**_BASE, "INSTAGRAM_ACCOUNT": "ubtalmaty"}).only_account == "ubtalmaty"
    assert from_env({**_BASE, "INSTAGRAM_ACCOUNT": " @UBTAlmaty "}).only_account == "UBTAlmaty"
    assert from_env(dict(_BASE)).only_account == "", "no name means every enabled account"


def test_the_graph_credentials_are_read_from_the_environment():
    """Instagram closed the logged-out endpoint; without these a run cannot read anything."""
    config = from_env(
        {
            **_BASE,
            "IG_GRAPH_USER_ID": " 17841400000000000 ",
            "IG_GRAPH_TOKEN": " EAAG-token ",
        }
    )
    assert config.graph_user_id == "17841400000000000"
    assert config.graph_token == "EAAG-token"


def test_the_graph_version_is_pinned_unless_it_is_overridden():
    """Meta changes field shapes between versions, so a run keeps reading the same one."""
    assert from_env(dict(_BASE)).graph_version == DEFAULT_GRAPH_VERSION
    assert from_env({**_BASE, "IG_GRAPH_VERSION": "v23.0"}).graph_version == "v23.0"


def test_missing_graph_credentials_are_empty_rather_than_fatal():
    """A local dry run still builds its config; the reader is what reports the missing token."""
    config = from_env(dict(_BASE))
    assert config.graph_user_id == ""
    assert config.graph_token == ""
