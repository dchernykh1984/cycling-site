"""Which commit the site runs (issue #153): the nightly deploy compares it with main before deploying."""

from django.conf import settings
from ninja import Router, Schema

router = Router(tags=["version"])


class VersionOut(Schema):
    commit: str


@router.get("", auth=None, response=VersionOut, summary="The commit the site runs")
def version(request) -> dict[str, str]:
    """Empty when the host does not name it; the nightly deploy then deploys main."""
    return {"commit": settings.RELEASE_COMMIT}
