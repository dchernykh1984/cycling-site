from django import template
from wagtail.models import Locale

register = template.Library()

_LANG_DISPLAY = {"kk": "KZ", "ru": "RU", "en": "EN"}


@register.filter
def lang_display_code(language_code: str | None) -> str:
    if not language_code:
        return ""
    base = str(language_code).split("-")[0].lower()
    return _LANG_DISPLAY.get(base, language_code.upper())


@register.simple_tag
def get_about_url():
    from home.models import AboutPage

    page = AboutPage.objects.live().filter(locale=Locale.get_active()).first()
    if page is None:
        page = AboutPage.objects.live().first()
    return page.url if page else None
