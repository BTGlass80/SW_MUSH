#!/usr/bin/env python3
"""
patches/patch_cp_db.py  --  Drop 2 of CP Progression system.

Applies two changes to db/database.py:
  1. Bumps SCHEMA_VERSION 6 → 7
  2. Adds migration v7 (cp_ticks + kudos_log tables)
  3. Appends CP-specific DB methods to the Database class

Run from project root:
    python patches/patch_cp_db.py
"""

import re
import sys
import shutil
import ast
from pathlib import Path

TARGET = Path("db/database.py")
BACKUP = Path("db/database.py.bak_cp")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def apply(src: str, old: str, new: str, label: str) -> str:
    # Try exact match first, then strip \r for CRLF files
    if old in src:
        return src.replace(old, new, 1)
    old_lf = old.replace("\r\n", "\n")
    src_lf = src.replace("\r\n", "\n")
    if old_lf in src_lf:
        result = src_lf.replace(old_lf, new, 1)
        return result
    print(f"ERROR: anchor not found for: {label}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    shutil.copy(TARGET, BACKUP)
    print(f"Backup: {BACKUP}")

    src = read(TARGET)

    # ── Change 1: bump SCHEMA_VERSION ────────────────────────────────────────
    src = apply(
        src,
        "SCHEMA_VERSION = 6",
        "SCHEMA_VERSION = 7",
        "SCHEMA_VERSION bump",
    )
    print("  [1/3] SCHEMA_VERSION 6 → 7")

    # ── Change 2: add migration v7 ────────────────────────────────────────────
    old_migration_tail = """    6: [
        \"\"\"CREATE TABLE IF NOT EXISTS smuggling_jobs (
            id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'available',
            accepted_by INTEGER,
            data TEXT NOT NULL
        )\"\"\",
    ],

}"""

    new_migration_tail = """    6: [
        \"\"\"CREATE TABLE IF NOT EXISTS smuggling_jobs (
            id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'available',
            accepted_by INTEGER,
            data TEXT NOT NULL
        )\"\"\",
    ],

    7: [
        \"\"\"CREATE TABLE IF NOT EXISTS cp_ticks (
            char_id         INTEGER PRIMARY KEY REFERENCES characters(id),
            ticks_total     INTEGER DEFAULT 0,
            ticks_this_week INTEGER DEFAULT 0,
            week_start_ts   REAL    DEFAULT 0,
            cap_hit_streak  INTEGER DEFAULT 0,
            last_passive_ts REAL    DEFAULT 0,
            last_scene_ts   REAL    DEFAULT 0,
            last_award_ts   REAL    DEFAULT 0,
            last_source     TEXT    DEFAULT ''
        )\"\"\",
        \"\"\"CREATE TABLE IF NOT EXISTS kudos_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            giver_id    INTEGER NOT NULL REFERENCES characters(id),
            target_id   INTEGER NOT NULL REFERENCES characters(id),
            ticks       INTEGER DEFAULT 0,
            awarded_at  REAL    NOT NULL
        )\"\"\",
    ],

}"""

    src = apply(src, old_migration_tail, new_migration_tail, "migration v7 insertion")
    print("  [2/3] Migration v7 added (cp_ticks + kudos_log tables)")

    # ── Change 3: append CP DB methods before end of file ────────────────────
    CP_METHODS = '''
    # ── CP Progression DB methods ─────────────────────────────────────────────

    async def cp_get_row(self, char_id: int):
        """Return the cp_ticks row for a character, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM cp_ticks WHERE char_id = ?", (char_id,)
        )
        return dict(rows[0]) if rows else None

    async def cp_ensure_row(self, char_id: int) -> None:
        """Insert a default cp_ticks row if one does not exist."""
        await self._db.execute(
            "INSERT OR IGNORE INTO cp_ticks (char_id) VALUES (?)", (char_id,)
        )
        await self._db.commit()

    async def cp_update_row(self, char_id: int, **fields) -> None:
        """Update arbitrary fields on a cp_ticks row."""
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [char_id]
        await self._db.execute(
            f"UPDATE cp_ticks SET {set_clause} WHERE char_id = ?", values
        )
        await self._db.commit()

    async def cp_add_character_points(self, char_id: int, amount: int) -> None:
        """Add CP to characters.character_points (floor at 0)."""
        await self._db.execute(
            "UPDATE characters SET character_points = MAX(0, character_points + ?) WHERE id = ?",
            (amount, char_id),
        )
        await self._db.commit()

    async def kudos_log(self, giver_id: int, target_id: int, ticks: int, ts: float) -> None:
        """Record a kudos event."""
        await self._db.execute(
            "INSERT INTO kudos_log (giver_id, target_id, ticks, awarded_at) VALUES (?, ?, ?, ?)",
            (giver_id, target_id, ticks, ts),
        )
        await self._db.commit()

    async def kudos_last_given(self, giver_id: int, target_id: int):
        """Return timestamp of last kudos given from giver to target, or None."""
        rows = await self._db.execute_fetchall(
            "SELECT MAX(awarded_at) as ts FROM kudos_log WHERE giver_id = ? AND target_id = ?",
            (giver_id, target_id),
        )
        if rows:
            return rows[0]["ts"]
        return None

    async def kudos_count_received_this_week(self, target_id: int) -> int:
        """Count kudos received by target in the rolling 7-day window."""
        import time as _time
        cutoff = _time.time() - (7 * 24 * 3600)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM kudos_log WHERE target_id = ? AND awarded_at >= ?",
            (target_id, cutoff),
        )
        return rows[0]["cnt"] if rows else 0
'''

    # Append before the last line (which is a blank line at EOF)
    src = src.rstrip() + "\n" + CP_METHODS + "\n"
    print("  [3/3] CP DB methods appended")

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        ast.parse(src)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  AST FAIL: {e}")
        sys.exit(1)

    write(TARGET, src)
    print(f"\nPatch applied successfully → {TARGET}")
    print("Schema will migrate to v7 on next server start.")
    print("(No need to delete the DB — migration is non-destructive.)")


if __name__ == "__main__":
    main()
