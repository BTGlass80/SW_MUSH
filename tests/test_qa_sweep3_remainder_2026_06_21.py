# -*- coding: utf-8 -*-
"""
tests/test_qa_sweep3_remainder_2026_06_21.py — QA break-it sweep #3 remainder
(2026-06-21): the non-housing findings (1 HIGH territory, 1 HIGH crafting,
1 MED + 1 LOW Force).

  * HIGH — Faction armory was permanently inaccessible. The parser gate in
    `_cmd_armory` called `engine.territory.is_room_claimed_by`, a SYN.1.b
    RETIRED stub that unconditionally returns False — so EVERY player in
    EVERY room got "must be standing in claimed rooms" and the armory (view,
    deposit, withdraw) was unreachable. Fix: gate on the live region-scope
    `is_region_owned_by(room.wilderness_region_id, faction)` — the same gate
    the deposit/withdraw engine fns already enforce, now also protecting the
    view path which had no gate of its own.

  * HIGH — `t5_master_grade_armor` declared `output_type: weapon` while its
    output_key `bounty_hunter_armor` is a `type: armor` item — so the crafted
    item was delivered via the weapon branch and stored with the wrong type
    tag (and no `condition` field). Fix: `output_type: armor`.

  * MED — A dark-side power that FAILED its roll printed "...the power has no
    effect." then an unexplained "You gain 1 Dark Side Point." The DSP accrual
    itself is CORRECT (WEG40120 p.81: a DSP is for *calling upon the dark
    side* — the act, not the dice result; the engine's existing
    extra_dsp_on_fail confirms the design). Fix: a connective narrative line on
    a failed dark cast so the message reads coherently. DSP accrual unchanged.

  * LOW — `parser.force_commands._get_skill_reg` loaded the bare relative
    "data/skills.yaml", raising FileNotFoundError (→ generic player error) when
    the server's CWD wasn't the project root. Fix: __file__-anchored path.

Run: python -m pytest tests/test_qa_sweep3_remainder_2026_06_21.py
"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ════════════════════════════════════════════════════════════════════════════
# HIGH — faction armory reachability (territory)
# ════════════════════════════════════════════════════════════════════════════
class _FakeArmorySession:
    def __init__(self):
        self.lines: list[str] = []

    async def send_line(self, msg=""):
        self.lines.append(msg)


class _FakeArmoryCtx:
    def __init__(self, db, session):
        self.db = db
        self.session = session


def _joined(lines):
    return "\n".join(lines).lower()


class TestFactionArmoryReachable:
    async def _seed_owned_region(self, harness, org_code, slug):
        from engine.territory import ensure_region_ownership_schema
        await ensure_region_ownership_schema(harness.db)
        await harness.db.execute(
            "INSERT OR REPLACE INTO region_ownership "
            "(region_slug, org_code, zone_id, claimed_by, claimed_at, maintenance) "
            "VALUES (?, ?, NULL, 1, ?, 3000)",
            (slug, org_code, time.time()),
        )
        await harness.db.commit()

    async def test_armory_reachable_in_owned_region(self, harness):
        """The core fix: a faction member standing in a room inside a region
        their faction owns can now REACH the armory (no gate message). Pre-fix
        the retired stub blocked this unconditionally."""
        from parser.faction_commands import FactionCommand

        slug = "qa_owned_region_a"
        await self._seed_owned_region(harness, "republic", slug)
        room_id = await harness.db.create_room(
            name="Owned Outpost", desc_short="x", desc_long="x", zone_id=None,
            properties="{}")
        await harness.db.execute(
            "UPDATE rooms SET wilderness_region_id = ? WHERE id = ?",
            (slug, room_id))
        await harness.db.commit()

        char = {"id": 1, "name": "ArmRep", "faction_id": "republic",
                "room_id": room_id, "inventory": "{}"}
        sess = _FakeArmorySession()
        ctx = _FakeArmoryCtx(harness.db, sess)
        await FactionCommand()._cmd_armory(ctx, char, "")

        out = _joined(sess.lines)
        assert "to access the armory" not in out, (
            "armory must be REACHABLE in an owned region — the gate fired")
        assert "claimed rooms" not in out, (
            "the retired per-room 'claimed rooms' message must be gone")

    async def test_armory_gate_message_is_region_scoped_when_unowned(self, harness):
        """In a room NOT in an owned region the gate fires — with the NEW
        region-scoped message, not the dead per-room stub message, and no
        crash."""
        from parser.faction_commands import FactionCommand

        room_id = await harness.db.create_room(
            name="Nowhere", desc_short="x", desc_long="x", zone_id=None,
            properties="{}")
        char = {"id": 1, "name": "ArmRep2", "faction_id": "republic",
                "room_id": room_id, "inventory": "{}"}
        sess = _FakeArmorySession()
        ctx = _FakeArmoryCtx(harness.db, sess)
        await FactionCommand()._cmd_armory(ctx, char, "")

        out = _joined(sess.lines)
        assert "owned wilderness regions" in out, (
            "the gate message must be the new region-scoped one")
        assert "claimed rooms" not in out

    def test_armory_gate_no_longer_calls_retired_stub(self):
        src = (PROJECT_ROOT / "parser" / "faction_commands.py").read_text(
            encoding="utf-8")
        # In the armory method, the retired stub must be gone.
        armory_start = src.find("async def _cmd_armory")
        armory_end = src.find("async def ", armory_start + 1)
        body = src[armory_start:armory_end]
        # The retired stub must not be CALLED (a comment may still name it to
        # explain the history).
        assert "await is_room_claimed_by(" not in body, (
            "_cmd_armory must not call the retired is_room_claimed_by stub")
        assert "is_region_owned_by" in body and "wilderness_region_id" in body


# ════════════════════════════════════════════════════════════════════════════
# HIGH — schematic output_type
# ════════════════════════════════════════════════════════════════════════════
class TestSchematicOutputType:
    def test_master_grade_armor_is_armor(self):
        from engine.crafting import get_schematic
        s = get_schematic("t5_master_grade_armor")
        assert s is not None, "t5_master_grade_armor schematic missing"
        assert s["output_type"] == "armor", (
            f"t5_master_grade_armor must be output_type=armor, got "
            f"{s['output_type']!r} — its output_key bounty_hunter_armor is a "
            f"type:armor item")

    def test_no_armor_item_schematic_is_typed_weapon(self):
        """Sweep guard: any schematic whose output_key resolves to a
        type:armor item must declare output_type=armor (catches the same
        mislabel class on siblings)."""
        import yaml
        sch = yaml.safe_load(
            (PROJECT_ROOT / "data" / "schematics.yaml").read_text(
                encoding="utf-8"))
        weap = yaml.safe_load(
            (PROJECT_ROOT / "data" / "weapons.yaml").read_text(
                encoding="utf-8"))
        armor_keys = {k for k, v in weap.items()
                      if isinstance(v, dict) and v.get("type") == "armor"}

        def walk(o):
            if isinstance(o, dict):
                if "output_key" in o and "output_type" in o:
                    yield o
                for v in o.values():
                    yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)

        offenders = [
            s for s in walk(sch)
            if s.get("output_key") in armor_keys
            and s.get("output_type") != "armor"
        ]
        assert not offenders, (
            f"armor-item schematics mislabeled output_type!=armor: "
            f"{[s.get('output_key') for s in offenders]}")


# ════════════════════════════════════════════════════════════════════════════
# MED — DSP message on a failed dark power
# ════════════════════════════════════════════════════════════════════════════
class TestDarkPowerFailMessage:
    def test_failed_dark_power_message_is_coherent_dsp_unchanged(self):
        import engine.force_powers as fp
        from engine.dice import DicePool, WildDieResult, RollResult
        from engine.character import Character, SkillRegistry, WoundLevel
        from engine.force_powers import resolve_force_power

        # Force a FAILED roll (low total vs injure_kill's difficulty).
        orig = fp.roll_d6_pool
        fp.roll_d6_pool = lambda pool: RollResult(
            pool=pool, normal_dice=[],
            wild_die=WildDieResult(rolls=[1], total=0, complication=True),
            pips=0, total=1, complication=True)
        try:
            sk = SkillRegistry()
            sk.load_file(str(PROJECT_ROOT / "data" / "skills.yaml"))
            char = Character()
            char.control = DicePool.parse("3D")
            char.sense = DicePool.parse("3D")
            char.alter = DicePool.parse("3D")
            char.dark_side_points = 0
            char.wound_level = WoundLevel(0)
            tgt = Character()
            tgt.strength = DicePool.parse("3D")
            tgt.wound_level = WoundLevel(0)
            r = resolve_force_power("injure_kill", char, sk, target_char=tgt)
        finally:
            fp.roll_d6_pool = orig

        # DSP accrual is unchanged — still +1 on a dark cast (WEG-correct).
        assert r.dsp_gained == 1
        assert char.dark_side_points == 1
        # The roll failed...
        assert r.success is False
        nar = r.narrative.lower()
        assert "no effect" in nar, "a failed power still reports no effect"
        # ...and the message now CONNECTS the failure to the DSP gain instead
        # of reading as a bare contradiction.
        assert "reach" in nar and "mark" in nar, (
            "a failed dark power must explain the DSP gain (the 'reaching "
            "leaves its mark' connective), not jump from 'no effect' to a DSP")


# ════════════════════════════════════════════════════════════════════════════
# LOW — force_commands skill-registry path is CWD-independent
# ════════════════════════════════════════════════════════════════════════════
class TestForceSkillRegPath:
    def test_get_skill_reg_loads_regardless_of_cwd(self):
        import parser.force_commands as fc
        fc._SKILL_REG_CACHE = None
        reg = fc._get_skill_reg()
        # A populated registry (blaster is a canonical skill).
        assert reg is not None
        assert reg.get("blaster") is not None or reg.get("Blaster") is not None

    def test_source_uses_anchored_path_not_bare_relative(self):
        src = (PROJECT_ROOT / "parser" / "force_commands.py").read_text(
            encoding="utf-8")
        assert 'load_file("data/skills.yaml")' not in src, (
            "force_commands must not load the bare relative data/skills.yaml "
            "(FileNotFoundError off-root) — anchor via __file__")
        assert "__file__" in src and "skills.yaml" in src
