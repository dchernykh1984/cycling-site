"""The calendar's week settings are refused at start when the period row's script could not use them."""

import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


def _start(**env):
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env={**os.environ, **env},
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


class WeekSettingsTests(SimpleTestCase):
    def test_the_defaults_start(self):
        self.assertEqual(_start().returncode, 0)

    def test_another_week_starts_too(self):
        self.assertEqual(_start(CALENDAR_FIRST_WEEKDAY="0", CALENDAR_WEEKEND="5,6").returncode, 0)

    def test_a_week_the_script_cannot_count_is_refused(self):
        for env in ({"CALENDAR_FIRST_WEEKDAY": "7"}, {"CALENDAR_WEEKEND": "6,8"}, {"CALENDAR_WEEKEND": "0,3"}):
            with self.subTest(env=str(env)):
                started = _start(**env)
                self.assertNotEqual(started.returncode, 0)
                self.assertIn("CALENDAR_WEEKEND", started.stderr)
