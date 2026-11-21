"""A member's profile is a link of the menu itself, in every skin.

The account menu -- behind the member's address, or an icon on a narrower desktop -- holds the
profile too, but on a phone it sits at the bottom of the folded menu and reads as an address rather
than a way in, and members missed everything the profile holds. The folded menu now carries it, right
before Search.
"""

import re

import pytest
from django.urls import reverse
from django.utils import translation
from django.utils.translation import pgettext

from accounts.models import User
from cycling_site import skins
from tests.test_profile_name import PAGE

LANGUAGES = ("ru", "kk", "en")


def _menu(html: str) -> str:
    """The list of the site's sections: the menu's links, without the account menu."""
    menu = re.search(r'<ul class="navbar-nav[^"]*">(.*?)</ul>', html, re.S)
    assert menu, "the page has no menu"
    return menu.group(1)


def _link(name: str, language: str) -> str:
    with translation.override(language):
        return f'href="{reverse(name)}"'


def _profile_link(language: str) -> str:
    return _link("account_profile", language)


@pytest.mark.django_db
@pytest.mark.parametrize("skin", sorted(skins.registry()))
@pytest.mark.parametrize("language", LANGUAGES)
def test_a_member_s_menu_links_their_profile_under_its_name(client, skin, language):
    member = User.objects.create_user(username="m", email="m@example.com", password="pw", theme=skin)
    client.force_login(member)
    menu = _menu(client.get(f"/{language}/news/").content.decode())
    with translation.override(language):
        name = pgettext(*PAGE)
    link = re.search(rf'<a class="nav-link" {_profile_link(language)}>(.*?)</a>', menu, re.S)
    assert link, f"{skin}: the menu has no link to the profile"
    assert re.sub(r"<[^>]+>", "", link.group(1)).strip() == name
    # Right before Search, which stays the menu's last link
    assert re.findall(r'<a class="nav-link" (href="[^"]*")', menu)[-2:] == [
        _profile_link(language),
        _link("search", language),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("skin", sorted(skins.registry()))
def test_a_guest_s_menu_has_no_profile_to_open(client, skin):
    client.cookies[skins.COOKIE] = skin
    assert _profile_link("ru") not in _menu(client.get("/ru/news/").content.decode())
