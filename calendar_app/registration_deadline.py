"""Business-timezone helpers for the competition registration deadline."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

# The site serves Kazakhstan cycling events; the deadline an organizer types into the
# datetime-local control is wall-clock time in this zone.
BUSINESS_TZ = ZoneInfo("Asia/Almaty")


def date_only_to_end_of_day(dt: datetime.datetime) -> datetime.datetime:
    """Map a legacy date-only deadline (stored as midnight) to end-of-day in the business tz.

    The old ``DateField`` kept registration open for the whole deadline day; a straight
    conversion to ``DateTimeField`` at midnight would instead close it at the day's start, so
    shift the value to 23:59:59 of the same local calendar day.
    """
    local_date = dt.astimezone(BUSINESS_TZ).date()
    return datetime.datetime.combine(local_date, datetime.time(23, 59, 59), tzinfo=BUSINESS_TZ)
