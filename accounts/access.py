from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from accounts import roles
from accounts.models import User

EMAIL_CONFIRMATION_REQUIRED_MESSAGE = _(
    "Please confirm your email address to activate your account. Until your email is confirmed, you can view the site "
    "but cannot submit, register, comment, contact site owners, or use API features."
)


def needs_email_confirmation(user) -> bool:
    return user.is_authenticated and not roles.at_least(user, User.Role.PARTICIPANT)


def redirect_to_profile_for_email_confirmation(request):
    messages.error(request, EMAIL_CONFIRMATION_REQUIRED_MESSAGE)
    return redirect("account_profile")


class ParticipantRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if needs_email_confirmation(request.user):
            return redirect_to_profile_for_email_confirmation(request)
        return super().dispatch(request, *args, **kwargs)
