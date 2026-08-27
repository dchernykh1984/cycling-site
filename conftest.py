"""Test-wide fixtures.

Kept at the repository root so it applies to every test module, app-level ones included.
"""

import pytest
from django.conf import settings
from django.utils import translation


@pytest.fixture(autouse=True)
def _reset_active_language():
    """Start every test in the site's default language.

    A request to /en/... or /kk/... leaves that language active in the worker afterwards, and the
    next test then reads a translated string, or queries a modeltranslation field, in a language
    it never asked for. Before the language prefixes existed this rarely bit; now that the URL
    carries the language, it would bite constantly.
    """
    translation.activate(settings.LANGUAGE_CODE)
    yield
    translation.activate(settings.LANGUAGE_CODE)
