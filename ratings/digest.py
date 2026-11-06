"""What the participants think of an event (issue #436), for the people who edit it.

The figures -- how many reviews, the average score, how the scores spread -- are counted here; the words
are summed up by the language model the event assistant uses (assistant.llm), which is told the scores
too. Nothing shows before DIGEST_FROM reviews, so that one participant's score and words are never theirs
alone to read. A digest is written by a button and kept; it is written again only once more reviews came.
"""

import json
import random

from django.conf import settings
from django.utils.translation import get_language

from assistant import llm
from ratings import form
from ratings.models import Review, ReviewSummary

#: How many reviews an event needs before its figures and its digest are shown
DIGEST_FROM = 2

_LANGUAGE_NAMES = {"ru": "Russian", "kk": "Kazakh", "en": "English"}
_INSTRUCTIONS = (
    "You sum up the anonymous reviews participants left about a sports event, for its organizers. Each review "
    "has an overall score from 1 (very bad) to 5 (excellent) and may have a comment. Write in {language}. Say "
    "what the participants liked and what they would improve, as short points, weighing how often a thing comes "
    "up and how the scores go; say plainly when the reviews disagree. Never quote a review word for word and "
    "never give a detail -- a name, a bib, a team, a place in the race -- that could tell who wrote it. Answer "
    'with a JSON object: {{"summary": "<the points, one per line, each starting with a dash>"}}.'
)


def figures(competition) -> dict:
    """How many reviews the event has, and -- from DIGEST_FROM of them -- their average and spread."""
    scores = [
        answers[form.RATED]
        for answers in Review.objects.filter(competition=competition).values_list("answers", flat=True)
        if isinstance(answers, dict) and form.RATED in answers
    ]
    count = Review.objects.filter(competition=competition).count()
    shown = count >= DIGEST_FROM and bool(scores)
    return {
        "reviews": count,
        "shown": shown,
        "average": sum(scores) / len(scores) if shown else None,
        "spread": [(value, scores.count(value)) for value in range(form.HIGHEST, form.LOWEST - 1, -1)] if shown else [],
    }


def language_code() -> str:
    code = (get_language() or settings.LANGUAGE_CODE).split("-")[0]
    return code if code in _LANGUAGE_NAMES else settings.LANGUAGE_CODE


def kept(competition) -> ReviewSummary | None:
    """The digest written in the page's language, if there is one."""
    return ReviewSummary.objects.filter(competition=competition, language=language_code()).first()


def write(competition) -> ReviewSummary:
    """A digest of the event's reviews in the page's language, written now and kept -- or the one kept,
    while no review came since it was written: the model is not asked, nor paid, for the same digest
    twice. Raises llm.UnavailableError when the model gives none, and ValueError while there are too
    few reviews."""
    reviews = list(Review.objects.filter(competition=competition).values_list("answers", flat=True))
    if len(reviews) < DIGEST_FROM:
        raise ValueError("too few reviews")
    language = language_code()
    written = ReviewSummary.objects.filter(competition=competition, language=language).first()
    if written is not None and written.reviews >= len(reviews):
        return written
    random.shuffle(reviews)  # the order they came in is nobody's business, the model's included
    lines = [
        {"score": answers.get(form.RATED), "comment": answers.get("comment", "")}
        for answers in reviews
        if isinstance(answers, dict)
    ]
    answer = llm.complete(
        [
            {"role": "system", "content": _INSTRUCTIONS.format(language=_LANGUAGE_NAMES[language])},
            {"role": "user", "content": json.dumps({"reviews": lines}, ensure_ascii=False)},
        ]
    )
    text = str(answer.get("summary") or "").strip()
    if not text:
        raise llm.UnavailableError(llm.UnavailableError.BAD_ANSWER)
    summary, _created = ReviewSummary.objects.update_or_create(
        competition=competition, language=language, defaults={"reviews": len(reviews), "text": text}
    )
    return summary
