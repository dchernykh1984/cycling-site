"""A picture floated beside an article's text: beside it on a computer, alone on a phone."""

import base64
import io

import pytest
from PIL import Image
from playwright.sync_api import Page

from knowledge.models import KnowledgeArticle
from tests.e2e.test_article_contents import knowledge_index  # noqa: F401 -- the fixture, used by name

TEXT = "<p>" + "Words that run beside the picture while there is room for them, then under it. " * 8 + "</p>"
MEASURE = """() => {
  const body = document.querySelector('.article-body').getBoundingClientRect();
  const [shot, icon] = [...document.querySelectorAll('.article-body img')];
  const box = el => el.getBoundingClientRect();
  return {
    body: body.width, left: body.left,
    shot: {float: getComputedStyle(shot).float, width: box(shot).width, left: box(shot).left, bottom: box(shot).bottom},
    icon: {float: getComputedStyle(icon).float, width: box(icon).width, left: box(icon).left, bottom: box(icon).bottom},
    second: document.querySelectorAll('.article-body h2')[1].getBoundingClientRect().top,
  };
}"""


def _picture(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (120, 140, 160)).save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("knowledge_index")
def test_a_floated_picture_sits_beside_the_text_on_a_computer_and_alone_on_a_phone(page: Page, live_server):
    shot = (
        f'<img src="{_picture(780, 1200)}" alt="A screen" width="390" height="600" '
        'style="float: right; width: 100%; max-width: 48%">'
    )
    # an icon an author floated at its own size, as the knowledge base already has some
    icon = f'<img src="{_picture(256, 256)}" alt="An icon" width="80" height="80" style="float: left; width: 80px">'
    body = f"<h2>One</h2><p>{shot}</p>{TEXT}<p>{icon}</p>{TEXT}<h2>Two</h2>{TEXT}"
    article = KnowledgeArticle.objects.create(title="Pictures", locale="en", body=body)

    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server.url}{article.get_absolute_url()}")
    wide = page.evaluate(MEASURE)
    assert wide["shot"]["float"] == "right"
    assert abs(wide["shot"]["width"] - 0.48 * wide["body"]) <= 1, wide
    assert wide["icon"]["float"] == "left"
    # the next section starts below the pictures of this one
    assert wide["second"] >= max(wide["shot"]["bottom"], wide["icon"]["bottom"]) - 1, wide

    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    narrow = page.evaluate(MEASURE)
    assert narrow["shot"]["float"] == "none"
    assert abs(narrow["shot"]["width"] - narrow["body"]) <= 1, narrow
    assert narrow["icon"]["float"] == "none"
    assert abs(narrow["icon"]["width"] - 80) <= 1, narrow
    assert abs(narrow["icon"]["left"] - (narrow["left"] + (narrow["body"] - 80) / 2)) <= 1, narrow
