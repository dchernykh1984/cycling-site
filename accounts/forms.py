"""The account pages' own questions, apart from the profile's forms (accounts/views.py).

This module imports nothing of allauth: ``ACCOUNT_SIGNUP_FORM_CLASS`` names a class here, and allauth
builds its own signup form on top of it while its forms module is being imported.
"""

from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext


def _privacy_field() -> forms.BooleanField:
    """The question every new member answers once (issue #438). The policy opens in a tab of its own,
    so the form keeps what was typed; built per form, so its words are the page's language."""
    return forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label_suffix="",
        # In one element, so that a label laid out as a row keeps the space before the link
        label=format_html(
            "<span>{}</span>",
            format_html(
                gettext('I agree with the <a href="{}" target="_blank" rel="noopener">privacy policy</a>'),
                reverse("privacy_policy"),
            ),
        ),
    )


class SignupForm(forms.Form):
    """What the sign-up form asks besides the address and the password: asked last, under them."""

    field_order = ("email", "password1", "password2", "privacy")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["privacy"] = _privacy_field()

    def signup(self, request, user) -> None:
        """allauth's hook, called once the new account is saved."""
        user.accept_privacy()


class PrivacyConsentForm(forms.Form):
    """The same question, for an account Google, GitHub or Strava made without the sign-up form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["privacy"] = _privacy_field()
