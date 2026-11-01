"""Runtime configuration, read from environment variables (passed in for testability)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# DeepSeek's cheapest model, when LLM_MODEL is unset; the three agents share it so a rename lands once.
DEFAULT_LLM_MODEL = "deepseek-flash"
_DEFAULT_MAX_EVENTS = 25
_DEFAULT_MAX_PER_SOURCE = 5
# Where an unset SITE_TIME_ZONE leaves a run: the runner's own clock, as before the setting existed.
UTC_ZONE = ZoneInfo("UTC")


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
    # Most a single source may contribute to one run. Without it the run's whole budget goes to
    # whichever source has the deepest supply of unseen events -- an endless calendar of foreign
    # races crowds out every organizer whose own races the site has already harvested.
    max_per_source: int
    dry_run: bool
    enrich_details: bool = True  # fetch each accepted event's own page and refine it (2nd pass)
    # The site's zone: "today" is the site's day there, not the runner's UTC one, which at the night
    # runs is still yesterday where the events are.
    time_zone: ZoneInfo = UTC_ZONE


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _whole_number(value: str | None, default: int, name: str) -> int:
    """A count from the environment: the default when unset, never below zero."""
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    return max(number, 0)


def _time_zone(value: str | None) -> ZoneInfo:
    """The zone named by SITE_TIME_ZONE (an IANA name); UTC when unset."""
    if not value:
        return UTC_ZONE
    try:
        return ZoneInfo(value.strip())
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"SITE_TIME_ZONE is not a time zone: {value}") from exc


def today_in(zone: ZoneInfo) -> datetime.date:
    """Today's date in ``zone``."""
    return datetime.datetime.now(zone).date()


def from_env(env: dict[str, str]) -> Config:
    """Build a Config from an env mapping; raise ConfigError listing anything required but missing."""
    required = ("SITE_BASE_URL", "AGENT_API_TOKEN", "LLM_API_KEY", "LLM_BASE_URL")
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
    return Config(
        site_base_url=env["SITE_BASE_URL"].rstrip("/"),
        api_token=env["AGENT_API_TOKEN"],
        llm_api_key=env["LLM_API_KEY"],
        llm_base_url=env["LLM_BASE_URL"].rstrip("/"),
        llm_model=env.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
        max_events=_whole_number(env.get("MAX_EVENTS_PER_RUN"), _DEFAULT_MAX_EVENTS, "MAX_EVENTS_PER_RUN"),
        max_per_source=_whole_number(
            env.get("MAX_EVENTS_PER_SOURCE"), _DEFAULT_MAX_PER_SOURCE, "MAX_EVENTS_PER_SOURCE"
        ),
        dry_run=_flag(env.get("AGENT_DRY_RUN")),
        enrich_details=_flag(env.get("AGENT_ENRICH_DETAILS") or "true"),
        time_zone=_time_zone(env.get("SITE_TIME_ZONE")),
    )
