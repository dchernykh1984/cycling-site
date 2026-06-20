#!/usr/bin/env bash
# backup.sh - create a timestamped backup of the database and media files.
#
# Usage:
#   ./scripts/backup.sh              # dev/local: local DB + local media/
#   ./scripts/backup.sh --production # production: remote DB (SSL) + cr download media
#
# Production requires:
#   .env with DB_HOST, DB_NAME, DB_USER (DB_PASSWORD prompted interactively)
#   CR_TOKEN in env (for `cr download`)
#   CR_MEDIA_REMOTE_PATH in .env or env (defaults to /www/media)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
PRODUCTION=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --production) PRODUCTION=true ;;
        *) echo "Unknown argument: $1" >&2; echo "Usage: $0 [--production]" >&2; exit 1 ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
sha256_file() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

prompt_required() {
    local varname="$1"
    local prompt="$2"
    local value=""
    while [[ -z "$value" ]]; do
        read -rp "$prompt: " value
    done
    printf -v "$varname" '%s' "$value"
}

# ---------------------------------------------------------------------------
# Load .env (sets env vars without exporting to subshells permanently)
# ---------------------------------------------------------------------------
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

CR_MEDIA_REMOTE_PATH="${CR_MEDIA_REMOTE_PATH:-/www/media}"
# DJANGO_SETTINGS_MODULE default is set after we know the --production flag.

# ---------------------------------------------------------------------------
# Resolve DB connection parameters
# ---------------------------------------------------------------------------
if [[ "$PRODUCTION" == "true" ]]; then
    # Production: always use individual DB_* vars. DATABASE_URL may point to
    # the local dev DB and must be ignored to avoid backing up the wrong DB.
    DB_HOST="${DB_HOST:-}"
    DB_PORT="${DB_PORT:-5432}"
    DB_NAME="${DB_NAME:-}"
    DB_USER="${DB_USER:-}"
    DB_PASSWORD="${DB_PASSWORD:-}"
elif [[ -n "${DATABASE_URL:-}" ]]; then
    # Dev mode with DATABASE_URL: parse it.
    url="${DATABASE_URL#postgresql://}"
    url="${url#postgres://}"
    if [[ "$url" == *@* ]]; then
        userinfo="${url%%@*}"
        hostinfo="${url##*@}"
        DB_USER="${userinfo%%:*}"
        if [[ "$userinfo" == *:* ]]; then
            DB_PASSWORD="${userinfo#*:}"
        fi
    else
        # No userinfo (e.g. postgres://localhost/dbname) -- peer auth via OS user.
        hostinfo="$url"
        DB_USER="${DB_USER:-$(id -un)}"
    fi
    hostport="${hostinfo%%/*}"
    DB_NAME="${hostinfo#*/}"
    DB_HOST="${hostport%%:*}"
    raw_port="${hostport##*:}"
    if [[ "$raw_port" != "$DB_HOST" ]]; then
        DB_PORT="$raw_port"
    fi
else
    DB_HOST="${DB_HOST:-localhost}"
    DB_PORT="${DB_PORT:-5432}"
    DB_NAME="${DB_NAME:-}"
    DB_USER="${DB_USER:-}"
    DB_PASSWORD="${DB_PASSWORD:-}"
fi

# Guarantee these are always bound under set -u (URL without port/password leaves them unset).
DB_PORT="${DB_PORT:-5432}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Production mode requires all three vars from .env -- interactive prompts are not safe here.
if [[ "$PRODUCTION" == "true" ]]; then
    [[ -z "$DB_HOST" ]] && { echo "ERROR: DB_HOST must be set in .env for --production backup." >&2; exit 1; }
    [[ -z "$DB_NAME" ]] && { echo "ERROR: DB_NAME must be set in .env for --production backup." >&2; exit 1; }
    [[ -z "$DB_USER" ]] && { echo "ERROR: DB_USER must be set in .env for --production backup." >&2; exit 1; }
else
    if [[ -z "$DB_NAME" ]]; then prompt_required DB_NAME "Database name"; fi
    if [[ -z "$DB_USER" ]]; then prompt_required DB_USER "Database user"; fi
fi

# Stored in the manifest to record the backup context -- not used for manage.py commands.
# Production backups record prod settings even though manage.py runs with dev settings.
if [[ "$PRODUCTION" == "true" ]]; then
    MANIFEST_SETTINGS="${DJANGO_SETTINGS_MODULE:-cycling_site.settings.prod}"
else
    MANIFEST_SETTINGS="${DJANGO_SETTINGS_MODULE:-cycling_site.settings.dev}"
fi

if [[ "$PRODUCTION" == "true" ]]; then
    echo ""
    echo "=== PRODUCTION BACKUP ==="
    echo "DB host : ${DB_HOST}"
    echo "DB name : ${DB_NAME}"
    echo "DB user : ${DB_USER}"
    echo ""
    echo "DB_PASSWORD will be prompted (not read from .env)."
    read -rsp "DB password for ${DB_USER}@${DB_HOST}: " DB_PASSWORD
    echo ""
else
    if [[ -z "$DB_PASSWORD" ]]; then
        read -rsp "DB password for ${DB_USER}@${DB_HOST} (leave blank for peer auth): " DB_PASSWORD
        echo ""
    fi
fi

# Build a DATABASE_URL from resolved vars for Django management commands.
# Always run manage.py with cycling_site.settings.dev to avoid requiring
# production-only vars (SECRET_KEY, VIRTUAL_HOST) on the local machine.
TARGET_DATABASE_URL=$(
    DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" \
    DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" \
    python3 -c "
import urllib.parse, os
user = urllib.parse.quote(os.environ['DB_USER'], safe='')
pw   = urllib.parse.quote(os.environ['DB_PASSWORD'], safe='')
host = os.environ['DB_HOST']
port = os.environ['DB_PORT']
name = os.environ['DB_NAME']
print(f'postgresql://{user}:{pw}@{host}:{port}/{name}')
"
)

# ---------------------------------------------------------------------------
# Create backup directory
# ---------------------------------------------------------------------------
DATETIME=$(date +%Y-%m-%d_%H-%M)
BACKUP_DIR="backup/${DATETIME}"
mkdir -p "$BACKUP_DIR"
echo "Backup directory: ${BACKUP_DIR}"

# ---------------------------------------------------------------------------
# Dump database
# ---------------------------------------------------------------------------
echo "Dumping database..."
DB_DUMP="${BACKUP_DIR}/db.dump"

# PGSSLMODE is read by libpq; --sslmode is not a valid pg_dump CLI flag.
[[ "$PRODUCTION" == "true" ]] && export PGSSLMODE=require

PGPASSWORD="$DB_PASSWORD" pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --format=custom \
    --no-password \
    --no-acl \
    --no-owner \
    "$DB_NAME" \
    --file="$DB_DUMP"

echo "Database dump: ${DB_DUMP}"

# ---------------------------------------------------------------------------
# Backup media
# ---------------------------------------------------------------------------
MEDIA_ARCHIVE="${BACKUP_DIR}/media.tar.gz"

if [[ "$PRODUCTION" == "true" ]]; then
    if [[ -z "${CR_TOKEN:-}" ]]; then
        echo "ERROR: CR_TOKEN is required for production media download." >&2
        exit 1
    fi
    MEDIA_TMP="${BACKUP_DIR}/media_tmp"
    mkdir -p "$MEDIA_TMP"
    echo "Downloading production media via cr..."
    CR_STDERR_LOG=$(mktemp)
    if cr download cycling --remote "$CR_MEDIA_REMOTE_PATH" --path "$MEDIA_TMP" 2>"$CR_STDERR_LOG"; then
        echo "Archiving downloaded media..."
        tar -czf "$MEDIA_ARCHIVE" -C "$MEDIA_TMP" .
    elif grep -qi "No such file" "$CR_STDERR_LOG"; then
        cat "$CR_STDERR_LOG" >&2
        echo "WARNING: media directory not found on server (${CR_MEDIA_REMOTE_PATH}); creating empty archive."
        tar -czf "$MEDIA_ARCHIVE" -T /dev/null
    else
        cat "$CR_STDERR_LOG" >&2
        echo "ERROR: cr download failed (see above)." >&2
        rm -f "$CR_STDERR_LOG"
        exit 1
    fi
    rm -f "$CR_STDERR_LOG"
    rm -rf "$MEDIA_TMP"
else
    if [[ -d "media" ]]; then
        echo "Archiving local media/..."
        tar -czf "$MEDIA_ARCHIVE" -C . media
    else
        echo "media/ directory not found; creating empty archive."
        tar -czf "$MEDIA_ARCHIVE" -T /dev/null
    fi
fi

echo "Media archive: ${MEDIA_ARCHIVE}"

# ---------------------------------------------------------------------------
# Compute checksums
# ---------------------------------------------------------------------------
echo "Computing checksums..."
DB_SHA256=$(sha256_file "$DB_DUMP")
MEDIA_SHA256=$(sha256_file "$MEDIA_ARCHIVE")

# ---------------------------------------------------------------------------
# Collect metadata
# ---------------------------------------------------------------------------
GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Use dev settings + TARGET_DATABASE_URL so manage.py connects to the same DB
# we just dumped without needing production-only env vars locally.
APPLIED_MIGRATIONS=$(
    DATABASE_URL="$TARGET_DATABASE_URL" DJANGO_SETTINGS_MODULE="cycling_site.settings.dev" \
    uv run python manage.py showmigrations --list 2>/dev/null || echo "unavailable"
)

# ---------------------------------------------------------------------------
# Write manifest.json
# ---------------------------------------------------------------------------
MANIFEST="${BACKUP_DIR}/manifest.json"
python3 - <<PYEOF
import json, sys

data = {
    "timestamp": "$TIMESTAMP",
    "git_commit": "$GIT_COMMIT",
    "django_settings_module": "$MANIFEST_SETTINGS",
    "applied_migrations": """${APPLIED_MIGRATIONS}""",
    "db_dump_sha256": "$DB_SHA256",
    "media_sha256": "$MEDIA_SHA256",
}
with open("$MANIFEST", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
PYEOF

echo "Manifest: ${MANIFEST}"
echo ""
echo "Backup complete: ${BACKUP_DIR}"
echo "  db.dump   sha256: ${DB_SHA256}"
echo "  media     sha256: ${MEDIA_SHA256}"
