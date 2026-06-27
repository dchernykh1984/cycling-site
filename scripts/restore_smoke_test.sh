#!/usr/bin/env bash
# restore_smoke_test.sh - smoke test for restore.sh's "clean restore into a non-empty
# target" behavior.
#
# It reproduces the exact failure we hit in practice: a backup taken AFTER a table was
# dropped on the source, restored over a target that still has that (now-leftover) table.
# pg_restore --clean alone cannot drop objects that are absent from the dump, so without
# the schema reset that restore.sh now performs the restore fails with dependency /
# "already exists" / "duplicate key" errors. This test asserts the schema-reset path:
#   - restore.sh contains the schema reset, and
#   - reset + pg_restore yields a clean target (leftover gone, data restored).
#
# Uses throwaway local databases and requires local pg client tools (psql/pg_dump/
# pg_restore). It is NOT wired into CI because the CI runner has no Postgres client tools
# installed; run it locally:  ./scripts/restore_smoke_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SRC="restore_smoke_src_$$"
DST="restore_smoke_dst_$$"
DUMP="$(mktemp -t restore_smoke.XXXXXX)"

cleanup() {
    dropdb --if-exists "$SRC" >/dev/null 2>&1 || true
    dropdb --if-exists "$DST" >/dev/null 2>&1 || true
    rm -f "$DUMP"
}
trap cleanup EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }

# 0. restore.sh must actually perform the schema reset this test relies on.
grep -q "DROP SCHEMA IF EXISTS public CASCADE" "$SCRIPT_DIR/restore.sh" \
    || fail "restore.sh is missing the schema reset before pg_restore"

# 0b. Production media must be auto-detected and synced over scp (Render), not left manual.
grep -qF '*render.com*)' "$SCRIPT_DIR/restore.sh" \
    || fail "restore.sh is missing the Render media auto-detect (DB_HOST case)"
grep -qF 'cycling_media_upload' "$SCRIPT_DIR/restore.sh" \
    || fail "restore.sh is missing the scp-based Render media upload"

# 0c. backup.sh must symmetrically pull Render media over scp (auto-detected by DB_HOST).
grep -qF '*render.com*)' "$SCRIPT_DIR/backup.sh" \
    || fail "backup.sh is missing the Render media auto-detect (DB_HOST case)"
grep -qF 'cycling_media_backup' "$SCRIPT_DIR/backup.sh" \
    || fail "backup.sh is missing the scp-based Render media download"

# 0d. restore.sh must support --media-only (sync media without touching the DB).
grep -qF -- '--media-only' "$SCRIPT_DIR/restore.sh" \
    || fail "restore.sh is missing the --media-only flag"

# 1. Source DB with data -> custom-format dump (same format as backup.sh's db.dump).
createdb "$SRC"
psql "$SRC" -v ON_ERROR_STOP=1 -q -c \
    "CREATE TABLE widget (id serial PRIMARY KEY, name text); INSERT INTO widget (name) VALUES ('alpha'), ('beta');"
pg_dump -Fc "$SRC" -f "$DUMP"

# 2. Dirty target: an object that is NOT in the dump (this is what broke the real restore).
createdb "$DST"
psql "$DST" -v ON_ERROR_STOP=1 -q -c "CREATE TABLE leftover (id integer PRIMARY KEY);"

# 3. Restore exactly the way restore.sh does: reset schema, then pg_restore --clean.
psql "$DST" -v ON_ERROR_STOP=1 -q -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
pg_restore --dbname="$DST" --clean --if-exists --no-owner --no-acl "$DUMP"

# 4. Assertions: leftover dropped, restored data present.
[[ -z "$(psql "$DST" -tAc "SELECT to_regclass('public.leftover');")" ]] \
    || fail "leftover table is still present after restore"
rows="$(psql "$DST" -tAc "SELECT count(*) FROM widget;")"
[[ "$rows" == "2" ]] || fail "expected 2 restored rows, got '$rows'"

echo "PASS: dirty-target restore is clean (leftover dropped, data restored)."
cd "$PROJECT_ROOT" >/dev/null
