# cycling-site

A Wagtail-based website for organizing cycling competitions, publishing news,
maintaining a knowledge base, and (in the future) running an online judge for
results processing.

## Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/docs/#installation) 1.8+
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
poetry install --no-root
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg
createdb cycling_site_dev
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
```

By default the project connects to `postgres://localhost/cycling_site_dev`
using the current OS user with no password. To use a different connection
string, copy `.env.example` to `.env` and set `DATABASE_URL`.

## Running the dev server

```bash
poetry run python manage.py runserver
```

Run `poetry run python manage.py migrate` again after pulling changes that
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

## License

See [LICENSE](LICENSE).
