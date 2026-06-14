#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/backup_db.py — operator CLI: consistent online backup of a SW_MUSH DB.

Produces a consistent snapshot of a (possibly live) SQLite DB using SQLite's
online backup API. With --verify, runs the integrity scanner (db/integrity.py)
against the backup so a corrupt/orphaned snapshot is caught immediately.

    python tools/backup_db.py <source.db> <dest.db> [--overwrite] [--verify]

Exit codes: 0 success, 1 verify problem / backup failure, 2 usage error.

Restore is a file copy: stop the server, replace the live DB file with the
backup, restart. See docs/design/backup_restore_runbook_v1.md.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _verify(dest_db: str) -> int:
    from db.database import Database
    from db.integrity import scan_integrity

    db = Database(dest_db)
    await db.connect()
    try:
        report = await scan_integrity(db)
    finally:
        await db.close()
    print(report.summary())
    return 0 if report.ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Consistent online backup of a SW_MUSH SQLite DB (safe on a live DB).")
    ap.add_argument("source_db", help="path to the live/source DB file")
    ap.add_argument("dest_db", help="path to write the backup snapshot to")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace dest_db if it already exists")
    ap.add_argument("--verify", action="store_true",
                    help="run the integrity scanner against the backup")
    args = ap.parse_args(argv)

    from db.backup import backup_database
    try:
        size = backup_database(args.source_db, args.dest_db, overwrite=args.overwrite)
    except (FileNotFoundError, FileExistsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # sqlite3.Error etc.
        print(f"backup failed: {e}", file=sys.stderr)
        return 1

    print(f"backup OK: {args.dest_db} ({size:,} bytes)")

    if args.verify:
        return asyncio.run(_verify(args.dest_db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
