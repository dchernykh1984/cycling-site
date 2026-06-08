import json
from typing import ClassVar

from allauth.account.models import EmailAddress
from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User


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
        context["has_verified_email"] = EmailAddress.objects.filter(user=self.request.user, verified=True).exists()
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

    return response
