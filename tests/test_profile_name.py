"""The profile goes by one name wherever the site sends a member to it.

Russian hints called it the member's cabinet while the menu and the page's heading said "profile",
and the coach's guide had to explain that the two were one page. Russian and Kazakh now call the page
itself the member's cabinet, and every hint that sends a member there names it as the menu does.
"""

import pytest
from django.utils import translation
from django.utils.translation import gettext

# The hints and buttons that send a member to the page; those about the profile's data ("Edit
# profile", "Complete your profile to register") speak of the data, not of the page, and keep it.
SENT_THERE = [
    "To your profile",
    "Confirm your email address: until then you cannot enter races, add events or comment. Look for the "
    "letter in your inbox, or send it again from your profile.",
    "Choose your sports, event types and places in your profile or straight from the calendar filter, and "
    "the calendar, list and map will open with them.",
    "Add your name, gender and date of birth to your profile: race entries will be filled in for you.",
    "Stop this reminder for good? You can still change it in your profile at any time.",
    "Your profile has no Strava link. Add it in your profile so it fills in here automatically.",
    "Your request waits until %(name)s accepts it. You can take it back in your profile at any time.",
    "The start list gives you no bib at this event. Name yours, and its photos will be here and in your "
    "profile; only a bib from the start list lets you mark them.",
    "A bib for a person without an account you added: their photos will be here and in your profile.",
    "Connect Strava in your profile first",
    "Connect intervals.icu in your profile first",
    "Connect the service in your profile first",
]


@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_a_hint_that_sends_a_member_to_the_profile_names_it_as_the_menu_does(language):
    with translation.override(language):
        name = gettext("Profile").split()[-1].lower()
        for hint in SENT_THERE:
            text = gettext(hint)
            assert text != hint or language == "en", f"no {language} translation: {hint}"
            assert name in text.lower(), f"{language}: {text}"
