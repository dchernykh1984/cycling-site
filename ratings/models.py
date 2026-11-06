"""Reviews of an event by the participants who took part in it (issue #436), kept apart from who wrote them.

An account keeps one mark for each event it answered -- with a review or with a refusal, which cannot be
told apart -- and no time. A review keeps a random id, its event, the version of the form it answered and
the answers: nothing that names its author or tells when it came. Neither is in the audit log, and no
page shows a review as it was written.
"""

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models


class ReviewMark(models.Model):
    """That an account answered the request to review an event: with a review, or with a refusal."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_marks")
    competition = models.ForeignKey("calendar_app.Competition", on_delete=models.CASCADE, related_name="review_marks")

    class Meta:
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["user", "competition"], name="review_mark_once"),
        ]

    def __str__(self) -> str:
        return f"u{self.user_id} answered c{self.competition_id}"


class Review(models.Model):
    """One participant's review of an event: a random id, so that no order tells when it came."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    competition = models.ForeignKey("calendar_app.Competition", on_delete=models.CASCADE, related_name="reviews")
    # The version of ratings.form the answers follow, and the answers by question key
    form = models.PositiveSmallIntegerField()
    answers = models.JSONField()

    def __str__(self) -> str:
        return f"review of c{self.competition_id}"
