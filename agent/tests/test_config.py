import pytest

from agent.config import ConfigError, from_env

_BASE = {
    "SITE_BASE_URL": "https://s/",
    "AGENT_API_TOKEN": "t",
    "LLM_API_KEY": "k",
    "LLM_BASE_URL": "https://llm/",
}


def test_defaults_and_trailing_slash_stripped():
    config = from_env(dict(_BASE))
    assert config.site_base_url == "https://s"
    assert config.llm_base_url == "https://llm"
    assert config.llm_model == "deepseek-chat"
    assert config.max_events == 25
    assert config.dry_run is False


def test_missing_required_raises():
    with pytest.raises(ConfigError):
        from_env({"SITE_BASE_URL": "x"})


def test_flag_model_and_max_events():
    config = from_env({**_BASE, "AGENT_DRY_RUN": "true", "MAX_EVENTS_PER_RUN": "3", "LLM_MODEL": "m"})
    assert config.dry_run is True
    assert config.max_events == 3
    assert config.llm_model == "m"


def test_non_integer_max_events_raises():
    with pytest.raises(ConfigError):
        from_env({**_BASE, "MAX_EVENTS_PER_RUN": "lots"})


def test_per_source_budget_defaults_and_is_configurable():
    assert from_env(dict(_BASE)).max_per_source == 5
    assert from_env({**_BASE, "MAX_EVENTS_PER_SOURCE": "2"}).max_per_source == 2
    assert from_env({**_BASE, "MAX_EVENTS_PER_SOURCE": "0"}).max_per_source == 0  # 0 = no limit


def test_non_integer_per_source_budget_raises():
    with pytest.raises(ConfigError):
        from_env({**_BASE, "MAX_EVENTS_PER_SOURCE": "five"})
