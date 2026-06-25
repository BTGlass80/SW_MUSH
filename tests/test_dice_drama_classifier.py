"""UX Drop 3 — engine drama classifier + drama field on the real producer.

Per dice_animation_and_ux_polish_2026-06-22.md §3, "dramatic" is a tier
computed at the dice chokepoint from signals the engine already has
(wild-die, outcome-significance, criticality, category, difficulty+margin),
NOT a hardcoded command list. This pins the combat half of that classifier
(the §6 pre-launch slice: Force powers + the combat finishing blow):

  1. `classify_drama` over the §3 matrix (pure-function unit).
  2. The additive `drama` field is EMITTED on a dramatic combat roll and is
     0 on an ordinary one — asserted on the REAL producer
     `make_combat_resolution_event`, not a mock.

No new system, no new push: `drama` is one additive field on the existing
combat_resolution_event payload.
"""
from __future__ import annotations

from engine.combat_events import (
    DRAMA_NONE, DRAMA_FLOURISH, DRAMA_FULL,
    classify_drama,
    make_combat_resolution_event,
    make_die,
    build_dice_pool_roll,
    build_wound_outcome,
    make_soak_component,
    SOURCE_SKILL, SOURCE_WEAPON,
    SOAK_STRENGTH,
    OUTCOME_WOUND, OUTCOME_NO_DAMAGE,
    OUTCOME_INCAPACITATED, OUTCOME_STUN_UNCONSCIOUS, OUTCOME_STUN,
)


# ════════════════════════════════════════════════════════════════════
# classify_drama — the §3 matrix (pure function)
# ════════════════════════════════════════════════════════════════════

def _pool(*, exploded: bool = False, complication: bool = False) -> dict:
    """Minimal attacker-pool dict with the wild-die flags the classifier reads."""
    return {"exploded": exploded, "complication": complication,
            "dice": [{"value": 4, "source": "skill"}], "total": 17}


def _classify(**over) -> int:
    base = dict(
        skill="blaster", is_opposed=False, actor_kind="pc", target_kind="npc",
        attacker_pool=_pool(), hit=True, wound_outcome={"outcome_type": OUTCOME_WOUND},
    )
    base.update(over)
    return classify_drama(**base)


class TestClassifyDramaMatrix:

    # ── Signal 1: the wild die (native WEG drama) → Tier 2 ──────────
    def test_exploding_wild_die_is_tier2(self):
        assert _classify(attacker_pool=_pool(exploded=True)) == DRAMA_FULL

    def test_complication_wild_die_is_tier2(self):
        # A rolled 1 (complication) is inherently dramatic even on a miss.
        assert _classify(attacker_pool=_pool(complication=True),
                         hit=False, wound_outcome={"outcome_type": OUTCOME_NO_DAMAGE}) == DRAMA_FULL

    # ── Signal 2: the decisive / finishing blow → Tier 2 ────────────
    def test_incapacitating_blow_is_tier2(self):
        assert _classify(wound_outcome={"outcome_type": OUTCOME_INCAPACITATED}) == DRAMA_FULL

    def test_stun_knockout_is_tier2(self):
        assert _classify(wound_outcome={"outcome_type": OUTCOME_STUN_UNCONSCIOUS}) == DRAMA_FULL

    def test_plain_stun_is_not_decisive_tier2(self):
        # A normal stun (margin 1-3) is a landed hit but not a finishing blow.
        # It still earns the Tier-1 flourish (it's a landed swing).
        assert _classify(wound_outcome={"outcome_type": OUTCOME_STUN}) == DRAMA_FLOURISH

    # ── Signal 4: high-stakes category → Tier 2 ─────────────────────
    def test_force_power_control_is_tier2(self):
        assert _classify(skill="control", wound_outcome={"outcome_type": OUTCOME_NO_DAMAGE},
                         hit=False) == DRAMA_FULL

    def test_force_power_sense_is_tier2(self):
        assert _classify(skill="sense") == DRAMA_FULL

    def test_lightsaber_combat_is_tier2(self):
        assert _classify(skill="lightsaber combat") == DRAMA_FULL

    def test_opposed_pvp_is_tier2(self):
        assert _classify(is_opposed=True, actor_kind="pc", target_kind="pc",
                         hit=True) == DRAMA_FULL

    # ── Tier 1: a deliberate, non-routine landed swing ──────────────
    def test_ordinary_hit_is_tier1_flourish(self):
        assert _classify(hit=True) == DRAMA_FLOURISH

    def test_opposed_pve_is_tier1(self):
        # Opposed vs an NPC is a contest but not PvP — flourish, not full.
        assert _classify(is_opposed=True, actor_kind="pc", target_kind="npc",
                         hit=False, wound_outcome={"outcome_type": OUTCOME_NO_DAMAGE}) == DRAMA_FLOURISH

    # ── Tier 0: routine ─────────────────────────────────────────────
    def test_routine_miss_is_tier0(self):
        assert _classify(skill="blaster", is_opposed=False, hit=False,
                         wound_outcome={"outcome_type": OUTCOME_NO_DAMAGE}) == DRAMA_NONE

    # ── Robustness: never raises on a garbled payload ───────────────
    def test_none_payload_degrades_to_lowest(self):
        assert classify_drama(skill=None, is_opposed=False, actor_kind="npc",
                              target_kind="npc", attacker_pool=None, hit=False,
                              wound_outcome=None) == DRAMA_NONE


# ════════════════════════════════════════════════════════════════════
# drama field on the REAL producer (make_combat_resolution_event)
# ════════════════════════════════════════════════════════════════════

def _attacker_pool(*, exploded=False, complication=False, total=17) -> dict:
    dice = [
        make_die(4, SOURCE_SKILL),
        make_die(5, SOURCE_SKILL),
        make_die(3, SOURCE_SKILL),
        make_die(5, SOURCE_SKILL, is_wild=True, exploded=exploded),
    ]
    return build_dice_pool_roll(
        pool_text="4D", pool_dice=4, pool_pips=0, total=total, dice=dice,
        exploded=exploded, complication=complication,
    )


def _damage_pool(total=14) -> dict:
    return build_dice_pool_roll(
        pool_text="4D", pool_dice=4, pool_pips=0, total=total,
        dice=[make_die(4, SOURCE_WEAPON), make_die(3, SOURCE_WEAPON, is_wild=True)],
    )


def _soak(total=8) -> dict:
    return {"total": total,
            "components": [make_soak_component(SOAK_STRENGTH, "Strength",
                                               value=8, rolls=[8])]}


def _event(**over) -> dict:
    defaults = dict(
        actor_id=1, actor_name="Tundra", actor_kind="pc",
        is_force_point_active=False,
        target_id=2, target_name="Yenn", target_kind="npc",
        skill="blaster", weapon_name="Blaster Pistol",
        range_band="medium", stun_mode=False, is_opposed=False,
        attacker_pool=_attacker_pool(),
        difficulty={"number": 11, "label": "Moderate", "breakdown": "base 11"},
        damage_pool=_damage_pool(),
        soak=_soak(),
        hit=True, margin=6, damage_margin=6,
        wound_outcome=build_wound_outcome(
            outcome_type=OUTCOME_WOUND, display_name="Wounded",
            wound_level_before="Healthy", wound_level_after="Wounded",
            wound_level_delta=2,
        ),
        round_num=3, combat_id=42,
    )
    defaults.update(over)
    return make_combat_resolution_event(**defaults)


class TestDramaFieldOnProducer:

    def test_drama_field_present_and_int(self):
        ev = _event()
        assert "drama" in ev, "the additive drama field must be on the payload"
        assert isinstance(ev["drama"], int)

    def test_dramatic_roll_emits_high_tier(self):
        # An exploding wild die → Tier 2 on the real producer.
        ev = _event(attacker_pool=_attacker_pool(exploded=True))
        assert ev["drama"] == DRAMA_FULL

    def test_incapacitating_blow_emits_tier2(self):
        ev = _event(
            wound_outcome=build_wound_outcome(
                outcome_type=OUTCOME_INCAPACITATED, display_name="Incapacitated",
                wound_level_before="Wounded", wound_level_after="Incapacitated",
                wound_level_delta=2,
            ),
        )
        assert ev["drama"] == DRAMA_FULL

    def test_ordinary_miss_emits_zero(self):
        # A routine miss against a static NPC target: drama 0 (no animation).
        ev = _event(
            hit=False,
            damage_pool=None, soak=None, damage_margin=0,
            wound_outcome=build_wound_outcome(
                outcome_type=OUTCOME_NO_DAMAGE, display_name="Miss",
                wound_level_before="Healthy", wound_level_after="Healthy",
                wound_level_delta=0,
            ),
        )
        assert ev["drama"] == DRAMA_NONE, "an ordinary roll must carry drama 0"

    def test_ordinary_hit_emits_flourish_tier(self):
        ev = _event()  # landed NPC blaster hit, normal wild die
        assert ev["drama"] == DRAMA_FLOURISH
