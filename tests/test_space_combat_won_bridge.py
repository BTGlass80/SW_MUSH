# -*- coding: utf-8 -*-
"""
tests/test_space_combat_won_bridge.py — capital-ship-combat-bridge
(2026-07-03): the space-combat -> chain-event bridge that credits a
DESTROY kill on a chain-tagged capital ship to a `space_combat_won`
questline step.

Per DESIGN_capital_ship_combat_2026-07-03.md — the FIRST slice (destroy
win only; disable/board and the crewed multi-gunner tier are deferred,
see TODO.json). Proves:

  1. `space_combat_won` is registered in ALLOWED_COMPLETION_TYPES (and
     the two linter copies stay in sync).
  2. `_match_space_combat_won` / `on_space_combat_won` advance a
     `space_combat_won` step on an exact tag match and no-op on a
     mismatch.
  3. The real `kuat_capital_intercept` questline loads with the new
     completion shape (step 1 `command_executed` "course intercept" ->
     step 2 `space_combat_won`).
  4. THE PROVING CRITERION: a walkthrough that actually DESTROYS the
     tagged light-capital through the REAL production seam --
     `CourseCommand._engage_intercept` (spawn + promote) ->
     `FireCommand._apply_hull_damage` (kill-detect) ->
     `handle_traffic_ship_destroyed` -> `on_space_combat_won` --
     advances step 2 and graduates the questline. NOT a hand-injected
     `on_space_combat_won` call. Same anti-hand-injection discipline as
     the staged-cult reward bug.
  5. The ground-foil winnability guard
     (test_questline_foil_winnability_band.py) keys off
     `ai_config.chain_enemy_template` on NPC yaml rows and never
     collects our ship tag -- confirmed by construction (no NPC drop
     file backs this arc; the tag lives on TrafficShip, a distinct
     field name in a distinct data shape).
  6. Verify-drop hardening (same-day code review): the destroy path is
     reentrancy-latched via TrafficShip.destroy_consumed (exactly one
     consumer per kill under a multi-gunner race), a failed
     promote_to_combat no longer claims "weapons hot", and lifetime
     expiry DEFERS while NpcSpaceCombatManager owns the ship --
     released again by remove_combatant().
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CHAIN_ID = "kuat_capital_intercept"
SHIP_TAG = "kuat_intercept_rogue_cutter"
SHIP_TEMPLATE_KEY = "rogue_customs_cutter"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── #1: registration ────────────────────────────────────────────────────

class TestSpaceCombatWonRegistered(unittest.TestCase):

    def test_type_registered_in_engine(self):
        from engine.tutorial_chains import ALLOWED_COMPLETION_TYPES
        self.assertIn("space_combat_won", ALLOWED_COMPLETION_TYPES)

    def test_linter_copies_in_sync(self):
        from tools.verify_tutorial_chains import (
            ALLOWED_COMPLETION_TYPES as VT_TYPES,
        )
        from tools.verify_jedi_village import (
            ALLOWED_COMPLETION_TYPES as VJ_TYPES,
        )
        self.assertIn("space_combat_won", VT_TYPES)
        self.assertIn("space_combat_won", VJ_TYPES)


# ── #2: matcher + dispatcher unit behavior ──────────────────────────────

class TestMatchSpaceCombatWon(unittest.TestCase):

    def test_exact_tag_match_and_count(self):
        from engine.chain_events import _match_space_combat_won
        completion = {"type": "space_combat_won",
                      "enemy_ship_template": SHIP_TAG, "enemy_count": 1}
        self.assertTrue(_match_space_combat_won(completion, SHIP_TAG, 1))

    def test_mismatched_tag_does_not_match(self):
        from engine.chain_events import _match_space_combat_won
        completion = {"type": "space_combat_won",
                      "enemy_ship_template": SHIP_TAG, "enemy_count": 1}
        self.assertFalse(
            _match_space_combat_won(completion, "some_other_ship", 1))

    def test_count_below_enemy_count_does_not_match(self):
        from engine.chain_events import _match_space_combat_won
        completion = {"type": "space_combat_won",
                      "enemy_ship_template": SHIP_TAG, "enemy_count": 2}
        self.assertFalse(_match_space_combat_won(completion, SHIP_TAG, 1))

    def test_empty_expected_template_never_matches(self):
        from engine.chain_events import _match_space_combat_won
        self.assertFalse(_match_space_combat_won({}, SHIP_TAG, 1))


# ── shared real-corpus harness (mirrors test_t5_questline_content.py) ──

def _char(attrs: dict = None) -> dict:
    base = {"chargen_complete": True}
    base.update(attrs or {})
    return {
        "id": 4242, "name": "Freelance Pilot", "room_id": 100,
        "credits": 0, "attributes": json.dumps(base),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


class _RealCorpusBase(unittest.TestCase):
    """Flip active era to clone_wars so both the real chain corpus AND
    the real ship registry (rogue_customs_cutter, consular_cruiser) are
    loaded, exactly as they are in production."""

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.starships import reset_ship_registry
        import engine.chain_events as ce
        set_active_config(SimpleNamespace(active_era="clone_wars"))
        reset_ship_registry()
        ce._reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.starships import reset_ship_registry
        import engine.chain_events as ce
        clear_active_config()
        reset_ship_registry()
        ce._reset_corpus_cache()


# ── #3: the chain loads with the new completion shape ───────────────────

class TestChainLoadsWithNewCompletionShape(_RealCorpusBase):

    def test_chain_in_real_corpus_is_two_step_bridge(self):
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains("clone_wars")
        chain = corpus.by_id().get(CHAIN_ID)
        self.assertIsNotNone(chain, f"{CHAIN_ID} missing from real corpus")
        self.assertEqual(chain.kind, "questline")
        self.assertEqual(len(chain.steps), 2)
        step_a, step_b = chain.steps
        self.assertEqual(step_a.completion.get("type"), "command_executed")
        self.assertEqual(step_a.completion.get("command"), "course")
        self.assertEqual(step_a.completion.get("target_contains"),
                          "intercept")
        self.assertEqual(step_b.completion.get("type"), "space_combat_won")
        self.assertEqual(step_b.completion.get("enemy_ship_template"),
                          SHIP_TAG)
        self.assertEqual(step_b.completion.get("enemy_count", 1), 1)

    def test_ship_template_resolves_capital_scale_and_beatable(self):
        """The tagged target's hull registers, is capital-scale, and its
        hull dice parse to a bounded (not marathon) destruction
        threshold -- hull_dice*6 per FireCommand._apply_hull_damage."""
        from engine.starships import get_ship_registry
        from engine.dice import DicePool
        reg = get_ship_registry()
        tmpl = reg.get(SHIP_TEMPLATE_KEY)
        self.assertIsNotNone(tmpl, f"{SHIP_TEMPLATE_KEY} not registered")
        self.assertEqual(tmpl.scale, "capital")
        hull_dice = int(tmpl.hull.split("D")[0])
        self.assertEqual(hull_dice, 2)  # -> 12-pip destruction threshold
        self.assertLess(DicePool.parse(tmpl.shields).total_pips(),
                         DicePool.parse(tmpl.hull).total_pips())


# ── #4 no-op-on-mismatch + advance-on-match against the REAL corpus ────

class TestOnSpaceCombatWonAgainstRealChain(_RealCorpusBase):

    def _char_at_step2(self):
        from engine.tutorial_chains import _QUESTLINE_KEY
        return _char({_QUESTLINE_KEY: {
            "completion_state": "active", "chain_id": CHAIN_ID, "step": 2,
        }})

    def test_mismatched_tag_is_a_no_op(self):
        from engine.chain_events import on_space_combat_won
        from engine.tutorial_chains import _QUESTLINE_KEY
        char = self._char_at_step2()
        db = mock.MagicMock()
        db.save_character = mock.AsyncMock()
        advanced = _run(on_space_combat_won(db, char, "not_the_tag", 1))
        self.assertFalse(advanced)
        self.assertEqual(_attrs(char)[_QUESTLINE_KEY]["step"], 2)
        db.save_character.assert_not_called()

    def test_exact_tag_advances_and_graduates(self):
        from engine.chain_events import on_space_combat_won
        from engine.tutorial_chains import _QUESTLINE_KEY, is_chain_complete
        char = self._char_at_step2()
        db = mock.MagicMock()
        db.save_character = mock.AsyncMock()
        db.get_room_by_slug = mock.AsyncMock(return_value={"id": 999})
        db.adjust_credits = mock.AsyncMock(return_value=450)
        advanced = _run(on_space_combat_won(db, char, SHIP_TAG, 1))
        self.assertTrue(advanced)
        self.assertTrue(is_chain_complete(_attrs(char), _QUESTLINE_KEY))


# ── #5: the proving criterion — a REAL kill through the REAL seam ──────

class _Sess:
    def __init__(self, character):
        self.character = character
        self.lines: list[str] = []

    async def send_line(self, text):
        self.lines.append(text)

    async def send_hud_update(self, **kw):
        pass


class _SessionMgr:
    def __init__(self):
        self.broadcasts = []

    async def broadcast_to_room(self, room_id, msg, exclude=None):
        self.broadcasts.append((room_id, msg))

    def sessions_in_room(self, room_id):
        return []


class _BridgeDB:
    """Minimal DB double covering every call the intercept-spawn +
    fire-kill + chain-advance + graduation path makes. Chain-state
    mutation itself is in-memory on the `char` dict (chain_events._
    persist_attrs writes char["attributes"] directly) -- this fake only
    needs to not blow up on the awaited calls."""

    def __init__(self, ship_by_room: dict, teleport_room_id: int = 999):
        self.ship_by_room = ship_by_room
        self._next_ship_id = 90000
        self.deleted_traffic_ships = []
        self.update_ship_calls = []
        self._teleport_room_id = teleport_room_id

    async def get_ship_by_bridge(self, room_id):
        return self.ship_by_room.get(room_id)

    async def create_traffic_ship(self, name, template):
        self._next_ship_id += 1
        return self._next_ship_id

    async def create_traffic_npc(self, name, ship_id, skill):
        return 1

    async def update_traffic_ship_state(self, ship_id, data):
        pass

    async def update_ship(self, ship_id, **kw):
        self.update_ship_calls.append((ship_id, kw))

    async def delete_traffic_ship(self, ship_id):
        self.deleted_traffic_ships.append(ship_id)

    async def get_ship(self, ship_id):
        return None

    async def adjust_credits(self, char_id, delta, tag, **kw):
        return delta

    async def save_character(self, char_id, **kw):
        return True

    async def get_room_by_slug(self, slug):
        # start_questline's inter-step teleport to step 1's authored
        # `location` resolves through this -- return the SAME room the
        # player's ship bridge lives in (see teleport_room_id) so the
        # move is a no-op and the ship lookup keeps working afterward.
        return {"id": self._teleport_room_id}


class _Ctx:
    def __init__(self, db, session, session_mgr, args=""):
        self.db = db
        self.session = session
        self.session_mgr = session_mgr
        self.args = args


class TestRealKillWalkthroughAdvancesAndGraduates(_RealCorpusBase):
    """The proving criterion. Every step below runs through the REAL
    production function -- no hand-injected on_space_combat_won call."""

    ZONE = "kuat_deep_space"
    BRIDGE_ROOM = 555

    def setUp(self):
        super().setUp()
        import engine.npc_space_traffic as nst
        import engine.npc_space_combat_ai as nsc
        self.traffic = nst.NpcSpaceTrafficManager()
        self.combat = nsc.NpcSpaceCombatManager()
        self._patchers = [
            mock.patch("parser.space_commands.get_traffic_manager",
                       lambda: self.traffic),
            mock.patch("engine.npc_space_combat_ai.get_npc_combat_manager",
                       lambda: self.combat),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        super().tearDown()

    def test_destroying_the_tagged_capital_advances_and_graduates(self):
        from engine.chain_events import (
            start_questline, on_command_executed,
        )
        from engine.tutorial_chains import (
            _QUESTLINE_KEY, get_current_step, load_tutorial_chains,
            is_chain_complete,
        )
        from parser.space_commands import CourseCommand, FireCommand

        char = _char()
        # The player starts already standing at their ship's bridge room --
        # `start_questline`'s inter-step teleport (step 1's authored
        # `location: kuat_arrivals`) will move char["room_id"] via the
        # fake DB's get_room_by_slug below, so keep both in lockstep with
        # BRIDGE_ROOM rather than a separate ground room this fake DB
        # doesn't otherwise model.
        char["room_id"] = self.BRIDGE_ROOM
        player_ship = {
            "id": 1, "docked_at": None, "bridge_room_id": self.BRIDGE_ROOM,
            "template": "consular_cruiser",
            "crew": json.dumps({"pilot": char["id"]}),
            "systems": json.dumps({"current_zone": self.ZONE}),
        }
        db = _BridgeDB({self.BRIDGE_ROOM: player_ship},
                       teleport_room_id=self.BRIDGE_ROOM)
        session = _Sess(char)
        session_mgr = _SessionMgr()
        ctx = _Ctx(db, session, session_mgr, args="intercept")

        # 1) Start the real questline -- lands on step 1.
        ok, msg = _run(start_questline(db, char, CHAIN_ID))
        self.assertTrue(ok, msg)
        corpus = load_tutorial_chains("clone_wars")
        step = get_current_step(_attrs(char), corpus, _QUESTLINE_KEY)
        self.assertEqual(step.step, 1)

        # 2) `course intercept` -- the REAL spawn+promote seam (mirrors
        # the live `course anomaly` promote path). NOT a hand-placed ship.
        cmd = CourseCommand()
        _run(cmd._engage_intercept(ctx, "intercept"))
        zone_ships = self.traffic.get_zone_ships(self.ZONE)
        tagged = [s for s in zone_ships
                  if s.chain_enemy_ship_template == SHIP_TAG]
        self.assertEqual(len(tagged), 1, zone_ships)
        ts = tagged[0]
        self.assertIsNotNone(
            self.combat.get_combatant(ts.ship_id),
            "spawned target was not promoted to live combat")

        # 3) The parser's real post-execute hook: `course intercept`
        # succeeded, so on_command_executed fires exactly like
        # parser/commands.py does after every successful command.
        advanced = _run(on_command_executed(db, char, "course", "intercept"))
        self.assertTrue(advanced)
        step = get_current_step(_attrs(char), corpus, _QUESTLINE_KEY)
        self.assertEqual(step.step, 2)
        self.assertEqual(step.completion.get("type"), "space_combat_won")

        # 4) The REAL kill seam: FireCommand._apply_hull_damage detects
        # the threshold cross and tears the target down --
        # destroy_combatant -> handle_traffic_ship_destroyed ->
        # on_space_combat_won -- all inside this ONE call, exactly as
        # production wires it (space_commands.py:2784-2865).
        target_ship_row = {
            "id": ts.ship_id, "hull_damage": 0, "name": ts.display_name,
            "systems": json.dumps({"current_zone": self.ZONE}),
        }
        target_template = SimpleNamespace(hull="2D+2")
        pools = {"target_eff": {"hull": "2D+2"}}
        result = SimpleNamespace(hull_damage=999, systems_hit=[])
        fire = FireCommand()
        _run(fire._apply_hull_damage(
            ctx, player_ship, target_ship_row, target_template, pools,
            result))

        # 5) The proof: step 2 advanced (graduation, since it's the last
        # step) WITHOUT ever calling on_space_combat_won by hand.
        self.assertTrue(
            is_chain_complete(_attrs(char), _QUESTLINE_KEY),
            f"questline did not graduate; state={_attrs(char).get(_QUESTLINE_KEY)}")
        # And the target is actually gone (real despawn, real teardown).
        self.assertIsNone(self.traffic.get_ship(ts.ship_id))
        self.assertIsNone(self.combat.get_combatant(ts.ship_id))
        self.assertEqual(db.deleted_traffic_ships, [ts.ship_id])


# ── #6: the ground-foil winnability guard never sees this ship ─────────

class TestFoilWinnabilityGuardDoesNotCollectShipTag(unittest.TestCase):
    """DESIGN_capital_ship_combat_2026-07-03.md §8 guard caveat: the
    guard keys off ai_config.chain_enemy_template on NPC yaml rows.
    Confirm it never collects our ship tag -- no NPC drop file backs
    this arc; the tag lives on TrafficShip under a distinct field
    name."""

    def test_ship_tag_absent_from_ground_foil_collection(self):
        from tests.test_questline_foil_winnability_band import _load_foils
        foils = _load_foils()
        tags = {ai.get("chain_enemy_template") for _arc, _name, _cs, ai
                in foils}
        self.assertNotIn(SHIP_TAG, tags)
        self.assertNotIn(SHIP_TEMPLATE_KEY, tags)
        arcs = {arc for arc, _name, _cs, _ai in foils}
        self.assertNotIn("capital_intercept", arcs)


# ── #7: verify-drop hardening (2026-07-03 code-review findings) ─────────

class TestDestroyReentrancyLatch(unittest.TestCase):
    """MAJOR finding: handle_traffic_ship_destroyed had no reentrancy
    guard -- two kill-confirming `fire` resolutions on the same target
    (multi-gunner capital race) could interleave at its awaits and each
    independently pay the bounty / credit the chain step off ONE kill.
    The TrafficShip.destroy_consumed latch makes exactly one caller the
    consumer (returns int); every other caller gets None."""

    def _mgr_with_ship(self, chain_tag="", archetype=None):
        import engine.npc_space_traffic as nst
        mgr = nst.NpcSpaceTrafficManager()
        ship = nst.TrafficShip(
            ship_id=777,
            archetype=archetype or nst.TrafficArchetype.PATROL,
            state=nst.TrafficState.IDLE,
            current_zone="kuat_deep_space",
            display_name="Latch Target",
            chain_enemy_ship_template=chain_tag,
        )
        mgr._ships[ship.ship_id] = ship
        return nst, mgr, ship

    def test_interleaved_calls_consume_exactly_once(self):
        _nst, mgr, _ship = self._mgr_with_ship(chain_tag=SHIP_TAG)
        db = _BridgeDB({})
        smgr = _SessionMgr()
        char = {"id": 5, "credits": 0}
        hook_calls = []

        async def _race():
            entered = asyncio.Event()

            async def _hook(_db, _ch, tag, _n):
                hook_calls.append(tag)
                entered.set()
                # Park the consumer INSIDE the handler's await window --
                # exactly where the unguarded version double-paid.
                await asyncio.sleep(0.01)

            with mock.patch("engine.chain_events.on_space_combat_won",
                            new=_hook):
                t1 = asyncio.ensure_future(
                    mgr.handle_traffic_ship_destroyed(777, char, db, smgr))
                await entered.wait()
                r2 = await mgr.handle_traffic_ship_destroyed(
                    777, char, db, smgr)
                r1 = await t1
                return r1, r2

        r1, r2 = _run(_race())
        self.assertEqual(r1, 0, "consumer should win with the normal int")
        self.assertIsNone(r2, "racer must see the latch and get None")
        self.assertEqual(hook_calls, [SHIP_TAG],
                         "chain step credited more than once for one kill")

    def test_pirate_bounty_paid_once_under_race(self):
        nst, mgr, ship = self._mgr_with_ship()
        ship.archetype = nst.TrafficArchetype.PIRATE
        smgr = _SessionMgr()
        char = {"id": 5, "credits": 0}

        class _CountingDB(_BridgeDB):
            def __init__(self):
                super().__init__({})
                self.credit_calls = []
                self.entered = None  # created inside the loop

            async def adjust_credits(self, char_id, delta, tag, **kw):
                self.credit_calls.append((char_id, delta, tag))
                self.entered.set()
                await asyncio.sleep(0.01)
                return delta

        db = _CountingDB()

        async def _race():
            db.entered = asyncio.Event()
            t1 = asyncio.ensure_future(
                mgr.handle_traffic_ship_destroyed(777, char, db, smgr))
            await db.entered.wait()
            r2 = await mgr.handle_traffic_ship_destroyed(777, char, db, smgr)
            r1 = await t1
            return r1, r2

        r1, r2 = _run(_race())
        self.assertIsInstance(r1, int)
        self.assertGreater(r1, 0)
        self.assertIsNone(r2)
        self.assertEqual(len(db.credit_calls), 1,
                         "pirate bounty must pay exactly once per kill")


class TestInterceptPromoteFailureMessaging(unittest.TestCase):
    """MINOR finding: _engage_intercept claimed '[COMBAT] ... weapons
    hot' even when promote_to_combat raised (the hull spawns and stays
    killable but never becomes a live combatant / never returns fire).
    Failure now sends the running-dark variant instead -- mirrors
    _engage_combat's spawned==0 gating."""

    ZONE = "kuat_deep_space"
    BRIDGE_ROOM = 555

    def test_promote_failure_drops_weapons_hot_claim(self):
        import engine.npc_space_traffic as nst
        import engine.npc_space_combat_ai as nsc
        from parser.space_commands import CourseCommand

        traffic = nst.NpcSpaceTrafficManager()
        combat = nsc.NpcSpaceCombatManager()
        char = _char()
        char["room_id"] = self.BRIDGE_ROOM
        player_ship = {
            "id": 1, "docked_at": None, "bridge_room_id": self.BRIDGE_ROOM,
            "template": "consular_cruiser",
            "crew": json.dumps({"pilot": char["id"]}),
            "systems": json.dumps({"current_zone": self.ZONE}),
        }
        db = _BridgeDB({self.BRIDGE_ROOM: player_ship},
                       teleport_room_id=self.BRIDGE_ROOM)
        session = _Sess(char)
        smgr = _SessionMgr()
        ctx = _Ctx(db, session, smgr, args="intercept")

        with mock.patch("parser.space_commands.get_traffic_manager",
                        lambda: traffic), \
             mock.patch("engine.npc_space_combat_ai.get_npc_combat_manager",
                        lambda: combat), \
             mock.patch.object(combat, "promote_to_combat",
                               side_effect=RuntimeError("boom")):
            _run(CourseCommand()._engage_intercept(ctx, "intercept"))

        joined = "\n".join(session.lines)
        self.assertNotIn("weapons hot", joined)
        self.assertIn("running dark", joined)
        # The hull is still real (spawned, killable in principle) ...
        tagged = [s for s in traffic.get_zone_ships(self.ZONE)
                  if s.chain_enemy_ship_template == SHIP_TAG]
        self.assertEqual(len(tagged), 1)
        # ... but it never got the ambient live-combat hold.
        self.assertFalse(getattr(tagged[0], "in_live_combat", False))


class TestLifetimeExpiryDeferredInLiveCombat(unittest.TestCase):
    """MINOR finding: the ambient lifetime wind-down ran unconditionally
    in _tick_ship, so an expired chain-tagged target could be despawned
    mid-fight through a path that never reaches
    handle_traffic_ship_destroyed -- silently voiding the
    space_combat_won kill. Expiry now DEFERS while in_live_combat holds
    and resumes once it clears."""

    def _expired_ship(self, nst):
        import time as _time
        ship = nst.TrafficShip(
            ship_id=778,
            archetype=nst.TrafficArchetype.PATROL,
            state=nst.TrafficState.IDLE,
            current_zone="kuat_deep_space",
            spawned_at=_time.time() - 99999,
            max_lifetime=1.0,
        )
        return ship

    def test_wind_down_defers_then_resumes(self):
        import engine.npc_space_traffic as nst
        mgr = nst.NpcSpaceTrafficManager()
        ship = self._expired_ship(nst)
        ship.in_live_combat = True
        mgr._ships[778] = ship
        db = _BridgeDB({})
        smgr = _SessionMgr()
        self.assertTrue(ship.is_expired())

        with mock.patch.object(mgr, "_begin_wind_down",
                               new=mock.AsyncMock()) as wind_down, \
             mock.patch.object(mgr, "_tick_idle",
                               new=mock.AsyncMock(return_value=False)):
            _run(mgr._tick_ship(ship, db, smgr))
            wind_down.assert_not_awaited()   # deferred while owned
            ship.in_live_combat = False
            _run(mgr._tick_ship(ship, db, smgr))
            wind_down.assert_awaited_once()  # resumes on release


class TestRemoveCombatantReleasesAmbientHold(unittest.TestCase):
    """Companion to the expiry deferral: remove_combatant is the single
    ownership-release seam (destroyed / fled / target_destroyed all pop
    through it), so it must clear in_live_combat -- otherwise a fled
    fight would leave the deferral stuck on and leak the ambient ship
    forever."""

    def test_remove_clears_in_live_combat(self):
        import engine.npc_space_traffic as nst
        import engine.npc_space_combat_ai as nsc
        traffic = nst.NpcSpaceTrafficManager()
        combat = nsc.NpcSpaceCombatManager()
        ship = nst.TrafficShip(
            ship_id=779,
            archetype=nst.TrafficArchetype.PATROL,
            state=nst.TrafficState.IDLE,
            current_zone="kuat_deep_space",
        )
        ship.in_live_combat = True
        traffic._ships[779] = ship
        combat._combatants[779] = SimpleNamespace(npc_ship_id=779)

        with mock.patch("engine.npc_space_traffic.get_traffic_manager",
                        lambda: traffic):
            removed = combat.remove_combatant(779)

        self.assertIsNotNone(removed)
        self.assertFalse(ship.in_live_combat,
                         "ambient hold must release when combat lets go")


if __name__ == "__main__":
    unittest.main()
