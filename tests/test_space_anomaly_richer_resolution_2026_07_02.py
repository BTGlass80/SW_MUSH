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
    """Every (skill, diff) across all mechanics, including two-step steps."""
    out = []
    for t, spec in _ANOMALY_ENGAGE.items():
        if spec["mechanic"] == "two_step":
            out += [(t, s, d) for (s, d) in spec["steps"]]
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
    assert _ANOMALY_ENGAGE["imperial"]["mechanic"] == "faucet"
    assert _ANOMALY_ENGAGE["cache"]["mechanic"] == "two_step"
    assert _ANOMALY_ENGAGE["mynock"]["mechanic"] == "detach_damage"
    assert _ANOMALY_ENGAGE["pirates"]["mechanic"] == "skirmish"


def test_cache_is_a_two_skill_gate():
    steps = _ANOMALY_ENGAGE["cache"]["steps"]
    assert [s for (s, d) in steps] == ["space transports", "security"]
    # approach easier than the security bypass
    assert steps[0][1] < steps[1][1]


def test_pirates_reward_is_salvage_not_a_faucet():
    # skirmish victory drops a wreck to salvage; no direct credit faucet
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
