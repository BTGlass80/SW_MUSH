# -*- coding: utf-8 -*-
"""Richer space-anomaly resolution (Brian 2026-07-02: 'make it more engaging').

The MVP resolved every non-derelict anomaly with one flat skill roll, and
cache/mynock/pirates passed a governing-ATTRIBUTE name where a skill SLUG was
expected -> the check silently rolled untrained dice. This drop branches each
type on a `mechanic` so the scan-readout's promised flow is delivered:
  distress = Perception (search) ambush gate
  cache    = two-step approach (space transports) + bypass (security), both pass
  mynock   = piloting detach; FAILURE damages a real ship system
  imperial = slicing decode (computer programming/repair)
  pirates  = a gunnery skirmish that drops a salvageable wreck on victory
The real multi-hostile combat is deferred (design call
SPACE.anomaly_combat_live_tick_vs_skirmish).
"""
import json
import asyncio

from engine.character import get_cached_skill_registry
from engine.skill_checks import _get_skill_pool
from engine.space_anomalies import Anomaly
from parser.space_commands import _ANOMALY_ENGAGE, CourseCommand


# ── helpers ────────────────────────────────────────────────────────────────
def _engagement_skills():
    """Every (skill, diff) across the skill-check mechanics, including two-step
    steps. `combat` (pirates) has no pre-roll skill — it spawns hostiles."""
    out = []
    for t, spec in _ANOMALY_ENGAGE.items():
        m = spec["mechanic"]
        if m == "two_step":
            out += [(t, s, d) for (s, d) in spec["steps"]]
        elif m == "combat":
            continue
        else:
            out.append((t, spec["skill"], spec["diff"]))
    return out


class _Sess:
    def __init__(self):
        self.lines = []

    async def send_line(self, text):
        self.lines.append(text)

    async def send_hud_update(self, **kw):
        pass


class _DB:
    def __init__(self, bal=5000):
        self.bal = bal
        self.adjust_calls = []
        self.update_ship_calls = []

    async def adjust_credits(self, char_id, delta, tag):
        self.adjust_calls.append((char_id, delta, tag))
        self.bal += delta
        return self.bal

    async def update_ship(self, ship_id, **kw):
        self.update_ship_calls.append((ship_id, kw))


class _Ctx:
    def __init__(self):
        self.db = _DB()
        self.session = _Sess()
        self.session_mgr = None


# ── spec shape ───────────────────────────────────────────────────────────────
def test_each_type_carries_its_mechanic():
    assert _ANOMALY_ENGAGE["distress"]["mechanic"] == "faucet"
    assert _ANOMALY_ENGAGE["imperial"]["mechanic"] == "slice_or_patrol"
    assert _ANOMALY_ENGAGE["cache"]["mechanic"] == "two_step"
    assert _ANOMALY_ENGAGE["mynock"]["mechanic"] == "detach_damage"
    assert _ANOMALY_ENGAGE["pirates"]["mechanic"] == "combat"


def test_cache_is_a_two_skill_gate():
    steps = _ANOMALY_ENGAGE["cache"]["steps"]
    assert [s for (s, d) in steps] == ["space transports", "security"]
    # approach easier than the security bypass
    assert steps[0][1] < steps[1][1]


def test_pirates_is_combat_not_a_faucet():
    # pirates spawns real hostiles into live combat; reward is the fire-kill
    # bounty + salvageable wreck via the existing fire path, not an engage faucet
    assert _ANOMALY_ENGAGE["pirates"]["mechanic"] == "combat"
    assert "tag" not in _ANOMALY_ENGAGE["pirates"]
    assert "credits" not in _ANOMALY_ENGAGE["pirates"]


# ── the untrained-roll bug guard: every slug must RESOLVE to a real skill ─────
def test_engagement_skills_resolve_to_trained_pools():
    """A trained char must roll a STRICTLY larger pool than an untrained one for
    every engagement skill. If a slug doesn't resolve (typo, or an attribute
    name), the trained value is ignored and the two pools are identical -- the
    exact defect this drop fixes."""
    reg = get_cached_skill_registry()
    attrs = json.dumps({"dexterity": "2D", "knowledge": "2D", "mechanical": "2D",
                        "perception": "2D", "strength": "2D", "technical": "2D"})
    for t, skill, _diff in _engagement_skills():
        untrained = _get_skill_pool(
            {"id": 1, "attributes": attrs, "skills": json.dumps({})}, skill, reg)
        trained = _get_skill_pool(
            {"id": 1, "attributes": attrs, "skills": json.dumps({skill: "5D"})},
            skill, reg)
        assert trained > untrained, (
            f"{t}: skill {skill!r} did not resolve to a trained pool "
            f"(untrained={untrained}, trained={trained}) -- likely a bad slug")


# ── mynock failure: real ship-system damage ──────────────────────────────────
def test_mynock_failure_damages_one_working_system():
    cmd = CourseCommand()
    ctx = _Ctx()
    ship = {"id": 7}
    systems = {}  # empty -> get_system_state treats all as 'working'
    asyncio.run(cmd._damage_random_system(ctx, ship, systems))
    damaged = [s for s, v in systems.items() if v == "damaged"]
    assert len(damaged) == 1, f"expected exactly one damaged system, got {systems}"
    assert damaged[0] in ("sensors", "weapons", "shields", "engines", "hyperdrive")
    assert len(ctx.db.update_ship_calls) == 1
    ship_id, kw = ctx.db.update_ship_calls[0]
    assert ship_id == 7 and "systems" in kw
    assert json.loads(kw["systems"])[damaged[0]] == "damaged"


def test_mynock_failure_noop_when_all_systems_already_damaged():
    cmd = CourseCommand()
    ctx = _Ctx()
    systems = {s: "damaged" for s in
               ("sensors", "weapons", "shields", "engines", "hyperdrive")}
    asyncio.run(cmd._damage_random_system(ctx, {"id": 7}, systems))
    assert ctx.db.update_ship_calls == []  # nothing left to damage


# ── faucet payout: funnel + range + crit ─────────────────────────────────────
def test_anomaly_payout_uses_the_credit_funnel_within_range():
    cmd = CourseCommand()
    ctx = _Ctx()
    char = {"id": 1, "credits": 5000}
    spec = _ANOMALY_ENGAGE["distress"]
    target = Anomaly(id=99, zone_id="z", anomaly_type="distress", resolution=2)
    asyncio.run(cmd._anomaly_payout(ctx, char, spec, "z", target, crit=False))
    assert len(ctx.db.adjust_calls) == 1
    cid, delta, tag = ctx.db.adjust_calls[0]
    assert cid == 1 and tag == "anomaly_distress"
    lo, hi = spec["credits"]
    assert lo <= delta <= hi
    assert char["credits"] == 5000 + delta
    assert any("[ANOMALY]" in ln for ln in ctx.session.lines)


def test_anomaly_payout_crit_pays_the_ceiling():
    cmd = CourseCommand()
    ctx = _Ctx()
    spec = _ANOMALY_ENGAGE["imperial"]
    target = Anomaly(id=1, zone_id="z", anomaly_type="imperial", resolution=4)
    asyncio.run(cmd._anomaly_payout(ctx, {"id": 1, "credits": 0}, spec, "z",
                                    target, crit=True))
    _cid, delta, _tag = ctx.db.adjust_calls[0]
    assert delta == spec["credits"][1]  # crit == max payout


# ── pirates/imperial-failure: real interactive combat (FORK-1 = A) ───────────
import pathlib
from engine.npc_space_traffic import TrafficArchetype


class _FakeTS:
    def __init__(self, sid, name):
        self.ship_id = sid
        self.display_name = name
        self.transponder_type = "none"
        self.in_live_combat = False


class _FakeTrafficMgr:
    def __init__(self):
        self.spawns = []
        self.ships = []

    async def spawn_for_encounter(self, db, session_mgr, zone_id, archetype):
        sid = 1000 + len(self.spawns)
        self.spawns.append((zone_id, archetype))
        ts = _FakeTS(sid, f"Hostile-{sid}")
        self.ships.append(ts)
        return ts, {"template": "z95", "crew_skill": "3D"}


class _FakeCombatMgr:
    def __init__(self):
        self.promotes = []

    def promote_to_combat(self, **kw):
        self.promotes.append(kw)
        return object()


def _patch_combat(monkeypatch):
    import engine.npc_space_traffic as nst
    import engine.npc_space_combat_ai as nsc
    import engine.space_anomalies as sa
    ftraffic, fcombat, removed = _FakeTrafficMgr(), _FakeCombatMgr(), []
    monkeypatch.setattr(nst, "get_traffic_manager", lambda: ftraffic)
    monkeypatch.setattr(nsc, "get_npc_combat_manager", lambda: fcombat)
    monkeypatch.setattr(sa, "remove_anomaly", lambda z, i: removed.append((z, i)) or True)
    return ftraffic, fcombat, removed


def test_engage_combat_pirates_spawns_2_3_and_promotes(monkeypatch):
    ftraffic, fcombat, removed = _patch_combat(monkeypatch)
    cmd = CourseCommand()
    ctx = _Ctx()
    ship = {"id": 5, "bridge_room_id": 42}
    target = Anomaly(id=7, zone_id="tz", anomaly_type="pirates", resolution=2)
    asyncio.run(cmd._engage_combat(ctx, ship, "tz", target, kind="pirate"))
    assert 2 <= len(ftraffic.spawns) <= 3                      # 2-3 hostiles
    assert all(z == "tz" for z, _a in ftraffic.spawns)         # in the anomaly's zone
    assert all(a == TrafficArchetype.PIRATE for _z, a in ftraffic.spawns)
    assert len(fcombat.promotes) == len(ftraffic.spawns)       # each promoted to combat
    assert all(p["profile"] == "aggressive" for p in fcombat.promotes)
    assert all(p["target_ship_id"] == 5 for p in fcombat.promotes)
    assert removed == [("tz", 7)]                              # the nest is consumed
    assert any("[COMBAT]" in ln for ln in ctx.session.lines)
    # BLOCKER-1 fix: each hostile is individually targetable (distinct callsign
    # + a display-surfacing 'combat' transponder, not all 'Unregistered fighter')
    names = [s.display_name for s in ftraffic.ships]
    assert len(set(names)) == len(names), f"raider names not distinct: {names}"
    assert all(s.transponder_type == "combat" for s in ftraffic.ships)
    # BLOCKER-2 fix: promoted ships are flagged so the ambient traffic tick
    # (tailing / extortion) leaves them alone
    assert all(s.in_live_combat for s in ftraffic.ships)


def test_engage_combat_patrol_spawns_exactly_one(monkeypatch):
    ftraffic, fcombat, removed = _patch_combat(monkeypatch)
    cmd = CourseCommand()
    ctx = _Ctx()
    target = Anomaly(id=3, zone_id="tz", anomaly_type="imperial", resolution=4)
    asyncio.run(cmd._engage_combat(ctx, {"id": 5, "bridge_room_id": 42}, "tz",
                                   target, kind="patrol"))
    assert len(ftraffic.spawns) == 1
    assert ftraffic.spawns[0][1] == TrafficArchetype.PATROL
    assert len(fcombat.promotes) == 1
    assert fcombat.promotes[0]["profile"] == "patrol"
    assert removed == [("tz", 3)]


def test_spawn_for_encounter_forces_the_given_zone():
    from engine.npc_space_traffic import get_traffic_manager
    mgr = get_traffic_manager()

    class _FakeDB:
        async def create_traffic_ship(self, name, template):
            return 424242

        async def create_traffic_npc(self, name, ship_id, skill):
            return 1

        async def update_traffic_ship_state(self, ship_id, data):
            pass

    try:
        res = asyncio.run(mgr.spawn_for_encounter(
            _FakeDB(), None, "tatooine_deep_space", TrafficArchetype.PIRATE))
        assert res is not None
        ts, tmpl = res
        assert ts.current_zone == "tatooine_deep_space"   # NOT a random SPAWN_ZONE
        assert ts.ship_id == 424242
        assert "template" in tmpl and "crew_skill" in tmpl
    finally:
        mgr._ships.pop(424242, None)


def test_npc_space_combat_tick_is_registered():
    """FORK-1=A: the dormant combat AI tick must actually be scheduled, else
    promoted anomaly hostiles never fire back."""
    src = pathlib.Path("server/game_server.py").read_text(encoding="utf-8")
    assert "async def npc_space_combat_tick" in src
    assert 'register("npc_space_combat"' in src


def test_combat_transponder_surfaces_distinct_name():
    """BLOCKER-1: a 'combat' transponder shows the ship's real (distinct) name so
    `fire <name>` can target it; ambient 'none' pirates still collapse to a
    single 'Unregistered fighter'."""
    from engine.npc_space_traffic import TrafficShip, TrafficState
    hostile = TrafficShip(ship_id=1, archetype=TrafficArchetype.PIRATE,
                          state=TrafficState.IDLE, current_zone="tz",
                          display_name="Raider Alpha", transponder_type="combat")
    assert hostile.sensors_name() == "Raider Alpha"
    ambient = TrafficShip(ship_id=2, archetype=TrafficArchetype.PIRATE,
                          state=TrafficState.IDLE, current_zone="tz",
                          display_name="Whatever", transponder_type="none")
    assert ambient.sensors_name() == "Unregistered fighter"


def test_idle_tick_skips_live_combat_ships():
    """BLOCKER-2: the ambient traffic tick must not tail/hail/extort a ship the
    combat manager owns (in_live_combat)."""
    from engine.npc_space_traffic import (
        get_traffic_manager, TrafficShip, TrafficState)
    mgr = get_traffic_manager()
    ts = TrafficShip(ship_id=1, archetype=TrafficArchetype.PIRATE,
                     state=TrafficState.IDLE, current_zone="tz",
                     display_name="Raider Alpha", transponder_type="combat")
    ts.in_live_combat = True
    result = asyncio.run(mgr._tick_idle(ts, None, None))  # guard returns before db use
    assert result is False
    assert ts.tailing_ship_id is None      # never began tailing
    assert ts.state == TrafficState.IDLE   # unchanged
