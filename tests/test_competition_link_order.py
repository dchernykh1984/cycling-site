"""Event actions belong before the announcement text, in every locale."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from calendar_app.models import Competition, CompetitionMaterial
from protocols.models import Protocol
from tests.language_urls import in_language

DOCUMENTS = ("route", "announcement", "regulations", "results")


class CompetitionLinkOrderTests(TestCase):
    def setUp(self):
        self.competition = Competition.objects.create(
            title_ru="Link order race",
            date_start=timezone.localdate() + datetime.timedelta(days=10),
            status=Competition.Status.APPROVED,
            description_ru="<p>Announcement body</p>",
            registration_enabled=True,
            url_registration="https://example.com/register",
            **{f"url_{name}": f"https://example.com/{name}" for name in DOCUMENTS},
        )
        self.protocol = Protocol.objects.create(competition=self.competition, protocol_type="absolute")
        self.material = CompetitionMaterial.objects.create(
            competition=self.competition, title="Photos", url="https://example.com/photos"
        )

    def _html(self, language="en"):
        response = self.client.get(in_language(self.competition.get_absolute_url(), language))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _assert_order(self, html, markers):
        positions = [html.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_registration_documents_protocols_and_materials_precede_description_in_every_locale(self):
        for language in ("ru", "kk", "en"):
            with self.subTest(language=language):
                markers = [
                    f'href="{self.competition.url_registration}"',
                    f'href="{in_language(reverse("registrations:register", args=[self.competition.pk]), language)}"',
                    *[f'href="{getattr(self.competition, f"url_{name}")}"' for name in DOCUMENTS],
                    f'href="{in_language(reverse("protocol_detail", args=[self.protocol.pk]), language)}"',
                    f'href="{self.material.url}"',
                    'class="mb-4 competition-description"',
                ]
                html = self._html(language)
                self._assert_order(html, markers)
                for marker in markers:
                    self.assertEqual(html.count(marker), 1)

    def test_uploaded_documents_keep_the_same_order_and_urls_take_precedence(self):
        for name in DOCUMENTS:
            setattr(self.competition, f"file_{name}", f"competitions/{name}.pdf")
        self.competition.save()
        html = self._html()
        for name in DOCUMENTS:
            self.assertNotIn(f'href="{getattr(self.competition, f"file_{name}").url}"', html)
            setattr(self.competition, f"url_{name}", "")
        self.competition.save()
        self._assert_order(
            self._html(),
            [
                *[f'href="{getattr(self.competition, f"file_{name}").url}"' for name in DOCUMENTS],
                'class="mb-4 competition-description"',
            ],
        )

    def test_closed_registration_keeps_the_participant_list_before_documents(self):
        self.competition.registration_deadline = timezone.now() - datetime.timedelta(days=1)
        self.competition.save()
        html = self._html()
        self.assertNotIn(
            f'href="{in_language(reverse("registrations:register", args=[self.competition.pk]), "en")}"', html
        )
        self._assert_order(
            html,
            [
                f'href="{in_language(reverse("registrations:participant_list", args=[self.competition.pk]), "en")}"',
                f'href="{self.competition.url_route}"',
                'class="mb-4 competition-description"',
            ],
        )
