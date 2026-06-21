# cycling-site

A Wagtail-based website for organizing cycling competitions, publishing news,
maintaining a knowledge base, and (in the future) running an online judge for
results processing.

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

Production variables are provided automatically by CodeRed - see
[Deployment](#deployment).

## Deployment

Auto-deploys to [CodeRed Cloud](https://www.codered.cloud/) via GitHub Actions:
a push to `main` triggers the CI workflow, and a successful run triggers the
deploy workflow.

In production the project reads its configuration from the environment variables
CodeRed provides automatically:

- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - PostgreSQL connection
- `RANDOM_SECRET_KEY` - Django secret key (or set your own `SECRET_KEY`)
- `VIRTUAL_HOST` - the site domain, used for `ALLOWED_HOSTS` and the Wagtail
  admin base URL

No manual database or host configuration is required in the dashboard.

Live site: <https://cycling.codered.cloud>.

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
- Create competitions through the web form as **approved** immediately, or
  through the API as **pending approval**.
- Configure registration, categories, limits, payment, approval, relay and
  related fields for their own competitions.
- Edit, hide and soft-delete their own competitions, and see their upload tokens.
- Moderate pending competitions (approve/reject); approving a competition
  auto-approves the location proposed with it.
- Add an approved venue under a city via web/API without separate moderation.
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

**1. Wagtail admin** - <https://cycling.codered.cloud/admin/users/>

- Find the user, click Edit
- Check **Administrator**
- Add the **owner** group, remove all other groups
- Save

**2. Django admin** - <https://cycling.codered.cloud/django-admin/accounts/user/>

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
# Requires: DB_HOST, DB_NAME, DB_USER in .env; CR_TOKEN in env
./scripts/backup.sh --production
```

Prompts for `DB_PASSWORD` interactively (not stored in `.env`). Downloads media
via `cr download`. Connects to the production database over SSL (`PGSSLMODE=require`).

The remote media path defaults to `/www/media`. If the actual path on the server
differs, set `CR_MEDIA_REMOTE_PATH` in `.env` (verify via `cr sftp cycling`).

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

Prompts for `DB_PASSWORD` and requires you to type the DB host name to confirm
before any destructive action is taken.

> **Media note:** production media is **not** restored by this script - the
> archive cannot be uploaded to the remote server locally. After a successful
> DB restore, upload `media.tar.gz` from the backup directory to the server
> manually (e.g. via `cr sftp cycling`).

The `backup/` directory is git-ignored.

## License

See [LICENSE](LICENSE).
