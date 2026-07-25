from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User
from home.forms import SiteContentForm
from home.models import SiteContent


class PrivacyPolicyView(TemplateView):
    """Public privacy policy at a stable URL.

    A plain template view rather than a CMS page so the URL always exists and cannot be renamed or
    unpublished by an editor: external parties link to it (the Strava API Agreement, for instance,
    expects a reachable privacy policy) and our own footer points at it on every page.
    """

    template_name = "home/privacy_page.html"


class TermsOfUseView(TemplateView):
    """Public terms of use, served at a stable URL for the same reasons as the privacy policy."""

    template_name = "home/terms_page.html"


class HomeEditView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != User.Role.OWNER:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        content = SiteContent.load()
        form = SiteContentForm(instance=content)
        return render(request, "home/home_edit.html", {"form": form, "content": content})

    def post(self, request):
        content = SiteContent.load()
        form = SiteContentForm(request.POST, instance=content)
        if form.is_valid():
            form.save()
            return redirect("/")
        return render(request, "home/home_edit.html", {"form": form, "content": content})
