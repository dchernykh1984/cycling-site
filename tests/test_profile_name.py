"""The profile goes by one name wherever the site sends a member to it.

Russian hints called it the member's cabinet while the menu and the page's heading said "profile",
and the coach's guide had to explain that the two were one page. Russian and Kazakh now call the page
itself the member's cabinet, and every hint that sends a member there names it as the menu does.
"""

import pytest
from django.utils import translation
from django.utils.translation import gettext, pgettext

# The page's name: a context of its own keeps a package's own "Profile" (Wagtail's admin has one) apart
PAGE = ("a member's own page", "Profile")

# The hints and buttons that send a member to the page, and the privacy policy's lines that tell where a
# member changes what is kept; those about the profile's data ("Edit profile", "Complete your profile to
# register") speak of the data, not of the page, and keep it.
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
    "Fill them in your profile",
    "Open your profile",
    "Add yours and those of the people you added without an account in your profile; ask the members you manage "
    "to complete their own profiles.",
    "Connect the service in your profile first",
    "We keep your data while your account exists. You can edit or clear most of it yourself in your profile "
    "at any time, and you can disconnect a linked Google, GitHub or Strava account from that service's "
    "settings. If you ask us to delete your account, we remove your personal data, including any identifier "
    "and name received from Strava. Published results of past events may be kept for historical accuracy in "
    "the same way they appear in ordinary sport protocols.",
    "<strong>People who manage your registrations and photos.</strong> You may let another member manage your"
    " race registrations and race photos: they send you a link, you allow it on the page it opens, and they "
    "accept your request. That member then sees your last name, first name, date of birth, gender, city and "
    "team, and the Strava link an event's form may ask for, but never your email address; they can register "
    "you for events, change and cancel your registrations, and see and mark your race photos. Either of you "
    "can end this in the profile at any time: from then on that member sees nothing of yours and can do "
    "nothing for you, and the registrations they made stay yours.",
    "<strong>Virtual rides.</strong> When you are signed in, the rides you finish on the virtual ride page "
    "are saved to your profile: the route, time, distance, speed, power, cadence and heart rate -- with the "
    "intervals between its beats when you turn on Write HRV there --, and the track of your position "
    "along the route. The settings you choose on that page -- your height, weight and "
    "maximum heart rate, your bike and trainer, your own plan and the like -- are kept with your profile too, "
    "so that the page shows them on every device you sign in on. While you are on that page, other signed-in "
    "members see your "
    "name, what you are riding and where you are on the route. If you connect Strava for your rides, we keep "
    "the access Strava gives us for this and use it to upload each ride you finish as a virtual ride. If you also "
    "turn on Strava live segments there, the same access reads your starred segments and your own times on them "
    "while you ride, for your page alone: we keep none of it and read nothing else of your Strava activities. You "
    "can disconnect Strava in your profile at any time, and we then revoke that access.",
    "<strong>Strava and intervals.icu.</strong> For each of them your profile shows whether it is connected, "
    "with a box that sends your rides there; you can turn the box off and keep the service connected. If you "
    "connect intervals.icu, you give us your API key from intervals.icu: we check it with intervals.icu and "
    "keep it encrypted. We also keep your athlete identifier and name there, to show which account is "
    "connected. We use the key only from our server: to send the rides you choose to send, and, while you "
    "have the virtual ride open, to read the workouts planned in your intervals.icu calendar for today and "
    "the next seven days, with the steps and the FTP of the one you pick. We keep none of them, and never "
    "show the key again. We do not read your intervals.icu activities. Disconnecting intervals.icu in your "
    "profile deletes the key.",
]


@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_a_hint_that_sends_a_member_to_the_profile_names_it_as_the_menu_does(language):
    with translation.override(language):
        name = pgettext(*PAGE).split()[-1].lower()
        for hint in SENT_THERE:
            text = gettext(hint)
            assert text != hint or language == "en", f"no {language} translation: {hint}"
            assert name in text.lower(), f"{language}: {text}"


@pytest.mark.parametrize("language", ["ru", "kk"])
def test_a_package_s_own_profile_keeps_its_word(language):
    """Wagtail's admin has a "Profile" tab of its own, for an editor's account settings; the member's
    cabinet, its own string, renames none of it (Kazakh falls back to Wagtail's Russian, as before)."""
    with translation.override(language):
        assert gettext("Profile") not in ("Profile", pgettext(*PAGE))
