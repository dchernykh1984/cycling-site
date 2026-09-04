import json
import logging
import uuid
from datetime import timedelta
from typing import ClassVar

from allauth.account.models import EmailAddress
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy
from django.views import View
from django.views.generic import TemplateView

from accounts.access import (
    EMAIL_CONFIRMATION_REQUIRED_MESSAGE,
    ParticipantRequiredMixin,
    needs_email_confirmation,
    redirect_to_profile_for_email_confirmation,
)
from accounts.models import User

_RESEND_COOLDOWN_SECONDS = 600  # 10 minutes
logger = logging.getLogger(__name__)


def signin_providers() -> list[tuple[str, str]]:
    """``(id, display name)`` for every social provider this site offers, in settings order.

    Read from ``SOCIALACCOUNT_PROVIDERS`` rather than hardcoded, so enabling another provider makes
    it manageable from the profile too instead of silently missing from the sign-in methods card.
    The display name comes from allauth's own provider class ("GitHub", not "Github").
    """
    from allauth.socialaccount import providers

    result = []
    for provider_id in settings.SOCIALACCOUNT_PROVIDERS:
        provider_class = providers.registry.get_class(provider_id)
        result.append((provider_id, getattr(provider_class, "name", None) or provider_id.capitalize()))
    return result


def signin_methods(user) -> dict:
    """State of every way this account can be signed in to (issue #237).

    allauth already supports any number of linked providers alongside an email/password login and
    ships pages to manage them, but nothing in our interface pointed at those pages. This feeds the
    profile's "Sign-in methods" card, which shows what is currently active -- the thing a member
    actually needs to know -- and links to the existing allauth pages for the actions themselves.

    Only structural data is returned; the wording lives in the template so it stays translatable.
    """
    from allauth.socialaccount.models import SocialAccount

    connected = set(SocialAccount.objects.filter(user=user).values_list("provider", flat=True))
    has_email = user.has_email_address()
    has_password = user.has_usable_password()
    # Both halves are needed for a password to count as a way in. Combined here rather than through
    # can_sign_in_with_password() so the address is looked up once; the model still owns the rule,
    # and the guard against unlinking the last provider applies exactly the same one.
    password_ready = has_email and has_password
    providers = [{"id": pid, "name": name, "connected": pid in connected} for pid, name in signin_providers()]
    method_count = len(connected) + (1 if password_ready else 0)
    return {
        "has_email": has_email,
        "has_password": has_password,
        "password_ready": password_ready,
        "providers": providers,
        "method_count": method_count,
        # Disconnecting the only remaining method would lock the member out of their own account.
        "can_disconnect": method_count > 1,
    }


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields: ClassVar[list[str]] = [
            "first_name",
            "last_name",
            "gender",
            "birth_date",
            "team",
            "city",
            "strava_link",
            # Saved calendar-filter preferences (issue #229). The cascade pickers in the template
            # post the chosen ids as hidden inputs of these names; the widgets are not rendered by
            # Django (MultipleHiddenInput just declares them optional so an empty pick clears them).
            "preferred_directions",
            "preferred_disciplines",
            "preferred_locations",
        ]
        widgets: ClassVar[dict] = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "gender": forms.RadioSelect(choices=[("M", "M"), ("F", "F")]),
            "preferred_directions": forms.MultipleHiddenInput,
            "preferred_disciplines": forms.MultipleHiddenInput,
            "preferred_locations": forms.MultipleHiddenInput,
        }


def role_ladder(user) -> list[dict]:
    """Every role the site has, weakest first, with the reader's own marked.

    A person cannot see what they are missing -- or what they could give up -- from a single line
    saying "Role: Participant", so the profile shows the whole ladder and where they stand on it.
    """
    labels = dict(User.Role.choices)
    return [{"value": role, "label": labels[role], "is_current": role == user.role} for role in User.ROLE_HIERARCHY]


class ProfileView(TemplateView):
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        user = self.request.user
        context["has_verified_email"] = (
            user.role not in (user.Role.GUEST, user.Role.PARTICIPANT)
            or EmailAddress.objects.filter(user=user, verified=True).exists()
        )
        context["email_confirmation_required_message"] = EMAIL_CONFIRMATION_REQUIRED_MESSAGE
        context["signin_methods"] = signin_methods(user)
        cooldown_remaining = 0
        sent_at = self.request.user.last_mail_action_at
        if sent_at:
            elapsed = (timezone.now() - sent_at).total_seconds()
            remaining = _RESEND_COOLDOWN_SECONDS - elapsed
            if remaining > 0:
                cooldown_remaining = int(remaining)
        context["resend_cooldown_seconds"] = cooldown_remaining
        # The contact-owners button shares the same timestamp/cooldown (issue #122).
        context["contact_cooldown_seconds"] = cooldown_remaining
        context["roles"] = role_ladder(user)
        from knowledge.models import DraftSubmission

        context["submissions"] = DraftSubmission.objects.filter(author=self.request.user).select_related("reviewed_by")
        if self.request.user.is_authenticated:
            # Hide registrations whose competition was soft-deleted (issue #161).
            context["registrations"] = self._registrations_with_actions(self.request.user)
            from django.db.models import Case, IntegerField, Value, When

            from calendar_app.models import Competition

            # Competitions this user submitted. Ones that still need attention (pending / rejected)
            # come first, already-approved ones last; newest first within each group.
            context["my_competitions"] = (
                Competition.objects.filter(submitted_by=self.request.user, is_deleted=False)
                .annotate(
                    _approved_last=Case(
                        When(status=Competition.Status.APPROVED, then=Value(1)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                )
                .order_by("_approved_last", "-date_start")
            )
        return context

    @staticmethod
    def _registrations_with_actions(user):
        """The reader's own entries, each carrying whether they may still edit or cancel it.

        The profile offers the same two buttons as the participant list, so it asks the same two
        questions the edit and delete views ask before they act -- rather than a second rule that
        can drift away from them and offer a button the server then refuses.
        """
        from registrations.views import can_manage, can_self_edit

        rows = list(
            user.competition_registrations.filter(competition__is_deleted=False)
            # An organizer's rights are decided by the event's submitter, so that row travels with
            # the event -- otherwise the permission check fetches it once per registration.
            .select_related("competition", "competition__submitted_by", "category")
            .order_by("-registered_at")
        )
        for reg in rows:
            reg.can_edit = can_manage(user, reg.competition) or can_self_edit(user, reg.competition, reg)
        return rows


class ProfileEditView(LoginRequiredMixin, View):
    template_name = "accounts/profile_edit.html"

    def _picker_context(self, form) -> dict:
        """Data the cascade preference pickers need: the same option sets the calendar filter uses,
        plus the pre-checked ids taken from the FORM (issue #229). Reading from the bound form (not
        the DB) keeps the user's in-progress selection when an unrelated field fails validation and
        the page is re-rendered, exactly as the plain text fields do."""
        from calendar_app.views import _categories_for_locale, _disciplines_for_locale, _get_locations_data

        def ids(field_name):
            out = []
            for value in form[field_name].value() or []:
                try:
                    out.append(int(getattr(value, "pk", value)))
                except (TypeError, ValueError):
                    continue
            return out

        return {
            "categories_json": _categories_for_locale(),
            "disciplines_json": _disciplines_for_locale(),
            "locations_data": _get_locations_data(),
            "pref_direction_ids": ids("preferred_directions"),
            "pref_discipline_ids": ids("preferred_disciplines"),
            "pref_location_ids": ids("preferred_locations"),
        }

    def get(self, request):
        from django.shortcuts import render

        form = ProfileEditForm(instance=request.user)
        return render(request, self.template_name, {"form": form, **self._picker_context(form)})

    def post(self, request):
        from django.shortcuts import render

        form = ProfileEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("account_profile")
        return render(request, self.template_name, {"form": form, **self._picker_context(form)})


class ResendEmailConfirmationView(LoginRequiredMixin, View):
    def post(self, request):
        user = request.user
        if EmailAddress.objects.filter(user=user, verified=True).exists():
            return redirect("account_profile")

        now = timezone.now()
        cutoff = now - timedelta(seconds=_RESEND_COOLDOWN_SECONDS)
        previous_sent_at = user.last_mail_action_at
        # Reserve the send slot atomically *before* sending, exactly like ContactOwnersView.
        # A check-then-send-then-save order lets concurrent resends from one guest all pass the
        # stale cooldown check and each fire a confirmation email (TOCTOU). last_mail_action_at
        # is the single controller for all outgoing mail, so reserving it here serializes them.
        reserved = (
            User.objects.filter(pk=user.pk)
            .filter(Q(last_mail_action_at__isnull=True) | Q(last_mail_action_at__lt=cutoff))
            .update(last_mail_action_at=now)
        )
        if not reserved:
            return redirect("account_profile")
        user.last_mail_action_at = now

        email_address, _ = EmailAddress.objects.get_or_create(
            user=user,
            defaults={"email": user.email, "primary": True, "verified": False},
        )
        try:
            email_address.send_confirmation(request, signup=False)
        except Exception:
            # Release the reserved slot so a transient mail failure does not lock the guest
            # out of resending for the whole cooldown window.
            logger.exception("Failed to resend confirmation email for user %s", user.pk)
            User.objects.filter(pk=user.pk, last_mail_action_at=now).update(last_mail_action_at=previous_sent_at)
            user.last_mail_action_at = previous_sent_at
        return redirect("account_profile")


class ApiTokenRegenerateView(LoginRequiredMixin, View):
    def post(self, request):
        user = request.user
        if needs_email_confirmation(user):
            return redirect_to_profile_for_email_confirmation(request)
        user.api_token = uuid.uuid4()
        user.save(update_fields=["api_token"])
        return redirect("account_profile")


def _mail_the_owners(request, subject: str, body: str, *, what: str) -> bool:
    """Send one message to the site owners, throttled per user. True when it went out.

    The slot is reserved with a conditional UPDATE *before* the send rather than checked and then
    written: concurrent POSTs from one person would all read the same stale timestamp and each fire
    a mail. Losing that race means being throttled, which is the point.

    On a mail-server failure the reservation is rolled back, so a transient outage does not lock
    somebody out for the whole cooldown, and the caller is told to re-render its form.
    """
    user = request.user
    now = timezone.now()
    cutoff = now - timedelta(seconds=_RESEND_COOLDOWN_SECONDS)
    previous_sent_at = user.last_mail_action_at
    reserved = (
        User.objects.filter(pk=user.pk)
        .filter(Q(last_mail_action_at__isnull=True) | Q(last_mail_action_at__lt=cutoff))
        .update(last_mail_action_at=now)
    )
    if not reserved:
        messages.error(request, gettext("Please wait a few minutes before sending another message."))
        return False
    user.last_mail_action_at = now
    try:
        send_mail(
            # Collapse any whitespace so a value carried into the subject cannot inject headers.
            subject=" ".join(subject.split()),
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send %s email for user %s", what, user.pk)
        User.objects.filter(pk=user.pk, last_mail_action_at=now).update(last_mail_action_at=previous_sent_at)
        user.last_mail_action_at = previous_sent_at
        messages.error(request, gettext("Sorry, we could not send your message right now. Please try again later."))
        return False
    return True


class RequestRoleForm(forms.Form):
    """Which role somebody is asking for, and why.

    The choices leave out the role they already hold and include the ones below it: stepping down
    is a real request -- an organizer who has stopped running races would rather not keep the
    buttons that go with it.
    """

    role = forms.ChoiceField(
        choices=(),
        label=gettext_lazy("Role"),
        widget=forms.RadioSelect,
    )
    reason = forms.CharField(
        max_length=5000,
        label=gettext_lazy("Why you need it"),
        help_text=gettext_lazy(
            "Tell us what you plan to do with this role, and how to reach you if we have questions."
        ),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6, "maxlength": 5000}),
    )

    def __init__(self, *args, current_role: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        labels = dict(User.Role.choices)
        # `self.fields` is typed as the base Field, which knows nothing of choices; the local
        # binding is what tells mypy which field this is.
        role_field: forms.ChoiceField = self.fields["role"]  # type: ignore[assignment]
        role_field.choices = [(role, labels[role]) for role in User.ROLE_HIERARCHY if role != current_role]


class RequestRoleView(ParticipantRequiredMixin, View):
    """Ask the owners for a different role.

    Nothing is granted here: the request is an email to the same mailbox the contact form writes
    to, and a human decides. It shares that form's cooldown as well as its mailbox -- one person
    firing off a burst of mail is the thing being throttled, whichever form they use.
    """

    template_name = "accounts/request_role.html"

    def get(self, request):
        return render(request, self.template_name, {"form": RequestRoleForm(current_role=request.user.role)})

    def post(self, request):
        user = request.user
        form = RequestRoleForm(request.POST, current_role=user.role)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        cd = form.cleaned_data
        # Internal notification, always English -- the owners read it, not the sender, and the role
        # names follow the active language now that the profile shows them.
        with translation.override("en"):
            wanted = dict(User.Role.choices)[cd["role"]]
            body = (
                f"A registered site user asks for a different role.\n\n"
                f"User: {user.get_username()}\n"
                f"Registered email: {user.email}\n"
                f"Current role: {user.get_role_display()}\n"
                f"Requested role: {wanted}\n"
                f"Sent: {timezone.now():%Y-%m-%d %H:%M %Z}\n\n"
                f"Reason:\n{cd['reason']}\n"
            )
        sent = _mail_the_owners(request, f"Role request: {user.get_username()} -> {wanted}", body, what="role-request")
        if not sent:
            return render(request, self.template_name, {"form": form})
        messages.success(request, gettext("Your request has been sent. We will get back to you."))
        return redirect("account_profile")


class ContactOwnersForm(forms.Form):
    subject = forms.CharField(
        max_length=200,
        label=gettext_lazy("Subject"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    message = forms.CharField(
        max_length=5000,  # generous for a detailed hand-typed message, but blocks huge payloads
        label=gettext_lazy("Message"),
        help_text=gettext_lazy(
            "Please tell us how to reach you (e.g. email or messenger) and describe your question or problem in detail."
        ),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6, "maxlength": 5000}),
    )


class ContactOwnersView(ParticipantRequiredMixin, View):
    """Registered users (participant+) can email the site owners (issue #122).

    The message goes to the same mailbox that sends the registration confirmation
    (DEFAULT_FROM_EMAIL) and includes who wrote it, when, and how they registered.
    """

    template_name = "accounts/contact_owners.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ContactOwnersForm()})

    def post(self, request):
        form = ContactOwnersForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        user = request.user
        cd = form.cleaned_data
        # Collapse any whitespace/newlines in the subject so it can't inject email headers.
        subject_line = " ".join(cd["subject"].split())
        # The owner notification is internal and always English (not the sender's UI language).
        with translation.override("en"):
            body = (
                f"New message from a registered site user.\n\n"
                f"User: {user.get_username()}\n"
                f"Registered email: {user.email}\n"
                f"Role: {user.get_role_display()}\n"
                f"Sent: {timezone.now():%Y-%m-%d %H:%M %Z}\n\n"
                f"Subject: {subject_line}\n\n"
                f"Message:\n{cd['message']}\n"
            )
        if not _mail_the_owners(request, f"Site contact: {subject_line}", body, what="contact-owners"):
            return render(request, self.template_name, {"form": form})
        messages.success(request, gettext("Your message has been sent to the site owners."))
        return redirect("account_profile")


class ThemeUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid JSON"}, status=400)
        theme = data.get("theme", "light")
        if theme not in ("light", "dark"):
            return JsonResponse({"error": "invalid theme"}, status=400)
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
        return JsonResponse({"theme": theme})


def set_language(request):
    """Wrap Django's set_language to also persist preference for authenticated users."""
    from django.utils.translation import check_for_language
    from django.views.i18n import set_language as _django_set_language

    response = _django_set_language(request)

    if request.method == "POST" and request.user.is_authenticated:
        lang = request.POST.get("language")
        if lang is not None and (lang == "" or check_for_language(lang)):
            request.user.preferred_language = lang
            request.user.save(update_fields=["preferred_language"])
            if lang == "":
                from django.conf import settings as django_settings

                response.delete_cookie(
                    django_settings.LANGUAGE_COOKIE_NAME,
                    path=django_settings.LANGUAGE_COOKIE_PATH,
                    domain=django_settings.LANGUAGE_COOKIE_DOMAIN,
                    samesite=django_settings.LANGUAGE_COOKIE_SAMESITE,
                )

    return response
