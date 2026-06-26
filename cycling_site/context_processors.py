"""Template context shared across every page.

``moderation_tasks`` powers the site-wide banner that tells a user what is waiting for them
to moderate (events, locations, article/news submissions, competition registrations), with a
count and a link to where each is handled. Each item is gated to whoever can actually act on
it under the existing permission rules, and the whole thing is a no-op (zero queries) for
anonymous users and plain participants, so it stays cheap on the hot path of every request.
"""

from django.db.models import Count, Q
from django.urls import reverse


def moderation_tasks(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    from accounts.models import User
    from calendar_app.models import Competition
    from knowledge.models import DraftSubmission
    from locations.models import Location, LocationProposal

    is_super = bool(getattr(user, "is_superuser", False))
    rank = user.get_role_rank()
    is_organizer_plus = is_super or rank >= User.ROLE_HIERARCHY.index(User.Role.ORGANIZER)
    is_admin_plus = is_super or rank >= User.ROLE_HIERARCHY.index(User.Role.ADMIN)

    tasks: list[dict] = []

    # Events: organizer+ can approve/reject pending competitions on the moderation page.
    if is_organizer_plus:
        events = Competition.objects.filter(status=Competition.Status.PENDING_APPROVAL, is_deleted=False).count()
        if events:
            tasks.append({"kind": "events", "count": events, "url": reverse("calendar_moderate")})

    # Locations and article/news submissions: admin+ only.
    if is_admin_plus:
        locations = Location.objects.filter(
            proposal__status=LocationProposal.Status.PENDING_APPROVAL, is_deleted=False
        ).count()
        if locations:
            tasks.append({"kind": "locations", "count": locations, "url": reverse("calendar_moderate")})

        articles = DraftSubmission.objects.filter(
            status=DraftSubmission.Status.PENDING,
            submission_type=DraftSubmission.SubmissionType.KNOWLEDGE_ARTICLE,
        ).count()
        if articles:
            tasks.append({"kind": "articles", "count": articles, "url": _knowledge_index_url()})

        news = DraftSubmission.objects.filter(
            status=DraftSubmission.Status.PENDING,
            submission_type=DraftSubmission.SubmissionType.NEWS,
        ).count()
        if news:
            tasks.append({"kind": "news", "count": news, "url": reverse("news_index")})

    # Registrations are competition-scoped: only the competition's creator-organizer moderates
    # them, so list one entry per own competition that has registrations awaiting approval/payment.
    if is_organizer_plus:
        pending = Q(registrations__is_rejected=False) & (
            Q(require_approval=True, registrations__is_approved=False)
            | Q(require_payment=True, registrations__is_paid=False)
        )
        own = (
            Competition.objects.filter(submitted_by=user, is_deleted=False)
            .annotate(pending_regs=Count("registrations", filter=pending))
            .filter(pending_regs__gt=0)
            .order_by("date_start")
        )
        for comp in own:
            tasks.append(
                {
                    "kind": "registrations",
                    "count": comp.pending_regs,
                    "competition": comp,
                    "url": reverse("registrations:participant_list", args=[comp.pk]),
                }
            )

    return {"moderation_tasks": tasks}


def _knowledge_index_url() -> str:
    """URL of the knowledge index page (where pending article submissions surface for review)."""
    from knowledge.models import KnowledgeIndexPage

    index = KnowledgeIndexPage.objects.live().first()
    return index.url if index else "/"
