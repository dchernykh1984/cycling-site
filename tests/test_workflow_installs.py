"""A job that holds the production secrets installs only what uv.lock names, each file checked by its hash:
a package installed by name alone takes whatever release came out last, and runs beside the secrets."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _jobs_with_secrets():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for name, job in (yaml.safe_load(path.read_text())["jobs"] or {}).items():
            if job.get("environment") == "production":
                yield pytest.param(job, id=f"{path.name}:{name}")


JOBS = list(_jobs_with_secrets())


def test_the_jobs_with_secrets_are_found():
    assert len(JOBS) >= 4, JOBS  # the deploy, both agents, the Dropbox check, the model check


@pytest.mark.parametrize("job", JOBS)
def test_a_job_with_production_secrets_installs_only_hashed_packages(job):
    for step in job.get("steps", []):
        for line in step.get("run", "").splitlines():
            if re.search(r"\bpip3? install\b", line):
                assert "--require-hashes" in line, line
            assert not re.search(r"\buvx\b", line), line  # runs the newest release of a tool
