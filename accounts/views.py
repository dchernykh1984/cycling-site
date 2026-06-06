import json

from allauth.account.models import EmailAddress
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView


class ProfileView(TemplateView):
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        context["has_verified_email"] = EmailAddress.objects.filter(user=self.request.user, verified=True).exists()
        return context


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
