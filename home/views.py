from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views import View

from accounts.models import User
from home.forms import SiteContentForm
from home.models import SiteContent


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
