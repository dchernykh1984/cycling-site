from django import template
from django.core.cache import cache
from wagtail.models import Locale

register = template.Library()


@register.filter
def dict_get(d, key):
    return d.get(key) if isinstance(d, dict) else None


@register.simple_tag
def get_page_translation_urls(page):
    """Return {lang_code: url} for all live translations of a Wagtail page, including the page itself."""
    from django.conf import settings
    from django.urls import translate_url
    from django.utils import translation

    # translate_url() first resolves the URL in the *current* language context.
    # Wagtail page.url uses the site-root locale (default lang) as the base, so
    # page.url is always a default-language path (e.g. '/about/', not '/kk/about/').
    # Under a non-default locale, i18n_patterns won't match that path -> translate_url
    # falls back to returning the URL unchanged. Force resolution under the default
    # language so the path is always resolved correctly before retranslating.
    default_lang = settings.LANGUAGE_CODE.split("-")[0]
    result = {}
    all_pages = [page, *list(page.get_translations().live().select_related("locale"))]
    for p in all_pages:
        lang = p.locale.language_code
        page_url = p.url or "/"
        with translation.override(default_lang):
            result[lang] = translate_url(page_url, lang)
    return result


@register.filter
def lang_display_code(language_code: str | None) -> str:
    """The language's own code, as its address names it (/kk/): KK, not the country's KZ (#388)."""
    if not language_code:
        return ""
    return str(language_code).split("-")[0].upper()


@register.filter
def lang_own_name(language_code: str | None) -> str:
    """The language's name in that language, the same on every page: what its readers look for (#388).

    The names in ``LANGUAGES`` are translated by each language's own catalogue, so none is written here.
    """
    from django.conf import settings
    from django.utils import translation

    name = dict(settings.LANGUAGES).get(language_code or "")
    if not name:
        return ""
    with translation.override(language_code):
        return translation.gettext(name)


@register.simple_tag
def get_about_url():
    from home.models import CACHE_SECONDS, AboutPage

    try:
        locale = Locale.get_active()
    except Locale.DoesNotExist:  # no locale rows: no About page to link to, and no page to fail (#385)
        return None
    cache_key = f"about_url_{locale.language_code}"
    url = cache.get(cache_key)
    if url is None:
        page = AboutPage.objects.live().filter(locale=locale).first()
        url = page.url if page else ""
        cache.set(cache_key, url, timeout=CACHE_SECONDS)
    return url or None


@register.simple_tag(takes_context=True)
def get_site_content(context):
    from django.utils.translation import get_language

    from home.models import LocalizedSiteContent, SiteContent

    request = context.get("request")
    lang = getattr(request, "LANGUAGE_CODE", None) or get_language()
    return LocalizedSiteContent(SiteContent.load(), lang)
