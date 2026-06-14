# Backup / Restore + Upgrade Runbook (v1)

**Scope:** T3.20 state-preservation `scope_notes` (d). The operator procedure for
backing up the live SQLite DB, restoring it, and safely applying a schema
migration. Pairs the two T3.20 tools:

- `tools/backup_db.py` → `db/backup.py::backup_database` — a CONSISTENT online
  snapshot via SQLite's backup API (safe while the game is running).
- `tools/check_db_integrity.py` → `db/integrity.py::scan_integrity` — a read-only
  corruption + orphaned-row scan (`PRAGMA integrity_check` + `foreign_key_check`).

All commands are read-only on the live DB except the documented file-replace in
**Restore**.

---

## 1. Back up (any time; safe on a live DB)

```
python tools/backup_db.py <live.db> <backup.db> --verify
```

`--verify` runs the integrity scanner against the fresh snapshot and exits
non-zero if it is corrupt or has orphaned rows — never archive an unverified
backup. The tool refuses to overwrite an existing `<backup.db>` unless you pass
`--overwrite`. Name backups with a timestamp you control (e.g.
`game_2026-06-14_pre-migration.db`).

## 2. Safe migration loop (the state-preservation contract in practice)

A schema change must PRESERVE all players' live state. The procedure:

1. **Back up + verify** the live DB (step 1). Keep the snapshot.
2. **Scan the live DB** before migrating: `python tools/check_db_integrity.py <live.db>`.
   It must be clean (exit 0). If not, fix the orphans/corruption first — do NOT
   migrate over a dirty DB.
3. **Apply the migration** (start the server, which runs `Database.initialize()` →
   `_run_migrations`; or run the migration path directly). Migrations are
   forward-only and gated on `SCHEMA_VERSION`; the framework integrity is pinned
   by `tests/test_migration_framework_integrity.py`.
4. **Scan again** after the migration: `python tools/check_db_integrity.py <live.db>`.
   A table-rebuild migration toggles `foreign_keys=OFF`, so this AFTER scan is the
   one that catches a migration that orphaned rows. Must be clean.
5. If step 4 is dirty (or any smoke check fails), **restore** (section 3) and
   investigate before retrying.

## 3. Restore

The backup is a plain SQLite file. To roll back:

1. **Stop the server** (release the live DB file).
2. Move the corrupt/unwanted live DB aside (keep it for diagnosis), then copy the
   backup into its place:
   ```
   copy <backup.db> <live.db>
   ```
   (Also remove any stale `<live.db>-wal` / `<live.db>-shm` sidecars before
   restarting so they cannot replay over the restored file.)
3. **Verify** the restored file: `python tools/check_db_integrity.py <live.db>`.
4. **Restart the server.**

## 4. Notes

- The online backup snapshots COMMITTED data; transactions in flight at snapshot
  time are simply excluded (consistent, never half-written).
- `backup_database` returns the snapshot's byte size and raises on a real
  failure (missing source, refused overwrite, SQLite error) — a silent 0-byte
  backup cannot happen.
- This runbook is the operator companion to the written state-preservation
  contract (T3.20 `scope_notes` f, candidate arch invariant at the v52 consolidation).
