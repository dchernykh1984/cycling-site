"""``{% load roles %}``: the role rules of ``accounts.roles`` in a template.

``user|at_least:"MODERATE_EVENTS"`` asks a rule by its name, ``user|role_at_least:"participant"`` a role
by its value; a name that is neither fails the page, so that a typo cannot hide a button for good.
"""

from django import template

from accounts import roles

register = template.Library()


def _role(name: str) -> str:
    if name in roles.Role.values:
        return name
    rule = getattr(roles, name, None)
    if not isinstance(rule, roles.Role):
        raise template.TemplateSyntaxError(f"{name!r} is neither a role nor a rule of accounts.roles")
    return rule


@register.filter
def at_least(user, name: str) -> bool:
    return roles.at_least(user, _role(name))


@register.filter
def role_at_least(user, name: str) -> bool:
    return roles.role_at_least(user, _role(name))
