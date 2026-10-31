from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from accounts import roles
from home.forms import HomeCardForm, SiteContentForm
from home.models import HomeCard, SiteContent


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


class OwnerRequiredMixin(LoginRequiredMixin):
    """The home page is the owner's to edit: a guest is sent to sign in, anyone else gets a 403."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not roles.role_at_least(request.user, roles.EDIT_HOME_PAGE):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _cards_list():
    # Back to the list of cards on the edit page, which is below the titles' form.
    return redirect(reverse("home_edit") + "#cards")


class HomeEditView(OwnerRequiredMixin, View):
    def get(self, request):
        content = SiteContent.load()
        form = SiteContentForm(instance=content)
        return self._render(request, form, content)

    def post(self, request):
        content = SiteContent.load()
        form = SiteContentForm(request.POST, instance=content)
        if form.is_valid():
            form.save()
            return redirect("/")
        return self._render(request, form, content)

    @staticmethod
    def _render(request, form, content):
        cards = HomeCard.objects.all()
        return render(request, "home/home_edit.html", {"form": form, "content": content, "cards": cards})


class HomeCardEditView(OwnerRequiredMixin, View):
    """A card of the home page, new (no pk) or one to change; a new one goes after the others."""

    def get(self, request, pk=None):
        card = get_object_or_404(HomeCard, pk=pk) if pk else None
        return render(request, "home/home_card_edit.html", {"form": HomeCardForm(instance=card), "card": card})

    def post(self, request, pk=None):
        card = get_object_or_404(HomeCard, pk=pk) if pk else HomeCard(position=HomeCard.next_position())
        form = HomeCardForm(request.POST, instance=card)
        if form.is_valid():
            form.save()
            return _cards_list()
        return render(request, "home/home_card_edit.html", {"form": form, "card": card if pk else None})


class HomeCardMoveView(OwnerRequiredMixin, View):
    """Put a card at the given position in the order, counted from 0 as the API counts it."""

    def post(self, request, pk):
        card = get_object_or_404(HomeCard, pk=pk)
        try:
            position = int(request.POST.get("position", ""))
        except ValueError:
            return HttpResponseBadRequest()
        card.place(position)
        return _cards_list()


class HomeCardDeleteView(OwnerRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(HomeCard, pk=pk).delete()
        return _cards_list()
