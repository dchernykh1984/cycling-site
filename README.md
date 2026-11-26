# cycling-site

A Wagtail-based website that helps people organize sport and the activities around it wherever
people move -- cycling, running, skiing, hiking and the rest: an events calendar with registration,
timing and live results protocols, news and a knowledge base, in several languages.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL 14+
- Git

### Installing PostgreSQL

macOS:

```bash
brew install postgresql@16
brew services start postgresql@16
```

Debian / Ubuntu:

```bash
sudo apt install postgresql
sudo systemctl start postgresql
```

## First-time setup

```bash
git clone git@github.com:dchernykh1984/cycling-site.git
cd cycling-site
uv sync
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
createdb cycling_site_dev
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

By default the project connects to `postgres://localhost/cycling_site_dev`
using the current OS user with no password. To use a different connection
string, copy `.env.example` to `.env` and set `DATABASE_URL`.

## Running the dev server

```bash
uv run python manage.py runserver
```

Run `uv run python manage.py migrate` again after pulling changes that
include new migrations.

The dev server runs at:

- <http://localhost:8000/> - public site
- <http://localhost:8000/admin/> - Wagtail admin
- <http://localhost:8000/django-admin/> - Django admin

## Environment variables

Local development needs no environment variables by default: `dev.py` ships an
insecure `SECRET_KEY`, `ALLOWED_HOSTS = ["*"]`, and connects to a local
PostgreSQL database.

| Variable       | Used in | Default                                 |
| -------------- | ------- | --------------------------------------- |
| `DATABASE_URL` | dev     | `postgres://localhost/cycling_site_dev` |

Production configuration comes from environment variables set in the Render
dashboard - see [Deployment](#deployment).

## Deployment

Hosted on [Render](https://render.com/). A push to `main` runs the CI workflow; the site itself is
deployed at night (issue #153). The web service keeps its media on a persistent disk, and with a
disk Render stops the running instance before it starts the new one, so every deploy takes the
site down for up to a minute.

- **Render's auto-deploy is off.** `scripts/deploy_if_behind.py` deploys `main` between 21:00
  and 01:00 UTC (02:00-06:00 in Almaty) when the site names another commit at
  `/api/v1/version/` and every check `main`'s push started is green: CI, the Dropbox check, any
  added later. It waits up to 30 minutes for a check still running and deploys nothing while one
  is red, by night or by hand. It then waits until the site names `main`'s commit: a deploy that
  fails turns the run red.
- **The night run is a Render Cron Job**, `nightly-deploy` in `render.yaml`, at 21:07 UTC (02:07 in
  Almaty). GitHub starts a cron when it has capacity: hours late or not at all, so on three nights
  of the four from 2026-11-22 none of the workflow's hourly runs started inside the window. Render
  starts a cron on time, and e-mails a failed run when the workspace's notifications include
  failures (Integrations -> Notifications).
- **`.github/workflows/deploy.yml` is the fallback** for a night the Render run deployed nothing: it
  asks for a run at 22:37, 23:37 and 00:37 UTC, after the Render run has ended (it waits at most 50
  minutes), so the two never deploy at once. A run that finds the site on `main`, or starts after
  01:00, does nothing.
- **An urgent change** goes out with the workflow's "Run workflow" (`gh workflow run deploy.yml`)
  or with Render's Manual Deploy. Both take the site down for up to a minute.
- **Setting it up:** the web service's deploy hook (Render: Settings -> Deploy Hook) goes into the
  secret `RENDER_DEPLOY_HOOK_URL` of the `production` environment (below), and Render's Auto-Deploy
  (Settings -> Build & Deploy) is set to Off. The Cron Job comes from the Blueprint: Render -> New ->
  Blueprint, this repository, branch `main`. Render asks once for `RENDER_DEPLOY_HOOK_URL`, the same
  hook, and for `GITHUB_TOKEN`, a fine-grained token with read-only access to public repositories
  and no other permission: without one GitHub answers 60 requests an hour per address, and Render's
  outbound addresses are shared. The hook now lives in both places: a regenerated one goes into the
  GitHub secret and into the Cron Job's variable. The Cron Job's Trigger Run in the daytime shows
  that it builds and starts: the run says it is outside the window and deploys nothing, before it
  reads GitHub or calls the hook, so the token and the hook are first used at night.
- **The secrets of GitHub Actions** live in the repository's `production` environment (Settings ->
  Environments), whose deployment branches are `main` only. A job receives them only when it names
  the environment and runs from `main`: a workflow pushed on any other branch, a collaborator's or a
  fork's, gets none, and `main` changes only through a reviewed pull request. None is kept as a
  repository secret, which every branch's workflow could read. The deploy, the agents and the
  Dropbox check run by hand, or run again, for the repository's owner only; CI's model check runs on
  every push to `main`, whoever starts it again.
- **Render runs `python manage.py migrate`** as a pre-deploy step.

Configuration comes from environment variables set in the Render dashboard:

- `DATABASE_URL` - PostgreSQL connection (Render Postgres); `prod.py` also accepts
  discrete `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` as a fallback
- `SECRET_KEY` - Django secret key (or `RANDOM_SECRET_KEY`)
- `PRIMARY_HOST` - canonical host for absolute URLs (sitemap, account emails, Wagtail
  admin); the custom `migrate` command syncs the Wagtail Site and the
  `django.contrib.sites` Site to it on every deploy
- `MEDIA_ROOT` - path to the mounted persistent disk that stores uploaded media
- `RELEASE_COMMIT` - the commit `/api/v1/version/` names; unset, Render's own `RENDER_GIT_COMMIT`
- `INTEGRATIONS_ENCRYPTION_KEY` - the Fernet key members' intervals.icu API keys and Strava tokens are
  sealed with (issue #471); unset, neither intervals.icu nor uploads to Strava are offered. Generate it with
  `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` and keep a copy:
  a lost key leaves the stored keys and tokens unreadable, and those members connect again.
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` - SMTP (Gmail)
- `ADMINS` - comma-separated error email recipients (defaults to `DEFAULT_FROM_EMAIL`);
  `SERVER_EMAIL` - error sender (defaults to `DEFAULT_FROM_EMAIL`);
  `EMAIL_TIMEOUT` - SMTP operation timeout in seconds (default 5)
- `CALENDAR_FIRST_WEEKDAY`, `CALENDAR_WEEKEND` - the calendar's week: the day it starts on and the
  weekend's days, 0 for Sunday (defaults `1` and `6,0`: Monday, and Saturday with Sunday)
- `MAP_LINK_SERVICES` - the map services an event's start point is offered in, in order: keys of
  `MAP_SERVICES` in `cycling_site/settings/base.py`, comma-separated (`prod.py` defaults to
  `2gis,yandex,google,apple,osm`; a key the catalogue lacks is reported by `manage.py check`)
- `GOOGLE_`/`GITHUB_`/`STRAVA_` `CLIENT_ID` and `CLIENT_SECRET` - social login; the Strava pair also
  sends members' virtual rides to Strava once they connect it on their profile
- `ASSISTANT_LLM_API_KEY` - the event assistant's key at its model provider; without it the chat is
  not offered. `ASSISTANT_LLM_BASE_URL` names another OpenAI-compatible provider (default
  `https://api.deepseek.com`)

The team domain (`universalbicycle.team` and `www.universalbicycle.team`) is always
in `ALLOWED_HOSTS`; set `VIRTUAL_HOST` to add more hosts. Static files are served by
WhiteNoise. DNS is managed by Cloudflare, with the apex `universalbicycle.team` as
the canonical host and `www` redirecting to it.

The apex is a proxied record (`CNAME @ -> cycling-site.onrender.com`, the orange cloud, SSL mode
Full), and the zone's "Add visitor location headers" managed transform is on: the guest's region
(#332) is read from those headers, so a grey cloud leaves every guest with the whole calendar. The
proxy gives up on an answer after 100 seconds, which is why the assistant waits for its model 90.
Keep the zone's Bot Fight Mode off: it would challenge the import agents' calls to the API.
The zone's Browser Integrity Check refuses Python's default user agent (`Python-urllib/3.x`,
403 "error code: 1010"), so every client of the API sends a name of its own -- the agents do --
and the check is off for `/api/` (a Configuration Rule), for the timing tools already in the field.

`gunicorn.conf.py` provides four threads per worker; the thumbnail service uses at most two for
storage downloads, leaving capacity for form submissions. On the small Render instance keep
`WEB_CONCURRENCY=1`. With Render's `--preload`, Gunicorn worker errors use the same admin email
handler as Django 500s. Proxy errors without a running application require external monitoring.

The read-only `Dropbox Integration` workflow checks a real index and decodes one thumbnail on
pushes to main and on manual dispatch. Set `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET` and
`DROPBOX_TEST_FOLDER_URL` (a shared folder containing `photo-index.v1.json` and at least one usable
photo/preview) as secrets of the `production` environment. Keep that fixture available; a
dedicated small album is preferable. No pull request receives these secrets, so a change is
checked once it is merged. The check tries up to ten times a minute apart, so a moment's outage at
Dropbox does not turn `main` red; a longer one does, and holds the deploy until it passes. Normal unit tests skip this network check; no race photos or shared
links are committed as fixtures.

Live site: <https://universalbicycle.team>.

## Specifications

The site is built spec-first with [Spec Kit](https://github.com/github/spec-kit). Every area of the
site is described as it works today in [`specs/site/`](specs/site/); a new feature gets its own
specification, plan and tasks in `specs/<issue>-<short-name>/` before it is built; the principles
every plan is checked against are the [constitution](.specify/memory/constitution.md). How to work
with them -- from Claude Code or Codex -- is in [`specs/README.md`](specs/README.md).

## REST API

The site exposes a REST API at `/api/v1/`. It supports admin CRUD for
competitions and news articles, read-only knowledge articles, CRUD for locations,
plus endpoints for participant list retrieval and protocol file uploads used by
the offline referee tools. Community submission of news/knowledge happens through
the on-site web forms, not the API.

All write operations require a Bearer token: `Authorization: Bearer <token>`.
Participants and higher can generate their personal API token on the profile page.
The full interactive API reference (Swagger UI) is linked from the profile page
after the token is generated.

## User roles

The role hierarchy is `guest < participant < organizer < admin < owner`, defined
in `accounts.User.Role` and stored on `accounts.User.role`. Each role includes
every capability of the roles below it.

Notes:

- **Anonymous** visitors are not a role: they can read public pages, public
  list/detail views and optional-auth read APIs, but cannot perform actions.
- New users register as **Guest** and are promoted to **Participant**
  automatically once they confirm their email.
- Saving a user with `role = owner` forces `is_staff = True` and
  `is_superuser = True`. `is_superuser` bypasses most checks, but editing the
  home page / `SiteContent` specifically requires `role = owner`.
- Role-gated API actions use `Authorization: Bearer <api_token>`; regenerating a
  personal API token requires `participant+`.
- Proposing locations and competitions requires `participant+`; a guest must
  confirm their email first.
- Capabilities exposed through Wagtail/Django admin are granted via the per-role
  groups (`Participants`/`Organizers`/`Admins`/`Owners`) plus
  `is_staff`/`is_superuser`, which are kept in sync with the role.
- Uploading protocols and listing participants via a competition's
  `competition_token` is outside the user-role system.

### Guest (`guest`)

- Browse the public calendar, competition list/map, news, knowledge base,
  locations and public read-only APIs.
- Sign in, edit basic profile data, theme and language.
- Resend the email confirmation while the address is unverified.
- Is promoted to **Participant** automatically after confirming email.

### Participant (`participant`)

- Everything a Guest can do.
- Regenerate a personal API token and use the Bearer-auth API.
- Propose competitions through the web form (sent to moderation).
- Propose a new venue together with a competition and use that pending venue
  immediately.
- Propose locations through the web form and the API (kept pending until
  moderated).
- Register for approved competitions, including entering a team in the entry.
- Comment on competitions and news.
- Submit news and knowledge-base articles for moderation through the on-site web
  forms (the draft submission/edit API has been removed).
- See their registrations and submissions in their profile, and manage their own
  submitted competitions via the API (without changing `is_hidden`).

### Organizer (`organizer`)

- Everything a Participant can do.
- Create competitions through the web form as **approved** immediately -- unless
  the event sits on a location still under review (a region or city proposed but
  not yet blessed), in which case it stays pending until an Admin approves the
  geography. Through the API a created competition is **pending approval**.
- Configure registration, categories, limits, payment, approval, relay and
  related fields for their own competitions.
- Edit, hide and soft-delete their own competitions, and see their upload tokens.
- Moderate pending competitions (approve/reject); approving a competition
  auto-approves the venue proposed with it. The region and city proposed
  alongside stay pending -- blessing geography is an Admin right, so approving an
  event is not a way around it. An event whose region or city is still under
  review therefore **cannot** be approved by an Organizer (the attempt is
  refused, "the location is still awaiting review"), and such events are hidden
  from the Organizer's moderation queue -- only an Admin, who can also approve the
  geography, sees and clears them.
- Add an approved venue under a city via web/API without separate moderation.
- **Propose** a region or a city via web/API. An Organizer's region or city is
  always a proposal -- visible only to them until an Admin approves it (an Admin
  creating one gets it approved outright). Countries stay Admin-only. A venue
  added under a location that is still pending stays pending with it.
- Get (or lazily create) a city's shared **catch-all venue** via the API, to attach a
  competition to a city when no exact start venue is known.
- Manage entrants of their own competitions: approve/reject, mark paid, edit,
  delete, add manually (free registration) and export to CSV.
- Delete comments on their own competitions.

### Admin (`admin`)

- Everything an Organizer can do.
- See hidden competitions, news, knowledge articles and hidden/pending
  locations.
- Manage **all** competitions globally: edit, hide/unhide, soft-delete,
  registration settings, categories and participants.
- Via the API: create approved competitions and toggle `is_hidden`.
- Moderate proposed locations directly (approve/reject); edit, hide and
  soft-delete any location; create hidden fallback venues and structural
  location nodes.
- Create, edit, hide and soft-delete news articles, and delete comments on news.
- Add knowledge-base articles directly, approve/reject submissions, hide/delete
  articles. Via the API: full CRUD for news articles; knowledge articles are
  read-only (authored and moderated on-site).
- In Wagtail/Django admin: manage users up to the `admin` role (cannot assign or
  demote `owner`) and manage the Teams snippet.

### Owner (`owner`)

- Everything an Admin can do.
- Is automatically staff/superuser and passes superuser-only checks.
- Edit the home page and the global `SiteContent`.
- View the audit log.
- Assign and change any role, including `owner`, and edit privilege fields
  (`is_staff`, `is_superuser`, groups, permissions).
- Full Django/Wagtail admin access, including deleting users.

### Manually confirming a user's email

If the confirmation email was not received, an admin can manually mark the
address as verified in two steps:

1. **Django admin** - `/django-admin/account/emailaddress/` - find the record
   by email, set **Verified** to checked, save.
2. **Django admin** - `/django-admin/accounts/user/` - find the user, change
   **Role** from `guest` to `participant`, save.

Step 1 alone does not change the role; both steps are required.

### Granting Owner access

Owner is the highest role: it gives full Wagtail admin access and Django
superuser rights. After a user registers, promote them in two admin panels:

**1. Wagtail admin** - <https://universalbicycle.team/admin/users/>

- Find the user, click Edit
- Check **Administrator**
- Add the **owner** group, remove all other groups
- Save

**2. Django admin** - <https://universalbicycle.team/django-admin/accounts/user/>

- Find the user, click their username
- Set **Role** to `owner`
- In the **Groups** section: add the **owner** group, remove all other groups
- Save

Both steps are required. Skipping the Django admin step leaves the user without
the correct role, and skipping the Wagtail step leaves them without Wagtail
admin access.

## Backup and restore

Scripts live in `scripts/`. They require `pg_dump` / `pg_restore` (PostgreSQL
client tools) to be installed, and must be run from the project root with
[uv](https://docs.astral.sh/uv/) available on `PATH` (the scripts call
`uv run python manage.py` internally).

### Local backup

```bash
./scripts/backup.sh
```

Prompts for a DB password (leave blank if using peer auth), then writes a
timestamped directory to `backup/YYYY-MM-DD_HH-MM/` containing:

- `db.dump` - PostgreSQL custom-format dump
- `media.tar.gz` - contents of the `media/` directory
- `manifest.json` - timestamp, git commit, applied migrations, SHA-256 hashes

### Production backup

```bash
# .env: DB_HOST, DB_NAME, DB_USER (DB_PASSWORD is prompted) plus RENDER_SSH
# (and optional RENDER_MEDIA_PATH, default /var/media) for media collection.
./scripts/backup.sh --production
```

Prompts for `DB_PASSWORD` interactively (not stored in `.env`) and connects to the
production database over SSL (`PGSSLMODE=require`). Media is pulled from the Render web
service's persistent disk over SSH (needs `RENDER_SSH` and your SSH public key in the
Render account; the disk path defaults to `/var/media`, override with `RENDER_MEDIA_PATH`).

### Local restore

```bash
./scripts/restore.sh backup/2026-06-10_23-17
```

Validates SHA-256 checksums, then restores the database and media, and runs
`manage.py migrate`. Refuses to run if `DB_HOST` is not `localhost` / `127.0.0.1`.

### Production restore

```bash
./scripts/restore.sh backup/2024-06-01_14-30 --production-restore
```

Prompts for `DB_PASSWORD` and requires you to type the DB host name to confirm before
any destructive action. After the DB restore it **also syncs media**, uploading it to the
Render web service's persistent disk over SSH (the same `RENDER_SSH` used by backup).

#### Media-only restore, and why it exists

```bash
./scripts/restore.sh backup/2024-06-01_14-30 --production-restore --media-only
```

`--media-only` skips the database completely (no schema reset / `pg_restore` / migrate)
and only syncs media. It is needed because **the DB restore and the media sync cannot run
together against a live service**:

- The DB restore drops and recreates the schema. If the web service is **running**, its
  requests write to the DB mid-restore (e.g. the `SiteContent` singleton is re-created) and
  collide with the dump, so the restore fails with duplicate-key errors.
- Media, in contrast, needs the service **running**: the persistent disk only mounts on a
  live instance.

So a **live** host (e.g. Render) is restored in two passes:

1. **Suspend** the web service, then run `--production-restore` (the DB restores with no
   concurrent writes; the media step is skipped/warns while the service is suspended).
2. **Resume** the service, then run `--production-restore --media-only` (uploads media to
   the now-running instance without touching the DB).

The `backup/` directory is git-ignored.

## License

See [LICENSE](LICENSE).
