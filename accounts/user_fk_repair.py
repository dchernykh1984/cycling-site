"""One-off repair for production database schema drift (issue #124).

The production database was first migrated while the project still used Django's
default ``auth.User`` model, so a number of *swappable* user foreign keys were
created pointing at the legacy ``auth_user`` table. After the switch to the custom
``accounts.User`` model (table ``accounts_user``) those constraints were never
repointed, so any admin action that writes a user reference -- uploading an image or
document, opening the page editor (which records an editing session), saving a
revision, locking a page, etc. -- raised ``IntegrityError`` -> HTTP 500.

``REPOINT_USER_FKS_SQL`` moves every such foreign key from ``auth_user`` to
``accounts_user``, preserving each constraint's original definition (ON DELETE rule,
deferrability) and name. It is **idempotent** and a **no-op** on databases that never
had an ``auth_user`` table (fresh installs, the test/CI database), so it is safe to
ship as a migration that runs on every deploy.

The two self-owned m2m tables of the legacy user (``auth_user_groups`` and
``auth_user_user_permissions``) are deliberately left untouched -- they belong to the
now-unused ``auth_user`` table and are handled by a separate cleanup migration.
"""

REPOINT_USER_FKS_SQL = r"""
DO $$
DECLARE
    r RECORD;
    newdef TEXT;
BEGIN
    -- Fresh databases use the custom user model from the start and never create
    -- auth_user; there is nothing to repoint, so bail out (keeps this a no-op in CI).
    IF to_regclass('auth_user') IS NULL THEN
        RETURN;
    END IF;

    FOR r IN
        SELECT con.conname,
               con.conrelid::regclass AS tbl,
               pg_get_constraintdef(con.oid) AS def
        FROM pg_constraint con
        WHERE con.contype = 'f'
          AND con.confrelid = 'auth_user'::regclass
          -- skip auth_user's own m2m tables; those are removed by the cleanup migration
          AND con.conrelid::regclass::text NOT IN ('auth_user_groups', 'auth_user_user_permissions')
    LOOP
        -- Reuse the existing definition (ON DELETE / DEFERRABLE preserved); only swap
        -- the referenced table. The constraint name is kept as-is -- it is cosmetic and
        -- Django introspects the live name when it later needs to alter the FK.
        newdef := replace(r.def, 'REFERENCES auth_user(', 'REFERENCES accounts_user(');
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s', r.tbl, r.conname, newdef);
    END LOOP;
END $$;
"""
