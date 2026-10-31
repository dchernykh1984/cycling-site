"""How ``accounts.roles`` compares roles: the visitor, the superuser, the rules by name in a template --
and that it is the only place that does."""

import os
import re
from pathlib import Path

from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template, TemplateSyntaxError
from django.test import TestCase

from accounts import roles
from accounts.models import User

Role = User.Role
ROOT = Path(__file__).resolve().parent.parent
# A rank; an index into the order of roles; a role compared with one of the roles, by its name in code
# or by its value in a template; a role read by name, the way that dodges the rest.
_ROLES = "GUEST|PARTICIPANT|ORGANIZER|ADMIN|OWNER"
COMPARING = re.compile(
    rf"get_role_rank|ROLE_HIERARCHY\.index"
    rf"|(?:[!=]=|\bin\s*\()\s*(?:\w+\.)*Role\.(?:{_ROLES})\b"
    rf"|role\s*(?:[!=]=|in)\s*\(?\s*['\"](?:{_ROLES.lower()})['\"]"
    rf"|getattr\([^,]+,\s*['\"]role['\"]"
)
# Where a role is defined and compared; where a guest becomes a participant on a confirmed address,
# which is not a right but a change of role.
ALLOWED = {"accounts/models.py", "accounts/roles.py", "accounts/signals.py", "accounts/adapters.py"}
# The tests, migrations and what is not the site's code; a designer's skin is its designers' own.
SKIPPED = {".git", ".venv", "node_modules", "tmp", "tests", "migrations", "skins", "__pycache__", "staticfiles"}


def _member(role: str, superuser: bool = False) -> User:
    person = User(username=f"u-{role}-{superuser}", role=role, is_superuser=superuser)
    person.save()
    return person


class RolesTests(TestCase):
    def test_a_visitor_and_what_is_not_a_member_stand_below_every_role(self):
        for nobody in (AnonymousUser(), object(), None):
            with self.subTest(nobody=repr(nobody)):
                self.assertEqual(roles.rank(nobody), -1)
                self.assertFalse(roles.at_least(nobody, Role.GUEST))

    def test_a_role_holds_itself_and_every_role_below_it(self):
        for held in User.ROLE_HIERARCHY:
            person = _member(held)
            for asked in User.ROLE_HIERARCHY:
                expected = User.ROLE_HIERARCHY.index(held) >= User.ROLE_HIERARCHY.index(asked)
                with self.subTest(held=str(held), asked=str(asked)):
                    self.assertEqual(roles.at_least(person, asked), expected)
                    self.assertEqual(roles.role_at_least(person, asked), expected)

    def test_a_superuser_holds_every_role_but_not_in_the_role_alone(self):
        root = _member(Role.GUEST, superuser=True)
        self.assertTrue(roles.at_least(root, Role.OWNER))
        self.assertFalse(roles.role_at_least(root, Role.PARTICIPANT))

    def test_a_template_names_a_rule_or_a_role_through_roles(self):
        page = Template(
            "{% load roles %}{% if user|at_least:ROLES.MODERATE_EVENTS %}m{% endif %}"
            "{% if user|role_at_least:ROLES.Role.ADMIN %}a{% endif %}"
        )
        for user, expected in (
            (_member(Role.ORGANIZER), "m"),
            (_member(Role.GUEST, superuser=True), "m"),
            (AnonymousUser(), ""),
        ):
            with self.subTest(user=repr(user)):
                self.assertEqual(page.render(Context({"user": user, "ROLES": roles})), expected)

    def test_every_rule_a_template_names_exists(self):
        # Django's {% if %} reads a name that does not resolve as false, so a typo would hide a
        # button without a word: every ROLES.<name> in every template is looked up here instead.
        missing = []
        for folder, subfolders, files in os.walk(ROOT):
            subfolders[:] = [name for name in subfolders if name not in {".git", ".venv", "node_modules", "tmp"}]
            for name in files:
                if not name.endswith(".html"):
                    continue
                path = Path(folder) / name
                for reference in re.findall(r"\bROLES\.([A-Za-z_.]+)", path.read_text(encoding="utf-8")):
                    value = roles
                    for part in reference.split("."):
                        value = getattr(value, part, None)
                    if not isinstance(value, roles.Role):
                        missing.append(f"{path.relative_to(ROOT)}: ROLES.{reference}")
        self.assertEqual(missing, [])

    def test_a_rule_written_as_a_string_fails_the_page(self):
        page = Template('{% load roles %}{% if user|at_least:"MODERATE_EVENTS" %}m{% endif %}')
        with self.assertRaises(TemplateSyntaxError):
            page.render(Context({"user": _member(Role.ADMIN)}))

    def test_every_page_has_roles(self):
        self.assertIs(self.client.get("/en/news/").context["ROLES"], roles)

    def test_no_role_is_compared_outside_accounts_roles(self):
        found = []
        for folder, subfolders, files in os.walk(ROOT):
            subfolders[:] = [name for name in subfolders if name not in SKIPPED]
            for name in files:
                path = Path(folder) / name
                where = path.relative_to(ROOT).as_posix()
                if path.suffix not in (".py", ".html") or where in ALLOWED or name == "tests.py":
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if COMPARING.search(line):
                        found.append(f"{where}:{number}: {line.strip()}")
        self.assertEqual(found, [], "compare roles through accounts.roles")
