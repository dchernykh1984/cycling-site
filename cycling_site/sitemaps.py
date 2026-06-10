from wagtail.contrib.sitemaps.sitemap_generator import Sitemap as WagtailSitemap


class WagtailPagesSitemap(WagtailSitemap):
    """Sitemap covering all live, public Wagtail pages across all locales."""
