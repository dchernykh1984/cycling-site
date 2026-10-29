"""The call to the model: what is asked, and what a failure becomes. The provider is never reached."""

import io
import json
import urllib.error
from unittest import mock

from django.test import SimpleTestCase, override_settings

from agent.config import DEFAULT_LLM_MODEL
from assistant import llm

KEY = "sk-test-key"


def _reply(content, usage=None):
    body = {"choices": [{"message": {"content": content}}], "usage": usage or {}}
    response = mock.MagicMock()
    response.read.return_value = json.dumps(body).encode()
    response.__enter__.return_value = response
    return response


def _http_error(code):
    return urllib.error.HTTPError("https://example.test", code, "error", {}, io.BytesIO(b""))


@override_settings(ASSISTANT_LLM_API_KEY=KEY, ASSISTANT_LLM_BASE_URL="https://llm.example.test/")
class CompleteTests(SimpleTestCase):
    def test_the_request_asks_for_json_without_thinking(self):
        with mock.patch("urllib.request.urlopen", return_value=_reply('{"reply": "Hi"}')) as urlopen:
            self.assertEqual(llm.complete([{"role": "user", "content": "Hello"}]), {"reply": "Hi"})
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://llm.example.test/chat/completions")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {KEY}")
        self.assertEqual(payload["model"], DEFAULT_LLM_MODEL)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Hello"}])

    @override_settings(ASSISTANT_LLM_API_KEY="")
    def test_without_a_key_nothing_is_sent(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(llm.UnavailableError) as caught:
                llm.complete([])
        self.assertEqual(caught.exception.reason, llm.UnavailableError.NO_KEY)
        urlopen.assert_not_called()

    def test_each_refusal_says_what_can_be_done(self):
        for code, reason in (
            (402, llm.UnavailableError.NO_BALANCE),
            (401, llm.UnavailableError.KEY_REFUSED),
            (429, llm.UnavailableError.BUSY),
            (503, llm.UnavailableError.BUSY),
        ):
            with self.subTest(code=code), mock.patch("urllib.request.urlopen", side_effect=_http_error(code)):
                with self.assertRaises(llm.UnavailableError) as caught:
                    llm.complete([])
                self.assertEqual(caught.exception.reason, reason)

    def test_no_connection_or_no_answer_in_time_is_busy(self):
        for error in (urllib.error.URLError("refused"), TimeoutError(), ConnectionResetError()):
            with self.subTest(error=type(error).__name__), mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(llm.UnavailableError) as caught:
                    llm.complete([])
                self.assertEqual(caught.exception.reason, llm.UnavailableError.BUSY)

    def test_an_answer_that_is_not_a_json_object_is_refused(self):
        for content in ("not json", "[1, 2]", None, ""):
            with self.subTest(content=content), mock.patch("urllib.request.urlopen", return_value=_reply(content)):
                with self.assertRaises(llm.UnavailableError) as caught:
                    llm.complete([])
                self.assertEqual(caught.exception.reason, llm.UnavailableError.BAD_ANSWER)

    def test_a_failure_never_carries_the_key(self):
        with mock.patch("urllib.request.urlopen", side_effect=_http_error(401)):
            with self.assertRaises(llm.UnavailableError) as caught:
                llm.complete([])
        self.assertNotIn(KEY, repr(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
