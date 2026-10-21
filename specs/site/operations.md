# Site Specification: Running the site

**Status**: Baseline -- describes the system as it works today
**Verified against**: `main` on 2026-10-21
**Code**: `cycling_site/settings/` (`base.py`, `prod.py`), `scripts/backup.sh`, `scripts/restore.sh`,
`scripts/restore_smoke_test.sh`, `.github/workflows/`, `accounts/management/commands/migrate.py`
**Tests**: `cycling_site/tests.py` (logging, media), `accounts/tests.py` (initial superuser, site
host), `tests/test_agent_schedules.py`
**Related**: the `production-access` and `shipping-changes` skills; `README.md` ("Deployment",
backups)

## Overview

The site runs on Render behind Cloudflare. A push to `main` runs CI and Render deploys the commit,
migrating the database before it serves. Backups of the database and media can be taken and
restored, locally or onto production.

## User Scenarios

### Story 1 -- Ship a change (P1)

1. **Given** a pull request, **Then** CI runs pre-commit (ruff, mypy, ASCII, requirements export),
   commitizen, the unit tests with coverage of 90% or more, the dependency audit, the browser suite on
   five browser/device combinations and once per skin, and the light/dark screenshot comparison.
2. **Given** a merge to `main`, **Then** Render deploys it, running `migrate` as a pre-deploy step;
   configuration comes from environment variables set on Render.

### Story 2 -- Keep the data safe (P1)

1. **Given** `scripts/backup.sh` (`--production` for the live site), **Then** a timestamped backup
   holds the database dump and the media files (pulled over SSH from the Render disk).
2. **Given** `scripts/restore.sh`, **Then** a backup is restored into a scratch or local database
   (schema reset, then restore, then migrate); a live host is restored in two passes (database while
   suspended, media once running).
3. **Given** a change touching many rows, **Then** it is tried first against a restored backup.

### Story 3 -- Look into production (P2)

1. **Given** the maintainer's SSH access, **Then** a shell on the running container runs management
   scripts; the application log of the current container is at `logs/django.log`; HTTP access logs
   are in Render's dashboard.
2. **Given** a server error, **Then** it is mailed to the admins (not in debug).

### Edge Cases

- Media lives on a mounted disk (`/var/media`) that survives deploys; the site serves it itself.
- On deploy the default Wagtail/Django site's host is synced from the primary host setting.
- The events agents run on GitHub Actions on their own schedules, independent of deploys.

## Functional Requirements

- **FR-OPS-001**: Secrets and hosts come from the environment, never from the repository.
- **FR-OPS-002**: Dependencies are locked with uv; `requirements.txt` is exported from the lock.

## Key Entities

- None of its own.

## Local assumptions

- Production settings list the site's own host names in code (`cycling_site/settings/prod.py`:
  `universalbicycle.team`, `www.universalbicycle.team`) beside those read from the environment.

## Open Questions

- None known.
