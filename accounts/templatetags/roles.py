"""``{% load roles %}``: the role rules of ``accounts.roles`` in a template.

The rule or the role is a constant the ``role_rules`` context processor hands every page as
``ROLES``: ``user|at_least:ROLES.MODERATE_EVENTS``, ``user|role_at_least:ROLES.Role.PARTICIPANT``.
A value that is no role fails the page. A name that does not exist never reaches a filter inside
``{% if %}``, which Django reads as false, so ``tests/test_roles.py`` looks up every ``ROLES.<name>``
in every template.
"""

from django import template

from accounts import roles

register = template.Library()


def _role(value: str) -> str:
    if value not in roles.Role.values:
        raise template.TemplateSyntaxError(f"{value!r} is no role: name a rule or a role of ROLES")
    return value


@register.filter
def at_least(user, name: str) -> bool:
    return roles.at_least(user, _role(name))


@register.filter
def role_at_least(user, name: str) -> bool:
    return roles.role_at_least(user, _role(name))
