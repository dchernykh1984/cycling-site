"""Structured data for the home page: who runs the site, and how to search it.

Search engines read schema.org/SportsOrganization to know the site belongs to a club in a place --
its name, logo and its profiles elsewhere -- and schema.org/WebSite with a SearchAction to offer a
search box under the result. Every value comes from the settings (ORGANIZATION_*), the Wagtail site
or the owner's own home-page text, so nothing is claimed that the owner did not write down.
"""

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from cycling_site.jsonld import dumps


def organization(request, site_content, site_name: str = "") -> str:
    """The JSON-LD body for the home page, ready to drop inside a script tag."""
    base = f"{request.scheme}://{request.get_host()}"
    home = f"{base}{request.path}"
    name = (
        getattr(settings, "ORGANIZATION_NAME", "")
        or site_name
        or getattr(site_content, "navbar_title", "")
        or getattr(site_content, "page_title", "")
    )
    language = (getattr(request, "LANGUAGE_CODE", "") or "")[:2]

    club: dict = {
        "@type": "SportsOrganization",
        "@id": f"{base}/#organization",
        "url": home,
        "logo": f"{base}{static('logo-512.png')}",
    }
    if name:
        club["name"] = name
    area = getattr(settings, "ORGANIZATION_AREA", "")
    if area:
        club["areaServed"] = {"@type": "City", "name": area}
    same_as = [link for link in getattr(settings, "ORGANIZATION_SAME_AS", []) if link.startswith("https://")]
    if same_as:
        club["sameAs"] = same_as

    website: dict = {
        "@type": "WebSite",
        "@id": f"{base}/#website",
        "url": home,
        "publisher": {"@id": club["@id"]},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": f"{base}{reverse('search')}?q={{search_term_string}}"},
            "query-input": "required name=search_term_string",
        },
    }
    if name:
        website["name"] = name
    if language:
        website["inLanguage"] = language

    data = {"@context": "https://schema.org", "@graph": [club, website]}
    # dumps() keeps a "</script>" that reached a name from ending the block early, and the JSON valid.
    return dumps(data)
