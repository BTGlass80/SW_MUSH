"""Guide_19 AUTHORITATIVE pass tests — Medical & Death (Opus quality lane).

Complements the earlier draft rework (test_guide_19_medical_death_rework.py).
This file pins the *mechanical* claims the authoritative pass reconciled against
HEAD — the ones the draft did not cover — and guards the phantoms it removed.
Guide_19 is the last player guide to receive an Opus authoritative pass.

Drifts fixed in the authoritative pass (all test-invisible before this file):
1. Respawn is a MANUAL command (`respawn`/`revive`), not automatic, and it
   lands at a FIXED room (DEFAULT_RESPAWN_ROOM_ID = 1, Mos Eisley landing pad) —
   the guide claimed "nearest cantina / BHG chapter house / closest town" and a
   "Coruscant central hub" respawn (all phantom).
2. Loot syntax was `loot <item> from corpse` / `loot all from corpse` + a
   `look corpse` examine — real syntax is `loot <name> [item_key]`, corpses are
   keyed by the dead owner's NAME, and there is no corpse-examine command.
3. "You never lose credits on death, insured or not" was unqualified — a
   bountied PC killed by a Guild BH eats a bh_insurance_hit (INSURANCE_FLAT +
   INSURANCE_PCT% of the bounty).
4. Stim effects: adrenaline_shot is +2D Strength (not +1D "sustained"); all
   stims are 5-minute timed buffs (not "one roll").
5. The medpac family (stim <player> with medpac/_advanced/_fastflesh) + the
   `stim/force` overdose path + self-stim -1D + one-active-stim were undocumented.
6. `+medical` is a verb umbrella, not a "dashboard/status"; `+sheet` renders the
   wound-LEVEL Condition line, not a wound_state countdown.
7. Anti-grief (repeat-kill loot decay) + the 60s PvP respawn grace were omitted.
"""
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_19_Medical_Death.md")


def _read_guide() -> str:
    with open(GUIDE_PATH, encoding="utf-8") as fh:
        return fh.read()


# ── Heal difficulties (pinned to _HEAL_DIFFICULTY) ──────────────────────────────

def test_heal_difficulty_ladder_matches_engine():
    """Guide §3/§9 heal table: Stunned 8 / Wounded 11 / x2 14 / Incap 16 / Mortal 21."""
    from parser.medical_commands import _HEAL_DIFFICULTY
    assert _HEAL_DIFFICULTY == {1: 8, 2: 11, 3: 14, 4: 16, 5: 21}, (
        f"_HEAL_DIFFICULTY changed to {_HEAL_DIFFICULTY}; update Guide_19 §3/§9."
    )


def test_default_heal_rate_is_200():
    from parser.medical_commands import _DEFAULT_HEAL_RATE
    assert _DEFAULT_HEAL_RATE == 200


# ── Stim catalog difficulties + effects ─────────────────────────────────────────

def test_stim_difficulties_match_catalog():
    """Guide §3 stim table difficulties pinned to _STIM_CATALOG."""
    from parser.medical_commands import _STIM_CATALOG
    assert _STIM_CATALOG["stimpack"]["difficulty"] == 10
    assert _STIM_CATALOG["adrenaline_shot"]["difficulty"] == 15
    assert _STIM_CATALOG["combat_stim"]["difficulty"] == 20
    assert _STIM_CATALOG["focus_stim"]["difficulty"] == 15


def test_medpac_family_heals_and_difficulties():
    """Guide §3 medpac block: heal 1/2/1 levels at First Aid 10/11/12, 8."""
    from parser.medical_commands import _STIM_CATALOG
    assert _STIM_CATALOG["medpac"]["heal_wound_levels"] == 1
    assert _STIM_CATALOG["medpac"]["difficulty"] == 10
    assert _STIM_CATALOG["medpac_advanced"]["heal_wound_levels"] == 2
    assert _STIM_CATALOG["medpac_fastflesh"]["heal_wound_levels"] == 1
    assert _STIM_CATALOG["medpac_fastflesh"]["difficulty"] == 8
    # All three are First Aid, buff-less heals.
    for k in ("medpac", "medpac_advanced", "medpac_fastflesh"):
        assert _STIM_CATALOG[k]["skill"] == "first aid"
        assert _STIM_CATALOG[k]["buff_type"] is None


def test_self_administration_rules():
    """Guide §3: stimpack/focus/medpacs self-OK; adrenaline/combat blocked."""
    from parser.medical_commands import _STIM_CATALOG
    assert _STIM_CATALOG["stimpack"]["self_administration_ok"] is True
    assert _STIM_CATALOG["focus_stim"]["self_administration_ok"] is True
    assert _STIM_CATALOG["adrenaline_shot"]["self_administration_ok"] is False
    assert _STIM_CATALOG["combat_stim"]["self_administration_ok"] is False
    for k in ("medpac", "medpac_advanced", "medpac_fastflesh"):
        assert _STIM_CATALOG[k]["self_administration_ok"] is True


def test_adrenaline_failure_inflicts_wound():
    """Guide §2/§3/§9: adrenaline shot failure = +1 wound level on the target."""
    from parser.medical_commands import _STIM_CATALOG
    assert _STIM_CATALOG["adrenaline_shot"]["failure_wound_levels"] == 1


def test_stim_buff_magnitudes_and_durations():
    """Guide §3 effect column: adrenaline is +2D STR, all stims are 5-min buffs."""
    from engine.buffs import BUFF_TEMPLATES
    # Magnitudes (pips: 3 = +1D, 6 = +2D).
    assert BUFF_TEMPLATES["stimpack"]["stat_modifiers"] == {"strength": 3}
    assert BUFF_TEMPLATES["adrenaline_shot"]["stat_modifiers"] == {"strength": 6}, (
        "adrenaline_shot is +2D Strength — Guide §3/§9 must NOT say '+1D, sustained'."
    )
    assert BUFF_TEMPLATES["combat_stim"]["stat_modifiers"] == {"dexterity": 3}
    assert BUFF_TEMPLATES["focus_stim"]["stat_modifiers"] == {"knowledge": 3}
    # Durations: all four stims are 5-minute (300s) buffs, not "one roll".
    for k in ("stimpack", "adrenaline_shot", "combat_stim", "focus_stim"):
        assert BUFF_TEMPLATES[k]["duration_seconds"] == 300, (
            f"{k} duration changed; Guide_19 §3 'Duration' column says 5 min."
        )


# ── Bacta + insurance prices ────────────────────────────────────────────────────

def test_bacta_prices():
    """Guide §3/§9: bacta tank 500 cr, bacta pack 150 cr."""
    from engine.death import BACTA_TANK_PRICE, BACTA_PACK_PRICE
    assert BACTA_TANK_PRICE == 500
    assert BACTA_PACK_PRICE == 150


def test_gear_insurance_premium_500():
    from engine.gear_insurance import GEAR_INSURANCE_PREMIUM
    assert GEAR_INSURANCE_PREMIUM == 500


def test_bounty_insurance_hit_constants():
    """Guide §4.5/§9 caveat: a Guild-BH kill of a bountied PC = flat 250 + 10%."""
    from engine.death import INSURANCE_FLAT, INSURANCE_PCT
    assert INSURANCE_FLAT == 250
    assert INSURANCE_PCT == 10


# ── Death-loop timing constants ─────────────────────────────────────────────────

def test_wound_recovery_one_hour():
    """Guide §4/§9: post-death wound_state debuff lasts 1 real-time hour."""
    from engine.death import WOUND_RECOVERY_SECONDS
    assert WOUND_RECOVERY_SECONDS == 3600.0


def test_corpse_decay_windows():
    """Guide §4/§9: contested 2h, lawless 4h, secured no corpse."""
    from engine.death import (
        CORPSE_DECAY_SECONDS_CONTESTED, CORPSE_DECAY_SECONDS_LAWLESS,
        decay_seconds_for_security, NO_CORPSE,
    )
    assert CORPSE_DECAY_SECONDS_CONTESTED == 7200.0
    assert CORPSE_DECAY_SECONDS_LAWLESS == 14400.0
    assert decay_seconds_for_security("secured") is NO_CORPSE
    assert decay_seconds_for_security("contested") == 7200.0
    assert decay_seconds_for_security("lawless") == 14400.0


def test_respawn_is_fixed_location():
    """Guide §4/§7/§9: respawn always lands at room 1 (Mos Eisley landing pad)."""
    from engine.death import DEFAULT_RESPAWN_ROOM_ID
    assert DEFAULT_RESPAWN_ROOM_ID == 1


def test_antigrief_and_respawn_grace():
    """Guide §4/§9: repeat-kill loot decay 1.0/0.5/0.25/0.0 in 30 min; 60s grace."""
    from engine.death import (
        GRIEF_LOOT_FACTORS, GRIEF_WINDOW_SECONDS, RESPAWN_GRACE_SECONDS,
    )
    assert GRIEF_LOOT_FACTORS == (1.0, 0.5, 0.25, 0.0)
    assert GRIEF_WINDOW_SECONDS == 1800.0
    assert RESPAWN_GRACE_SECONDS == 60.0


# ── Wound ladder penalties + hazard interval ────────────────────────────────────

def test_wound_penalty_dice():
    """Guide §1: Wounded -1D, Wounded Twice -2D (and stun is per-timer, not here)."""
    from engine.character import WoundLevel
    assert WoundLevel.WOUNDED.penalty_dice == 1
    assert WoundLevel.WOUNDED_TWICE.penalty_dice == 2
    # Incapacitated and worse can't act — penalty is moot (0).
    assert WoundLevel.INCAPACITATED.penalty_dice == 0
    assert WoundLevel.WOUNDED_TWICE.can_act is True
    assert WoundLevel.INCAPACITATED.can_act is False


def test_hazard_check_interval_300():
    """Guide §2/§9: hazards tick every 5 minutes (300 seconds)."""
    from engine.hazards import HAZARD_CHECK_INTERVAL
    assert HAZARD_CHECK_INTERVAL == 300


# ── Force healing ────────────────────────────────────────────────────────────────

def test_force_heal_difficulties_and_self_only():
    """Guide §3/§6: accelerate_healing Moderate 15 (self only); control_pain Easy 10."""
    from engine.force_powers import POWERS
    ah = POWERS["accelerate_healing"]
    cp = POWERS["control_pain"]
    assert ah.base_diff == 15, "accelerate_healing is Moderate (15) per Guide §3/§9."
    assert cp.base_diff == 10, "control_pain is Easy (10) per Guide §3."
    # Guide §6: accelerate_healing heals only yourself — it targets self.
    assert ah.target == "self", (
        "accelerate_healing now targets others — Guide §6 says it is self-only."
    )


# ── Command-key truth (the verbs the guide tells players to type) ────────────────

def test_command_keys_exist():
    """The verbs Guide_19 documents resolve to real command keys."""
    from parser.medical_commands import (
        HealCommand, HealAcceptCommand, HealRateCommand,
        StimCommand, StimAcceptCommand, MedicalCommand,
    )
    from parser.builtin_commands import RespawnCommand, LootCommand, BactaTankCommand
    from parser.insurance_commands import InsureCommand
    assert HealCommand.key == "heal"
    assert HealAcceptCommand.key == "healaccept"
    assert HealRateCommand.key == "+healrate"
    assert StimCommand.key == "stim"
    assert StimAcceptCommand.key == "stimaccept"
    assert MedicalCommand.key == "+medical"
    assert RespawnCommand.key == "respawn" and "revive" in RespawnCommand.aliases
    assert LootCommand.key == "loot"
    assert BactaTankCommand.key == "bacta"
    assert InsureCommand.key == "+insure"
    # +medical is a verb umbrella (dispatches heal/accept/rate/stim), not a screen.
    assert set(MedicalCommand.valid_switches) >= {"heal", "accept", "rate", "stim"}


# ── Guide-text phantom guards (the corrected drift must not creep back) ──────────

def test_guide_has_no_loot_from_corpse_phantom():
    text = _read_guide().lower()
    assert "from corpse" not in text, (
        "Guide_19 still shows `loot ... from corpse` — real syntax is "
        "`loot <name> [item_key]` (corpse keyed by the dead owner's name)."
    )
    assert "loot all from corpse" not in text


def test_guide_has_no_look_corpse_phantom():
    text = _read_guide().lower()
    assert "look corpse" not in text, (
        "Guide_19 still references `look corpse` — there is no corpse-examine "
        "command; corpses appear in the room `look` listing only."
    )


def test_guide_documents_manual_respawn_and_fixed_location():
    text = _read_guide()
    assert "respawn" in text.lower() and "revive" in text.lower()
    assert "Mos Eisley landing" in text, (
        "Guide_19 must state respawn lands at the fixed Mos Eisley landing pad."
    )
    # The phantom 'Coruscant central hub' respawn must be gone.
    assert "Coruscant central hub" not in text


def test_guide_documents_medpac_and_overdose():
    text = _read_guide()
    assert "medpac" in text, "Guide_19 must document the medpac healing family."
    assert "stim/force" in text, "Guide_19 must document the overdose path."


def test_guide_qualifies_credit_loss_on_death():
    text = _read_guide().lower()
    # The bounty insurance-hit exception must be present.
    assert "bounty insurance hit" in text, (
        "Guide_19 §4.5 must note the bounty insurance hit — death is not always "
        "credit-free for a bountied PC killed by a Guild BH."
    )


def test_guide_does_not_call_medical_a_dashboard():
    text = _read_guide().lower()
    assert "medical dashboard" not in text, (
        "+medical is a verb umbrella, not a dashboard/status screen."
    )


def test_guide_era_clean():
    """Era cleanness: no Imperial/Empire/Rebel/TIE in the player-facing guide."""
    text = _read_guide()
    for term in ("Imperial", "Empire", "Rebel", "TIE fighter", "Stormtrooper"):
        assert term not in text, f"Guide_19 contains era-dirty term '{term}'."
