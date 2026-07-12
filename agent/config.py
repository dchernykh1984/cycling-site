"""Runtime configuration, read from environment variables (passed in for testability)."""

from __future__ import annotations

from dataclasses import dataclass


class ConfigError(RuntimeError):
    """A required setting is missing."""


@dataclass
class Config:
    site_base_url: str
    api_token: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    max_events: int
    dry_run: bool


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def from_env(env: dict[str, str]) -> Config:
    """Build a Config from an env mapping; raise ConfigError listing anything required but missing."""
    required = ("SITE_BASE_URL", "AGENT_API_TOKEN", "LLM_API_KEY", "LLM_BASE_URL")
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
    try:
        max_events = int(env.get("MAX_EVENTS_PER_RUN") or "10")
    except ValueError as exc:
        raise ConfigError("MAX_EVENTS_PER_RUN must be an integer") from exc
    return Config(
        site_base_url=env["SITE_BASE_URL"].rstrip("/"),
        api_token=env["AGENT_API_TOKEN"],
        llm_api_key=env["LLM_API_KEY"],
        llm_base_url=env["LLM_BASE_URL"].rstrip("/"),
        llm_model=env.get("LLM_MODEL") or "deepseek-chat",
        max_events=max(max_events, 0),
        dry_run=_flag(env.get("AGENT_DRY_RUN")),
    )
