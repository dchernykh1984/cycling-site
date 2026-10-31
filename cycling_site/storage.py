"""Static files in production: WhiteNoise's storage, which names every file after a hash of its content."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    """WhiteNoise's storage, plus the links of the trainer's static page to its own files.

    Django rewrites a stylesheet's ``url()`` to the hashed name of what it points at, so changing an
    image renames the stylesheet too. The trainer page (trainer/alatau.html) loads its stylesheet and
    scripts by relative links, and needs the same: served under a hashed name it is cached for a year,
    so it must name the very versions of its files it was built with, cached as long. Addresses with a
    scheme or starting with // (a CDN, the fonts) are left as they are, as Django leaves them in CSS.
    Only trainer/*.html: the skins' templates are collected as static files too, and their
    ``{% static %}`` links are not files to hash.
    """

    patterns = (
        *CompressedManifestStaticFilesStorage.patterns,
        ("trainer/*.html", ((r"""(?P<matched>(?P<attr>src|href)="(?P<url>[^"]+)")""", """%(attr)s="%(url)s\""""),)),
    )
