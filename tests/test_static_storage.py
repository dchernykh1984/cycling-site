"""Production's static storage: the trainer page names its own files by their hashed names."""

import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from cycling_site.storage import StaticFilesStorage
from tests import trainer_page

SKIN_TEMPLATE = '<img src="{% static \'skins/orange/img/logo.png\' %}" alt="">\n'


class TrainerPageHashedLinksTests(SimpleTestCase):
    """Collected as production collects it: the trainer's files, and a skin template beside them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(tempfile.mkdtemp())
        shutil.copytree(Path(settings.BASE_DIR) / "trainer" / "static" / "trainer", cls.root / "trainer")
        (cls.root / "orange" / "templates").mkdir(parents=True)
        (cls.root / "orange" / "templates" / "base.html").write_text(SKIN_TEMPLATE, encoding="utf-8")
        cls.storage = StaticFilesStorage(location=cls.root, base_url="/static/")
        names = [path.relative_to(cls.root).as_posix() for path in cls.root.rglob("*") if path.is_file()]
        for _name, _hashed, processed in cls.storage.post_process({name: (cls.storage, name) for name in names}):
            if isinstance(processed, Exception):
                raise processed
        cls.page = cls.storage.open(cls.storage.stored_name("trainer/alatau.html")).read().decode()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)
        super().tearDownClass()

    def test_the_page_links_the_hashed_versions_of_its_own_files(self):
        links = re.findall(r'(?:src|href)="(alatau/[^"]+)"', self.page)
        self.assertEqual(len(links), len(trainer_page.local_files()))
        for link in links:
            # the very file the page was built with: a changed script renames itself and the page
            name = "trainer/" + re.sub(r"\.[0-9a-f]{12}(\.(?:js|css))$", r"\1", link)
            self.assertNotEqual(name, "trainer/" + link, link)
            self.assertEqual("trainer/" + link, self.storage.stored_name(name))
            self.assertTrue(self.storage.exists("trainer/" + link), link)

    def test_addresses_with_a_scheme_stay_as_they_are(self):
        self.assertIn('src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"', self.page)
        self.assertIn('href="https://fonts.googleapis.com"', self.page)

    def test_a_skin_template_collected_beside_it_is_left_alone(self):
        self.assertEqual(self.storage.open("orange/templates/base.html").read().decode(), SKIN_TEMPLATE)
