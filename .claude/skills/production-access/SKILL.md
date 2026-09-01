---
name: production-access
description: Reaching the live site - a Django shell on the running instance, the database, uploaded media, and the logs. Read before touching anything in production.
---

# Production

The site runs on Render at `universalbicycle.team`. Secrets live in the repository's `.env`
(gitignored); load them with `set -a; source .env; set +a` before anything below.

## A shell on the running instance

`$RENDER_SSH` opens a shell on the same container that serves the site.

Piping a script in is more reliable than typing at an interactive shell, and `manage.py shell`
sometimes prints nothing when fed directly, so use a file:

```bash
ssh $RENDER_SSH 'cat > /tmp/task.py' < local_task.py
ssh $RENDER_SSH 'cd /opt/render/project/src && python manage.py shell < /tmp/task.py 2>&1'
```

Every such script starts with `sys.path.insert(0, "/opt/render/project/src")`.

The SSH banner prints warnings about post-quantum key exchange and a host-key signature; they are
noise from the host, not a failure. Filter them out of the output you read.

Scripts under `/tmp` on your own machine are not covered by the repository's ASCII rule, so Russian
text may be written there directly.

## Data

The database is PostgreSQL, reached through the Django ORM in that shell. Prefer the site's own
helpers over raw writes -- `add_location_child`, `soft_delete_location`, `Competition.approve` --
because they hold invariants the ORM does not.

Two deletes with different meanings:

- **Soft delete** (`is_deleted = True`) is what the site's own buttons do. A soft-deleted event
  becomes a deduplication key that the import agents are blocked from proposing again.
- **Hard delete** (`.delete()`) removes the row. This is what you want when the point is to let an
  agent propose the same event again.

## Media

`MEDIA_ROOT` is `/var/media`, a mounted disk that survives deploys. Files land under
`https://universalbicycle.team/media/...`. To put a file there:

```bash
ssh $RENDER_SSH 'mkdir -p /var/media/<folder>'
ssh $RENDER_SSH 'cat > /var/media/<folder>/<name>.jpg' < local.jpg
```

Downscale first -- a 4000 px product photo helps nobody -- and check the file answers 200 over HTTP
before referencing it.

## Logs

`/opt/render/project/src/logs/django.log` on the instance holds the application log of the *current*
container; it is ephemeral and carries no HTTP access lines, so crawler visits and per-request
detail are not there. Those live in Render's own dashboard logs.
