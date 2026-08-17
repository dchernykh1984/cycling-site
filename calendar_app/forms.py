import json
from typing import ClassVar

from django import forms
from django.db.models import Field
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from accounts.models import User
from cycling_site.forms import LocalizedMaxLengthMixin
from locations.models import Location, competition_location_block_reason
from registrations.models import RegistrationCategory

from .models import (
    MAX_DESCRIPTION_LENGTH,
    Competition,
    CompetitionComment,
    CompetitionMaterial,
    Discipline,
    EventType,
)

_ADMIN_RANK = User.ROLE_HIERARCHY.index(User.Role.ADMIN)

# Registration categories arrive as a JSON blob, so their names never met a form field. The limit
# is read off the column (``max_length`` is typed as optional, hence the narrowing) rather than
# written out, so the form cannot come to disagree with what the database will store.
_category_name_field = RegistrationCategory._meta.get_field("name")
_CATEGORY_NAME_MAX_LENGTH = _category_name_field.max_length if isinstance(_category_name_field, Field) else None

# Taken from the column rather than written out, so the form cannot drift from what the database
# will actually accept. A URLField declared without max_length is varchar(200), and a link past
# that used to reach the INSERT and come back as a 500 instead of a field error -- which is what a
# Google form link with a Facebook click-id (fbclid) does at 294 characters.
_URL_MAX_LENGTH = Competition._meta.get_field("url_route").max_length


def _url_field() -> forms.URLField:
    """A link field bounded by the column behind it; Django renders the maxlength attribute itself."""
    return forms.URLField(
        required=False,
        max_length=_URL_MAX_LENGTH,
        widget=forms.URLInput(attrs={"class": "form-control"}),
    )


class SubmitCompetitionForm(LocalizedMaxLengthMixin, forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        # The submitting user is needed to validate location ownership (issue #111).
        self.user = user
        super().__init__(*args, **kwargs)

    title_ru = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}))
    title_kk = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    title_en = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    # Rich-text descriptions: the shared Quill editor (includes/rich_text_editor.html) writes
    # HTML into these hidden fields per locale; the HTML is sanitized in clean_* below.
    description_ru = forms.CharField(required=False, widget=forms.HiddenInput())
    description_kk = forms.CharField(required=False, widget=forms.HiddenInput())
    description_en = forms.CharField(required=False, widget=forms.HiddenInput())
    # A start can be more than one thing at once -- a race with a kids race inside it, an open
    # mass start that also holds a professional field -- so the types are a set, like disciplines.
    event_types: forms.ModelMultipleChoiceField[EventType] = forms.ModelMultipleChoiceField(
        queryset=EventType.objects.all(),
        required=False,
        label=_("Event type"),
        help_text=_("Choose one or more types - an event can be a race and a kids race at once."),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "5"}),
    )
    # A competition can belong to several disciplines (and thus directions) at once (#multi-discipline).
    disciplines: forms.ModelMultipleChoiceField[Discipline] = forms.ModelMultipleChoiceField(
        queryset=Discipline.objects.select_related("category"),
        required=False,
        label=_("Disciplines"),
        widget=forms.CheckboxSelectMultiple,
    )
    location: forms.ModelChoiceField[Location] = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_deleted=False),
        required=False,
        empty_label="--",
        widget=forms.HiddenInput(),
    )
    # Proposing a new venue: any registered user can suggest a venue under the chosen
    # city (issue #111). new_venue_city carries the selected city; if new_venue_name is
    # filled, the view creates the venue (pending unless the submitter is organizer+).
    new_venue_city: forms.ModelChoiceField[Location] = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_deleted=False),
        required=False,
        widget=forms.HiddenInput(),
    )
    new_venue_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "id": "new-venue-name"}),
    )
    new_venue_lat = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "any", "id": "new-venue-lat"}),
    )
    new_venue_lng = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm", "step": "any", "id": "new-venue-lng"}),
    )
    date_start = forms.DateField(
        label=_("Date start"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
    )
    date_end = forms.DateField(
        required=False,
        label=_("Date end"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
    )
    url_announcement = _url_field()
    file_announcement = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
    url_registration = _url_field()
    url_route = _url_field()
    file_route = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
    url_regulations = _url_field()
    file_regulations = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))
    url_results = _url_field()
    file_results = forms.FileField(required=False, widget=forms.FileInput(attrs={"class": "form-control"}))

    _MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
    _ALLOWED_EXTENSIONS: ClassVar[frozenset[str]] = frozenset(
        {"pdf", "doc", "docx", "xls", "xlsx", "gpx", "kml", "zip", "jpg", "jpeg", "png", "gif", "webp"}
    )

    def _validate_file(self, f):
        if not f:
            return f
        if f.size > self._MAX_FILE_BYTES:
            raise forms.ValidationError(_("File size must not exceed 10 MB."))
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in self._ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(self._ALLOWED_EXTENSIONS))
            raise forms.ValidationError(_("Unsupported file type. Allowed: %(allowed)s.") % {"allowed": allowed})
        return f

    # Descriptions arrive as raw Quill HTML in these hidden fields; sanitization happens
    # centrally in Competition.save() so every write path (form, API, admin, snippet) is
    # covered. The form only bounds their size (inline images are embedded base64).

    def _clean_description_length(self, field):
        value = self.cleaned_data.get(field) or ""
        if len(value) > MAX_DESCRIPTION_LENGTH:
            raise forms.ValidationError(_("Description is too large. Use fewer or smaller inline images."))
        return value

    def clean_description_ru(self):
        return self._clean_description_length("description_ru")

    def clean_description_kk(self):
        return self._clean_description_length("description_kk")

    def clean_description_en(self):
        return self._clean_description_length("description_en")

    def clean_file_announcement(self):
        return self._validate_file(self.cleaned_data.get("file_announcement"))

    def clean_file_route(self):
        return self._validate_file(self.cleaned_data.get("file_route"))

    def clean_file_regulations(self):
        return self._validate_file(self.cleaned_data.get("file_regulations"))

    def clean_file_results(self):
        return self._validate_file(self.cleaned_data.get("file_results"))

    def clean(self):
        cleaned_data = super().clean()
        self._validate_location(cleaned_data)
        date_start = cleaned_data.get("date_start")
        date_end = cleaned_data.get("date_end")
        if date_start and date_end and date_end < date_start:
            raise forms.ValidationError(_("End date cannot be before start date."))
        return cleaned_data

    def _validate_location(self, cleaned_data) -> None:
        """Guard against forged POSTs (issue #111): a new venue must hang off a city, and a
        chosen location must be one this user may use (not someone else's pending proposal)."""
        from locations.models import location_visible_to

        city = cleaned_data.get("new_venue_city")
        new_name = (cleaned_data.get("new_venue_name") or "").strip()
        if city is not None and (city.depth != 3 or not location_visible_to(city, self.user)):
            # Same rule as for `location` below: a city that is someone else's pending proposal is
            # not a city this user may build under, however the POST reached us.
            self.add_error("new_venue_city", _("Please choose a city for the new venue."))
        # If a new venue is being proposed it is used instead of `location`, so skip that check.
        if new_name and city is not None:
            return
        location = cleaned_data.get("location")
        user = self.user
        is_admin = bool(getattr(user, "is_superuser", False)) or (
            getattr(user, "is_authenticated", False) and user.get_role_rank() >= _ADMIN_RANK
        )
        if competition_location_block_reason(location, user, is_admin=is_admin):
            self.add_error("location", _("This location is not available."))


class RegistrationSettingsForm(forms.Form):
    registration_enabled = forms.BooleanField(required=False)
    registration_mode = forms.ChoiceField(
        choices=Competition.RegistrationMode.choices,
        required=False,
        widget=forms.RadioSelect,
    )
    birth_date_mode = forms.ChoiceField(
        choices=Competition.BirthDateMode.choices,
        required=False,
        widget=forms.RadioSelect,
    )
    require_approval = forms.BooleanField(required=False)
    require_payment = forms.BooleanField(required=False)
    allow_multiple_registrations = forms.BooleanField(required=False)
    registration_deadline = forms.DateTimeField(
        required=False,
        # <input type="datetime-local"> submits/expects "YYYY-MM-DDTHH:MM" (no seconds).
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"),
    )
    max_participants = forms.IntegerField(
        required=False, min_value=1, widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    show_unapproved_in_list = forms.BooleanField(required=False)
    show_unpaid_in_list = forms.BooleanField(required=False)
    show_approval_status_col = forms.BooleanField(required=False)
    show_payment_status_col = forms.BooleanField(required=False)
    additional_info_mode = forms.ChoiceField(
        choices=Competition.AdditionalInfoMode.choices,
        required=False,
        initial=Competition.AdditionalInfoMode.FREE,
    )
    show_additional_info_in_list = forms.BooleanField(required=False, initial=True)
    additional_info_required = forms.BooleanField(required=False, initial=False)
    relay_enabled = forms.BooleanField(required=False)
    relay_max_members = forms.IntegerField(
        required=False,
        min_value=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "style": "width:80px;"}),
    )
    categories_json = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_categories_json(self) -> str:
        """Refuse a category name the column cannot hold, before the INSERT does it with a 500.

        The field is a hidden JSON blob the page's JavaScript assembles, so nothing between the
        text box and the database checked how long a name was; one longer than the column turned
        saving the registration settings into a server error.
        """
        raw = self.cleaned_data.get("categories_json", "")
        if not raw:
            return raw
        try:
            categories = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Unparseable input keeps its long-standing meaning of "no categories" (get_categories).
            return raw
        if not isinstance(categories, list):
            return raw
        if _CATEGORY_NAME_MAX_LENGTH is None:  # a column without a limit needs no guard here
            return raw
        for category in categories:
            name = category.get("name", "") if isinstance(category, dict) else ""
            if isinstance(name, str) and len(name) > _CATEGORY_NAME_MAX_LENGTH:
                raise forms.ValidationError(
                    _("Category name is too long: at most %(limit_value)d characters."),
                    params={"limit_value": _CATEGORY_NAME_MAX_LENGTH},
                    code="max_length",
                )
        return raw

    def get_categories(self) -> list[dict]:
        raw = self.cleaned_data.get("categories_json", "")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []


_MATERIAL_NAME = pgettext_lazy("photo or video material", "Name")


class CompetitionMaterialForm(forms.ModelForm):
    """One row of the coverage list: what the link is called, and where it goes.

    Both halves are required, which the model's columns already say; spelling it out here is only
    about the message the editor sees, since a half-filled row is the one mistake this form can make.
    """

    class Meta:
        model = CompetitionMaterial
        fields: ClassVar[list] = ["title", "url"]
        # A material's name is the caption on a button, not a person's -- the plain "Name" already in
        # the catalog is the one on a registration form and translates to a personal name. The
        # context keeps the two apart while leaving the English label short.
        labels: ClassVar[dict] = {"title": _MATERIAL_NAME, "url": _("Link")}
        error_messages: ClassVar[dict] = {
            "title": {"required": _("Give this material a name.")},
            "url": {"required": _("Add a link to this material.")},
        }
        # The rows are a grid with no visible label above each field, so the placeholder is what a
        # sighted editor reads and aria-label is what everyone else gets.
        widgets: ClassVar[dict] = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _MATERIAL_NAME, "aria-label": _MATERIAL_NAME}
            ),
            "url": forms.URLInput(attrs={"class": "form-control", "placeholder": _("Link"), "aria-label": _("Link")}),
        }


class BaseCompetitionMaterialFormSet(forms.BaseInlineFormSet):
    """Adds the one thing the factory cannot: Bootstrap's class on the delete box.

    ``DELETE`` is added by the formset itself, after the form class has had its say, so its widget
    is the plain unstyled checkbox unless it is reached here.
    """

    def add_fields(self, form, index):
        super().add_fields(form, index)
        delete_field = form.fields.get("DELETE")
        if delete_field is not None:
            delete_field.widget.attrs["class"] = "form-check-input"


# ``extra=1`` leaves one blank row waiting on the edit page, so adding the first link needs no
# button press; a row left untouched is dropped rather than validated (Django's empty_permitted).
# Only saved rows offer a delete box -- a row that was just added is removed by emptying it, which
# is what the "x" button in the template does.
CompetitionMaterialFormSet = forms.inlineformset_factory(
    Competition,
    CompetitionMaterial,
    form=CompetitionMaterialForm,
    formset=BaseCompetitionMaterialFormSet,
    extra=1,
    can_delete=True,
    can_delete_extra=False,
)


class AddCompetitionCommentForm(forms.ModelForm):
    body = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": _("Write a comment..."), "class": "form-control w-100"}),
    )

    class Meta:
        model = CompetitionComment
        fields: ClassVar[list] = ["body"]


class RejectCompetitionForm(forms.Form):
    # Required: the reason is shown to the author on their submission's page, so a rejection must
    # always carry an explanation.
    rejection_reason = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control w-100"}),
    )


class ReportCompetitionForm(forms.Form):
    # The reason is optional (issue #233): a confirmed user can flag an event with just a click, but
    # a short note helps the admin see what to check. Capped at the model's reason length.
    reason = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control w-100",
                "placeholder": _("Optional: what looks wrong?"),
            }
        ),
    )


class CompetitionFilterForm(forms.Form):
    # event_type / direction / discipline are multi-select dropdowns (issue #108)
    # handled directly in the view via request.GET.getlist(); only the date range
    # is parsed through this form.
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
    )
