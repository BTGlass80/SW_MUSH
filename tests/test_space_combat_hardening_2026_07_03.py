# -*- coding: utf-8 -*-
"""tests/test_space_combat_hardening_2026_07_03.py

Space-combat hardening drop (1 BLOCKER + 3 corruption bugs in the
`space-anomaly-live-combat` feature, all proven live by a break-it pass).

  #1 BLOCKER -- `fire`-killing a live combat-AI combatant (a `course anomaly`
     pirate) never flipped the combatant's own destroyed check (nothing feeds
     `NpcSpaceCombatManager.apply_damage_to_npc` -- the fire path writes hull
     damage straight to the DB row), leaving an unkillable ghost combatant
     that keeps firing and can't be re-targeted (its DB row is already gone).
     Fix: `FireCommand._apply_hull_damage` now calls the new
     `NpcSpaceCombatManager.destroy_combatant(..., already_rewarded=True)`
     the moment it confirms a kill, so the combat-AI's own
     `_handle_combat_end("destroyed")` teardown runs (removing the
     combatant) but SKIPS its own wreck-spawn + bounty section (the fire
     path already owns both) -- exactly-once reward, exactly-once wreck.

  #2 `course anomaly <id>` special-cased BEFORE the pilot/authorization
     gate (`_validate_helm`), letting a non-pilot passenger with no station
     unilaterally commit the crewed ship to combat. Fix: `_engage_anomaly`
     now runs `_validate_helm` (pilot/docked/hyperspace/ion-frozen) first,
     exactly like `course <zone>`.

  #3 Two sessions racing `course anomaly <id>` on the SAME anomaly both
     passed the exists/resolved check (the up-front `remove_anomaly` claim
     used to happen only at the tail end, after the awaited hostile-spawn
     loop) -- both got independent combat + potential bounty from ONE
     anomaly. Fix: `_engage_anomaly` claims the anomaly (removes it)
     synchronously, immediately after resolving `spec`, before any mechanic
     dispatch ever awaits -- the loser's own `remove_anomaly` call (or its
     subsequent anomaly lookup) finds it already gone.

  #4 Engaging mid-sublight-transit spawned a hostile whose zone never gets
     reconciled once the player's ship arrives at its destination zone,
     leaving an untargetable hostile. Fix: `_engage_anomaly` now refuses
     while `systems["sublight_transit"]` is set, mirroring `course <zone>`'s
     own "Already in transit" refusal (and `in_hyperspace` is covered for
     free via the reused `_validate_helm`).

Mirrors the lightweight fake-ctx/db/session harness style already used by
tests/test_space_anomaly_richer_resolution_2026_07_02.py (no live GameServer
boot needed for these unit-level seams).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from engine.npc_space_combat_ai import NpcSpaceCombatManager, SpaceCombatProfile
from engine.npc_space_traffic import (
    NpcSpaceTrafficManager, TrafficArchetype, TrafficShip, TrafficState,
)
from engine.space_anomalies import Anomaly, _anomalies
from parser.space_commands import CourseCommand, FireCommand


# ── shared fakes ─────────────────────────────────────────────────────────────

class _Sess:
    def __init__(self, character):
        self.character = character
        self.lines: list[str] = []

    async def send_line(self, text):
        self.lines.append(text)

    async def send_hud_update(self, **kw):
        pass


class _SessionMgr:
    """Tracks bridge broadcasts + lets tests register per-room sessions."""

    def __init__(self):
        self.broadcasts: list[tuple] = []
        self._rooms: dict[int, list] = {}

    def register(self, room_id, sess):
        self._rooms.setdefault(room_id, []).append(sess)

    def sessions_in_room(self, room_id):
        return list(self._rooms.get(room_id, []))

    async def broadcast_to_room(self, room_id, msg, exclude=None):
        self.broadcasts.append((room_id, msg))


class _FireDB:
    """Minimal DB double for FireCommand._apply_hull_damage."""

    def __init__(self):
        self.update_ship_calls = []
        self.adjust_calls = []
        self.deleted_traffic_ships = []

    async def update_ship(self, ship_id, **kw):
        self.update_ship_calls.append((ship_id, kw))

    async def adjust_credits(self, char_id, delta, tag, **kw):
        self.adjust_calls.append((char_id, delta, tag))
        return delta

    async def delete_traffic_ship(self, ship_id):
        self.deleted_traffic_ships.append(ship_id)

    async def get_ship(self, ship_id):
        return None


class _FireCtx:
    def __init__(self, db, session, session_mgr):
        self.db = db
        self.session = session
        self.session_mgr = session_mgr


def _run(coro):
    return asyncio.run(coro)


# ── #1 BLOCKER: fire-kill tears down the ghost combatant, exactly-once ──────

def test_fire_kill_of_live_combatant_removes_ghost_pays_and_wrecks_once(
        monkeypatch):
    NPC_ID = 900123
    BRIDGE_ROOM = 4242
    ZONE = "hardening_b1_zone"

    fresh_traffic = NpcSpaceTrafficManager()
    fresh_combat = NpcSpaceCombatManager()
    # _apply_hull_damage resolves `get_traffic_manager` as a MODULE GLOBAL of
    # parser.space_commands (eager `from ... import get_traffic_manager` at
    # the top of the file) -- patch it there, not on engine.npc_space_traffic,
    # or the patch is invisible to this call site.
    monkeypatch.setattr(
        "parser.space_commands.get_traffic_manager", lambda: fresh_traffic)
    # The new teardown call is a LAZY `from engine.npc_space_combat_ai import
    # get_npc_combat_manager` inside _apply_hull_damage -- patch it at its
    # source module so the lazy re-import picks it up.
    monkeypatch.setattr(
        "engine.npc_space_combat_ai.get_npc_combat_manager",
        lambda: fresh_combat)

    ts = TrafficShip(
        ship_id=NPC_ID, archetype=TrafficArchetype.PIRATE,
        state=TrafficState.IDLE, current_zone=ZONE,
        display_name="Raider Ghost", transponder_type="combat",
    )
    ts.in_live_combat = True
    fresh_traffic._ships[NPC_ID] = ts

    fresh_combat.promote_to_combat(
        npc_ship_id=NPC_ID, target_ship_id=1, target_bridge_room=BRIDGE_ROOM,
        zone_id=ZONE, template_key="z95", display_name="Raider Ghost",
        crew_skill="3D", profile="aggressive",
    )
    assert fresh_combat.get_combatant(NPC_ID) is not None  # sanity: live

    player_char = {"id": 1, "name": "Firer", "credits": 0}
    session = _Sess(player_char)
    session_mgr = _SessionMgr()
    session_mgr.register(BRIDGE_ROOM, session)
    db = _FireDB()
    ctx = _FireCtx(db, session, session_mgr)

    ship = {"id": 5, "bridge_room_id": BRIDGE_ROOM,
            "systems": json.dumps({"current_zone": ZONE})}
    target_ship = {"id": NPC_ID, "hull_damage": 0,
                   "name": "Raider Ghost", "systems": json.dumps({})}
    target_template = SimpleNamespace(hull="1D")
    pools = {"target_eff": {"hull": "1D"}}
    result = SimpleNamespace(hull_damage=999, systems_hit=[])

    import engine.space_anomalies as sa
    wreck_calls = []
    orig_add_wreck = sa.add_wreck_anomaly

    def _spy_add_wreck(zone_id, name):
        wreck_calls.append((zone_id, name))
        return orig_add_wreck(zone_id, name)

    monkeypatch.setattr(sa, "add_wreck_anomaly", _spy_add_wreck)

    fire = FireCommand()
    _run(fire._apply_hull_damage(
        ctx, ship, target_ship, target_template, pools, result))

    # (a) the ghost combatant is gone -- no longer tracked at all.
    assert fresh_combat.get_combatant(NPC_ID) is None

    # (b) bounty paid EXACTLY once (the fire path's own award).
    bounty_calls = [c for c in db.adjust_calls if c[2] == "npc_pirate_bounty"]
    assert len(bounty_calls) == 1, db.adjust_calls

    # (c) wreck spawned EXACTLY once (not doubled by the combat-AI teardown).
    assert len(wreck_calls) == 1, wreck_calls

    # (d) traffic-side despawn actually happened (DB row deleted, in-memory
    # entry gone) -- this is *why* `fire`/`fleeship` couldn't re-target it.
    assert fresh_traffic.get_ship(NPC_ID) is None
    assert db.deleted_traffic_ships == [NPC_ID]

    # (e) the regression itself: a subsequent tick fires NO further
    # [INCOMING] from the (now nonexistent) ghost -- pre-fix this would
    # still be in _combatants and keep shooting forever.
    _run(fresh_combat.tick(db, session_mgr))
    incoming = [m for _r, m in session_mgr.broadcasts if "[INCOMING]" in m]
    assert incoming == []


def test_fire_kill_of_ordinary_traffic_ship_unaffected(monkeypatch):
    """A normal (non-combat-AI) traffic-ship kill must still work exactly as
    before -- destroy_combatant() must no-op cleanly when there's no live
    combatant for the id (the overwhelming majority of `fire` kills)."""
    NPC_ID = 900456
    ZONE = "hardening_b1_ordinary_zone"

    fresh_traffic = NpcSpaceTrafficManager()
    fresh_combat = NpcSpaceCombatManager()  # NO combatant registered
    monkeypatch.setattr(
        "parser.space_commands.get_traffic_manager", lambda: fresh_traffic)
    monkeypatch.setattr(
        "engine.npc_space_combat_ai.get_npc_combat_manager",
        lambda: fresh_combat)

    ts = TrafficShip(
        ship_id=NPC_ID, archetype=TrafficArchetype.PIRATE,
        state=TrafficState.IDLE, current_zone=ZONE,
        display_name="Ambient Raider", transponder_type="none",
    )
    fresh_traffic._ships[NPC_ID] = ts

    db = _FireDB()
    session = _Sess({"id": 1, "name": "Firer", "credits": 0})
    ctx = _FireCtx(db, session, _SessionMgr())
    ship = {"id": 5, "bridge_room_id": 1,
            "systems": json.dumps({"current_zone": ZONE})}
    target_ship = {"id": NPC_ID, "hull_damage": 0, "name": "Ambient Raider",
                   "systems": json.dumps({})}
    target_template = SimpleNamespace(hull="1D")
    pools = {"target_eff": {"hull": "1D"}}
    result = SimpleNamespace(hull_damage=999, systems_hit=[])

    fire = FireCommand()
    _run(fire._apply_hull_damage(
        ctx, ship, target_ship, target_template, pools, result))

    bounty_calls = [c for c in db.adjust_calls if c[2] == "npc_pirate_bounty"]
    assert len(bounty_calls) == 1
    assert db.deleted_traffic_ships == [NPC_ID]
    assert fresh_combat.get_combatant(NPC_ID) is None  # still nothing there


# ── #2: pilot/authorization gate ────────────────────────────────────────────

class _AnomalyDB:
    def __init__(self, ships_by_room):
        self.ships_by_room = ships_by_room
        self.adjust_calls = []

    async def get_ship_by_bridge(self, room_id):
        return self.ships_by_room.get(room_id)

    async def adjust_credits(self, char_id, delta, tag, **kw):
        # perform_skill_check rolls real dice -- a pilot's engagement attempt
        # may succeed (payout) or fail-closed depending on the roll, so this
        # must be a real (if trivial) funnel target either way, not absent.
        self.adjust_calls.append((char_id, delta, tag))
        return delta


class _AnomalyCtx:
    def __init__(self, db, character, args):
        self.db = db
        self.session = _Sess(character)
        self.session_mgr = None
        self.args = args


def test_course_anomaly_refuses_non_pilot_passenger():
    ZONE = "hardening_b2_zone"
    _anomalies[ZONE] = [
        Anomaly(id=501, zone_id=ZONE, anomaly_type="distress", resolution=2)]
    ship = {"id": 1, "docked_at": None, "bridge_room_id": 100,
            "crew": json.dumps({"pilot": 11}),
            "systems": json.dumps({"current_zone": ZONE})}
    db = _AnomalyDB({100: ship})

    # A passenger with no station (not the pilot) tries to commit the ship.
    passenger_ctx = _AnomalyCtx(db, {"id": 99, "room_id": 100}, "anomaly 501")
    cmd = CourseCommand()
    _run(cmd._engage_anomaly(passenger_ctx, "anomaly 501"))

    assert any("Only the pilot" in l for l in passenger_ctx.session.lines)
    # Refused before ever touching the anomaly -- still there, unclaimed.
    assert len(_anomalies[ZONE]) == 1


def test_course_anomaly_pilot_is_not_refused():
    ZONE = "hardening_b2_pilot_zone"
    _anomalies[ZONE] = [
        Anomaly(id=502, zone_id=ZONE, anomaly_type="distress", resolution=2)]
    ship = {"id": 1, "docked_at": None, "bridge_room_id": 100,
            "crew": json.dumps({"pilot": 11}),
            "systems": json.dumps({"current_zone": ZONE})}
    db = _AnomalyDB({100: ship})

    pilot_ctx = _AnomalyCtx(
        db, {"id": 11, "room_id": 100, "attributes": json.dumps({}),
             "skills": json.dumps({})},
        "anomaly 502")
    cmd = CourseCommand()
    _run(cmd._engage_anomaly(pilot_ctx, "anomaly 502"))

    assert not any("Only the pilot" in l for l in pilot_ctx.session.lines)
    # distress is one-shot: claimed (removed) whether the roll succeeds or
    # fails-closed -- proves the pilot got PAST the authorization gate and
    # into the real engagement mechanic.
    assert _anomalies.get(ZONE, []) == []


# ── #3: concurrent-engage race ──────────────────────────────────────────────

def test_concurrent_engage_of_same_anomaly_exactly_one_wins(monkeypatch):
    import engine.npc_space_traffic as nst
    import engine.npc_space_combat_ai as nsc

    ZONE = "hardening_b3_zone"
    _anomalies[ZONE] = [
        Anomaly(id=777, zone_id=ZONE, anomaly_type="pirates", resolution=2)]

    class _FakeTrafficMgr:
        def __init__(self):
            self.spawns = []

        async def spawn_for_encounter(self, db, session_mgr, zone_id, archetype):
            # Real production award has a genuine DB-await yield point here
            # (db.create_traffic_ship); reproduce it so the two racing
            # coroutines actually interleave instead of one running to
            # completion before the other is ever scheduled.
            await asyncio.sleep(0)
            sid = 90000 + len(self.spawns)
            self.spawns.append((zone_id, archetype))
            ts = SimpleNamespace(ship_id=sid, display_name=f"Hostile-{sid}",
                                 transponder_type="none", in_live_combat=False)
            return ts, {"template": "z95", "crew_skill": "3D"}

    class _FakeCombatMgr:
        def __init__(self):
            self.promotes = []

        def promote_to_combat(self, **kw):
            self.promotes.append(kw)
            return object()

    ftraffic, fcombat = _FakeTrafficMgr(), _FakeCombatMgr()
    monkeypatch.setattr(nst, "get_traffic_manager", lambda: ftraffic)
    monkeypatch.setattr(nsc, "get_npc_combat_manager", lambda: fcombat)

    class _RaceDB:
        def __init__(self, ships_by_room):
            self.ships_by_room = ships_by_room

        async def get_ship_by_bridge(self, room_id):
            # The shared, deliberate concurrency window: BOTH racers pass
            # through this exact await before either reaches the claim, so
            # the test genuinely exercises the interleave instead of
            # trivially serializing.
            await asyncio.sleep(0)
            return self.ships_by_room.get(room_id)

    ship_a = {"id": 1, "docked_at": None, "bridge_room_id": 100,
              "crew": json.dumps({"pilot": 11}),
              "systems": json.dumps({"current_zone": ZONE})}
    ship_b = {"id": 2, "docked_at": None, "bridge_room_id": 200,
              "crew": json.dumps({"pilot": 22}),
              "systems": json.dumps({"current_zone": ZONE})}
    db = _RaceDB({100: ship_a, 200: ship_b})

    ctx_a = _AnomalyCtx(db, {"id": 11, "room_id": 100}, "anomaly 777")
    ctx_b = _AnomalyCtx(db, {"id": 22, "room_id": 200}, "anomaly 777")

    cmd = CourseCommand()

    async def _race():
        await asyncio.gather(
            cmd._engage_anomaly(ctx_a, "anomaly 777"),
            cmd._engage_anomaly(ctx_b, "anomaly 777"),
        )

    _run(_race())

    # Exactly one anomaly's worth of hostiles spawned (2-3), not two nests.
    assert 2 <= len(ftraffic.spawns) <= 3, ftraffic.spawns
    assert len(fcombat.promotes) == len(ftraffic.spawns)

    all_lines = ctx_a.session.lines + ctx_b.session.lines
    combat_msgs = [l for l in all_lines if "[COMBAT]" in l]
    refusal_msgs = [l for l in all_lines if "No anomaly #777" in l]
    assert len(combat_msgs) == 1, all_lines
    assert len(refusal_msgs) == 1, all_lines

    # The contact is fully consumed -- not left half-claimed for a 3rd racer.
    assert _anomalies.get(ZONE, []) == []


# ── #4: mid-transit refusal ──────────────────────────────────────────────────

def test_course_anomaly_refused_mid_sublight_transit():
    ZONE = "hardening_b4_zone"
    _anomalies[ZONE] = [
        Anomaly(id=901, zone_id=ZONE, anomaly_type="mynock", resolution=1)]
    ship = {"id": 1, "docked_at": None, "bridge_room_id": 100,
            "crew": json.dumps({"pilot": 11}),
            "systems": json.dumps({"current_zone": ZONE,
                                   "sublight_transit": True})}
    db = _AnomalyDB({100: ship})

    ctx = _AnomalyCtx(db, {"id": 11, "room_id": 100}, "anomaly 901")
    cmd = CourseCommand()
    _run(cmd._engage_anomaly(ctx, "anomaly 901"))

    assert any("Already in transit" in l for l in ctx.session.lines)
    # Never reached the claim -- the anomaly is untouched.
    assert len(_anomalies[ZONE]) == 1


def test_course_anomaly_refused_mid_hyperspace():
    """Bonus coverage: _validate_helm's existing in_hyperspace refusal is now
    reused for free by _engage_anomaly -- pin it too."""
    ZONE = "hardening_b4_hyperspace_zone"
    _anomalies[ZONE] = [
        Anomaly(id=902, zone_id=ZONE, anomaly_type="mynock", resolution=1)]
    ship = {"id": 1, "docked_at": None, "bridge_room_id": 100,
            "crew": json.dumps({"pilot": 11}),
            "systems": json.dumps({"current_zone": ZONE,
                                   "in_hyperspace": True})}
    db = _AnomalyDB({100: ship})

    ctx = _AnomalyCtx(db, {"id": 11, "room_id": 100}, "anomaly 902")
    cmd = CourseCommand()
    _run(cmd._engage_anomaly(ctx, "anomaly 902"))

    assert any("hyperspace" in l.lower() for l in ctx.session.lines)
    assert len(_anomalies[ZONE]) == 1
