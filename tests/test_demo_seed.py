"""The demo content designers fill a local database with (skins/README.md) still loads."""

import runpy

from django.test import TestCase

from accounts.models import User
from calendar_app.models import Competition


class DemoSeedTests(TestCase):
    def test_the_seed_fills_a_freshly_migrated_database(self):
        runpy.run_path("scripts/demo_seed.py")
        self.assertTrue(User.objects.filter(email="member_light@example.com").exists())
        self.assertTrue(Competition.objects.exists())
