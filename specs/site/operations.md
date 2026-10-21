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
2. **Given** `scripts/restore.sh`, **Then** a backup is restored into the local database, or onto
   production with `--production-restore` (schema reset, then restore, then migrate); a live host is
   restored in two passes -- the database while the service is suspended, then the media
   (`--media-only`) once it runs again.
3. **Given** a change touching many rows, **Then** the practice is to try it first against a
   restored backup in a scratch database (the `production-access` skill).

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

- **FR-OPS-001**: Secrets come from the environment, never from the repository; so do the hosts,
  apart from the site's own names listed under "Local assumptions".
- **FR-OPS-002**: Dependencies are locked with uv; `requirements.txt` is exported from the lock.

## Key Entities

- None of its own.

## Local assumptions

- Production settings list the site's own host names in code (`cycling_site/settings/prod.py`:
  `universalbicycle.team`, `www.universalbicycle.team`) beside those read from the environment.

## Open Questions

- None known.
