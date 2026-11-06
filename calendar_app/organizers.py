"""The organizers the calendar can be narrowed to (issue #336): the members who posted its public events --
the same person the organizers' ratings rate -- named last name first. The account the site's agents post
through is nobody's to choose: what it posts was found, not organized."""

from accounts.models import User
from calendar_app.visibility import public_events


def name(person) -> str:
    """A person as the filter names them: last name, then first name."""
    return f"{person.last_name} {person.first_name}".strip() or person.public_display_name


def choices() -> list[dict]:
    """Everybody with a public event, by name: what the filter offers, as {"pk", "name"}."""
    people = User.objects.filter(pk__in=public_events().values("submitted_by"), is_service_account=False)
    rows = [{"pk": person.pk, "name": name(person)} for person in people]
    return sorted(rows, key=lambda row: (row["name"].casefold(), row["pk"]))
