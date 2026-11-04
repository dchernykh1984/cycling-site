"""The site's own statistics (issue #184): how many times things were seen, summed per day.

Only sums are kept -- never a visit, an address, a cookie or a browser's whole User-Agent -- so a row
cannot lead back to anybody, and a year of them is a few megabytes: they are kept for good.
"""

from typing import ClassVar

from django.db import models

#: How long a tally's key may be: a page's path, a site's name, a robot's name.
KEY_LENGTH = 200


class Tally(models.Model):
    class Dimension(models.TextChoices):
        VIEWS = "views"  # key: an Audience
        VISITS = "visits"  # key: an Audience; a person's view that came from outside the site
        HOUR = "hour"  # key: "00".."23", people's views in that hour of the day
        PAGE = "page"  # key: the path people viewed
        SOURCE = "source"  # key: the site people came from, DIRECT when none
        DEVICE = "device"  # key: a Device, people's visits
        LANGUAGE = "language"  # key: the language of the page, people's views
        BOT = "bot"  # key: "<kind>:<name>" (stats.robots), robots' views
        TEAM = "team"  # key: a member's id, the pages the people who run the site opened

    class Audience(models.TextChoices):
        PEOPLE = "people"
        BOTS = "bots"
        TEAM = "team"

    class Device(models.TextChoices):
        PHONE = "phone"
        COMPUTER = "computer"

    #: The source of a visit that came from no other site: a typed address, a bookmark, an app.
    DIRECT = "direct"

    day = models.DateField()
    dimension = models.CharField(max_length=10, choices=Dimension.choices)
    key = models.CharField(max_length=KEY_LENGTH)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["day", "dimension", "key"], name="stats_tally_unique")
        ]
        indexes: ClassVar[list] = [models.Index(fields=["dimension", "day"], name="stats_tally_dimension_day")]

    def __str__(self) -> str:
        return f"{self.day} {self.dimension} {self.key}: {self.count}"
