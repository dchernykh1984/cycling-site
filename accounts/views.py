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
from django.utils import timezone
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


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields: ClassVar[list[str]] = ["first_name", "last_name", "gender", "birth_date", "team", "city"]
        widgets: ClassVar[dict] = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "gender": forms.RadioSelect(choices=[("M", "M"), ("F", "F")]),
        }


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
        from knowledge.models import DraftSubmission

        context["submissions"] = DraftSubmission.objects.filter(author=self.request.user).select_related("reviewed_by")
        if self.request.user.is_authenticated:
            # Hide registrations whose competition was soft-deleted (issue #161).
            context["registrations"] = (
                self.request.user.competition_registrations.filter(competition__is_deleted=False)
                .select_related("competition", "category")
                .order_by("-registered_at")
            )
        return context


class ProfileEditView(LoginRequiredMixin, View):
    template_name = "accounts/profile_edit.html"

    def get(self, request):
        from django.shortcuts import render

        form = ProfileEditForm(instance=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        from django.shortcuts import render

        form = ProfileEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("account_profile")
        return render(request, self.template_name, {"form": form})


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
        now = timezone.now()
        cutoff = now - timedelta(seconds=_RESEND_COOLDOWN_SECONDS)
        previous_sent_at = user.last_mail_action_at
        # Atomically reserve the send slot *before* sending. A plain check-then-send-then-save
        # is a TOCTOU race: concurrent POSTs from one participant+ would all read the stale
        # timestamp and each fire an email. This conditional UPDATE lets only one request flip
        # the timestamp; the losers get reserved=0 and are throttled. Reuses the same
        # timestamp/cooldown as the confirmation-email resend (participant+ never use that flow).
        reserved = (
            User.objects.filter(pk=user.pk)
            .filter(Q(last_mail_action_at__isnull=True) | Q(last_mail_action_at__lt=cutoff))
            .update(last_mail_action_at=now)
        )
        if not reserved:
            messages.error(request, gettext("Please wait a few minutes before sending another message."))
            return render(request, self.template_name, {"form": form})
        user.last_mail_action_at = now
        cd = form.cleaned_data
        # Collapse any whitespace/newlines in the subject so it can't inject email headers.
        subject_line = " ".join(cd["subject"].split())
        # The owner notification is internal and always English (not the sender's UI language).
        body = (
            f"New message from a registered site user.\n\n"
            f"User: {user.get_username()}\n"
            f"Registered email: {user.email}\n"
            f"Role: {user.get_role_display()}\n"
            f"Sent: {now:%Y-%m-%d %H:%M %Z}\n\n"
            f"Subject: {subject_line}\n\n"
            f"Message:\n{cd['message']}\n"
        )
        try:
            send_mail(
                subject=f"Site contact: {subject_line}",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
        except Exception:
            # A mail-server failure must not 500 the user; log it and release the slot we
            # reserved so a transient failure does not lock them out for the whole cooldown.
            logger.exception("Failed to send contact-owners email for user %s", user.pk)
            User.objects.filter(pk=user.pk, last_mail_action_at=now).update(last_mail_action_at=previous_sent_at)
            user.last_mail_action_at = previous_sent_at
            messages.error(request, gettext("Sorry, we could not send your message right now. Please try again later."))
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
