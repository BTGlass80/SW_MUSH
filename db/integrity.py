# -*- coding: utf-8 -*-
"""db/integrity.py — T3.20 live-DB integrity / orphan validator.

A READ-ONLY scanner that checks a live SQLite database for the two failure
classes a state-preservation pass cares about (scope_notes e):

  * CORRUPTION — ``PRAGMA integrity_check``: malformed pages, broken/ inconsistent
    indexes, missing pages, etc. A healthy DB returns the single row ``"ok"``.
  * ORPHANS    — ``PRAGMA foreign_key_check``: every row that violates one of the
    schema's declared ``REFERENCES`` (FOREIGN KEY) constraints — a child row whose
    parent is gone. The schema declares 80+ FKs, so this one pragma covers the
    WHOLE referential surface with no hand-written per-table SQL to drift.

WHY THIS EXISTS even though ``PRAGMA foreign_keys=ON`` is set at connect (so the
LIVE write path already refuses to create an orphan): foreign-key enforcement is
per-connection and only governs writes made AFTER it is enabled. The paths that
can still introduce orphans/corruption are exactly the ones T3.20 worries about —
a migration that rebuilds a table (the canonical 12-step ALTER recipe toggles
``foreign_keys=OFF``), a backup/restore, an offline/manual DB edit, or pre-FK
legacy rows. So this is the belt-and-suspenders scan to run BEFORE & AFTER a
migration and on any restored backup.

Read-only: issues only ``PRAGMA`` reads, never a write. Safe against a live DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OrphanFinding:
    """One row that violates a declared FOREIGN KEY (its parent is missing)."""

    table: str
    rowid: Optional[int]   # NULL for WITHOUT ROWID tables
    parent_table: str
    fk_index: int          # which FK on `table` (the pragma's fkid)

    def describe(self) -> str:
        where = f"rowid {self.rowid}" if self.rowid is not None else "a row"
        return (f"{self.table}: {where} references a missing "
                f"{self.parent_table} (fk #{self.fk_index})")


@dataclass
class IntegrityReport:
    corruption: List[str] = field(default_factory=list)        # integrity_check msgs (excl. "ok")
    orphans: List[OrphanFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.corruption and not self.orphans

    def summary(self) -> str:
        if self.ok:
            return "DB integrity: OK - no corruption, no orphaned rows."
        lines: List[str] = ["DB integrity: PROBLEMS FOUND"]
        if self.corruption:
            lines.append(f"  corruption ({len(self.corruption)}):")
            lines += [f"    - {c}" for c in self.corruption]
        if self.orphans:
            lines.append(f"  orphaned rows ({len(self.orphans)}):")
            lines += [f"    - {o.describe()}" for o in self.orphans]
        return "\n".join(lines)


async def scan_integrity(db) -> IntegrityReport:
    """Run ``PRAGMA integrity_check`` + ``PRAGMA foreign_key_check`` against a
    connected ``Database`` and return a structured ``IntegrityReport``.

    ``db`` is duck-typed: it only needs an awaitable ``fetchall(sql)`` returning
    rows that support positional indexing (the real ``Database`` qualifies).
    Read-only — runs no writes and does not change the connection's pragmas.
    """
    report = IntegrityReport()

    # --- corruption: integrity_check returns one or more rows; "ok" means clean ---
    for row in await db.fetchall("PRAGMA integrity_check"):
        val = row[0]
        if val is not None and str(val).strip().lower() != "ok":
            report.corruption.append(str(val))

    # --- orphans: foreign_key_check returns (table, rowid, parent, fkid) per
    #     violating row across EVERY declared FK; no rows == fully referentially
    #     intact. Works regardless of whether foreign_keys enforcement is ON. ---
    for row in await db.fetchall("PRAGMA foreign_key_check"):
        report.orphans.append(OrphanFinding(
            table=row[0],
            rowid=row[1],
            parent_table=row[2],
            fk_index=row[3],
        ))

    return report
