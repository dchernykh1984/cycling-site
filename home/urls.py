from django.urls import path

from home.views import HomeEditView, PrivacyPolicyView, TermsOfUseView

urlpatterns = [
    path("home/edit/", HomeEditView.as_view(), name="home_edit"),
    # Legal pages. Declared here (before Wagtail's catch-all in cycling_site/urls.py) so the URLs
    # are fixed and always resolve, independent of what editors do in the CMS.
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms/", TermsOfUseView.as_view(), name="terms_of_use"),
]
