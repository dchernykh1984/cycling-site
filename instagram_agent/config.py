"""Settings for one Instagram-agent run, read from the environment (no I/O, unit-tested).

Its own settings rather than the web agent's: the two run on different schedules with different
budgets, and a limit meant for a night of calendars is the wrong limit for a handful of club feeds.
The credentials are shared -- it posts to the same site with the same token and talks to the same
model.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import DEFAULT_LLM_MODEL, ConfigError, _flag, _whole_number
from instagram_agent.fetch import DEFAULT_GRAPH_VERSION

# A club feed carries a couple of announcements a week, so a run that proposes more than this is
# reading something wrong -- a cap here keeps that from reaching the moderation queue in bulk.
_DEFAULT_MAX_EVENTS = 10
# How far back a run looks. Anything older has either happened or been proposed on an earlier night.
_DEFAULT_RECENT_DAYS = 21
# How many of an account's newest posts a run reads. A club posts a couple of announcements a week
# and the agent runs nightly, so ten is already generous; it exists to keep a chatty account from
# filling the prompt with a fortnight of memes. Raising it has a ceiling: Instagram's profile reply
# carries only about a dozen posts, and this reader does not page further back on purpose.
_DEFAULT_MAX_POSTS = 10


@dataclass
class Config:
    site_base_url: str
    api_token: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    max_events: int
    recent_days: int
    max_posts: int
    dry_run: bool
    # Meta's Graph API, the only way left to read an account (see instagram_agent/fetch.py). The
    # id is our own professional account; the token is its long-lived access token, which expires
    # about every 60 days and has to be replaced -- a run says so plainly when it has gone stale.
    graph_user_id: str
    graph_token: str
    graph_version: str
    # The one account this run reads. Each account gets a job of its own, so a refused address
    # costs that account and no other; empty means read every enabled account (a local run).
    only_account: str = ""


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
        max_events=_whole_number(env.get("INSTAGRAM_MAX_EVENTS"), _DEFAULT_MAX_EVENTS, "INSTAGRAM_MAX_EVENTS"),
        recent_days=_whole_number(env.get("INSTAGRAM_RECENT_DAYS"), _DEFAULT_RECENT_DAYS, "INSTAGRAM_RECENT_DAYS"),
        max_posts=_whole_number(env.get("INSTAGRAM_MAX_POSTS"), _DEFAULT_MAX_POSTS, "INSTAGRAM_MAX_POSTS"),
        dry_run=_flag(env.get("INSTAGRAM_DRY_RUN")),
        graph_user_id=(env.get("IG_GRAPH_USER_ID") or "").strip(),
        graph_token=(env.get("IG_GRAPH_TOKEN") or "").strip(),
        graph_version=(env.get("IG_GRAPH_VERSION") or "").strip() or DEFAULT_GRAPH_VERSION,
        only_account=(env.get("INSTAGRAM_ACCOUNT") or "").strip().lstrip("@"),
    )
