# Site Specification: Running the site

**Status**: Baseline -- describes the system as it works today
**Verified against**: `main` on 2026-10-21; the night deploy's two schedules against branch
nightly-deploy-render-cron on 2026-11-26
**Code**: `cycling_site/settings/` (`base.py`, `prod.py`), `scripts/backup.sh`, `scripts/restore.sh`,
`scripts/restore_smoke_test.sh`, `scripts/deploy_if_behind.py`, `render.yaml`, `.github/workflows/`,
`accounts/management/commands/migrate.py`
**Tests**: `cycling_site/tests.py` (logging, media), `accounts/tests.py` (initial superuser, site
host), `tests/test_agent_schedules.py`, `tests/test_deploy_if_behind.py`
**Related**: the `production-access` and `shipping-changes` skills; `README.md` ("Deployment",
backups)

## Overview

The site runs on Render behind Cloudflare. A push to `main` runs CI; the site is deployed at night
(issue #153), migrating the database before it serves. Backups of the database and media can be taken and
restored, locally or onto production.

## User Scenarios

### Story 1 -- Ship a change (P1)

1. **Given** a pull request, **Then** CI runs pre-commit (ruff, mypy, ASCII, requirements export),
   commitizen, the unit tests with coverage of 90% or more, the dependency audit, and the browser
   suite on five browser/device combinations and once per skin.
2. **Given** a merge to `main`, **Then** it reaches the site at night. The web service's auto-deploy
   is off. `scripts/deploy_if_behind.py` deploys `main` between 21:00 and 01:00 UTC (02:00-06:00 in
   Almaty), and only when two things hold: the site names another commit at `/api/v1/version/`, and
   every check `main`'s push started is green (CI, the Dropbox check, any added later). It waits up
   to 30 minutes for a check still running, and a red one holds the deploy, by night or by hand. It
   then waits until the site names the new commit, so a deploy that fails turns the run red.
   - The night run is a Render Cron Job at 21:07 UTC (`render.yaml`). GitHub starts a cron when it
     has capacity: on three nights of the four from 2026-11-22 none of the workflow's hourly runs
     started inside the window. Render e-mails a failed run when the workspace's notifications
     include failures.
   - `.github/workflows/deploy.yml` is the fallback: GitHub is asked for a run at 22:37, 23:37 and
     00:37 UTC, after the Render run has ended, so the two never deploy at once.
   - An urgent change goes out by running the workflow by hand, or with Render's Manual Deploy.
   - Render runs `migrate` as a pre-deploy step.
   - Configuration comes from environment variables set on Render.
3. **Given** a reader's request, **Then** it passes through the site's Cloudflare zone -- the apex
   record is proxied -- which adds the visitor location headers the guest's region is read from
   (#332, [calendar](calendar.md)) and gives up on an answer after 100 seconds (the README's
   Deployment section). Its Browser Integrity Check refuses Python's default user agent (403,
   "error code: 1010"), so the import agents name themselves (`agent/site_api.py`); for `/api/`
   the check is to be switched off, since the timing tools in the field send that default.

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
  apart from the site's own names listed under "Local assumptions". The secrets of GitHub Actions
  are the `production` environment's, whose deployment branches are `main` only: no workflow on
  another branch receives them, and none is a repository secret. The deploy, the agents and the
  Dropbox check run by hand, or run again, for the repository's owner only.
- **FR-OPS-002**: Dependencies are locked with uv; `requirements.txt` is exported from the lock, and
  so is `requirements-agents.txt`, with hashes, for the agents' jobs (FR-AGT-007 in events-agents.md).
- **FR-OPS-003**: An upload opened at its `/media/` address cannot act as a page of the site
  (`cycling_site/urls.py`, `serve_media`): every file but a PDF carries `Content-Security-Policy:
  sandbox` (a browser's PDF viewer may refuse a sandboxed document), and HTML and XML are downloaded
  rather than shown. The private prefix and the protocol folders are not served there at all.

## Key Entities

- None of its own.

## Local assumptions

- Production settings list the site's own host names in code (`cycling_site/settings/prod.py`:
  `universalbicycle.team`, `www.universalbicycle.team`) beside those read from the environment.
- Production settings name Cloudflare's `CF-Connecting-IP` as the header holding a visitor's address
  (Render passes every request through Cloudflare); `CLIENT_IP_HEADER` in the environment names
  another host's header, or none.

## Open Questions

- None known.
