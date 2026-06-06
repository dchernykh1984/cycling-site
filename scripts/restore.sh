#!/usr/bin/env bash
# restore.sh - restore a backup created by backup.sh.
#
# Usage:
#   ./scripts/restore.sh <backup-dir>                    # restore to local/dev DB
#   ./scripts/restore.sh <backup-dir> --production-restore  # restore to production DB (requires confirmation)
#
# <backup-dir>: path to a backup directory containing db.dump, media.tar.gz, manifest.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
BACKUP_DIR=""
PRODUCTION_RESTORE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --production-restore) PRODUCTION_RESTORE=true ;;
        -*) echo "Unknown flag: $1" >&2; echo "Usage: $0 <backup-dir> [--production-restore]" >&2; exit 1 ;;
        *) BACKUP_DIR="$1" ;;
    esac
    shift
done

if [[ -z "$BACKUP_DIR" ]]; then
    echo "Usage: $0 <backup-dir> [--production-restore]" >&2
    exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "ERROR: backup directory not found: ${BACKUP_DIR}" >&2
    exit 1
fi

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

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# ---------------------------------------------------------------------------
# Resolve DB connection parameters
# ---------------------------------------------------------------------------
if [[ "$PRODUCTION_RESTORE" == "true" ]]; then
    # Production: always use individual DB_* vars. DATABASE_URL may point to
    # the local dev DB and must be ignored to avoid restoring the wrong DB.
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

# Production mode requires all three vars from .env -- fail early before any destructive action.
if [[ "$PRODUCTION_RESTORE" == "true" ]]; then
    [[ -z "$DB_HOST" ]] && { echo "ERROR: DB_HOST must be set in .env for --production-restore." >&2; exit 1; }
    [[ -z "$DB_NAME" ]] && { echo "ERROR: DB_NAME must be set in .env for --production-restore." >&2; exit 1; }
    [[ -z "$DB_USER" ]] && { echo "ERROR: DB_USER must be set in .env for --production-restore." >&2; exit 1; }
fi

# ---------------------------------------------------------------------------
# Read and display manifest
# ---------------------------------------------------------------------------
MANIFEST="${BACKUP_DIR}/manifest.json"
if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest.json not found in ${BACKUP_DIR}" >&2
    exit 1
fi

echo ""
echo "=== BACKUP MANIFEST ==="
python3 - <<PYEOF
import json
with open("$MANIFEST") as f:
    m = json.load(f)
print(f"  Timestamp      : {m.get('timestamp', 'unknown')}")
print(f"  Git commit     : {m.get('git_commit', 'unknown')}")
print(f"  Settings module: {m.get('django_settings_module', 'unknown')}")
print(f"  db.dump  sha256: {m.get('db_dump_sha256', 'unknown')}")
print(f"  media    sha256: {m.get('media_sha256', 'unknown')}")
PYEOF
echo ""

# ---------------------------------------------------------------------------
# Production restore confirmation
# ---------------------------------------------------------------------------
if [[ "$PRODUCTION_RESTORE" == "true" ]]; then
    echo "!!! WARNING: PRODUCTION RESTORE !!!"
    echo ""
    echo "Target database:"
    echo "  Host : ${DB_HOST}"
    echo "  Name : ${DB_NAME}"
    echo "  User : ${DB_USER}"
    echo ""
    echo "This will OVERWRITE all data in the production database."
    echo ""
    echo "NOTE: Production media is NOT restored by this script."
    echo "      After DB restore, upload media.tar.gz to the server manually"
    echo "      (e.g. via cr sftp cycling or your deployment workflow)."
    echo ""
    read -rsp "DB password for ${DB_USER}@${DB_HOST}: " DB_PASSWORD
    echo ""
    echo ""
    read -rp "Type the DB host name (${DB_HOST}) to confirm: " CONFIRM_HOST
    if [[ "$CONFIRM_HOST" != "$DB_HOST" ]]; then
        echo "Confirmation failed. Aborting." >&2
        exit 1
    fi
else
    # Safety: refuse to restore to a remote host without the explicit production flag.
    if [[ "$DB_HOST" != "localhost" && "$DB_HOST" != "127.0.0.1" && -n "$DB_HOST" ]]; then
        echo "ERROR: DB_HOST=${DB_HOST} is not localhost." >&2
        echo "To restore to a remote database use --production-restore (requires typed confirmation)." >&2
        exit 1
    fi

    echo "Target database:"
    echo "  Host : ${DB_HOST}"
    echo "  Name : ${DB_NAME}"
    echo "  User : ${DB_USER}"
    echo ""
    if [[ -z "$DB_PASSWORD" ]]; then
        read -rsp "DB password for ${DB_USER}@${DB_HOST} (leave blank for peer auth): " DB_PASSWORD
        echo ""
    fi
    echo ""
    read -rp "Proceed with restore? This will overwrite local DB data [y/N]: " CONFIRM
    if [[ "${CONFIRM,,}" != "y" ]]; then
        echo "Aborted." >&2
        exit 1
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
# Validate checksums
# ---------------------------------------------------------------------------
echo ""
echo "Validating checksums..."

DB_DUMP="${BACKUP_DIR}/db.dump"
MEDIA_ARCHIVE="${BACKUP_DIR}/media.tar.gz"

if [[ ! -f "$DB_DUMP" ]]; then
    echo "ERROR: db.dump not found in ${BACKUP_DIR}" >&2
    exit 1
fi
if [[ ! -f "$MEDIA_ARCHIVE" ]]; then
    echo "ERROR: media.tar.gz not found in ${BACKUP_DIR}" >&2
    exit 1
fi

EXPECTED_DB_SHA=$(python3 -c "import json; m=json.load(open('$MANIFEST')); print(m.get('db_dump_sha256',''))")
EXPECTED_MEDIA_SHA=$(python3 -c "import json; m=json.load(open('$MANIFEST')); print(m.get('media_sha256',''))")

ACTUAL_DB_SHA=$(sha256_file "$DB_DUMP")
ACTUAL_MEDIA_SHA=$(sha256_file "$MEDIA_ARCHIVE")

if [[ "$ACTUAL_DB_SHA" != "$EXPECTED_DB_SHA" ]]; then
    echo "ERROR: db.dump checksum mismatch!" >&2
    echo "  Expected: ${EXPECTED_DB_SHA}" >&2
    echo "  Actual  : ${ACTUAL_DB_SHA}" >&2
    exit 1
fi
echo "  db.dump   OK (${ACTUAL_DB_SHA})"

if [[ "$ACTUAL_MEDIA_SHA" != "$EXPECTED_MEDIA_SHA" ]]; then
    echo "ERROR: media.tar.gz checksum mismatch!" >&2
    echo "  Expected: ${EXPECTED_MEDIA_SHA}" >&2
    echo "  Actual  : ${ACTUAL_MEDIA_SHA}" >&2
    exit 1
fi
echo "  media.tar.gz OK (${ACTUAL_MEDIA_SHA})"

# ---------------------------------------------------------------------------
# Restore database
# ---------------------------------------------------------------------------
echo ""
echo "Restoring database..."

# PGSSLMODE is read by libpq; --sslmode is not a valid pg_restore CLI flag.
[[ "$PRODUCTION_RESTORE" == "true" ]] && export PGSSLMODE=require

PGPASSWORD="$DB_PASSWORD" pg_restore \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --clean \
    --if-exists \
    --no-password \
    "$DB_DUMP"

echo "Database restored."

# ---------------------------------------------------------------------------
# Restore media
# ---------------------------------------------------------------------------
echo ""
MEDIA_ROOT=""
if [[ "$PRODUCTION_RESTORE" == "true" ]]; then
    # Production media lives on the remote server. Uploading it from a local
    # script is out of scope -- restore media manually via cr sftp or your
    # deployment workflow after confirming the DB restore is correct.
    echo "NOTE: Production media restore is out of scope for this script."
    echo "      Media archive is preserved at: ${MEDIA_ARCHIVE}"
    echo "      Upload it to the server manually if needed."
else
    echo "Restoring media..."
    MEDIA_ROOT=$(
        DATABASE_URL="$TARGET_DATABASE_URL" DJANGO_SETTINGS_MODULE="cycling_site.settings.dev" \
        poetry run python manage.py shell -c "from django.conf import settings; print(settings.MEDIA_ROOT)" 2>/dev/null
    )
    if [[ -z "$MEDIA_ROOT" ]]; then
        echo "WARNING: Could not determine MEDIA_ROOT from Django settings; using ./media/" >&2
        MEDIA_ROOT="./media"
    fi
    mkdir -p "$MEDIA_ROOT"
    tar -xzf "$MEDIA_ARCHIVE" -C "$MEDIA_ROOT" --strip-components=1
    echo "Media restored to: ${MEDIA_ROOT}"
fi

# ---------------------------------------------------------------------------
# Run migrations
# ---------------------------------------------------------------------------
echo ""
echo "Running migrations..."
DATABASE_URL="$TARGET_DATABASE_URL" DJANGO_SETTINGS_MODULE="cycling_site.settings.dev" \
    poetry run python manage.py migrate --no-input

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== RESTORE COMPLETE ==="
echo "  Backup  : ${BACKUP_DIR}"
echo "  DB      : ${DB_NAME} @ ${DB_HOST}"
if [[ -n "$MEDIA_ROOT" ]]; then
    echo "  Media   : ${MEDIA_ROOT}"
else
    echo "  Media   : skipped (production -- restore manually)"
fi
