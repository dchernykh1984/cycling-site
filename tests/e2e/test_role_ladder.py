"""The profile's role card: each role's name stands apart from the line on what it may do."""

import pytest
from playwright.sync_api import Page, expect

from accounts.models import User
from tests.e2e.conftest import inject_session

LOOK = "e => { const s = getComputedStyle(e); return {color: s.color, size: parseFloat(s.fontSize)}; }"


@pytest.mark.django_db(transaction=True)
def test_a_roles_name_reads_apart_from_its_line(page: Page, live_server):
    """The name in the page's text colour, the line smaller and in another, muted one: the line is a hint, the
    name the role -- muted alike, they read as one (seen in the dark UBT skin, 2026-11-12)."""
    member = User.objects.create_user(
        username="e2e_roles", email="e2e_roles@test.local", password="testpass123!", role=User.Role.PARTICIPANT
    )
    inject_session(page, live_server, member)
    page.goto(f"{live_server.url}/ru/accounts/profile/")
    rows = page.locator("#role .role-ladder > li")
    expect(rows).to_have_count(len(User.ROLE_HIERARCHY))
    for row in rows.all():
        name = row.locator(".role-name").evaluate(LOOK)
        line = row.locator(".role-about").evaluate(LOOK)
        assert name["color"] != line["color"] and name["size"] > line["size"], (name, line)
