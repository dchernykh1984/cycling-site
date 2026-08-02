"""Settings for one Telegram-agent run, read from the environment (no I/O, unit-tested).

Its own settings rather than the web agent's, for the same reason the Instagram agent has its own:
different schedule, different budget. The site and LLM credentials are shared; on top of them this
agent needs a Telegram identity -- the api_id/api_hash pair issued at my.telegram.org and the
exported session string of the service account that joined the channels.

The Telegram credentials are deliberately optional at the run level: without them there is nothing
this agent can read, so it says so and stops cleanly instead of failing a scheduled run red every
night before the account is set up.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import ConfigError, _flag

# A private club channel carries a couple of announcements a week; a run proposing more than this
# is reading something wrong, and the cap keeps that out of the moderation queue in bulk.
_DEFAULT_MAX_EVENTS = 10
# What one talkative channel may contribute, so a lively group chat cannot spend the whole budget.
_DEFAULT_MAX_PER_CHANNEL = 5
# How far back a run reads, in hours. The run is nightly, so a day plus an hour of overlap: the
# overlap covers a cron that fired late, and costs nothing, because an announcement seen twice is
# dropped by the dedup that already knows it. Hours rather than days because this has to line up
# with how often the run happens -- measured on these channels, the newest 50 messages of a busy
# group do not even reach back a full day, while 50 of a quiet channel reach back two years.
_DEFAULT_RECENT_HOURS = 25
# A safety net, not a budget: the run reads by time, and this only stops one runaway chat from
# swallowing a night. When it bites, the run says so -- a silent truncation would read like "the
# channel had nothing to say".
_DEFAULT_MAX_POSTS = 1000


@dataclass
class Config:
    site_base_url: str
    api_token: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session: str
    max_events: int
    max_per_channel: int
    recent_hours: int
    max_posts: int
    dry_run: bool


def telegram_credentials_missing(env: dict[str, str]) -> list[str]:
    """The Telegram secrets a run cannot read without; empty when the account is fully set up."""
    names = ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION")
    return [name for name in names if not env.get(name)]


def from_env(env: dict[str, str]) -> Config:
    """Build a Config from an env mapping; raise ConfigError listing anything required but missing.

    The Telegram secrets are checked separately with :func:`telegram_credentials_missing`, so the
    caller can tell "the site is misconfigured" (an error) from "the account is not set up yet"
    (a clean, reported skip).
    """
    required = ("SITE_BASE_URL", "AGENT_API_TOKEN", "LLM_API_KEY", "LLM_BASE_URL")
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")
    return Config(
        site_base_url=env["SITE_BASE_URL"].rstrip("/"),
        api_token=env["AGENT_API_TOKEN"],
        llm_api_key=env["LLM_API_KEY"],
        llm_base_url=env["LLM_BASE_URL"].rstrip("/"),
        llm_model=env.get("LLM_MODEL") or "deepseek-chat",
        telegram_api_id=_whole_number(env.get("TELEGRAM_API_ID"), 0, "TELEGRAM_API_ID"),
        telegram_api_hash=env.get("TELEGRAM_API_HASH") or "",
        telegram_session=env.get("TELEGRAM_SESSION") or "",
        max_events=_whole_number(env.get("TELEGRAM_MAX_EVENTS"), _DEFAULT_MAX_EVENTS, "TELEGRAM_MAX_EVENTS"),
        max_per_channel=_whole_number(
            env.get("TELEGRAM_MAX_PER_CHANNEL"), _DEFAULT_MAX_PER_CHANNEL, "TELEGRAM_MAX_PER_CHANNEL"
        ),
        recent_hours=_whole_number(env.get("TELEGRAM_RECENT_HOURS"), _DEFAULT_RECENT_HOURS, "TELEGRAM_RECENT_HOURS"),
        max_posts=_whole_number(env.get("TELEGRAM_MAX_POSTS"), _DEFAULT_MAX_POSTS, "TELEGRAM_MAX_POSTS"),
        dry_run=_flag(env.get("TELEGRAM_DRY_RUN")),
    )


def _whole_number(value: str | None, default: int, name: str) -> int:
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    return max(number, 0)


def as_agent_config(config: Config):
    """The same settings in the shape agent.llm.chat expects, so all agents share one API adapter."""
    from agent.config import Config as AgentConfig

    return AgentConfig(
        site_base_url=config.site_base_url,
        api_token=config.api_token,
        llm_api_key=config.llm_api_key,
        llm_base_url=config.llm_base_url,
        llm_model=config.llm_model,
        max_events=config.max_events,
        max_per_source=config.max_per_channel,
        dry_run=config.dry_run,
    )
