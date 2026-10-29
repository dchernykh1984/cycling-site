"""Pictures go to the model as marks and come back as themselves; a picture it adds goes."""

import datetime
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from assistant import conversations, fields, images
from assistant.tests.helpers import user
from cycling_site.sanitize import sanitize_rich_html

PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
PHOTO = f'<img src="data:image/png;base64,{PIXEL}">'
MAP = '<img src="https://example.org/map.png" data-align="center">'


class MarkTests(SimpleTestCase):
    def test_each_picture_becomes_a_numbered_mark(self):
        originals: list[str] = []
        hidden = images.hide(f"<p>Start</p>{PHOTO}<p>Route</p>{MAP}", originals)
        self.assertEqual(hidden, '<p>Start</p><img src="image:1"><p>Route</p><img src="image:2">')
        self.assertEqual(originals, [PHOTO, MAP])

    def test_marks_come_back_where_the_answer_keeps_them_and_nothing_else_does(self):
        answer = (
            "<p>Route</p><img src='image:2' /><p>Start</p>"
            '<img src="image:1"><img src="https://made.up/x.png"><img src="image:7">'
        )
        self.assertEqual(images.restore(answer, [PHOTO, MAP]), f"<p>Route</p>{MAP}<p>Start</p>{PHOTO}")


class AnswerTests(TestCase):
    def test_the_page_gets_the_pictures_and_the_conversation_does_without(self):
        answer = {"description": {"ru": '<p>Start</p><img src="image:1">', "kk": "", "en": ""}}
        checked = fields.check(answer, current={}, texts=[], rows=[], images=[PHOTO])
        self.assertEqual(checked.form["description_ru"], sanitize_rich_html(f"<p>Start</p>{PHOTO}", allow_img=True))
        self.assertEqual(checked.set["description"]["ru"], "<p>Start</p>")


@override_settings(ASSISTANT_LLM_API_KEY="sk-test")
class TurnTests(TestCase):
    def test_a_picture_never_reaches_the_model_and_stays_in_the_description(self):
        admin = user()
        conversation, _ = conversations.start(admin)
        form = {"description_ru": f"<p>Start 08:00</p>{PHOTO}"}
        answer = {"reply": "Done.", "set": {"description": {"ru": '<p>Start at 08:00</p><img src="image:1">'}}}
        with mock.patch("assistant.llm.complete", return_value=answer) as complete:
            turn = conversations.take_turn(
                conversation,
                admin,
                "Fix it",
                form=form,
                attachments=[],
                today=datetime.date(2026, 10, 29),
                language="ru",
            )
        prompt = complete.call_args.args[0][-1]["content"]
        self.assertNotIn("base64", prompt)
        self.assertIn('<img src=\\"image:1\\">', prompt)
        self.assertEqual(
            turn.form["description_ru"], sanitize_rich_html(f"<p>Start at 08:00</p>{PHOTO}", allow_img=True)
        )
