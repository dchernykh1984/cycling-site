"""Which robot a request came from, by what its User-Agent says (issue #184).

The table is data, not logic: a robot that turns up under "other" is one more line here. The first
name found wins, so a specific name stands before a general one ("Claude-User" before "ClaudeBot").
A User-Agent can lie; for counting that is good enough. Every marker of BOT_USER_AGENT_MARKERS (the
settings: readers the calendar shows unfiltered) is a robot here too, which a test holds.
"""

import re

#: Kinds of robots, in the order they are told apart, each with the names that mark it.
KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Our own scripts: the events agents, the calendar's curation.
    ("own", ("UniversalBicycleTeam",)),
    # An AI assistant opening the page for a person who asked it something just now.
    ("assistant", ("ChatGPT-User", "Claude-User", "Perplexity-User", "MistralAI-User", "DuckAssistBot")),
    # AI search: reading pages for the answers an assistant gives people later.
    ("ai_search", ("OAI-SearchBot", "Claude-SearchBot", "PerplexityBot", "YouBot")),
    # Collecting pages to train AI models.
    (
        "ai_training",
        ("GPTBot", "ClaudeBot", "anthropic-ai", "CCBot", "Bytespider", "Amazonbot", "meta-externalagent", "cohere-ai"),
    ),
    # A messenger or a social network drawing the preview of a link somebody pasted.
    (
        "preview",
        (
            "TelegramBot",
            "WhatsApp",
            "facebookexternalhit",
            "Twitterbot",
            "Slackbot",
            "Discordbot",
            "LinkedInBot",
            "vkShare",
            "Viber",
            "SkypeUriPreview",
            "Embedly",
        ),
    ),
    # Search engines.
    (
        "search",
        (
            "Googlebot",
            "InspectionTool",
            "bingbot",
            "BingPreview",
            "YandexBot",
            "YandexMobileBot",
            "Applebot",
            "Amzn-SearchBot",
            "DuckDuckBot",
            "Baiduspider",
            "PetalBot",
            "SeznamBot",
            "Mail.RU_Bot",
        ),
    ),
    # Services that study sites for their customers' marketing.
    ("seo", ("SemrushBot", "AhrefsBot", "MJ12bot", "DotBot", "DataForSeoBot", "Barkrowler", "serpstatbot", "BLEXBot")),
    # Uptime checks, domain watchers and plain HTTP libraries.
    (
        "monitor",
        (
            "UptimeRobot",
            "Pingdom",
            "StatusCake",
            "fresh-domain-watch",
            "curl/",
            "Wget/",
            "python-requests",
            "python-httpx",
            "Go-http-client",
            "HeadlessChrome",
            "Lighthouse",
        ),
    ),
)

#: The kind of a robot found by none of the names above.
OTHER = "other"

#: Words that give away a robot whose name is not in the table.
_GIVEAWAYS = ("bot", "crawl", "spider", "slurp", "fetch", "scan", "monitor", "headless")
#: The name a robot gives itself: "SomeBot" in "Mozilla/5.0 (compatible; SomeBot/1.0; +https://...)".
_COMPATIBLE = re.compile(r"compatible;\s*([^;/()]+)", re.IGNORECASE)
#: Else the word that gave it away: "SomeCrawler" in "... Safari/537.36 SomeCrawler/2.1".
_NAMED = re.compile(r"[\w.\-]*(?:" + "|".join(_GIVEAWAYS) + r")[\w.\-]*", re.IGNORECASE)


def robot(user_agent: str) -> tuple[str, str] | None:
    """``(kind, name)`` of the robot this User-Agent belongs to, or None for a browser a person may use.

    A browser is only a candidate: whether a person is behind it is for the page's own script to show.
    """
    lowered = user_agent.lower()
    for kind, names in KINDS:
        for name in names:
            if name.lower() in lowered:
                return kind, name
    if "mozilla/" not in lowered or any(word in lowered for word in _GIVEAWAYS):
        return OTHER, _name(user_agent)
    return None


def _name(user_agent: str) -> str:
    """The name a robot gives itself, else the word that gave it away -- not "bots" from the address of
    its page -- else its User-Agent's first word ("Java/17" gives "Java")."""
    found = _COMPATIBLE.search(user_agent) or _NAMED.search(user_agent)
    if found:
        return (found.group(found.lastindex or 0).strip() or "-")[:40]
    words = user_agent.split("/", 1)[0].split()
    return words[0][:40] if words else "-"


def is_phone(user_agent: str) -> bool:
    """A phone, as browsers say it: "Mobi" in the User-Agent, which tablets leave out."""
    return "mobi" in user_agent.lower()
