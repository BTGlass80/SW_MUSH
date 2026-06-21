# -*- coding: utf-8 -*-
"""
tests/test_vanity_titles.py — Drop 3 B3: vanity titles (aspirational cosmetic sink).

A character buys an honorific *title* — pure social standing, no payout, no
mechanical benefit, nothing to farm. It is a load-bearing high-tier *sink*
(beside the Kuat brokerage B1, the spacedock drain F2, and the home-prestige
ladder B2): it gives veteran credit somewhere to go.

Covers: the pure catalog/helpers; `purchase_title` branches against a recording
stub (buy / unknown / owned / insufficient / refund-on-persist-failure);
`set_worn_title` (set owned / reject non-owned / clear, all with NO credit
movement); a real in-memory `Database` happy path proving the column migration +
the `vanity_title` ledger debit + persistence + auto-wear + set; and structural
pins (the sink tag, the schema columns, the `+title` registration, and the
who/room/sheet display integration).
"""

import os
import sys
import json
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.titles import (                                            # noqa: E402
    VANITY_TITLES, title_by_key, owned_title_keys, is_owned, worn_title,
    title_status_lines, catalog_lines, purchase_title, set_worn_title,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure catalog / helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestTitlesPure(unittest.TestCase):
    def test_catalog_well_formed(self):
        keys = [t["key"] for t in VANITY_TITLES]
        labels = [t["label"] for t in VANITY_TITLES]
        self.assertEqual(len(keys), len(set(keys)), "title keys must be unique")
        self.assertEqual(len(labels), len(set(labels)),
                         "title labels must be unique")
        self.assertTrue(all(int(t["cost"]) > 0 for t in VANITY_TITLES),
                        "every title must cost something (it's a sink)")
        # The headline tier is a genuine money-burn for the wealthy.
        self.assertGreaterEqual(max(int(t["cost"]) for t in VANITY_TITLES),
                                100_000)

    def test_era_clean(self):
        # B3 era-cleanness: no Empire/Rebel/Imperial flavour in purchasable titles.
        blob = " ".join(
            (t["key"] + " " + t["label"] + " " + t["blurb"]).lower()
            for t in VANITY_TITLES
        )
        for banned in ("empire", "imperial", "rebel", "stormtrooper", "jedi",
                       "sith"):
            self.assertNotIn(banned, blob)

    def test_title_by_key(self):
        self.assertIsNone(title_by_key(""))
        self.assertIsNone(title_by_key("nope"))
        t = title_by_key("MAGNATE")  # case-insensitive
        self.assertEqual(t["label"], "Sector Magnate")
        self.assertEqual(t["cost"], 60_000)

    def test_owned_parse_safe(self):
        self.assertEqual(owned_title_keys({}), [])
        self.assertEqual(owned_title_keys({"vanity_titles": "[]"}), [])
        self.assertEqual(
            owned_title_keys({"vanity_titles": '["wayfarer", "magnate"]'}),
            ["wayfarer", "magnate"])
        # Already-a-list (defensive) is accepted.
        self.assertEqual(
            owned_title_keys({"vanity_titles": ["dealmaker"]}), ["dealmaker"])
        # Dedup, case-normalised.
        self.assertEqual(
            owned_title_keys({"vanity_titles": '["Wayfarer", "wayfarer"]'}),
            ["wayfarer"])
        # Malformed JSON fails safe to empty (never raises).
        self.assertEqual(owned_title_keys({"vanity_titles": "{not json"}), [])

    def test_is_owned_and_worn(self):
        char = {"vanity_titles": '["wayfarer"]', "display_title": "the Wayfarer"}
        self.assertTrue(is_owned(char, "wayfarer"))
        self.assertTrue(is_owned(char, "WAYFARER"))
        self.assertFalse(is_owned(char, "magnate"))
        self.assertEqual(worn_title(char), "the Wayfarer")
        self.assertIsNone(worn_title({"display_title": ""}))
        self.assertIsNone(worn_title({}))

    def test_status_and_catalog_marks(self):
        # No titles: status shows none; catalog marks by affordability.
        poor = {"credits": 3_000, "vanity_titles": "[]", "display_title": ""}
        st = title_status_lines(poor)
        self.assertTrue(any("(none)" in l for l in st))
        marks = {r["key"]: r["mark"] for r in catalog_lines(poor)}
        self.assertEqual(marks["wayfarer"], "buy")      # 2,000 <= 3,000
        self.assertEqual(marks["high_roller"], "locked")  # 12,000 > 3,000
        # Owns one, wearing it: that row is 'owned', status reflects it.
        rich = {"credits": 1_000_000,
                "vanity_titles": '["magnate"]', "display_title": "Sector Magnate"}
        marks2 = {r["key"]: r["mark"] for r in catalog_lines(rich)}
        self.assertEqual(marks2["magnate"], "owned")
        self.assertEqual(marks2["wayfarer"], "buy")
        self.assertTrue(any("Sector Magnate" in l for l in title_status_lines(rich)))


# ─────────────────────────────────────────────────────────────────────────────
# purchase_title / set_worn_title — branches (recording stub)
# ─────────────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, fail_persist=False):
        self.credit_log = []   # (delta, source)
        self.saves = []        # list of field dicts
        self.fail_persist = fail_persist

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((delta, source))
        return 1_000_000 + delta

    async def save_character(self, cid, **fields):
        if self.fail_persist:
            raise RuntimeError("persist boom")
        self.saves.append(fields)


class TestPurchaseBranches(unittest.TestCase):
    def _char(self, credits=1_000_000, owned=None, worn=""):
        return {"id": 7, "credits": credits,
                "vanity_titles": json.dumps(owned or []),
                "display_title": worn}

    def test_buy_debits_persists_and_auto_wears(self):
        db = _StubDB()
        char = self._char()
        res = _run(purchase_title(db, char, "wayfarer"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["label"], "the Wayfarer")
        self.assertEqual(db.credit_log, [(-2_000, "vanity_title")])
        # Persisted: owned list grew AND the title auto-wears.
        self.assertEqual(len(db.saves), 1)
        saved = db.saves[0]
        self.assertEqual(json.loads(saved["vanity_titles"]), ["wayfarer"])
        self.assertEqual(saved["display_title"], "the Wayfarer")
        # In-memory char advanced too.
        self.assertEqual(worn_title(char), "the Wayfarer")
        self.assertTrue(is_owned(char, "wayfarer"))

    def test_unknown_title_no_charge(self):
        db = _StubDB()
        res = _run(purchase_title(db, self._char(), "nonexistent"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "unknown")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.saves, [])

    def test_already_owned_no_charge(self):
        db = _StubDB()
        char = self._char(owned=["wayfarer"])
        res = _run(purchase_title(db, char, "wayfarer"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "owned")
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.saves, [])

    def test_insufficient_funds_no_charge(self):
        db = _StubDB()
        char = self._char(credits=1_999)   # wayfarer is 2,000
        res = _run(purchase_title(db, char, "wayfarer"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "insufficient")
        self.assertEqual(res["short"], 1)
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.saves, [])

    def test_refund_on_persist_failure(self):
        db = _StubDB(fail_persist=True)
        res = _run(purchase_title(db, self._char(), "magnate"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "persist_failed")
        sources = [s for _, s in db.credit_log]
        self.assertIn("vanity_title", sources)
        self.assertIn("vanity_title_refund", sources)


class TestSetWornTitle(unittest.TestCase):
    def _char(self, owned=None, worn=""):
        return {"id": 9, "vanity_titles": json.dumps(owned or []),
                "display_title": worn}

    def test_set_owned_persists_no_credit_movement(self):
        db = _StubDB()
        char = self._char(owned=["magnate"], worn="")
        res = _run(set_worn_title(db, char, "magnate"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["label"], "Sector Magnate")
        self.assertEqual(db.credit_log, [])            # selection is free
        self.assertEqual(db.saves, [{"display_title": "Sector Magnate"}])
        self.assertEqual(char["display_title"], "Sector Magnate")

    def test_set_not_owned_rejected_no_write(self):
        db = _StubDB()
        char = self._char(owned=["wayfarer"], worn="the Wayfarer")
        res = _run(set_worn_title(db, char, "magnate"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_owned")
        self.assertEqual(db.saves, [])
        self.assertEqual(char["display_title"], "the Wayfarer")  # unchanged

    def test_clear(self):
        db = _StubDB()
        char = self._char(owned=["wayfarer"], worn="the Wayfarer")
        res = _run(set_worn_title(db, char, None))
        self.assertTrue(res["ok"])
        self.assertTrue(res.get("cleared"))
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.saves, [{"display_title": ""}])
        self.assertEqual(char["display_title"], "")


# ─────────────────────────────────────────────────────────────────────────────
# Real in-memory Database — column migration + ledger + persistence + set
# ─────────────────────────────────────────────────────────────────────────────
_OPEN_DBS = []


async def _real_db(credits=1_000_000):
    from db.database import Database
    from engine import titles
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    await db._db.execute(
        """CREATE TABLE credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
            delta INTEGER NOT NULL, source TEXT NOT NULL,
            balance INTEGER NOT NULL, created_at REAL NOT NULL)""")
    await db._db.execute(
        """CREATE TABLE economy_config (
            key TEXT PRIMARY KEY, value REAL NOT NULL, updated_at REAL NOT NULL)""")
    await db._db.commit()
    # The migration adds vanity_titles + display_title to `characters`.
    await titles.ensure_schema(db)
    await db._db.execute("INSERT INTO characters (id, credits) VALUES (1, ?)",
                         (credits,))
    await db._db.commit()
    _OPEN_DBS.append(db)
    return db


class TestRealDBHappyPath(unittest.TestCase):
    def test_columns_migrate_purchase_persists_and_set(self):
        async def go():
            db = await _real_db(credits=1_000_000)
            char = await db.get_character(1)
            # Migration added the columns with their defaults.
            self.assertEqual((char.get("vanity_titles") or "[]"), "[]")
            self.assertEqual((char.get("display_title") or ""), "")

            # Buy one — debits through the real ledger, auto-wears.
            r1 = await purchase_title(db, char, "wayfarer")
            self.assertTrue(r1["ok"])
            # Buy a second — owned set grows; auto-wears the new one.
            r2 = await purchase_title(db, char, "dealmaker")
            self.assertTrue(r2["ok"])

            # Re-fetch: both persisted to the DB, display = last bought.
            fresh = await db.get_character(1)
            self.assertEqual(set(owned_title_keys(fresh)),
                             {"wayfarer", "dealmaker"})
            self.assertEqual(worn_title(fresh), "the Dealmaker")

            # Ledger: two debits, both tagged vanity_title.
            crows = await db._db.execute_fetchall(
                "SELECT delta, source FROM credit_log "
                "WHERE char_id = 1 ORDER BY id")
            self.assertEqual([r["source"] for r in crows],
                             ["vanity_title", "vanity_title"])
            self.assertEqual([r["delta"] for r in crows], [-2_000, -5_000])

            # Switch worn title back to the first — free, persists.
            r3 = await set_worn_title(db, fresh, "wayfarer")
            self.assertTrue(r3["ok"])
            again = await db.get_character(1)
            self.assertEqual(worn_title(again), "the Wayfarer")
            # No new credit row from the switch.
            crows2 = await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM credit_log WHERE char_id = 1")
            self.assertEqual(crows2[0]["n"], 2)
            # Close on the same loop so aiosqlite's worker thread is joined
            # (keeps a bare `unittest` process exit clean; harmless otherwise).
            try:
                await db.close()
                _OPEN_DBS.remove(db)
            except Exception:
                pass
        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# Structural pins
# ─────────────────────────────────────────────────────────────────────────────
def _read(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_sink_tag_and_columns(self):
        src = _read("engine", "titles.py")
        self.assertIn('"vanity_title"', src)          # the sink tag
        self.assertIn('"vanity_title_refund"', src)   # refund-safe
        self.assertIn("ADD COLUMN vanity_titles", src)
        self.assertIn("ADD COLUMN display_title", src)
        self.assertIn("_TITLE_COLS", src)             # idempotent column-loop

    def test_command_registered(self):
        src = _read("parser", "title_commands.py")
        self.assertIn('"+title"', src)
        self.assertIn("def register_title_commands", src)
        gs = _read("server", "game_server.py")
        self.assertIn("register_title_commands(self.registry)", gs)
        self.assertIn("from engine.titles import ensure_schema", gs)

    def test_columns_allowlisted(self):
        db = _read("db", "database.py")
        self.assertIn('"vanity_titles"', db)
        self.assertIn('"display_title"', db)

    def test_display_surfaces_wired(self):
        # The worn title must reach observers: who + room listing + sheet.
        bc = _read("parser", "builtin_commands.py")
        self.assertIn("from engine.titles import worn_title", bc)
        self.assertIn("title_suffix", bc)   # +who line suffix
        self.assertIn("title_str", bc)       # room "is here" honorific
        sr = _read("engine", "sheet_renderer.py")
        self.assertIn("worn_title", sr)      # Telnet sheet + web payload
        self.assertIn('"title":', sr)        # web identity payload field


if __name__ == "__main__":
    unittest.main(verbosity=2)
