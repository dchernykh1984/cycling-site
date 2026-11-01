"""Which knowledge and news articles a reader may see: one rule for the pages, the feeds and the API."""


def visible(articles, *, can_manage: bool):
    """``articles`` without the deleted ones, and without the hidden ones unless the reader manages them."""
    articles = articles.filter(is_deleted=False)
    return articles if can_manage else articles.filter(is_hidden=False)


def public(articles):
    """``articles`` as anyone may see them: the sitemap, the feeds and the search read these."""
    return visible(articles, can_manage=False)


def is_public(article) -> bool:
    return not article.is_hidden and not article.is_deleted
