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
# A rank, an index into the order of roles, a member's role compared with a value.
COMPARING = re.compile(r"get_role_rank|ROLE_HIERARCHY\.index|user\.role\s*(?:[!=]=|(?:not\s+)?in\b)")
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

    def test_a_template_asks_a_rule_by_name_or_a_role_by_value(self):
        page = Template(
            '{% load roles %}{% if user|at_least:"MODERATE_EVENTS" %}m{% endif %}'
            '{% if user|role_at_least:"admin" %}a{% endif %}'
        )
        self.assertEqual(page.render(Context({"user": _member(Role.ORGANIZER)})), "m")
        self.assertEqual(page.render(Context({"user": _member(Role.GUEST, superuser=True)})), "m")
        self.assertEqual(page.render(Context({"user": AnonymousUser()})), "")

    def test_a_name_that_is_neither_fails_the_page(self):
        page = Template('{% load roles %}{% if user|at_least:"MODERATE_EVENT" %}m{% endif %}')
        with self.assertRaises(TemplateSyntaxError):
            page.render(Context({"user": _member(Role.ADMIN)}))

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
