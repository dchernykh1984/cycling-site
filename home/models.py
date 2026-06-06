from typing import ClassVar

from wagtail.models import Page
from wagtail_localize.fields import SynchronizedField


class HomePage(Page):
    override_translatable_fields: ClassVar[list] = [
        SynchronizedField("slug", overridable=False),
    ]
