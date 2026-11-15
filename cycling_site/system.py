"""What the server has: the disk the site keeps its files on."""

import shutil
from pathlib import Path

from django.conf import settings


def media_disk():
    """The disk MEDIA_ROOT is on, measured at its nearest folder that exists yet."""
    path = Path(settings.MEDIA_ROOT)
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path)
