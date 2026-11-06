"""The questions a review of an event answers (issue #436), in one list with a version.

A review keeps its answers by question key, with the version it answered, so a question can be added --
a score for the timing, for the course -- without touching the reviews written before. The organizer's
rating reads the score of the question that counts; the digest reads them all.
"""

from dataclasses import dataclass

from django.utils.functional import Promise
from django.utils.translation import gettext, gettext_lazy

VERSION = 1
SCORE = "score"
TEXT = "text"
LOWEST, HIGHEST = 1, 5
TEXT_LENGTH = 3000


@dataclass(frozen=True)
class Question:
    key: str
    kind: str  # SCORE or TEXT
    label: str | Promise  # translated when drawn
    required: bool
    counts: bool = False  # its score is what the organizer's rating is made of


QUESTIONS = (
    Question("overall", SCORE, gettext_lazy("Your overall score of the event"), required=True, counts=True),
    Question("comment", TEXT, gettext_lazy("What went well, and what could be better"), required=False),
)
#: The question whose score the organizer's rating is made of
RATED = next(question.key for question in QUESTIONS if question.counts)


def clean(raw) -> tuple[dict, dict]:
    """The answers in ``raw`` -- a form's data or an API request's -- checked: the answers, and the
    mistakes by question key."""
    answers: dict = {}
    errors: dict = {}
    for question in QUESTIONS:
        value = raw.get(question.key)
        if question.kind == SCORE:
            try:
                number = int(value)
            except (TypeError, ValueError):
                number = None
            if number is not None and LOWEST <= number <= HIGHEST:
                answers[question.key] = number
            elif question.required or value not in (None, ""):
                errors[question.key] = gettext("Choose a score from %(lowest)s to %(highest)s.") % {
                    "lowest": LOWEST,
                    "highest": HIGHEST,
                }
        else:
            text = str(value or "").strip()
            if len(text) > TEXT_LENGTH:
                errors[question.key] = gettext("At most %(count)s characters.") % {"count": TEXT_LENGTH}
            elif text:
                answers[question.key] = text
            elif question.required:
                errors[question.key] = gettext("This field is required.")
    return answers, errors
