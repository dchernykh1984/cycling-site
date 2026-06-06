from allauth.account.models import EmailAddress
from django.views.generic import TemplateView


class ProfileView(TemplateView):
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        context["has_verified_email"] = EmailAddress.objects.filter(user=self.request.user, verified=True).exists()
        return context
