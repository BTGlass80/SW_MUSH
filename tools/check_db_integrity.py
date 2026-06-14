#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/check_db_integrity.py — operator CLI for the T3.20 DB integrity scanner.

Run a READ-ONLY corruption + orphaned-row scan against a SW_MUSH SQLite DB file.
Intended to be run BEFORE and AFTER a schema migration, and on any restored
backup, to confirm no corruption and no rows orphaned by a parent that vanished
(scope_notes e). Prints a human-readable report and exits:

    0  clean (no corruption, no orphans)
    1  problems found
    2  usage error (DB file missing)

Usage:
    python tools/check_db_integrity.py path/to/game.db
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _scan(db_path: str) -> int:
    from db.database import Database
    from db.integrity import scan_integrity

    db = Database(db_path)
    await db.connect()
    try:
        report = await scan_integrity(db)
    finally:
        await db.close()

    print(report.summary())
    return 0 if report.ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Scan a SW_MUSH SQLite DB for corruption + orphaned rows "
                    "(read-only). Run before/after a migration or on a restored backup.")
    ap.add_argument("db_path", help="path to the SQLite DB file to scan")
    args = ap.parse_args(argv)

    if not Path(args.db_path).is_file():
        print(f"error: DB file not found: {args.db_path}", file=sys.stderr)
        return 2

    return asyncio.run(_scan(args.db_path))


if __name__ == "__main__":
    sys.exit(main())
