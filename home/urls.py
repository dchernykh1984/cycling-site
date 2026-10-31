from django.urls import path

from home.views import (
    HomeCardDeleteView,
    HomeCardEditView,
    HomeCardMoveView,
    HomeEditView,
    PrivacyPolicyView,
    TermsOfUseView,
)

urlpatterns = [
    path("home/edit/", HomeEditView.as_view(), name="home_edit"),
    path("home/cards/new/", HomeCardEditView.as_view(), name="home_card_add"),
    path("home/cards/<int:pk>/edit/", HomeCardEditView.as_view(), name="home_card_edit"),
    path("home/cards/<int:pk>/move/", HomeCardMoveView.as_view(), name="home_card_move"),
    path("home/cards/<int:pk>/delete/", HomeCardDeleteView.as_view(), name="home_card_delete"),
    # Legal pages. Declared here (before Wagtail's catch-all in cycling_site/urls.py) so the URLs
    # are fixed and always resolve, independent of what editors do in the CMS.
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms/", TermsOfUseView.as_view(), name="terms_of_use"),
]
