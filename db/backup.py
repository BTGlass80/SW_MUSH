# -*- coding: utf-8 -*-
"""db/backup.py — T3.20 consistent online backup of the live SQLite DB.

scope_notes (d): backup/restore. Uses SQLite's online Backup API
(``sqlite3.Connection.backup``), which copies a CONSISTENT snapshot of the source
database even while the live server holds it open (WAL pages included) — so a
backup can be taken WITHOUT stopping the game. The destination is a plain SQLite
file you can archive and, to restore, copy back into place (stop server, replace
the live DB file, restart). See docs/design/backup_restore_runbook_v1.md.

Pair with db/integrity.py: take a backup, scan it, migrate, scan again — the
state-preservation safety loop for any schema change.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_database(source_path: str, dest_path: str, *, overwrite: bool = False) -> int:
    """Copy a consistent snapshot of ``source_path`` to ``dest_path`` using
    SQLite's online backup API. Safe to run against a live, open DB.

    Returns the destination file size in bytes.

    Raises:
        FileNotFoundError -- the source DB file does not exist.
        FileExistsError   -- dest exists and ``overwrite`` is False.
        sqlite3.Error     -- the backup itself failed.
    """
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"source DB not found: {source_path}")

    dst = Path(dest_path)
    if dst.exists() and not overwrite:
        raise FileExistsError(
            f"destination already exists (pass overwrite=True to replace): {dest_path}")

    source = sqlite3.connect(str(src))
    try:
        dest = sqlite3.connect(str(dst))
        try:
            # The online backup API streams a CONSISTENT snapshot of committed
            # data from source -> dest, coordinating with any concurrent writer.
            source.backup(dest)
            dest.commit()
        finally:
            dest.close()
    finally:
        source.close()

    return dst.stat().st_size
