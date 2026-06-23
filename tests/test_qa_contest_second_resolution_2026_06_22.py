# -*- coding: utf-8 -*-
"""
tests/test_qa_contest_second_resolution_2026_06_22.py — QA break-it regression.

Faction break-it sweep (2026-06-22): a region's SECOND contest silently failed
to transfer ownership. region_contests carries UNIQUE(region_slug, status)
(engine/contest.py) — intended to keep ONE ACTIVE contest per region, but it
ALSO forbids a second *resolved* row of the same status. Resolved rows are never
deleted, so once a region had a 'resolved_challenger' (or 'resolved_defender')
row, the next same-outcome resolution's
  UPDATE region_contests SET status='resolved_challenger' WHERE id=? AND status='active'
collided with the leftover row -> IntegrityError -> swallowed by the resolution
path's try/except -> the function returned early, ownership never transferred (no
cooldown / anchor-despawn / notification). Every future contest on that region
was permanently broken (CORRUPTION).

Fix: _resolve_challenger_win and _resolve_defender_win DELETE the prior
same-status resolved row for the region before the resolving UPDATE (cooldowns
live in a separate table, so resolved rows are stale history). This also
self-heals a region already stuck from the old bug on its next resolution.

Pins: (1) the constraint semantics against the REAL schema — the bare UPDATE
collides on a second same-status resolution while the fix's DELETE-then-UPDATE
succeeds, and one-active-contest-per-region stays enforced; (2) a structural
guard that both resolution paths DELETE the stale row before the UPDATE.
"""
from __future__ import annotations

import sqlite3
import time
import unittest
from pathlib import Path

from engine.contest import REGION_CONTEST_SCHEMA_SQL

REPO = Path(__file__).resolve().parent.parent
CONTEST_SRC = (REPO / "engine" / "contest.py").read_text(encoding="utf-8")


def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(REGION_CONTEST_SCHEMA_SQL)
    return conn


def _insert_active(conn, slug, defender, challenger):
    now = time.time()
    cur = conn.execute(
        "INSERT INTO region_contests "
        "(region_slug, defender_org_code, challenger_org_code, zone_id, "
        " started_at, accumulation_ends_at, ends_at, status) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, 'active')",
        (slug, defender, challenger, now, now + 100, now + 200),
    )
    conn.commit()
    return cur.lastrowid


class TestContestSecondResolution(unittest.TestCase):
    def test_bare_update_collides_on_second_same_status(self):
        """The bug class, against the real schema: the OLD bare UPDATE raises
        IntegrityError on a region's second same-status resolution."""
        conn = _fresh_db()
        c1 = _insert_active(conn, "dune_sea", "republic", "hutts")
        conn.execute("UPDATE region_contests SET status='resolved_challenger' "
                     "WHERE id=? AND status='active'", (c1,))
        conn.commit()
        c2 = _insert_active(conn, "dune_sea", "hutts", "republic")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE region_contests SET status='resolved_challenger' "
                         "WHERE id=? AND status='active'", (c2,))
            conn.commit()

    def test_delete_then_update_resolves_repeated_challenger_wins(self):
        """The fix: DELETE the stale same-status row, then the UPDATE succeeds —
        three successive challenger-wins on one region resolve cleanly."""
        conn = _fresh_db()
        for i in range(3):
            cid = _insert_active(conn, "dune_sea", f"def{i}", f"chal{i}")
            conn.execute("DELETE FROM region_contests WHERE region_slug=? "
                         "AND status='resolved_challenger' AND id!=?",
                         ("dune_sea", cid))
            conn.execute("UPDATE region_contests SET status='resolved_challenger' "
                         "WHERE id=? AND status='active'", (cid,))
            conn.commit()
            got = conn.execute("SELECT status FROM region_contests WHERE id=?",
                               (cid,)).fetchone()[0]
            self.assertEqual(got, "resolved_challenger")
        n = conn.execute("SELECT COUNT(*) FROM region_contests WHERE "
                         "region_slug='dune_sea' AND status='resolved_challenger'"
                         ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_delete_then_update_resolves_repeated_defender_wins(self):
        conn = _fresh_db()
        for i in range(3):
            cid = _insert_active(conn, "kamino", "republic", f"chal{i}")
            conn.execute("DELETE FROM region_contests WHERE region_slug=? "
                         "AND status='resolved_defender' AND id!=?",
                         ("kamino", cid))
            conn.execute("UPDATE region_contests SET status='resolved_defender' "
                         "WHERE id=? AND status='active'", (cid,))
            conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM region_contests WHERE "
                         "region_slug='kamino' AND status='resolved_defender'"
                         ).fetchone()[0]
        self.assertEqual(n, 1)

    def test_one_active_contest_per_region_still_enforced(self):
        """The fix must NOT weaken the real intent: still ONE active contest
        per region (the constraint's legitimate job)."""
        conn = _fresh_db()
        _insert_active(conn, "geonosis", "cis", "republic")
        with self.assertRaises(sqlite3.IntegrityError):
            _insert_active(conn, "geonosis", "cis", "separatists")


class TestResolutionPathsDeleteBeforeUpdate(unittest.TestCase):
    def _slice(self, fn_name):
        i = CONTEST_SRC.index("async def %s(" % fn_name)
        nxt = CONTEST_SRC.find("\nasync def ", i + 1)
        return CONTEST_SRC[i:] if nxt == -1 else CONTEST_SRC[i:nxt]

    def test_challenger_path_deletes_stale_resolved_row(self):
        body = self._slice("_resolve_challenger_win")
        d = body.find("DELETE FROM region_contests")
        u = body.find("UPDATE region_contests SET status = 'resolved_challenger'")
        self.assertNotEqual(d, -1, "challenger path missing stale-row DELETE")
        self.assertNotEqual(u, -1)
        self.assertLess(d, u, "DELETE must precede the resolving UPDATE")
        self.assertIn("'resolved_challenger'", body[d:u])

    def test_defender_path_deletes_stale_resolved_row(self):
        body = self._slice("_resolve_defender_win")
        d = body.find("DELETE FROM region_contests")
        u = body.find("UPDATE region_contests SET status = 'resolved_defender'")
        self.assertNotEqual(d, -1, "defender path missing stale-row DELETE")
        self.assertNotEqual(u, -1)
        self.assertLess(d, u, "DELETE must precede the resolving UPDATE")
        self.assertIn("'resolved_defender'", body[d:u])


if __name__ == "__main__":
    unittest.main()
