"""The album form stops a batch too big to send before Cloudflare would refuse it with a bare page."""

import datetime

import pytest
from playwright.sync_api import FilePayload, Page, Request, expect

from accounts.models import User
from gallery.models import Album
from tests.e2e.conftest import inject_session


@pytest.mark.django_db(transaction=True)
def test_a_batch_over_the_limit_is_not_sent(page: Page, live_server, settings):
    settings.GALLERY_MAX_BATCH_MB = 1
    admin = User.objects.create_user(username="gallery.admin", email="gallery.admin@example.com", role=User.Role.ADMIN)
    album = Album.objects.create(title="Camp 2026", date=datetime.date(2026, 3, 1), created_by=admin)
    inject_session(page, live_server, admin)
    page.goto(f"{live_server.url}/ru/gallery/albums/{album.pk}/edit/")

    big = FilePayload(name="big.jpg", mimeType="image/jpeg", buffer=b"0" * (700 * 1024))
    file_input = page.locator('input[type="file"]')
    file_input.set_input_files([big, FilePayload(name="big2.jpg", mimeType="image/jpeg", buffer=big["buffer"])])
    expect(page.locator("#photo-count")).to_have_class("form-text text-danger")

    posts: list[str] = []

    def record(request: Request) -> None:
        if request.method == "POST":
            posts.append(request.url)

    page.on("request", record)
    file_input.evaluate("input => input.form.requestSubmit()")
    page.wait_for_timeout(1000)
    assert posts == []
