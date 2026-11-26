"""A date typed in as DD.MM.YYYY, with the browser's calendar on a button beside it.

The browser's own date field was hard to use (the maintainer, 2026-11-26, from the coaches): typing into it
worked in some browsers only, or once the right part of it was tapped, and its calendar opened on this month,
decades from a date of birth. Here the date is typed -- the dots come as the digits are typed -- and the button
beside the field opens the browser's calendar on the date typed. A date that cannot be read is named under the
field: by the page before the form goes (js/cycling_site.js) and by the server, in the same words.
"""

import datetime
import re
from typing import ClassVar

from django import forms
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: As a reader types it, and as the browser's calendar and older forms and tests send it.
TYPED_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")
#: Day, month and a four-digit year, apart by a dot, a slash, a dash, a comma or a space: as typed on any keyboard.
_DAY_MONTH_YEAR = re.compile(r"^\s*(\d{1,2})\s*[./,\- ]\s*(\d{1,2})\s*[./,\- ]\s*(\d{4})\s*$")
FORMAT_ERROR = _("Enter the date as DD.MM.YYYY, for example 05.03.2012.")
MASK = _("DD.MM.YYYY")


class TypedDateInput(forms.DateInput):
    """A text field for DD.MM.YYYY and a calendar button; the calendar spans ``earliest`` to today."""

    template_name = "_typed_date.html"
    input_type = "text"

    def __init__(self, attrs=None, earliest=datetime.date(1900, 1, 1)):
        # a numeric keyboard on a phone: the dots are put in by the page, and autofill offers nobody's birthday
        # unless the field asks for the member's own ("bday")
        base = {"class": "form-control", "inputmode": "numeric", "autocomplete": "off", "maxlength": "10"}
        super().__init__({**base, **(attrs or {})}, format="%d.%m.%Y")
        self.earliest = earliest

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        if widget["attrs"].get("aria-invalid") == "true":  # the server refused it: drawn as refused
            widget["attrs"]["class"] = (widget["attrs"].get("class", "") + " is-invalid").strip()
        # the words come from here, not the template: a template's DD.MM.YYYY reads like a model's choice to the checks
        widget.update(
            earliest=self.earliest.isoformat(),
            latest=timezone.localdate().isoformat(),
            mask=MASK,
            format_error=FORMAT_ERROR,
            range_error=_("Enter a date of birth between 1900 and today."),
        )
        return context

    def render(self, name, value, attrs=None, renderer=None):
        # the site's own templates, a skin's copy among them, rather than the form renderer's
        return render_to_string(self.template_name, self.get_context(name, value, attrs))


class TypedDateField(forms.DateField):
    """A date as DD.MM.YYYY (or ISO), its separators as any keyboard types them; refused in words that say how."""

    widget = TypedDateInput
    input_formats = TYPED_FORMATS
    default_error_messages: ClassVar[dict] = {"invalid": FORMAT_ERROR}

    def to_python(self, value):
        if isinstance(value, str) and (parts := _DAY_MONTH_YEAR.match(value)):
            value = ".".join(parts.groups())
        return super().to_python(value)
