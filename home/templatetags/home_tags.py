from django import template
from django.core.cache import cache
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

    locale = Locale.get_active()
    cache_key = f"about_url_{locale.language_code}"
    url = cache.get(cache_key)
    if url is None:
        page = AboutPage.objects.live().filter(locale=locale).first()
        url = page.url if page else ""
        cache.set(cache_key, url, timeout=300)
    return url or None
