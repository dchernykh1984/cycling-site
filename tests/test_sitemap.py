"""The knowledge base moved off Wagtail pages, so its articles need their own sitemap entry."""

import pytest
from django.test import Client

from knowledge.models import KnowledgeArticle


@pytest.mark.django_db
def test_sitemap_includes_visible_knowledge_article():
    art = KnowledgeArticle.objects.create(title="Sitemap Visible", locale="ru", body="<p>x</p>")
    resp = Client().get("/sitemap.xml")
    assert resp.status_code == 200
    assert art.get_absolute_url() in resp.content.decode()


@pytest.mark.django_db
def test_sitemap_excludes_hidden_and_deleted_articles():
    hidden = KnowledgeArticle.objects.create(title="Sitemap Hidden", locale="ru", is_hidden=True)
    deleted = KnowledgeArticle.objects.create(title="Sitemap Deleted", locale="ru", is_deleted=True)
    body = Client().get("/sitemap.xml").content.decode()
    assert hidden.get_absolute_url() not in body
    assert deleted.get_absolute_url() not in body
