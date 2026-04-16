# -*- coding: utf-8 -*-
"""
Combat Flavor Matrix — auto-pose generation for NPCs and player pass.

Assembles narrative poses from three modular components:
  1. Approach verb   — weapon-type dependent
  2. Connection text — margin-of-success dependent
  3. Wound result    — damage outcome dependent

Used by:
  - NPC auto-poses every round (all NPCs)
  - Player `pass` command / grace-timer auto-pass
  - Multi-action NPC compound sentences

Seeding: round_number * 1000 + combatant_id ensures reproducibility
for reconnection and log replay.
"""
import random
from typing import Optional

# ── Approach verbs: keyed by weapon skill ──────────────────────────────

APPROACH_VERBS: dict[str, list[str]] = {
    # Ranged
    "blaster": [
        "fires a quick shot at",
        "squeezes the trigger, blasting at",
        "levels their weapon and shoots at",
        "snaps off a shot at",
    ],
    "bowcaster": [
        "fires a bolt at",
        "looses a quarrel at",
        "takes aim and fires at",
    ],
    "firearms": [
        "fires at",
        "squeezes off a round at",
        "shoots at",
    ],
    "blaster artillery": [
        "fires a barrage at",
        "unleashes heavy fire at",
    ],
    "missile weapons": [
        "fires a missile at",
        "launches a projectile at",
    ],
    "grenade": [
        "hurls a grenade at",
        "lobs an explosive at",
    ],
    # Melee
    "lightsaber": [
        "lunges forward, swinging at",
        "brings the blade down in a heavy strike against",
        "slashes horizontally at",
        "drives the humming blade toward",
    ],
    "melee combat": [
        "swings at",
        "slashes at",
        "thrusts at",
        "jabs at",
    ],
    "brawling": [
        "throws a punch at",
        "swings a fist at",
        "charges at",
        "lunges at",
    ],
}
_RANGED_FALLBACK = ["fires at", "shoots at"]
_MELEE_FALLBACK = ["swings at", "strikes at"]

# ── Margin ranges (inclusive) ──────────────────────────────────────────

MARGIN_RANGES: dict[str, tuple[int, int]] = {
    "miss_wild":    (-999, -6),
    "miss_close":   (-5, -1),
    "hit_glancing": (0, 4),
    "hit_solid":    (5, 9),
    "hit_critical": (10, 999),
}

# ── Connection text: keyed by margin bucket ────────────────────────────

CONNECTION_TEXT: dict[str, list[str]] = {
    "miss_wild": [
        "but the shot goes completely wide.",
        "missing by a mile.",
        "but the attack sails past harmlessly.",
        "the shot hitting nothing but air.",
        "firing wide into the dust.",
        "missing entirely.",
    ],
    "miss_close": [
        "but the attack is barely deflected.",
        "scoring the surface but doing no real harm.",
        "the strike narrowly missing its mark.",
        "but the shot skips off armor plating.",
        "barely grazing past.",
        "deflected at the last instant.",
    ],
    "hit_glancing": [
        "landing a glancing blow.",
        "clipping them just enough to stagger.",
        "catching them with a grazing strike.",
        "nicking them with a shallow hit.",
        "tagging them with a partial hit.",
    ],
    "hit_solid": [
        "connecting dead center!",
        "landing a heavy, punishing strike!",
        "slamming into them with force!",
    ],
    "hit_critical": [
        "with devastating precision!",
        "finding a critical weak point!",
        "striking with brutal accuracy!",
    ],
}

# ── Dodge verbs ────────────────────────────────────────────────────────

DODGE_VERBS: list[str] = [
    "ducks behind cover as",
    "throws themselves sideways as",
    "drops into a roll as",
    "pivots sharply as",
]

# ── Wound escalation flavor ───────────────────────────────────────────

WOUND_FLAVOR: dict[str, list[str]] = {
    "stunned": [
        "staggers, shaking it off.",
        "flinches from the impact.",
    ],
    "wounded": [
        "grimaces in pain.",
        "stumbles, clutching the wound.",
    ],
    "wounded twice": [
        "staggers, struggling to stay upright.",
        "drops to one knee, badly hurt.",
    ],
    "incapacitated": [
        "crumples to the ground.",
        "collapses, unable to continue.",
    ],
    "mortally wounded": [
        "falls, life slipping away.",
        "hits the ground hard, barely breathing.",
    ],
}


# ── Helper: classify ranged vs melee ──────────────────────────────────

_RANGED_SKILLS = {
    "blaster", "bowcaster", "firearms", "blaster artillery",
    "bows", "grenade", "missile weapons", "vehicle blasters",
}


def _is_ranged(skill: str) -> bool:
    return skill.lower() in _RANGED_SKILLS


# ── Core API ──────────────────────────────────────────────────────────

def _get_margin_bucket(margin: int) -> str:
    """Map an integer margin to a named bucket."""
    for bucket, (lo, hi) in MARGIN_RANGES.items():
        if lo <= margin <= hi:
            return bucket
    return "miss_wild"


def generate_auto_pose(
    char_name: str,
    weapon_skill: str,
    target_name: str,
    margin: int,
    wound_result: str,
    round_num: int = 0,
    combatant_id: int = 0,
) -> str:
    """
    Assemble a flavor pose from FLAVOR_MATRIX components.

    Args:
        char_name:    Combatant's display name
        weapon_skill: Skill used for the action (e.g. "blaster", "lightsaber")
        target_name:  Target's display name
        margin:       (attacker_roll - difficulty); negative = miss
        wound_result: Wound level string ("No Damage", "Wounded", etc.) or ""
        round_num:    Current round number (for seed)
        combatant_id: Combatant's DB id (for seed)

    Returns:
        A single narrative sentence suitable for the Action Log.
    """
    rng = random.Random(round_num * 1000 + combatant_id)

    # Pick approach verb
    skill_key = weapon_skill.lower()
    pool = APPROACH_VERBS.get(skill_key)
    if pool is None:
        pool = _RANGED_FALLBACK if _is_ranged(skill_key) else _MELEE_FALLBACK
    approach = rng.choice(pool)

    # Pick connection text from margin bucket
    bucket = _get_margin_bucket(margin)
    connection = rng.choice(CONNECTION_TEXT[bucket])

    # Assemble
    pose = f"{char_name} {approach} {target_name}, {connection}"

    # Append wound result if damage was dealt
    if wound_result and wound_result.lower() != "no damage":
        pose += f" {target_name} is {wound_result}!"

    return pose


def generate_dodge_pose(
    char_name: str,
    incoming_name: str,
    success: bool,
    round_num: int = 0,
    combatant_id: int = 0,
) -> str:
    """Generate a dodge narrative for the Action Log."""
    rng = random.Random(round_num * 1000 + combatant_id + 500)
    verb = rng.choice(DODGE_VERBS)
    if success:
        return f"{char_name} {verb} {incoming_name}'s attack barely misses."
    return f"{char_name} tries to dodge but {incoming_name}'s shot finds its mark."


def generate_pass_pose(char_name: str) -> str:
    """Generate a minimal pose for a combatant who passed or timed out."""
    return f"{char_name} hesitates, taking no action."


def generate_compound_npc_pose(
    npc_name: str,
    action_poses: list[str],
) -> str:
    """
    Combine multiple NPC action poses into a single compound sentence.

    For multi-action NPCs (e.g., an officer who commands and fires),
    this joins individual action fragments with connectors.
    """
    if not action_poses:
        return f"{npc_name} holds their ground."
    if len(action_poses) == 1:
        return action_poses[0]

    # Join with ", then " for sequential actions
    # First action keeps full sentence, subsequent strip the NPC name prefix
    combined = action_poses[0]
    for extra in action_poses[1:]:
        # Strip the NPC name from the start of subsequent poses
        lower = extra.lower()
        name_lower = npc_name.lower()
        if lower.startswith(name_lower):
            extra = extra[len(npc_name):].lstrip(" ,")
        combined = combined.rstrip(".!") + f", then {extra}"

    return combined


def get_wound_flavor(wound_text: str, target_name: str,
                     seed: int = 0) -> Optional[str]:
    """
    Return an optional wound-escalation drama beat, or None.

    Only returns flavor for severe wounds (wounded twice+).
    """
    pool = WOUND_FLAVOR.get(wound_text.lower())
    if not pool:
        return None
    return f"  {target_name} {pool[seed % len(pool)]}"
