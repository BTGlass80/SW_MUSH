# -*- coding: utf-8 -*-
"""T3.21 optimization — kill the N+1 in the character directory.

`handle_characters` (GET /api/portal/characters) is a PUBLIC, unauthenticated,
paginated endpoint. It used to fetch the page of rows, then loop and call
`db.get_character(row["id"])` ONCE PER ROW purely to read the `faction` field
out of the attributes JSON blob — up to `per_page` (50) extra full-character
round-trips per page request. On an open endpoint that's a real load / DoS
amplifier.

The fix selects the `attributes` column inline in the single page query and
parses faction from it, so the page costs exactly two queries (count + page)
regardless of page size. These tests prove:
  * faction is still parsed correctly from the inline blob,
  * `get_character` is no longer called per row (the N+1 is gone),
  * malformed / missing attributes degrade to "Neutral" without crashing,
  * the faction filter still works against the inline-parsed value.
"""
import asyncio
import json
import os
import pathlib
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

WEB_PORTAL_SRC = (
    pathlib.Path(PROJECT_ROOT) / "server" / "web_portal.py"
).read_text(encoding="utf-8")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeReq:
    """Just enough of aiohttp's Request for handle_characters."""

    def __init__(self, query=None):
        self.query = query or {}
        self.headers = {}
        self.match_info = {}


class _FakeSessionMgr:
    """No one is online for these tests."""

    all = ()


class _FakeDB:
    """Dispatches fetchall on the COUNT vs page query. get_character is a
    spy that records calls — the whole point is that it stays at zero."""

    def __init__(self, page_rows):
        self._page_rows = page_rows
        self.get_character_calls = 0

    async def fetchall(self, sql, params=()):
        if "COUNT(*)" in sql:
            return [{"c": len(self._page_rows)}]
        return [dict(r) for r in self._page_rows]

    async def get_character(self, char_id):
        self.get_character_calls += 1
        return {"id": char_id, "attributes": "{}"}


def _make_api(page_rows):
    from server.web_portal import PortalAPI
    db = _FakeDB(page_rows)
    api = PortalAPI(db=db, session_mgr=_FakeSessionMgr(), game=None)
    return api, db


# ── Sample rows: attributes is a TEXT JSON blob, exactly as SELECTed ─────────
_ROWS = [
    {"id": 1, "name": "Aayla", "species": "Twi'lek", "template": "Jedi",
     "description": "A Jedi.", "attributes": json.dumps({"faction": "Republic"})},
    {"id": 2, "name": "Bossk", "species": "Trandoshan", "template": "Bounty Hunter",
     "description": "A hunter.", "attributes": json.dumps({"faction": "Hutt Cartel"})},
    {"id": 3, "name": "Cassian", "species": "Human", "template": "Spy",
     "description": "", "attributes": "{}"},          # no faction key -> Neutral
    {"id": 4, "name": "Dengar", "species": "Human", "template": "Merc",
     "description": "", "attributes": "not valid json"},  # malformed -> Neutral
]


class TestCharacterDirectoryNoN1(unittest.TestCase):

    def test_faction_parsed_from_inline_attributes(self):
        api, _db = _make_api(_ROWS)
        resp = _run(api.handle_characters(_FakeReq()))
        data = json.loads(resp.text)
        by_name = {c["name"]: c for c in data["characters"]}
        self.assertEqual(by_name["Aayla"]["faction"], "Republic")
        self.assertEqual(by_name["Bossk"]["faction"], "Hutt Cartel")

    def test_no_per_row_get_character_call(self):
        """The N+1: get_character must NOT be invoked while building the page."""
        api, db = _make_api(_ROWS)
        _run(api.handle_characters(_FakeReq()))
        self.assertEqual(
            db.get_character_calls, 0,
            "handle_characters still calls get_character per row — N+1 regressed",
        )

    def test_missing_and_malformed_attributes_default_to_neutral(self):
        api, _db = _make_api(_ROWS)
        resp = _run(api.handle_characters(_FakeReq()))
        by_name = {c["name"]: c for c in json.loads(resp.text)["characters"]}
        self.assertEqual(by_name["Cassian"]["faction"], "Neutral")  # {} blob
        self.assertEqual(by_name["Dengar"]["faction"], "Neutral")   # bad json

    def test_faction_filter_uses_inline_value(self):
        api, _db = _make_api(_ROWS)
        resp = _run(api.handle_characters(_FakeReq(query={"faction": "Republic"})))
        data = json.loads(resp.text)
        names = [c["name"] for c in data["characters"]]
        self.assertEqual(names, ["Aayla"])

    def test_page_query_selects_attributes_inline(self):
        # Source-level guard: the optimization rests on the page SELECT
        # carrying the attributes column so no per-row fetch is needed.
        self.assertIn(
            "SELECT id, name, species, template, description, attributes",
            WEB_PORTAL_SRC,
        )

    def test_response_shape_preserved(self):
        api, _db = _make_api(_ROWS)
        resp = _run(api.handle_characters(_FakeReq()))
        data = json.loads(resp.text)
        for field in ("characters", "total", "page", "per_page"):
            self.assertIn(field, data)
        first = data["characters"][0]
        for field in ("id", "name", "species", "template",
                      "faction", "description_snippet", "online"):
            self.assertIn(field, first)


if __name__ == "__main__":
    unittest.main()
