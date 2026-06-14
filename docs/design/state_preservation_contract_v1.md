# State-Preservation Contract (v1)

**Scope:** T3.20 `scope_notes` (f) — the written state-preservation contract that
every schema-touching or serializer-touching change must honor. Candidate arch
invariant to fold at the v52 consolidation. This document is **self-enforcing**:
`tests/test_state_preservation_contract.py` fails the build if the code drifts
from it (a new persisted serializer with no round-trip guard, an asymmetric
serializer pair, a deleted round-trip test, or a phantom reference below).

The governing launch criterion: *"ANY post-launch schema change has a CLEAR,
TESTED path that PRESERVES all players' live game state."*

---

## The five invariants

### I1 — Every persisted entity round-trips
Any class with a deserializer (`from_dict` / `from_db_dict` / `from_json`) and its
matching serializer (`to_dict` / `to_db_dict` / `to_json`) MUST survive a reload
round-trip unchanged: `from_*(x.to_*())` reproduces `x`, and `to_*` is stable under
the round trip. Production persists these as `json.dumps(x.to_*())` in a TEXT
column (or blob), so a round-trip test MUST exercise the real `json.dumps`/`json.loads`
path, not just the in-memory dict.

**Enforced by:** a per-entity round-trip test for each of the registered
deserializers, plus the coverage meta-test that asserts the set of deserializers
in the tree equals the registry (so a NEW deserializer cannot ship without a
round-trip test). Current registry (8): Character, ItemInstance, Mission,
BountyContract, SmugglingJob, Buff (board/inventory/buff), TrafficShip, NPCConfig.

**PR rule:** add a deserializer → add its round-trip test → register it in
`tests/test_state_preservation_contract.py::_DESERIALIZER_REGISTRY`.

### I2 — Derived state reconstructs, never persists
State DERIVED from stored fields is reconstructed on load, never written as its own
column/key. Canonical case: `force_sensitive` is derived from the presence of
`control`/`sense`/`alter` in the attributes blob; it is NEVER a `save_character`
kwarg. A path-committed character with an unreadable attrs blob fails SAFE to
`force_sensitive=True` (the village_chosen_path typed column survives blob
corruption). Reload-round-trip tests cover derived reconstruction.

### I3 — Migrations are forward-only, versioned, gated
`SCHEMA_VERSION == max(MIGRATIONS)` (the drift guard — a migration added without
bumping the version never runs on a live DB). Migrations run once each behind the
version gate; the production reboot path (`initialize()` every startup) is a no-op
on an already-current populated DB. Additive columns land via
`ALTER TABLE ADD COLUMN ... DEFAULT`; config / world-YAML / definition fields are
read with explicit defaults each load and are NOT persisted per-save (so they need
no backfill).

**Enforced by:** `tests/test_migration_framework_integrity.py`.

### I4 — No orphaned rows, no corruption
The DB stays referentially intact: no row orphaned by a missing parent across the
80+ declared `REFERENCES` FKs, and no structural corruption. `foreign_keys=ON` at
connect blocks orphan WRITES on the live path; the scanner is the belt-and-suspenders
check for the paths that bypass enforcement (table-rebuild migrations, backup/restore,
manual edits).

**Tool:** `db/integrity.py::scan_integrity` / `tools/check_db_integrity.py`
(`PRAGMA integrity_check` + `foreign_key_check`). Scan BEFORE and AFTER every migration.

### I5 — Back up before you migrate; restore is a file replace
Take a CONSISTENT, verified backup before any schema change. The safety loop is
**backup → scan → migrate → scan**; the AFTER scan catches a migration that
orphaned rows. Restore = stop server, replace the live DB file (+ clear stale
`-wal`/`-shm`), verify, restart.

**Tool + doc:** `db/backup.py::backup_database` / `tools/backup_db.py` and
`docs/design/backup_restore_runbook_v1.md`.

---

## Checklist for a schema / serializer / persistence PR

1. [ ] New deserializer? Added a reload-round-trip test (pure + json path + `to_*`
       stability) AND registered it (I1).
2. [ ] No derived state persisted as its own field; derived state reconstructs on
       reload, with a round-trip test proving it (I2).
3. [ ] New migration bumps `SCHEMA_VERSION` to `max(MIGRATIONS)`; additive columns
       use `ADD COLUMN ... DEFAULT`; the reboot-no-op test still passes (I3).
4. [ ] `tools/check_db_integrity.py` is clean before AND after the migration (I4).
5. [ ] A verified backup exists before applying the migration to live data (I5).

---

## Referenced artifacts (kept honest by the self-enforcing test)

- Round-trip tests: `tests/test_character_reload_roundtrip.py`,
  `tests/test_persisted_entity_roundtrip.py`, `tests/test_serializer_roundtrip_extra.py`
- Migration framework: `tests/test_migration_framework_integrity.py`
- Integrity scanner: `db/integrity.py`, `tools/check_db_integrity.py`
- Backup: `db/backup.py`, `tools/backup_db.py`
- Runbook: `docs/design/backup_restore_runbook_v1.md`
