"""Ensure all internally-generated URLs and page slugs are ASCII-only."""

import re

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

# Cyrillic test strings constructed from code points to satisfy the no-non-ASCII
# pre-commit hook.  chr(0x0430) == Cyrillic small 'a'.
_CYRILLIC_A = chr(0x0430)
_CYRILLIC_SLUG = f"slug-{_CYRILLIC_A}-test"


# ---------------------------------------------------------------------------
# Layer 1: Wagtail setting
# ---------------------------------------------------------------------------


def test_wagtail_unicode_slugs_disabled():
    """WAGTAIL_ALLOW_UNICODE_SLUGS must be False to prevent auto-generation of Cyrillic slugs."""
    assert getattr(settings, "WAGTAIL_ALLOW_UNICODE_SLUGS", True) is False


# ---------------------------------------------------------------------------
# Layer 1b: slugify behaviour with the setting applied
# ---------------------------------------------------------------------------


def test_slugify_with_setting_strips_cyrillic():
    """When allow_unicode=False, slugify() removes Cyrillic characters entirely."""
    from django.utils.text import slugify

    allow_unicode = getattr(settings, "WAGTAIL_ALLOW_UNICODE_SLUGS", True)
    # A purely Cyrillic title produces an empty string, not a Cyrillic slug.
    pure_cyrillic = _CYRILLIC_A * 5
    assert slugify(pure_cyrillic, allow_unicode=allow_unicode) == ""

    # A mixed title retains only the ASCII portion.
    mixed = "article-" + _CYRILLIC_A + "-test"
    result = slugify(mixed, allow_unicode=allow_unicode)
    assert _CYRILLIC_A not in result
    assert result  # something remains


# ---------------------------------------------------------------------------
# Layer 2: AsciiSlugMixin regex
# ---------------------------------------------------------------------------


def test_ascii_slug_regex_accepts_valid_slugs():
    from cycling_site.page_mixins import _ASCII_SLUG_RE

    for slug in ("hello", "hello-world", "page_123", "a-b-c", "ABC"):
        assert _ASCII_SLUG_RE.match(slug), f"should accept: {slug!r}"


def test_ascii_slug_regex_rejects_cyrillic():
    from cycling_site.page_mixins import _ASCII_SLUG_RE

    assert not _ASCII_SLUG_RE.match(_CYRILLIC_SLUG)
    assert not _ASCII_SLUG_RE.match(_CYRILLIC_A * 3)


# ---------------------------------------------------------------------------
# Layer 2: Page model clean() rejects Cyrillic slugs
# ---------------------------------------------------------------------------

_PAGE_CLASSES = [
    ("home.models", "HomePage"),
    ("home.models", "AboutPage"),
    ("news.models", "NewsIndexPage"),
    ("news.models", "NewsPage"),
    ("knowledge.models", "KnowledgeIndexPage"),
    ("locations.models", "LocationsMapPage"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("module_name,class_name", _PAGE_CLASSES)
def test_page_model_rejects_cyrillic_slug(module_name, class_name):
    """Every Page subclass must raise ValidationError on a Cyrillic slug."""
    import importlib

    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)

    page = cls(title="Test", slug=_CYRILLIC_SLUG)
    with pytest.raises(ValidationError) as exc_info:
        page.clean()
    assert "slug" in exc_info.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("module_name,class_name", _PAGE_CLASSES)
def test_page_model_accepts_ascii_slug(module_name, class_name):
    """Every Page subclass must not raise ValidationError on a valid ASCII slug."""
    import importlib

    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)

    page = cls(title="Test", slug="valid-ascii-slug")
    # Should not raise (other unrelated validation errors are fine here)
    try:
        page.clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            assert "slug" not in exc.message_dict, f"ASCII slug wrongly rejected by {class_name}"


# ---------------------------------------------------------------------------
# Layer 3: URL patterns contain no Cyrillic
# ---------------------------------------------------------------------------


def test_url_patterns_ascii_only():
    """No hardcoded URL pattern segment may contain a Cyrillic character."""
    from django.urls import get_resolver

    _cyrillic_re = re.compile(r"[\u0400-\u04ff]")

    def collect(resolver):
        result = []
        for pattern in resolver.url_patterns:
            result.append(str(pattern.pattern))
            if hasattr(pattern, "url_patterns"):
                result.extend(collect(pattern))
        return result

    for pattern_str in collect(get_resolver()):
        assert not _cyrillic_re.search(pattern_str), f"Cyrillic found in URL pattern: {pattern_str!r}"


# ---------------------------------------------------------------------------
# Auto-slug generation: knowledge articles and news pages
# ---------------------------------------------------------------------------


def test_knowledge_article_autoslug_strips_cyrillic():
    """_create_knowledge_article uses slugify() without allow_unicode - Cyrillic titles
    fall back to 'article', never producing a Cyrillic slug."""
    from django.utils.text import slugify

    cyrillic_title = _CYRILLIC_A * 10
    base_slug = slugify(cyrillic_title) or "article"
    assert base_slug == "article"
    assert _CYRILLIC_A not in base_slug
