import json
import uuid
from datetime import timedelta
from typing import ClassVar

from allauth.account.models import EmailAddress
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User

_RESEND_COOLDOWN_SECONDS = 600  # 10 minutes
_PARTICIPANT_RANK = User.ROLE_HIERARCHY.index(User.Role.PARTICIPANT)


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields: ClassVar[list[str]] = ["first_name", "last_name", "gender", "birth_date"]
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
        cooldown_remaining = 0
        sent_at = self.request.user.email_confirmation_sent_at
        if sent_at:
            elapsed = (timezone.now() - sent_at).total_seconds()
            remaining = _RESEND_COOLDOWN_SECONDS - elapsed
            if remaining > 0:
                cooldown_remaining = int(remaining)
        context["resend_cooldown_seconds"] = cooldown_remaining
        from knowledge.models import DraftSubmission

        context["submissions"] = DraftSubmission.objects.filter(author=self.request.user).select_related("reviewed_by")
        if self.request.user.is_authenticated:
            context["registrations"] = self.request.user.competition_registrations.select_related(
                "competition", "category"
            ).order_by("-registered_at")
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

        sent_at = user.email_confirmation_sent_at
        if sent_at and (timezone.now() - sent_at) < timedelta(seconds=_RESEND_COOLDOWN_SECONDS):
            return redirect("account_profile")

        email_address, _ = EmailAddress.objects.get_or_create(
            user=user,
            defaults={"email": user.email, "primary": True, "verified": False},
        )
        email_address.send_confirmation(request, signup=False)
        user.email_confirmation_sent_at = timezone.now()
        user.save(update_fields=["email_confirmation_sent_at"])
        return redirect("account_profile")


class ApiTokenRegenerateView(LoginRequiredMixin, View):
    def post(self, request):
        user = request.user
        if user.get_role_rank() < user.ROLE_HIERARCHY.index(user.Role.PARTICIPANT):
            return JsonResponse({"error": "forbidden"}, status=403)
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


class ContactOwnersView(LoginRequiredMixin, View):
    """Registered users (participant+) can email the site owners (issue #122).

    The message goes to the same mailbox that sends the registration confirmation
    (DEFAULT_FROM_EMAIL) and includes who wrote it, when, and how they registered.
    """

    template_name = "accounts/contact_owners.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_superuser and request.user.get_role_rank() < _PARTICIPANT_RANK:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name, {"form": ContactOwnersForm()})

    def post(self, request):
        form = ContactOwnersForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        user = request.user
        # Rate limit: reuse the same timestamp/cooldown as the confirmation-email resend
        # (participant+ are already verified, so the resend flow never uses this field) (#122).
        sent_at = user.email_confirmation_sent_at
        if sent_at and (timezone.now() - sent_at) < timedelta(seconds=_RESEND_COOLDOWN_SECONDS):
            messages.error(request, gettext("Please wait a few minutes before sending another message."))
            return render(request, self.template_name, {"form": form})
        cd = form.cleaned_data
        # Collapse any whitespace/newlines in the subject so it can't inject email headers.
        subject_line = " ".join(cd["subject"].split())
        body = gettext(
            "New message from a registered site user.\n\n"
            "User: %(username)s\n"
            "Registered email: %(email)s\n"
            "Role: %(role)s\n"
            "Sent: %(when)s\n\n"
            "Subject: %(subject)s\n\n"
            "Message:\n%(message)s\n"
        ) % {
            "username": user.get_username(),
            "email": user.email,
            "role": user.get_role_display(),
            "when": timezone.now().strftime("%Y-%m-%d %H:%M %Z"),
            "subject": subject_line,
            "message": cd["message"],
        }
        try:
            send_mail(
                subject=gettext("Site contact: %(subject)s") % {"subject": subject_line},
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
        except Exception:
            # A mail-server failure must not 500 the user; let them retry.
            messages.error(request, gettext("Sorry, we could not send your message right now. Please try again later."))
            return render(request, self.template_name, {"form": form})
        user.email_confirmation_sent_at = timezone.now()
        user.save(update_fields=["email_confirmation_sent_at"])
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
