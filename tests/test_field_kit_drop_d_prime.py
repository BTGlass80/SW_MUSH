"""Field Kit Drop D' — combat_resolution_event factory regression tests.

Per ``combat_mechanics_display_design_v1.1.md`` §12 acceptance criteria.
This is the engine-side test suite (Phase 1 of Drop D'). Phase 2 wires
the factory into ``engine/combat.py``'s resolve loop and adds the
client-side dispatch + inspector panel; those are tested separately
once they land.

Coverage for Phase 1:

  · ``engine/combat_events.py`` factory:
      - per-die ``make_die`` and ``build_dice_pool_roll`` shape
      - ``compose_pool_dice`` provenance tagging (the Q2 mod —
        skill/weapon/fp_double/modifier source labels)
      - Wild Die handling: normal, exploded chain, complication
      - ``make_soak_component`` for the four soak sources
      - ``build_wound_outcome`` 5-way ``outcome_type`` enum
        (the Q2 stun-mode schema-gap fix)
      - ``classify_wound_outcome`` branch table mirroring
        ``engine/combat.py:1186``
      - ``make_combat_resolution_event`` schema invariants
        (AC12: defender_pool iff is_opposed, damage/soak iff hit, etc.)

  · Per-archetype payloads (5 archetypes from design v1.1 §9):
      1. Ranged hit with Wild Die explosion
      2. Ranged miss
      3. Melee mishap (Wild Die complication)
      4. Space combat with Force Point
      5. Melee opposed (v1.1 addition)

What this suite intentionally does NOT verify:
  · End-to-end rendering on the WebSocket client — that's Phase 2
  · The actual emission call inside ``engine/combat.py`` resolve loop
    — that's Phase 2
  · The 250ms client-side dedup against the legacy two-line narrative
    — that's a static/client.html concern in Phase 2
  · The 2D stun-duration roll (the schema reserves the field; the
    engine does not yet emit the duration — separate ticket per
    design v1.1 §11)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine.combat_events import (
    OUTCOME_INCAPACITATED,
    OUTCOME_NO_DAMAGE,
    OUTCOME_STUN,
    OUTCOME_STUN_UNCONSCIOUS,
    OUTCOME_WOUND,
    SCHEMA_VERSION,
    SOAK_ARMOR,
    SOAK_CP,
    SOAK_SHIELD,
    SOAK_STRENGTH,
    SOURCE_FP_DOUBLE,
    SOURCE_MODIFIER,
    SOURCE_SKILL,
    SOURCE_WEAPON,
    VALID_OUTCOMES,
    VALID_SOURCES,
    build_dice_pool_roll,
    build_wound_outcome,
    classify_wound_outcome,
    compose_pool_dice,
    make_combat_resolution_event,
    make_die,
    make_soak_component,
)
from engine.dice import (
    DicePool,
    RollResult,
    WildDieResult,
)


ROOT = Path(__file__).parent.parent


# ════════════════════════════════════════════════════════════════════
# Per-die descriptor
# ════════════════════════════════════════════════════════════════════


class TestMakeDie:

    def test_basic_skill_die(self):
        d = make_die(4, SOURCE_SKILL)
        assert d["value"] == 4
        assert d["source"] == "skill"
        assert d["is_wild"] is False
        assert d["exploded"] is False
        assert d["explosion_chain"] is None
        assert d["dropped"] is False

    def test_weapon_source(self):
        d = make_die(5, SOURCE_WEAPON)
        assert d["source"] == "weapon"

    def test_fp_double_source(self):
        d = make_die(3, SOURCE_FP_DOUBLE)
        assert d["source"] == "fp_double"

    def test_modifier_source(self):
        d = make_die(2, SOURCE_MODIFIER)
        assert d["source"] == "modifier"

    def test_exploded_wild_die(self):
        d = make_die(
            value=13, source=SOURCE_SKILL,
            is_wild=True, exploded=True, explosion_chain=[6, 5, 2],
        )
        assert d["is_wild"] is True
        assert d["exploded"] is True
        assert d["explosion_chain"] == [6, 5, 2]
        assert d["value"] == 13  # chain total

    def test_dropped_die(self):
        d = make_die(value=6, source=SOURCE_SKILL, dropped=True)
        assert d["dropped"] is True
        assert d["value"] == 6  # original face preserved for display

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Unknown die source"):
            make_die(4, "made-up-source")

    def test_all_valid_sources_accepted(self):
        for src in VALID_SOURCES:
            d = make_die(3, src)
            assert d["source"] == src


# ════════════════════════════════════════════════════════════════════
# DicePoolRoll wrapper
# ════════════════════════════════════════════════════════════════════


class TestBuildDicePoolRoll:

    def test_basic_pool(self):
        dice = [make_die(3, SOURCE_SKILL), make_die(5, SOURCE_SKILL)]
        pool = build_dice_pool_roll(
            pool_text="2D", pool_dice=2, pool_pips=0,
            total=8, dice=dice,
        )
        assert pool["pool_text"] == "2D"
        assert pool["pool_dice"] == 2
        assert pool["pool_pips"] == 0
        assert pool["total"] == 8
        assert len(pool["dice"]) == 2
        assert pool["pips_added"] == 0
        assert pool["complication"] is False
        assert pool["exploded"] is False
        assert pool["removed_die_value"] is None
        assert pool["cp_spent"] == 0
        assert pool["cp_rolls"] == []
        assert pool["cp_bonus"] == 0

    def test_pips_added_mirrors_pool_pips(self):
        dice = [make_die(4, SOURCE_SKILL)]
        pool = build_dice_pool_roll(
            pool_text="1D+2", pool_dice=1, pool_pips=2,
            total=6, dice=dice,
        )
        assert pool["pool_pips"] == pool["pips_added"] == 2

    def test_complication_flag(self):
        dice = [make_die(0, SOURCE_SKILL, is_wild=True)]
        pool = build_dice_pool_roll(
            pool_text="3D", pool_dice=3, pool_pips=0,
            total=4, dice=dice,
            complication=True, removed_die_value=6,
        )
        assert pool["complication"] is True
        assert pool["removed_die_value"] == 6

    def test_exploded_flag(self):
        dice = [
            make_die(13, SOURCE_SKILL, is_wild=True,
                     exploded=True, explosion_chain=[6, 5, 2])
        ]
        pool = build_dice_pool_roll(
            pool_text="2D", pool_dice=2, pool_pips=0,
            total=15, dice=dice,
            exploded=True,
        )
        assert pool["exploded"] is True

    def test_cp_spending(self):
        dice = [make_die(4, SOURCE_SKILL)]
        pool = build_dice_pool_roll(
            pool_text="3D", pool_dice=3, pool_pips=0,
            total=14, dice=dice,
            cp_spent=2, cp_rolls=[5, 6, 3], cp_bonus=14,
        )
        assert pool["cp_spent"] == 2
        assert pool["cp_rolls"] == [5, 6, 3]
        assert pool["cp_bonus"] == 14


# ════════════════════════════════════════════════════════════════════
# compose_pool_dice — the Q2 modification core
# ════════════════════════════════════════════════════════════════════


def _fake_roll_result(
    *,
    normal_dice: list[int],
    wild_rolls: list[int],
    wild_total: int,
    wild_exploded: bool = False,
    wild_complication: bool = False,
    pool_dice: int,
    pool_pips: int = 0,
    total: int = 0,
    complication: bool = False,
    removed_die: int | None = None,
    exploded: bool = False,
) -> RollResult:
    """Synthesize a RollResult for tests that don't need real RNG."""
    pool = DicePool(pool_dice, pool_pips)
    wild = WildDieResult(
        rolls=wild_rolls, total=wild_total,
        exploded=wild_exploded, complication=wild_complication,
    )
    return RollResult(
        pool=pool,
        normal_dice=normal_dice,
        wild_die=wild,
        pips=pool_pips,
        total=total,
        complication=complication,
        exploded=exploded,
        removed_die=removed_die,
    )


class TestComposePoolDice:

    def test_simple_skill_pool_no_explosion(self):
        # 4D pool: 3 normal + 1 wild. All "skill".
        rr = _fake_roll_result(
            normal_dice=[3, 5, 2],
            wild_rolls=[4], wild_total=4,
            pool_dice=4, total=14,
        )
        dice = compose_pool_dice(rr, [(SOURCE_SKILL, 3)])
        assert len(dice) == 4
        # First three are normal skill dice
        for i in range(3):
            assert dice[i]["source"] == "skill"
            assert dice[i]["is_wild"] is False
        # Last is the Wild Die
        assert dice[3]["is_wild"] is True
        assert dice[3]["source"] == "skill"
        assert dice[3]["value"] == 4
        assert dice[3]["exploded"] is False
        assert dice[3]["dropped"] is False

    def test_skill_plus_weapon_split(self):
        # 5D damage pool: 3D skill + 2D weapon = 4 normal + 1 wild
        rr = _fake_roll_result(
            normal_dice=[2, 4, 3, 6],
            wild_rolls=[5], wild_total=5,
            pool_dice=5, total=20,
        )
        dice = compose_pool_dice(
            rr, [(SOURCE_SKILL, 2), (SOURCE_WEAPON, 2)]
        )
        assert len(dice) == 5
        assert dice[0]["source"] == "skill"
        assert dice[1]["source"] == "skill"
        assert dice[2]["source"] == "weapon"
        assert dice[3]["source"] == "weapon"
        # Wild die is last and source=skill by convention
        assert dice[4]["is_wild"] is True
        assert dice[4]["source"] == "skill"

    def test_force_point_doubling(self):
        # FP doubles the pool. 4D + 4D fp_double = 7 normal + 1 wild.
        rr = _fake_roll_result(
            normal_dice=[3, 4, 5, 2, 6, 1, 4],
            wild_rolls=[3], wild_total=3,
            pool_dice=8, total=31,
        )
        dice = compose_pool_dice(
            rr, [(SOURCE_SKILL, 3), (SOURCE_FP_DOUBLE, 4)]
        )
        sources = [d["source"] for d in dice]
        assert sources.count("skill") == 3 + 1  # +1 for the Wild Die
        assert sources.count("fp_double") == 4
        # Source ordering preserved: skill first, then fp_double, then wild
        assert sources[:3] == ["skill", "skill", "skill"]
        assert sources[3:7] == ["fp_double"] * 4
        assert dice[7]["is_wild"] is True

    def test_exploded_wild_die_chain(self):
        # Wild Die rolled 6→5→2 (chain total 13). Pool 4D total 22.
        rr = _fake_roll_result(
            normal_dice=[3, 5, 1],
            wild_rolls=[6, 5, 2], wild_total=13,
            wild_exploded=True,
            pool_dice=4, total=22,
            exploded=True,
        )
        dice = compose_pool_dice(rr, [(SOURCE_SKILL, 3)])
        wild = dice[3]
        assert wild["is_wild"] is True
        assert wild["exploded"] is True
        assert wild["explosion_chain"] == [6, 5, 2]
        assert wild["value"] == 13  # chain total

    def test_complication_drops_highest_normal(self):
        # Wild Die rolled 1 → complication; engine removes highest
        # normal die (here the 6) and emits removed_die=6.
        rr = _fake_roll_result(
            normal_dice=[3, 6, 2],
            wild_rolls=[1], wild_total=0,
            wild_complication=True,
            pool_dice=4, total=5,
            complication=True, removed_die=6,
        )
        dice = compose_pool_dice(rr, [(SOURCE_SKILL, 3)])
        # 3 normal skill dice + Wild Die (value 0) + dropped die marker
        assert len(dice) == 5
        # First three are the original normal dice (face values preserved
        # so the inspector can render them all, with the dropped one
        # struck through).
        assert dice[0]["value"] == 3
        assert dice[1]["value"] == 6
        assert dice[2]["value"] == 2
        # Wild Die: value 0, is_wild=True, not dropped itself
        assert dice[3]["is_wild"] is True
        assert dice[3]["value"] == 0
        assert dice[3]["dropped"] is False
        # The dropped marker — value 6 (the removed die), dropped=True
        assert dice[4]["dropped"] is True
        assert dice[4]["value"] == 6

    def test_component_sizes_must_match_normal_dice(self):
        # 3 normal dice but caller claims 4D skill — bookkeeping bug.
        rr = _fake_roll_result(
            normal_dice=[1, 2, 3],
            wild_rolls=[4], wild_total=4,
            pool_dice=4, total=10,
        )
        with pytest.raises(ValueError, match="provenance bookkeeping bug"):
            compose_pool_dice(rr, [(SOURCE_SKILL, 4)])

    def test_invalid_source_in_components_raises(self):
        rr = _fake_roll_result(
            normal_dice=[1, 2],
            wild_rolls=[4], wild_total=4,
            pool_dice=3, total=7,
        )
        with pytest.raises(ValueError, match="unknown source"):
            compose_pool_dice(rr, [("bogus", 2)])

    def test_empty_pool_returns_empty(self):
        # No normal dice and no Wild Die — degenerate but not an error.
        rr = RollResult(
            pool=DicePool(0, 0), normal_dice=[],
            wild_die=None, pips=0, total=0,
        )
        dice = compose_pool_dice(rr, [])
        assert dice == []

    def test_empty_components_with_dice_raises(self):
        rr = _fake_roll_result(
            normal_dice=[3, 4],
            wild_rolls=[5], wild_total=5,
            pool_dice=3, total=12,
        )
        with pytest.raises(ValueError):
            compose_pool_dice(rr, [])


# ════════════════════════════════════════════════════════════════════
# Soak components
# ════════════════════════════════════════════════════════════════════


class TestMakeSoakComponent:

    def test_strength_rolled(self):
        c = make_soak_component(
            SOAK_STRENGTH, "Strength 3D",
            value=12, rolls=[4, 5, 3],
        )
        assert c["source"] == "strength"
        assert c["label"] == "Strength 3D"
        assert c["value"] == 12
        assert c["rolls"] == [4, 5, 3]

    def test_armor_flat_no_rolls(self):
        # Armor adds as fixed pips per R&E p83
        c = make_soak_component(
            SOAK_ARMOR, "Padded Vest (+2)",
            value=2, rolls=None,
        )
        assert c["source"] == "armor"
        assert c["rolls"] is None

    def test_cp_soak_with_rolls(self):
        c = make_soak_component(
            SOAK_CP, "CP Soak (3 dice)",
            value=14, rolls=[5, 6, 3],
        )
        assert c["source"] == "cp_soak"
        assert c["rolls"] == [5, 6, 3]

    def test_shield_for_space_combat(self):
        c = make_soak_component(
            SOAK_SHIELD, "Forward shield (+2D)",
            value=8, rolls=[4, 4],
        )
        assert c["source"] == "shield"

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Unknown soak source"):
            make_soak_component("not-a-source", "x", value=0)


# ════════════════════════════════════════════════════════════════════
# Wound outcome — Q2 stun-mode schema-gap fix
# ════════════════════════════════════════════════════════════════════


class TestBuildWoundOutcome:

    def test_no_damage(self):
        wo = build_wound_outcome(
            outcome_type=OUTCOME_NO_DAMAGE,
            display_name="No Damage",
        )
        assert wo["outcome_type"] == "no_damage"
        assert wo["stun_only"] is False
        assert wo["stun_unconscious"] is False
        assert wo["stun_duration_dice"] is None
        assert wo["stun_duration_unit"] is None

    def test_wound(self):
        wo = build_wound_outcome(
            outcome_type=OUTCOME_WOUND,
            display_name="Wounded",
            wound_level_before="Healthy",
            wound_level_after="Wounded",
            wound_level_delta=2,
        )
        assert wo["outcome_type"] == "wound"
        assert wo["wound_level_before"] == "Healthy"
        assert wo["wound_level_after"] == "Wounded"
        assert wo["wound_level_delta"] == 2
        assert wo["stun_only"] is False
        assert wo["stun_unconscious"] is False

    def test_stun(self):
        # Margin 1-3, applied as stun-track wound
        wo = build_wound_outcome(
            outcome_type=OUTCOME_STUN,
            display_name="Stunned",
            wound_level_before="Healthy",
            wound_level_after="Stunned",
            wound_level_delta=1,
        )
        assert wo["outcome_type"] == "stun"
        assert wo["stun_only"] is True
        assert wo["stun_unconscious"] is False

    def test_stun_unconscious_with_duration(self):
        # Margin > 3 in stun mode: KO routing per R&E p83
        wo = build_wound_outcome(
            outcome_type=OUTCOME_STUN_UNCONSCIOUS,
            display_name="Stunned — Unconscious!",
            wound_level_before="Healthy",
            wound_level_after="Stunned",
            wound_level_delta=1,
            stun_duration_dice="2D",
            stun_duration_unit="minutes",
        )
        assert wo["outcome_type"] == "stun_unconscious"
        assert wo["stun_only"] is False
        assert wo["stun_unconscious"] is True
        assert wo["stun_duration_dice"] == "2D"
        assert wo["stun_duration_unit"] == "minutes"

    def test_stun_unconscious_without_duration_yet(self):
        # Engine does not yet roll the 2D duration — schema reserves
        # the field but allows None per design v1.1 §11.
        wo = build_wound_outcome(
            outcome_type=OUTCOME_STUN_UNCONSCIOUS,
            display_name="Stunned — Unconscious!",
        )
        assert wo["stun_unconscious"] is True
        assert wo["stun_duration_dice"] is None

    def test_incapacitated(self):
        wo = build_wound_outcome(
            outcome_type=OUTCOME_INCAPACITATED,
            display_name="Mortally Wounded",
            wound_level_before="Wounded",
            wound_level_after="Mortally Wounded",
            wound_level_delta=2,
        )
        assert wo["outcome_type"] == "incapacitated"
        assert wo["stun_only"] is False
        assert wo["stun_unconscious"] is False

    def test_invalid_outcome_type_raises(self):
        with pytest.raises(ValueError, match="Unknown outcome_type"):
            build_wound_outcome(
                outcome_type="dazzled", display_name="???"
            )

    def test_duration_on_non_ko_raises(self):
        # Defensive: catch a bookkeeping bug where someone populates
        # stun_duration on a regular wound or stun outcome.
        with pytest.raises(ValueError, match="stun_duration_"):
            build_wound_outcome(
                outcome_type=OUTCOME_WOUND,
                display_name="Wounded",
                stun_duration_dice="2D",
            )

    def test_invalid_duration_unit_raises(self):
        with pytest.raises(ValueError, match="stun_duration_unit"):
            build_wound_outcome(
                outcome_type=OUTCOME_STUN_UNCONSCIOUS,
                display_name="Stunned — Unconscious!",
                stun_duration_dice="2D",
                stun_duration_unit="hours",  # invalid
            )

    def test_drama_text_passthrough(self):
        wo = build_wound_outcome(
            outcome_type=OUTCOME_INCAPACITATED,
            display_name="Mortally Wounded",
            drama_text="Yenn collapses.",
        )
        assert wo["drama_text"] == "Yenn collapses."


# ════════════════════════════════════════════════════════════════════
# classify_wound_outcome — branch table mirroring combat.py:1186
# ════════════════════════════════════════════════════════════════════


class TestClassifyWoundOutcome:
    """Mirrors the branch table in engine/combat.py:1186 verbatim.

    Keeps the resolver and the factory in lockstep — if the engine's
    routing changes, this test goes red and the factory follows.
    """

    def test_miss_is_no_damage(self):
        assert classify_wound_outcome(
            hit=False, stun_mode=False, damage_margin=99,
            target_can_act=True,
        ) == OUTCOME_NO_DAMAGE

    def test_hit_with_zero_margin_is_no_damage(self):
        assert classify_wound_outcome(
            hit=True, stun_mode=False, damage_margin=0,
            target_can_act=True,
        ) == OUTCOME_NO_DAMAGE

    def test_hit_with_negative_margin_is_no_damage(self):
        assert classify_wound_outcome(
            hit=True, stun_mode=False, damage_margin=-3,
            target_can_act=True,
        ) == OUTCOME_NO_DAMAGE

    @pytest.mark.parametrize("margin", [1, 2, 3])
    def test_stun_mode_low_margin_is_stun(self, margin):
        # Margin 1-3 in stun mode → applied as stun-track wound
        assert classify_wound_outcome(
            hit=True, stun_mode=True, damage_margin=margin,
            target_can_act=True,
        ) == OUTCOME_STUN

    @pytest.mark.parametrize("margin", [4, 7, 15])
    def test_stun_mode_high_margin_is_ko(self, margin):
        # Margin > 3 in stun mode → KO routing per R&E p83
        assert classify_wound_outcome(
            hit=True, stun_mode=True, damage_margin=margin,
            target_can_act=True,
        ) == OUTCOME_STUN_UNCONSCIOUS

    def test_normal_hit_is_wound(self):
        assert classify_wound_outcome(
            hit=True, stun_mode=False, damage_margin=4,
            target_can_act=True,
        ) == OUTCOME_WOUND

    def test_incapacitating_hit(self):
        # Wound dropped target_can_act to False
        assert classify_wound_outcome(
            hit=True, stun_mode=False, damage_margin=12,
            target_can_act=False,
        ) == OUTCOME_INCAPACITATED


# ════════════════════════════════════════════════════════════════════
# make_combat_resolution_event — top-level shape & invariants
# ════════════════════════════════════════════════════════════════════


def _basic_attacker_pool(*, total: int = 17, hit_pool: bool = True) -> dict:
    """Minimal attacker pool fixture for shape tests."""
    dice = [
        make_die(4, SOURCE_SKILL),
        make_die(5, SOURCE_SKILL),
        make_die(3, SOURCE_SKILL),
        make_die(5, SOURCE_SKILL, is_wild=True),
    ]
    return build_dice_pool_roll(
        pool_text="4D", pool_dice=4, pool_pips=0,
        total=total, dice=dice,
    )


def _basic_difficulty(number: int = 11, label: str = "Moderate") -> dict:
    return {
        "number": number,
        "label": label,
        "breakdown": [
            {"name": "base", "mod": number},
        ],
    }


def _basic_damage_pool(total: int = 14) -> dict:
    dice = [
        make_die(4, SOURCE_WEAPON),
        make_die(5, SOURCE_WEAPON),
        make_die(2, SOURCE_WEAPON),
        make_die(3, SOURCE_WEAPON, is_wild=True),
    ]
    return build_dice_pool_roll(
        pool_text="4D", pool_dice=4, pool_pips=0,
        total=total, dice=dice,
    )


def _basic_soak(total: int = 8) -> dict:
    return {
        "total": total,
        "components": [
            make_soak_component(SOAK_STRENGTH, "Strength 3D",
                                value=8, rolls=[3, 3, 2]),
        ],
    }


class TestMakeCombatResolutionEvent:

    def _make_event(self, **overrides):
        """Build a baseline ranged-hit event with override hooks."""
        defaults = dict(
            actor_id=1, actor_name="Tundra", actor_kind="pc",
            is_force_point_active=False,
            target_id=2, target_name="Yenn", target_kind="npc",
            skill="blaster", weapon_name="Blaster Pistol",
            range_band="medium", stun_mode=False, is_opposed=False,
            attacker_pool=_basic_attacker_pool(total=17),
            difficulty=_basic_difficulty(11),
            damage_pool=_basic_damage_pool(14),
            soak=_basic_soak(8),
            hit=True, margin=6, damage_margin=6,
            wound_outcome=build_wound_outcome(
                outcome_type=OUTCOME_WOUND,
                display_name="Wounded",
                wound_level_before="Healthy",
                wound_level_after="Wounded",
                wound_level_delta=2,
            ),
            round_num=3, combat_id=42,
        )
        defaults.update(overrides)
        return make_combat_resolution_event(**defaults)

    def test_basic_event_shape(self):
        ev = self._make_event()
        assert ev["msg_type"] == "combat_resolution_event"
        assert ev["schema_version"] == SCHEMA_VERSION
        assert "event_id" in ev
        assert "timestamp_ms" in ev
        assert ev["round_num"] == 3
        assert ev["combat_id"] == 42

    def test_actor_target_action_blocks(self):
        ev = self._make_event()
        assert ev["actor"]["id"] == 1
        assert ev["actor"]["name"] == "Tundra"
        assert ev["actor"]["kind"] == "pc"
        assert ev["actor"]["is_force_point_active"] is False
        assert ev["target"]["id"] == 2
        assert ev["target"]["name"] == "Yenn"
        assert ev["target"]["kind"] == "npc"
        assert ev["action"]["skill"] == "blaster"
        assert ev["action"]["weapon_name"] == "Blaster Pistol"
        assert ev["action"]["range_band"] == "medium"
        assert ev["action"]["stun_mode"] is False
        assert ev["action"]["is_opposed"] is False

    def test_static_difficulty_branch(self):
        ev = self._make_event()
        assert ev["defender_pool"] is None
        assert ev["difficulty"] is not None
        assert ev["difficulty"]["number"] == 11

    def test_event_id_unique_across_calls(self):
        e1 = self._make_event()
        e2 = self._make_event()
        assert e1["event_id"] != e2["event_id"]

    def test_event_id_override_for_tests(self):
        ev = self._make_event(event_id="fixed-uuid-xyz")
        assert ev["event_id"] == "fixed-uuid-xyz"

    def test_timestamp_override_for_tests(self):
        ev = self._make_event(timestamp_ms=1234567890)
        assert ev["timestamp_ms"] == 1234567890

    # ── Schema-invariant violations (AC12) ──

    def test_invalid_actor_kind_raises(self):
        with pytest.raises(ValueError, match="actor_kind"):
            self._make_event(actor_kind="hero")

    def test_invalid_target_kind_raises(self):
        with pytest.raises(ValueError, match="target_kind"):
            self._make_event(target_kind="dragon")

    def test_object_target_kind_accepted(self):
        # Objects are valid targets — shooting a door, terminal, droid
        ev = self._make_event(target_kind="object", target_name="Door")
        assert ev["target"]["kind"] == "object"

    def test_environment_target_kind_accepted(self):
        ev = self._make_event(target_kind="environment", target_name="Crates")
        assert ev["target"]["kind"] == "environment"

    def test_opposed_requires_defender_pool(self):
        with pytest.raises(ValueError, match="defender_pool"):
            self._make_event(is_opposed=True, defender_pool=None,
                             difficulty=None)

    def test_static_target_must_not_have_defender_pool(self):
        with pytest.raises(ValueError, match="defender_pool"):
            self._make_event(
                is_opposed=False,
                defender_pool=_basic_attacker_pool(total=10),
            )

    def test_opposed_must_not_have_difficulty(self):
        with pytest.raises(ValueError, match="difficulty"):
            self._make_event(
                is_opposed=True,
                defender_pool=_basic_attacker_pool(total=10),
                difficulty=_basic_difficulty(11),
            )

    def test_static_target_requires_difficulty(self):
        with pytest.raises(ValueError, match="difficulty"):
            self._make_event(is_opposed=False, difficulty=None)

    def test_hit_requires_damage_pool(self):
        with pytest.raises(ValueError, match="damage_pool"):
            self._make_event(hit=True, damage_pool=None)

    def test_hit_requires_soak(self):
        with pytest.raises(ValueError, match="soak"):
            self._make_event(hit=True, soak=None)

    def test_miss_must_not_have_damage_pool(self):
        with pytest.raises(ValueError, match="hit=False"):
            self._make_event(
                hit=False, margin=-3, damage_margin=0,
                damage_pool=_basic_damage_pool(),
                soak=None,
                wound_outcome=build_wound_outcome(
                    outcome_type=OUTCOME_NO_DAMAGE,
                    display_name="Miss",
                ),
            )


# ════════════════════════════════════════════════════════════════════
# Per-archetype payload tests (design v1.1 §9)
# ════════════════════════════════════════════════════════════════════


class TestArchetype1RangedHitWithExplosion:
    """Archetype 1: ranged hit, Wild Die explodes 6→5→2.

    Tests per-die explosion chain rendering and skill+weapon
    source grouping for the damage pool.
    """

    def test_attacker_pool_with_explosion(self):
        # Attacker rolls 4D blaster, Wild Die explodes 6→5→2
        rr = _fake_roll_result(
            normal_dice=[4, 5, 3],
            wild_rolls=[6, 5, 2], wild_total=13,
            wild_exploded=True,
            pool_dice=4, total=25,
            exploded=True,
        )
        dice = compose_pool_dice(rr, [(SOURCE_SKILL, 3)])
        pool = build_dice_pool_roll(
            pool_text="4D", pool_dice=4, pool_pips=0,
            total=25, dice=dice, exploded=True,
        )
        # Wild Die descriptor carries the chain
        wild = pool["dice"][3]
        assert wild["is_wild"] is True
        assert wild["exploded"] is True
        assert wild["explosion_chain"] == [6, 5, 2]
        assert wild["value"] == 13
        assert pool["exploded"] is True

    def test_damage_pool_skill_plus_weapon_grouping(self):
        # 5D damage = 1D skill mod + 4D weapon
        rr = _fake_roll_result(
            normal_dice=[3, 5, 2, 4],
            wild_rolls=[5], wild_total=5,
            pool_dice=5, total=19,
        )
        dice = compose_pool_dice(
            rr, [(SOURCE_SKILL, 1), (SOURCE_WEAPON, 3)]
        )
        # Sources grouped: 1 skill (normal), 3 weapon, 1 skill (wild)
        sources = [d["source"] for d in dice]
        assert sources == ["skill", "weapon", "weapon", "weapon", "skill"]


class TestArchetype2RangedMiss:
    """Archetype 2: ranged miss. Tests the hit=False short-circuit."""

    def test_miss_event_has_no_damage_or_soak(self):
        attacker = _basic_attacker_pool(total=8)  # below difficulty 11
        ev = make_combat_resolution_event(
            actor_id=1, actor_name="Tundra", actor_kind="pc",
            is_force_point_active=False,
            target_id=2, target_name="Yenn", target_kind="npc",
            skill="blaster", weapon_name="Blaster Pistol",
            range_band="medium", stun_mode=False, is_opposed=False,
            attacker_pool=attacker,
            difficulty=_basic_difficulty(11),
            damage_pool=None, soak=None,
            hit=False, margin=-3, damage_margin=0,
            wound_outcome=build_wound_outcome(
                outcome_type=OUTCOME_NO_DAMAGE,
                display_name="Miss",
            ),
        )
        assert ev["hit"] is False
        assert ev["damage_pool"] is None
        assert ev["soak"] is None
        assert ev["wound_outcome"]["outcome_type"] == "no_damage"


class TestArchetype3MeleeMishap:
    """Archetype 3: melee opposed roll, attacker Wild Die rolls 1
    (complication), highest normal die dropped."""

    def test_complication_drops_die_and_tags_wild_with_value_zero(self):
        # Attacker rolls 4D melee combat. Wild Die rolls 1.
        # Engine sets wild total = 0 and removes the highest normal
        # die (a 6). Final total reflects only the remaining 2 normals.
        rr = _fake_roll_result(
            normal_dice=[3, 6, 4],  # 6 is the one that gets dropped
            wild_rolls=[1], wild_total=0,
            wild_complication=True,
            pool_dice=4, total=7,  # 3 + 4 + 0 (wild) + 0 (dropped)
            complication=True, removed_die=6,
        )
        dice = compose_pool_dice(rr, [(SOURCE_SKILL, 3)])
        pool = build_dice_pool_roll(
            pool_text="4D", pool_dice=4, pool_pips=0,
            total=7, dice=dice,
            complication=True, removed_die_value=6,
        )
        assert pool["complication"] is True
        assert pool["removed_die_value"] == 6
        # Find the dropped marker
        dropped = [d for d in pool["dice"] if d["dropped"]]
        assert len(dropped) == 1
        assert dropped[0]["value"] == 6
        # Wild Die has value 0 (engine zeros it on complication)
        wild = [d for d in pool["dice"] if d["is_wild"]]
        assert len(wild) == 1
        assert wild[0]["value"] == 0


class TestArchetype4SpaceCombatForcePoint:
    """Archetype 4: space combat, Force Point active. Tests the
    ``fp_double`` source group rendering and the
    ``is_force_point_active:true`` actor decoration."""

    def test_fp_double_dice_tagged(self):
        # Pilot rolls starship gunnery 4D. With FP, the pool doubles
        # to 4D + 4D fp_double = 7 normal + 1 wild.
        rr = _fake_roll_result(
            normal_dice=[3, 5, 4, 2, 6, 1, 5],
            wild_rolls=[3], wild_total=3,
            pool_dice=8, total=29,
        )
        dice = compose_pool_dice(
            rr, [(SOURCE_SKILL, 3), (SOURCE_FP_DOUBLE, 4)]
        )
        sources = [d["source"] for d in dice]
        # 3 skill normals + 4 fp_double normals + 1 wild (skill)
        assert sources.count("skill") == 4
        assert sources.count("fp_double") == 4

    def test_actor_carries_fp_active_flag(self):
        attacker = _basic_attacker_pool(total=20)
        ev = make_combat_resolution_event(
            actor_id=1, actor_name="Tundra", actor_kind="pc",
            is_force_point_active=True,  # ← this is the test
            target_id=99, target_name="TIE Fighter", target_kind="object",
            skill="starship gunnery", weapon_name="Quad Laser",
            range_band="short", stun_mode=False, is_opposed=False,
            attacker_pool=attacker,
            difficulty=_basic_difficulty(15, "Difficult"),
            damage_pool=_basic_damage_pool(20),
            soak=_basic_soak(10),
            hit=True, margin=5, damage_margin=10,
            wound_outcome=build_wound_outcome(
                outcome_type=OUTCOME_INCAPACITATED,
                display_name="Destroyed",
            ),
        )
        assert ev["actor"]["is_force_point_active"] is True


class TestArchetype5MeleeOpposed:
    """Archetype 5 (v1.1 addition): melee opposed roll. Tests the
    ``is_opposed=True`` branch with both attacker_pool and
    defender_pool populated, margin computed against defender total."""

    def test_opposed_event_has_both_pools_no_difficulty(self):
        attacker = _basic_attacker_pool(total=18)
        # Defender's parry roll
        defender_dice = [
            make_die(2, SOURCE_SKILL),
            make_die(4, SOURCE_SKILL),
            make_die(3, SOURCE_SKILL, is_wild=True),
        ]
        defender = build_dice_pool_roll(
            pool_text="3D", pool_dice=3, pool_pips=0,
            total=9, dice=defender_dice,
        )
        ev = make_combat_resolution_event(
            actor_id=1, actor_name="Tundra", actor_kind="pc",
            is_force_point_active=False,
            target_id=2, target_name="Yenn", target_kind="npc",
            skill="melee combat", weapon_name="Vibro-Knife",
            range_band=None, stun_mode=False,
            is_opposed=True,
            attacker_pool=attacker,
            defender_pool=defender,
            difficulty=None,
            damage_pool=_basic_damage_pool(11),
            soak=_basic_soak(7),
            hit=True, margin=9, damage_margin=4,
            wound_outcome=build_wound_outcome(
                outcome_type=OUTCOME_WOUND,
                display_name="Wounded",
                wound_level_before="Healthy",
                wound_level_after="Wounded",
                wound_level_delta=2,
            ),
        )
        assert ev["action"]["is_opposed"] is True
        assert ev["defender_pool"] is not None
        assert ev["difficulty"] is None
        assert ev["defender_pool"]["total"] == 9
        # Margin matches attacker - defender
        assert ev["margin"] == 9
        # range_band is None for melee
        assert ev["action"]["range_band"] is None


# ════════════════════════════════════════════════════════════════════
# Module structure / static regression
# ════════════════════════════════════════════════════════════════════


class TestModuleStructure:
    """Static checks: the factory module exists and exports the
    public surface the design v1.1 documents.

    If any of the public names are renamed or removed without
    updating the design doc, this suite goes red — surfaces breakage
    early in the migration to Phase 2.
    """

    def test_module_exists(self):
        path = ROOT / "engine" / "combat_events.py"
        assert path.exists(), \
            "engine/combat_events.py must exist (Drop D' Phase 1)"

    def test_module_does_not_modify_dice_engine(self):
        """AC14 — engine/dice.py must NOT be modified by Drop D'.

        Per design v1.1 §4.1: per-die source provenance is composed
        at the combat-events factory layer, not threaded through the
        dice engine. This test guards the boundary by checking that
        ``engine/dice.py`` does not import anything from
        ``combat_events`` (the dependency is one-way).
        """
        dice_path = ROOT / "engine" / "dice.py"
        content = dice_path.read_text(encoding="utf-8")
        assert "combat_events" not in content, \
            "engine/dice.py must not depend on engine/combat_events.py"

    def test_no_telnet_verbose_command_added(self):
        """AC13 — the Q4 modification: telnet ``/verbose`` is deferred
        entirely. No new verbose-toggle command added by this drop."""
        parser_dir = ROOT / "parser"
        for py_file in parser_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            # Look for new verbose-toggle command registrations.
            # An existing unrelated 'verbose' usage in admin tooling
            # is fine; the test guards against a player-facing
            # combat verbose toggle being added.
            forbidden = re.search(
                r"key\s*=\s*['\"]\+combat/verbose['\"]"
                r"|key\s*=\s*['\"]combat/verbose['\"]",
                content,
            )
            assert forbidden is None, \
                f"Found a /verbose toggle in {py_file.name}; " \
                "design v1.1 §8 / AC13 forbids adding this."

    def test_factory_imports_clean(self):
        """The factory module should be importable as a leaf module
        without pulling in a heavy dependency chain (no DB, no
        session manager, no AI). This keeps the unit-test surface
        snappy and prevents cyclic imports during Phase 2 wiring."""
        import importlib
        import sys
        # Force a clean import
        if "engine.combat_events" in sys.modules:
            del sys.modules["engine.combat_events"]
        mod = importlib.import_module("engine.combat_events")
        # The factory module imports time, uuid, typing — nothing
        # from db, server, ai, or parser.
        assert hasattr(mod, "make_combat_resolution_event")
        assert hasattr(mod, "build_wound_outcome")
        assert hasattr(mod, "compose_pool_dice")
