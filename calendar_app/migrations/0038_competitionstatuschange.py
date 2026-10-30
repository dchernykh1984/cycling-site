"""Keep each event's way through review: added, rejected, resubmitted, approved -- who and when (#741).

From now on Competition.save() writes a step whenever an event changes status. For the events already
there, the steps are filled in from what was recorded at the time, and nothing else:

- added: the audit log's creation entry, by the event's author (or whoever the entry names);
- rejected: every row of the rejection history, with its reason; a rejected event whose rejection
  came before that history keeps its reviewer and time in its own fields;
- approved: an approved event's own record of its last approval, where it has one.

A resubmission, or an approval that a later edit undid, left no trace that says which it was -- the
audit log names the fields a save wrote, and approving, rejecting and resubmitting write the same
four -- so those steps of the old events stay unknown rather than guessed.
"""

import datetime

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

# A rejection's history row is written in the same transaction as the event's own fields.
SAME_MOMENT = datetime.timedelta(minutes=1)


def backfill(apps, schema_editor):
    Competition = apps.get_model("calendar_app", "Competition")
    Rejection = apps.get_model("calendar_app", "CompetitionRejection")
    Step = apps.get_model("calendar_app", "CompetitionStatusChange")
    AuditLog = apps.get_model("audit", "AuditLog")

    created = {}
    for entry in AuditLog.objects.filter(object_type="calendar_app.Competition", action="created").order_by(
        "timestamp", "pk"
    ):
        created.setdefault(entry.object_id, entry)
    rejections = {}
    for rejection in Rejection.objects.all():
        rejections.setdefault(rejection.competition_id, []).append(rejection)
    has_steps = set(Step.objects.values_list("competition_id", flat=True))

    steps = []
    for event in Competition.objects.exclude(pk__in=has_steps).only(
        "pk", "status", "submitted_by_id", "approved_by_id", "approved_at", "rejection_reason"
    ):
        own = []
        entry = created.get(str(event.pk))
        if entry is not None:
            own.append(
                Step(
                    competition_id=event.pk,
                    added=True,
                    changed_by_id=event.submitted_by_id or entry.user_id,
                    changed_at=entry.timestamp,
                )
            )
        for rejection in rejections.get(event.pk, []):
            own.append(
                Step(
                    competition_id=event.pk,
                    status="rejected",
                    changed_by_id=rejection.rejected_by_id,
                    changed_at=rejection.rejected_at,
                    reason=rejection.reason,
                )
            )
        if event.approved_at is not None and event.status == "approved":
            own.append(
                Step(
                    competition_id=event.pk,
                    status="approved",
                    changed_by_id=event.approved_by_id,
                    changed_at=event.approved_at,
                )
            )
        if (
            event.approved_at is not None
            and event.status == "rejected"
            and not any(abs(r.rejected_at - event.approved_at) < SAME_MOMENT for r in rejections.get(event.pk, []))
        ):
            own.append(
                Step(
                    competition_id=event.pk,
                    status="rejected",
                    changed_by_id=event.approved_by_id,
                    changed_at=event.approved_at,
                    reason=event.rejection_reason,
                )
            )
        # The added step first when two fall in one moment, as for an admin's own event.
        steps.extend(sorted(own, key=lambda step: (step.changed_at, not step.added)))
    Step.objects.bulk_create(steps, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("calendar_app", "0037_competition_updated_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompetitionStatusChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("added", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("draft", "Draft"),
                            ("pending_approval", "Pending approval"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "previous_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("draft", "Draft"),
                            ("pending_approval", "Pending approval"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        max_length=30,
                    ),
                ),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reason", models.TextField(blank=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_changes",
                        to="calendar_app.competition",
                    ),
                ),
            ],
            options={
                "ordering": ["changed_at", "pk"],
            },
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
