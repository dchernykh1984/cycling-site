"""Ask the site to close the Discord rooms of the events that are over (calendar_app/discord.py).

Run each night by the Render Cron Job before the deploy (render.yaml). Its failure is said and the deploy still
runs: a room not closed tonight is closed the next night. Environment: SITE_BASE_URL.
"""

import json
import os
import sys
import urllib.request

USER_AGENT = "UniversalBicycleTeam-Rooms/1.0"


def run(site: str, opener=urllib.request.urlopen) -> int:
    url = f"{site.rstrip('/')}/api/v1/competitions/discord-rooms/close-due"
    request = urllib.request.Request(url, data=b"", method="POST", headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=120) as response:
            closed = json.loads(response.read())["closed"]
    except (OSError, ValueError, KeyError) as error:
        print(f"::warning::The site did not close the Discord rooms: {type(error).__name__}.")
        return 1
    print(f"Discord rooms closed: {closed}.")
    return 0


if __name__ == "__main__":
    sys.exit(run(os.environ["SITE_BASE_URL"]))
