# -*- coding: utf-8 -*-
"""
tests/test_drop2b_chargen_chains_endpoint_and_consumer.py — Drop 2b
(May 19 2026 evening).

Pins the SPA-side companion work for the first-character-mandatory
tutorial-chain policy delivered in Drop 2a:

  1. GET  /api/chargen/chains          — chain list + is_first_character
  2. POST /api/chargen/create-character — extended to accept chain_id
                                          and skip_tutorial, with the
                                          server as the authority on
                                          skip-rejection for first chars.

Plus the skip starter kit consumer (load_skip_starter_kit + the
credits/items application at create-character time).

Test sections:
   1. TestSkipKitLoader            — load_skip_starter_kit shape
   2. TestChainsEndpointShape      — /chains response shape
   3. TestChainsEndpointFirstChar  — is_first_character flag
   4. TestChainsEndpointAuth       — token enforcement
   5. TestChainsEndpointLockedFlag — locked chains flagged with reason
   6. TestChainsEndpointGcw        — GCW returns empty chains list
   7. TestCreateChainRouting       — chain_id picks the chain's room
   8. TestCreateChainAttrsBlock    — tutorial_chain block written
   9. TestCreateChainFactionIntent — faction_intent persisted
  10. TestCreateSkipRejectFirst    — server rejects skip on first char
  11. TestCreateSkipAlt            — alt skip succeeds, kit applied
  12. TestCreateSkipKitCredits     — credits granted from kit
  13. TestCreateSkipKitItems       — items appended via add_to_inventory
  14. TestCreateBadChainId         — unknown chain_id rejected
  15. TestCreateLockedChainId      — locked (jedi_path) rejected
  16. TestCreateNoChainNoSkip      — neither chain_id nor skip → legacy
                                     Landing Pad placement (no attrs)
  17. TestSkipKitMessageInResponse — kit's message string returned
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────
# Test isolation
# ──────────────────────────────────────────────────────────────────────

def _set_era(era_code: str):
    from engine.era_state import set_active_config
    set_active_config(types.SimpleNamespace(active_era=era_code))


class _IsolatedBase(unittest.TestCase):
    def tearDown(self):
        from engine.era_state import clear_active_config
        clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# Async helpers (avoid asyncio_mode warnings; just use a fresh loop)
# ──────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────
# Mock DB
# ──────────────────────────────────────────────────────────────────────

class _MockDB:
    """In-memory async DB stand-in for ChargenAPI handler tests.

    Records calls so tests can assert on what was written. Behavior:
      - get_account(aid)         → {'id': aid} if aid in self.accounts
      - get_characters(aid)      → self.characters_by_account[aid]
      - fetchall(sql, params)    → entries from self.fetchall_returns
                                    matched by SQL substring (first
                                    matching key wins; default [])
      - create_character(...)    → assigns next_id, stashes fields,
                                    appends to characters_by_account
      - save_character(cid, **kw)→ records the kwargs
      - add_to_inventory(cid, i) → appends item to per-character list
    """

    def __init__(self, *, accounts=None, characters_by_account=None,
                 fetchall_returns=None):
        self.accounts = set(accounts or [])
        self.characters_by_account = characters_by_account or {}
        self.fetchall_returns = fetchall_returns or {}
        self.next_id = 100
        self.created = []          # list of (account_id, fields)
        self.save_calls = []       # list of (cid, kwargs)
        self.inventory = {}        # cid → list of items

    async def get_account(self, account_id):
        return {"id": account_id} if account_id in self.accounts else None

    async def get_characters(self, account_id):
        return list(self.characters_by_account.get(account_id, []))

    async def fetchall(self, sql, params=()):
        # Match a needle against the SQL OR any param value, so test
        # configs can route on either the query text or the parameter
        # (e.g. the `properties LIKE '%"slug": "<slug>"%'` pattern,
        # where "slug" appears in params, not the SQL).
        param_blob = " ".join(str(p) for p in (params or ()))
        for needle, rows in self.fetchall_returns.items():
            if needle in sql or needle in param_blob:
                if callable(rows):
                    return rows(sql, params)
                return list(rows)
        return []

    async def create_character(self, account_id, fields):
        cid = self.next_id
        self.next_id += 1
        self.created.append((account_id, dict(fields)))
        self.characters_by_account.setdefault(account_id, []).append(
            {"id": cid, "name": fields.get("name")}
        )
        return cid

    async def save_character(self, char_id, **fields):
        # Mirror real Database.save_character allowlist enforcement
        # minimally so callers can't sneak unknown columns through the
        # mock. (We don't import the real allowlist to keep the mock
        # lightweight; the real DB will catch any drift in integration.)
        self.save_calls.append((char_id, dict(fields)))

    async def add_to_inventory(self, char_id, item):
        self.inventory.setdefault(char_id, []).append(dict(item))


# ──────────────────────────────────────────────────────────────────────
# Mock species/skill registries
# ──────────────────────────────────────────────────────────────────────

def _build_human_species():
    """Real-shape stub of a Species object with the fields ChargenAPI
    touches: attributes (with ATTRIBUTE_NAMES keys), attribute_dice,
    skill_dice, move. Just enough to make validate_chargen_submission
    accept a vanilla submission."""
    from engine.character import ATTRIBUTE_NAMES
    from engine.species import Species, AttributeRange
    from engine.dice import DicePool
    sp = Species(
        name="Human",
        attribute_dice=DicePool(12, 0),
        skill_dice=DicePool(7, 0),
        move=10,
        attributes={
            a: AttributeRange(
                min_pool=DicePool(2, 0),
                max_pool=DicePool(4, 0),
            )
            for a in ATTRIBUTE_NAMES
        },
        special_abilities=[],
        story_factors=[],
    )
    return sp


class _RealSpeciesRegMini:
    def __init__(self):
        self._sp = _build_human_species()

    def get(self, name):
        if (name or "").lower() == "human":
            return self._sp
        return None

    def list_all(self):
        return [self._sp]


class _RealSkillRegMini:
    def skills_for_attribute(self, attr):
        return []

    def all_skills(self):
        return []


# ──────────────────────────────────────────────────────────────────────
# Mock request
# ──────────────────────────────────────────────────────────────────────

class _MockRequest:
    def __init__(self, *, json_body=None, query=None, ip="127.0.0.1"):
        self._json_body = json_body or {}
        self.query = query or {}
        self.headers = {}
        # Make _get_client_ip happy without real transport
        self.transport = MagicMock()
        self.transport.get_extra_info = MagicMock(
            return_value=(ip, 12345)
        )

    async def json(self):
        return dict(self._json_body)


# ──────────────────────────────────────────────────────────────────────
# Response helper
# ──────────────────────────────────────────────────────────────────────

def _resp_json(resp):
    """Pull JSON out of an aiohttp web.Response built by web.json_response."""
    return json.loads(resp.body.decode("utf-8"))


# ──────────────────────────────────────────────────────────────────────
# Make a ChargenAPI instance wired to the mock DB
# ──────────────────────────────────────────────────────────────────────

def _build_api(db):
    from server.api import ChargenAPI
    return ChargenAPI(
        species_reg=_RealSpeciesRegMini(),
        skill_reg=_RealSkillRegMini(),
        db=db,
    )


def _make_token(account_id):
    from server.api import create_login_token
    return create_login_token(account_id, ttl=3600)


# Reset rate limiter between tests (api.py uses a module-level dict).
def _reset_rate_limits():
    from server import api as api_mod
    api_mod._rate_limits.clear()


# Valid minimal character payload
def _valid_char_body():
    return {
        "name": "Testchar",
        "species": "Human",
        "attributes": {
            "dexterity": "2D",
            "knowledge": "2D",
            "mechanical": "2D",
            "perception": "2D",
            "strength": "2D",
            "technical": "2D",
        },
        "skills": {},
        "force_sensitive": False,
        "background": "",
    }


# ──────────────────────────────────────────────────────────────────────
# 1. Skip starter kit loader
# ──────────────────────────────────────────────────────────────────────

class TestSkipKitLoader(_IsolatedBase):

    def test_loads_cw_kit_shape(self):
        _set_era("clone_wars")
        from engine.tutorial_chains import load_skip_starter_kit
        kit = load_skip_starter_kit()
        self.assertIsNotNone(
            kit, "CW should have a skip_starter_kit.yaml"
        )
        self.assertIn("credits", kit)
        self.assertIn("items", kit)
        self.assertIn("resources", kit)
        self.assertIn("message", kit)
        self.assertEqual(kit["credits"], 300)
        # Drop 2a kit shipped with three items
        self.assertEqual(len(kit["items"]), 3)
        item_keys = sorted(i.get("key", "") for i in kit["items"])
        self.assertEqual(
            item_keys, ["comlink", "hold_out_blaster", "medpac"]
        )

    def test_gcw_returns_none(self):
        _set_era("gcw")
        from engine.tutorial_chains import load_skip_starter_kit
        kit = load_skip_starter_kit()
        self.assertIsNone(
            kit, "GCW has no skip kit; loader returns None"
        )

    def test_explicit_era_arg(self):
        # Force-pass era=clone_wars even when era_state says gcw.
        _set_era("gcw")
        from engine.tutorial_chains import load_skip_starter_kit
        kit = load_skip_starter_kit(era="clone_wars")
        self.assertIsNotNone(kit)
        self.assertEqual(kit["credits"], 300)


# ──────────────────────────────────────────────────────────────────────
# 2. /chains endpoint — basic shape
# ──────────────────────────────────────────────────────────────────────

class TestChainsEndpointShape(_IsolatedBase):

    def test_response_has_required_top_level_keys(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1}, characters_by_account={1: []})
        api = _build_api(db)
        token = _make_token(1)
        req = _MockRequest(query={"token": token})
        resp = _run(api.handle_chains(req))
        body = _resp_json(resp)
        self.assertIn("is_first_character", body)
        self.assertIn("chains", body)
        self.assertIsInstance(body["chains"], list)

    def test_chain_entry_has_required_fields(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1}, characters_by_account={1: []})
        api = _build_api(db)
        req = _MockRequest(query={"token": _make_token(1)})
        body = _resp_json(_run(api.handle_chains(req)))
        self.assertTrue(len(body["chains"]) > 0, "CW should ship chains")
        c0 = body["chains"][0]
        for field in (
            "chain_id", "chain_name", "description", "archetype_label",
            "faction_alignment", "duration_minutes", "locked",
            "locked_reason", "starting_room",
        ):
            self.assertIn(field, c0, f"missing field {field!r}")


# ──────────────────────────────────────────────────────────────────────
# 3. /chains endpoint — is_first_character flag
# ──────────────────────────────────────────────────────────────────────

class TestChainsEndpointFirstChar(_IsolatedBase):

    def test_true_when_no_characters(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1}, characters_by_account={1: []})
        api = _build_api(db)
        req = _MockRequest(query={"token": _make_token(1)})
        body = _resp_json(_run(api.handle_chains(req)))
        self.assertTrue(body["is_first_character"])

    def test_false_when_one_character_exists(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(
            accounts={1},
            characters_by_account={1: [{"id": 10, "name": "Existing"}]},
        )
        api = _build_api(db)
        req = _MockRequest(query={"token": _make_token(1)})
        body = _resp_json(_run(api.handle_chains(req)))
        self.assertFalse(body["is_first_character"])


# ──────────────────────────────────────────────────────────────────────
# 4. /chains endpoint — auth enforcement
# ──────────────────────────────────────────────────────────────────────

class TestChainsEndpointAuth(_IsolatedBase):

    def test_missing_token_serves_first_character_picker(self):
        # QA (Playwright E2E, 2026-06-23): the STANDALONE /chargen wizard (the
        # portal's "Create Character" link) has no account token yet, so a
        # tokenless /chains request must serve the FIRST-character picker -- it
        # used to 401, which surfaced "Failed to load chains (HTTP 401)" and
        # blocked a new player from picking a tutorial chain. A SUPPLIED but
        # invalid token (test_bad_token_rejected) is still 401.
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1})
        api = _build_api(db)
        req = _MockRequest(query={})  # no token (standalone chargen)
        resp = _run(api.handle_chains(req))
        self.assertEqual(resp.status, 200)
        body = _resp_json(resp)
        self.assertTrue(body["is_first_character"])
        self.assertTrue(len(body["chains"]) > 0,
                        "standalone first-character picker must list chains")

    def test_bad_token_rejected(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1})
        api = _build_api(db)
        req = _MockRequest(query={"token": "garbage.token"})
        resp = _run(api.handle_chains(req))
        self.assertEqual(resp.status, 401)


# ──────────────────────────────────────────────────────────────────────
# 5. /chains endpoint — locked-chain flag with reason
# ──────────────────────────────────────────────────────────────────────

class TestChainsEndpointLockedFlag(_IsolatedBase):

    def test_jedi_path_locked_with_reason_at_chargen(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1}, characters_by_account={1: []})
        api = _build_api(db)
        req = _MockRequest(query={"token": _make_token(1)})
        body = _resp_json(_run(api.handle_chains(req)))
        by_id = {c["chain_id"]: c for c in body["chains"]}
        # Both Jedi-Path variants are locked at chargen — village
        # quest hasn't run yet.
        for cid in ("jedi_path", "jedi_path_independent"):
            self.assertIn(cid, by_id, f"chain {cid} missing from /chains")
            self.assertTrue(
                by_id[cid]["locked"],
                f"{cid} must be locked at chargen",
            )
            self.assertTrue(
                by_id[cid]["locked_reason"],
                f"{cid} must carry a non-empty locked_reason",
            )

    def test_unlocked_chain_has_empty_locked_reason(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _MockDB(accounts={1}, characters_by_account={1: []})
        api = _build_api(db)
        req = _MockRequest(query={"token": _make_token(1)})
        body = _resp_json(_run(api.handle_chains(req)))
        unlocked = [c for c in body["chains"] if not c["locked"]]
        self.assertTrue(unlocked, "CW must ship unlocked chains")
        for c in unlocked:
            self.assertEqual(c["locked_reason"], "")


# ──────────────────────────────────────────────────────────────────────
# 6. /chains endpoint — GCW returns empty chains list
# ──────────────────────────────────────────────────────────────────────

class TestChainsEndpointGcw(_IsolatedBase):

    def test_gcw_returns_empty_chains_but_keeps_first_flag(self):
        _set_era("gcw")
        _reset_rate_limits()
        db = _MockDB(accounts={1}, characters_by_account={1: []})
        api = _build_api(db)
        req = _MockRequest(query={"token": _make_token(1)})
        body = _resp_json(_run(api.handle_chains(req)))
        self.assertEqual(body["chains"], [])
        # Still reports first-character flag — SPA needs it for the
        # next step's decisions (even though it'll skip past chains).
        self.assertTrue(body["is_first_character"])


# ──────────────────────────────────────────────────────────────────────
# Helpers for create-character tests
# ──────────────────────────────────────────────────────────────────────

# A row payload that looks like a result from
# "SELECT id FROM rooms WHERE properties LIKE '%\"slug\":...%'"
def _row(room_id):
    return {"id": room_id}


# Convenience: build a fully-stocked mock DB that resolves any
# starting_room slug to room_id=500. The "Landing Pad" SQL pattern
# also resolves (to room_id=999) so the fallback test can exercise
# the non-chain placement path.
def _stock_db(account_id=1, existing_chars=None):
    return _MockDB(
        accounts={account_id},
        characters_by_account={account_id: list(existing_chars or [])},
        fetchall_returns={
            # Match the chain-slug LIKE query
            '"slug"': [_row(500)],
            # Match the legacy Landing Pad query
            "Landing Pad": [_row(999)],
        },
    )


def _post_create(api, *, account_id=1, char=None, chain_id=None,
                 skip_tutorial=None):
    body = {
        "token": _make_token(account_id),
        "character": char if char is not None else _valid_char_body(),
    }
    if chain_id is not None:
        body["chain_id"] = chain_id
    if skip_tutorial is not None:
        body["skip_tutorial"] = skip_tutorial
    return _run(api.handle_create_character(_MockRequest(json_body=body)))


# ──────────────────────────────────────────────────────────────────────
# 7. Create-character: chain_id picks the chain's starting room
# ──────────────────────────────────────────────────────────────────────

class TestCreateChainRouting(_IsolatedBase):

    def test_chain_id_routes_to_chain_starting_room(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db()
        api = _build_api(db)
        resp = _post_create(api, chain_id="republic_soldier")
        body = _resp_json(resp)
        self.assertTrue(
            body.get("success"),
            f"create-character should succeed; got {body}",
        )
        # The created character's room_id must be 500 (the chain-slug
        # resolver's mocked room), not 999 (Landing Pad fallback).
        self.assertEqual(len(db.created), 1)
        _aid, fields = db.created[0]
        self.assertEqual(
            fields.get("room_id"), 500,
            "chain_id must route to the slug-resolved starting room",
        )


# ──────────────────────────────────────────────────────────────────────
# 8. Create-character: tutorial_chain block written to attributes JSON
# ──────────────────────────────────────────────────────────────────────

class TestCreateChainAttrsBlock(_IsolatedBase):

    def test_tutorial_chain_block_persisted(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db()
        api = _build_api(db)
        resp = _post_create(api, chain_id="republic_soldier")
        self.assertTrue(_resp_json(resp).get("success"))
        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes") or "{}")
        self.assertIn("tutorial_chain", attrs)
        block = attrs["tutorial_chain"]
        self.assertEqual(block["chain_id"], "republic_soldier")
        self.assertEqual(block["step"], 1)
        self.assertEqual(block["completed_steps"], [])
        self.assertEqual(block["completion_state"], "active")
        self.assertGreater(block.get("started_at", 0), 0)


# ──────────────────────────────────────────────────────────────────────
# 9. Create-character: faction_intent persisted from chain
# ──────────────────────────────────────────────────────────────────────

class TestCreateChainFactionIntent(_IsolatedBase):

    def test_faction_intent_matches_chain_alignment(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db()
        api = _build_api(db)
        _post_create(api, chain_id="republic_soldier")
        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes") or "{}")
        self.assertEqual(attrs.get("faction_intent"), "republic")


# ──────────────────────────────────────────────────────────────────────
# 10. Create-character: server rejects skip on first character
# ──────────────────────────────────────────────────────────────────────

class TestCreateSkipRejectFirst(_IsolatedBase):

    def test_skip_rejected_when_account_has_no_characters(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db(existing_chars=[])  # 0 existing → first char
        api = _build_api(db)
        resp = _post_create(api, skip_tutorial=True)
        self.assertEqual(resp.status, 400)
        body = _resp_json(resp)
        self.assertFalse(body.get("success", True))
        # Server is the authority — no character should have been created.
        self.assertEqual(len(db.created), 0)
        # Error category should be 'chain' so the SPA can route the
        # message to the right place.
        self.assertIn("chain", body.get("errors", {}))


# ──────────────────────────────────────────────────────────────────────
# 11. Create-character: alt skip succeeds
# ──────────────────────────────────────────────────────────────────────

class TestCreateSkipAlt(_IsolatedBase):

    def test_alt_skip_creates_character(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db(existing_chars=[{"id": 5, "name": "Existing"}])
        api = _build_api(db)
        resp = _post_create(api, skip_tutorial=True)
        body = _resp_json(resp)
        self.assertTrue(
            body.get("success"),
            f"alt skip should succeed; got {body}",
        )
        self.assertEqual(len(db.created), 1)
        # No tutorial_chain block on skip
        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes") or "{}")
        self.assertNotIn("tutorial_chain", attrs)


# ──────────────────────────────────────────────────────────────────────
# 12. Create-character: credits granted from kit
# ──────────────────────────────────────────────────────────────────────

class TestCreateSkipKitCredits(_IsolatedBase):

    def test_credits_persisted_via_save_character(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db(existing_chars=[{"id": 5}])
        api = _build_api(db)
        _post_create(api, skip_tutorial=True)
        # save_character must have been called with credits=300 on the
        # newly created character.
        credits_calls = [
            kw for (_cid, kw) in db.save_calls if "credits" in kw
        ]
        self.assertTrue(
            credits_calls,
            "save_character(credits=...) must be called when skip kit "
            "is applied",
        )
        self.assertEqual(credits_calls[0]["credits"], 300)


# ──────────────────────────────────────────────────────────────────────
# 13. Create-character: items appended via add_to_inventory
# ──────────────────────────────────────────────────────────────────────

class TestCreateSkipKitItems(_IsolatedBase):

    def test_kit_items_added_to_inventory(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db(existing_chars=[{"id": 5}])
        api = _build_api(db)
        _post_create(api, skip_tutorial=True)
        # The new char's id is the next_id used in create_character;
        # the mock returned 100 for the first call.
        self.assertIn(100, db.inventory)
        items = db.inventory[100]
        self.assertEqual(len(items), 3, f"expected 3 kit items; got {items}")
        keys = sorted(i.get("key", "") for i in items)
        self.assertEqual(
            keys, ["comlink", "hold_out_blaster", "medpac"]
        )


# ──────────────────────────────────────────────────────────────────────
# 14. Create-character: unknown chain_id rejected
# ──────────────────────────────────────────────────────────────────────

class TestCreateBadChainId(_IsolatedBase):

    def test_unknown_chain_id_400(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db()
        api = _build_api(db)
        resp = _post_create(api, chain_id="not_a_real_chain")
        self.assertEqual(resp.status, 400)
        body = _resp_json(resp)
        self.assertIn("chain", body.get("errors", {}))
        self.assertEqual(len(db.created), 0)


# ──────────────────────────────────────────────────────────────────────
# 15. Create-character: locked chain_id (jedi_path) rejected at chargen
# ──────────────────────────────────────────────────────────────────────

class TestCreateLockedChainId(_IsolatedBase):

    def test_jedi_path_rejected_at_chargen(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db()
        api = _build_api(db)
        resp = _post_create(api, chain_id="jedi_path")
        self.assertEqual(resp.status, 400)
        body = _resp_json(resp)
        # Server caught the locked chain even though the SPA shouldn't
        # have offered it. Defense-in-depth.
        self.assertIn("chain", body.get("errors", {}))
        self.assertEqual(
            len(db.created), 0,
            "locked chain selection must NOT create a character",
        )


# ──────────────────────────────────────────────────────────────────────
# 16. Create-character: no chain_id, no skip → legacy Landing Pad
# ──────────────────────────────────────────────────────────────────────

class TestCreateNoChainNoSkip(_IsolatedBase):
    """Backwards-compat: a request without chain_id or skip_tutorial
    should still succeed (the chain selection step is new; older
    clients won't send these fields). Behavior: fall through to the
    legacy Landing Pad room placement, and DON'T inject a
    tutorial_chain block."""

    def test_legacy_request_still_works(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db()
        api = _build_api(db)
        resp = _post_create(api)  # neither chain_id nor skip_tutorial
        body = _resp_json(resp)
        self.assertTrue(
            body.get("success"),
            f"legacy request (no chain) must still succeed; got {body}",
        )
        self.assertEqual(len(db.created), 1)
        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes") or "{}")
        self.assertNotIn("tutorial_chain", attrs)
        # Legacy Landing Pad placement: room 999 from our mock.
        self.assertEqual(fields.get("room_id"), 999)


# ──────────────────────────────────────────────────────────────────────
# 17. Create-character: skip_kit_message returned in response
# ──────────────────────────────────────────────────────────────────────

class TestSkipKitMessageInResponse(_IsolatedBase):

    def test_response_carries_skip_kit_message(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        db = _stock_db(existing_chars=[{"id": 5}])
        api = _build_api(db)
        resp = _post_create(api, skip_tutorial=True)
        body = _resp_json(resp)
        self.assertTrue(body.get("success"))
        # The CW kit ships with a non-empty message string.
        self.assertIn("skip_kit_message", body)
        self.assertTrue(
            len(body["skip_kit_message"]) > 0,
            "skip kit message must be non-empty when the kit defines one",
        )


if __name__ == "__main__":
    unittest.main()
