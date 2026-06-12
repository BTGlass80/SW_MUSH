# -*- coding: utf-8 -*-
"""
engine/dsp_hunter.py — the roaming Dark-Side bounty hunter (Drop 4b, hunter.1).

The "soft consequence for the dark path" promised by the III.3 persistent-threat
design: once a Force-user's Dark Side Points cross the wanted threshold (the same
DSP 4 band the BH board already flags under "Dark-Side Notoriety"), a **named,
non-canon bounty hunter** picks up the trail and *closes in over time*. The
pursuit escalates through stages, is surfaced on the BH board and as escalating
personal warnings to the hunted character, and the only way to shake it is to
**atone** — drop back under the threshold and the trail goes cold.

Design constraints honored (all locked):
  * **Deterministic.** No LLM decides anything here: the quarry is chosen by a
    fixed rule, the hunter's identity is a stable function of the character id,
    and the pursuit advances by a fixed per-tick step keyed to the DSP tier.
    (Per the project rule: "deterministic" = the engine computes it, not that it
    uses a frozen number.)
  * **Faction-agnostic, prestige-domain.** The hunt tracks the dark side, not any
    player faction, and confers no credits — it mirrors the existing DSP-notoriety
    surface (engine/bounty_board.py), which is prestige-only by design.
  * **Era / Q1 clean.** Every hunter name is invented (no canonical figure), and
    no Imperial/Rebel string appears.
  * **AI flavor is Ollama-only.** This module ships **deterministic** flavor
    (the stage warnings + a fallback taunt). When the live-spawn climax lands
    (hunter.2) its bark layer uses the local idle queue (Mistral), never the
    Haiku budget.

This module is **pure** — no DB, no sessions, no I/O. The tick driver
(server/tick_handlers_progression.py::dsp_hunter_tick) owns persistence and
message delivery; the BH board (parser/pc_bounty_commands.py via
engine/bounty_board.format_dsp_notoriety_section) owns the board surface.

hunter.2 (deferred, documented in the handoff) replaces the held "at your heels"
state with a live, fightable hunter NPC spawned into the quarry's room and a
reward-on-defeat loop wired through the existing combat-death hook
(parser/combat_commands.py → on_npc_killed_in_combat precedent).
"""

from __future__ import annotations

# Single-source the wanted threshold from the DSP-notoriety module so the hunter
# and the board can never drift apart.
from engine.bounty_board import DSP_BOUNTY_THRESHOLD

# ── ANSI (mirrors engine/bounty_board.py's local palette) ───────────────────
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_RED = "\033[1;31m"
_YELLOW = "\033[1;33m"


# ── Pursuit stages ──────────────────────────────────────────────────────────
# Stored lowercase in dsp_hunter_pursuit.stage. Progress is an integer 0..100.
STAGE_TRACKING = "tracking"    # the hunter has the scent; distant
STAGE_CLOSING = "closing"      # gaining ground
STAGE_IMMINENT = "imminent"    # nearly on top of the quarry
STAGE_AT_HEELS = "at_heels"    # caught up — maximal dread (held until hunter.2 / atonement)

PROGRESS_MAX = 100

# Stage boundaries on the 0..100 progress scale.
_CLOSING_AT = 40
_IMMINENT_AT = 75
_AT_HEELS_AT = 100

# Per-tick advance, keyed to the DSP tier (the deeper the fall, the faster the
# hunter closes — the dark path bites harder). Tiers mirror bounty_board's
# dsp_bounty_tier: Marked (4-5), Hunted (6-8), Darkest (9+).
_STEP_MARKED = 5
_STEP_HUNTED = 9
_STEP_DARKEST = 14

# Invented, Q1-clean hunter roster. A character is assigned one deterministically
# (stable across restarts), so "their" hunter has a consistent name.
HUNTER_ROSTER = (
    "Varn Kessate", "Dax Morrun", "Silari Vohn", "Greel Tannic",
    "Mira Sceln", "Korvan Dree", "Tholos Venar", "Jexa Rul",
    "Bron Achael", "Nessa Quill", "Renik Halar", "Osca Pell",
)


def hunter_for(char_id: int) -> str:
    """Deterministically assign a hunter name to a quarry (stable per id)."""
    try:
        return HUNTER_ROSTER[int(char_id) % len(HUNTER_ROSTER)]
    except (TypeError, ValueError):
        return HUNTER_ROSTER[0]


def is_wanted(dsp: int) -> bool:
    """True iff this DSP total draws a hunter (mirrors bounty_board.is_dsp_wanted)."""
    try:
        return int(dsp or 0) >= DSP_BOUNTY_THRESHOLD
    except (TypeError, ValueError):
        return False


def should_clear(dsp: int) -> bool:
    """True iff a pursuit should end because the quarry has atoned (dropped
    back under the wanted threshold) — the intended escape hatch."""
    return not is_wanted(dsp)


def select_primary_quarry(wanted: list) -> "dict | None":
    """Pick the single most-wanted character (highest DSP; tie-break by lowest
    char id for determinism). Used for logging / future single-hunter modes;
    the tick tracks *every* wanted PC, not just this one.

    ``wanted`` is a list of dicts with 'id' and 'dark_side_points'.
    """
    rows = [w for w in (wanted or []) if is_wanted((w or {}).get("dark_side_points", 0))]
    if not rows:
        return None
    rows.sort(key=lambda w: (-int(w.get("dark_side_points", 0) or 0),
                             int(w.get("id", 0) or 0)))
    return rows[0]


def step_for_dsp(dsp: int) -> int:
    """How far the hunter closes in one tick, by DSP tier."""
    d = int(dsp or 0)
    if d >= 9:
        return _STEP_DARKEST
    if d >= 6:
        return _STEP_HUNTED
    return _STEP_MARKED


def advance_progress(progress: int, dsp: int) -> int:
    """Advance pursuit progress by one tick's worth, clamped to [0, PROGRESS_MAX]."""
    try:
        p = int(progress or 0)
    except (TypeError, ValueError):
        p = 0
    p += step_for_dsp(dsp)
    if p < 0:
        return 0
    if p > PROGRESS_MAX:
        return PROGRESS_MAX
    return p


def pursuit_stage(progress: int) -> str:
    """Map a progress value to its stage label."""
    try:
        p = int(progress or 0)
    except (TypeError, ValueError):
        p = 0
    if p >= _AT_HEELS_AT:
        return STAGE_AT_HEELS
    if p >= _IMMINENT_AT:
        return STAGE_IMMINENT
    if p >= _CLOSING_AT:
        return STAGE_CLOSING
    return STAGE_TRACKING


# ── Player-facing flavor (deterministic) ────────────────────────────────────

def warning_for_stage(stage: str, hunter_name: str) -> "str | None":
    """The escalating warning the hunted character sees when their pursuit
    *enters* a new stage (fired once per stage change by the tick). Returns
    None for an unknown stage.
    """
    h = hunter_name or "a hunter"
    if stage == STAGE_TRACKING:
        return (f"  {_DIM}You can't shake the feeling you're being watched. "
                f"Somewhere out there, a hunter has caught your scent.{_RESET}")
    if stage == STAGE_CLOSING:
        return (f"  {_YELLOW}A contact warns you: the bounty hunter {_BOLD}{h}{_RESET}"
                f"{_YELLOW} has been asking after you — and getting closer.{_RESET}")
    if stage == STAGE_IMMINENT:
        return (f"  {_RED}You spot the same figure twice in one day. {_BOLD}{h}{_RESET}"
                f"{_RED} is nearly on top of you. There is nowhere left to hide.{_RESET}")
    if stage == STAGE_AT_HEELS:
        return (f"  {_RED}{_BOLD}{h} is at your heels.{_RESET}{_RED} You can feel "
                f"the hunt closing around you. Atone — or face them.{_RESET}")
    return None


def trail_cold_line(hunter_name: str) -> str:
    """Shown to a character when their pursuit clears (they dropped back under
    the wanted threshold — they atoned and the hunter loses the trail)."""
    h = hunter_name or "the hunter"
    return (f"  {_DIM}The shadow that has been dogging you falls away. "
            f"{h} has lost the trail.{_RESET}")


def fallback_taunt(hunter_name: str, stage: str) -> str:
    """A deterministic taunt line for the hunter, used as the offline/cold
    fallback (and reused by hunter.2 when the idle-Ollama bark isn't ready).
    Never routed through the Haiku budget."""
    h = hunter_name or "The hunter"
    if stage in (STAGE_IMMINENT, STAGE_AT_HEELS):
        return f'"{h} doesn\'t lose a trail. You\'ve made yourself easy to find."'
    return f'"{h} has worked harder jobs than you. This is just patience."'


# ── BH board surface helpers ────────────────────────────────────────────────

def board_suffix(stage: str) -> str:
    """A short, colored suffix appended to a quarry's BH-board notoriety line to
    show their live pursuit state. Empty string for an unknown/absent stage."""
    if stage == STAGE_TRACKING:
        return f"  {_DIM}— a hunter has the trail{_RESET}"
    if stage == STAGE_CLOSING:
        return f"  {_YELLOW}— hunter closing{_RESET}"
    if stage == STAGE_IMMINENT:
        return f"  {_RED}— hunter closing in{_RESET}"
    if stage == STAGE_AT_HEELS:
        return f"  {_RED}{_BOLD}— hunter at their heels{_RESET}"
    return ""


# ════════════════════════════════════════════════════════════════════════════
# hunter.2 — live-spawn climax seam (PURE: builders + flavor only)
#
# When a pursuit reaches `at_heels`, the tick driver
# (server/tick_handlers_progression.py) spawns a real, fightable hunter NPC into
# the quarry's room via the IO orchestrator engine/dsp_hunter_runtime.py, which
# uses these pure builders. Reward-on-defeat is wired through the combat-death
# hook (parser/combat_commands.py → engine.dsp_hunter_runtime.on_dsp_hunter_killed).
#
# Constraints unchanged: deterministic (stats/identity are a fixed function of
# char id + DSP tier), prestige-domain (no credits — defeating the hunter ends
# the trail; that IS the reward), faction-agnostic, era/Q1-clean, and any LLM
# bark is Ollama-only (the personality below tells the idle queue what to say;
# the deterministic fallback_lines are the only thing that ever ships without it,
# and the Haiku budget is never touched).
# ════════════════════════════════════════════════════════════════════════════

# ai_config_json marker that identifies a runtime-spawned DSP-hunter NPC and ties
# it back to its quarry. Read by the combat-death hook to award the reward and
# clear the pursuit. (These NPCs are created at runtime via db.create_npc, never
# loaded from YAML, so no npc_loader whitelist is involved.)
DSP_HUNTER_AI_KEY = "dsp_hunter_for"


def _dsp_tier(dsp: int) -> str:
    """Marked (4-5) / hunted (6-8) / darkest (9+) — mirrors bounty_board's
    dsp_bounty_tier and the per-tick step tiers above."""
    try:
        d = int(dsp)
    except (TypeError, ValueError):
        d = 0
    if d >= 9:
        return "darkest"
    if d >= 6:
        return "hunted"
    return "marked"


# Per-tier combat profile for the spawned hunter. A real threat, scaled to how
# far the quarry has fallen — but beatable. Deterministic.
_HUNTER_TIER_SHEET = {
    "marked": {
        "attributes": {"dexterity": "3D+1", "knowledge": "2D+1", "mechanical": "2D+2",
                       "perception": "3D", "strength": "3D", "technical": "2D+1"},
        "skills": {"blaster": "5D", "dodge": "4D+1", "brawling": "4D",
                   "melee_combat": "3D+2", "search": "4D", "intimidation": "4D"},
        "weapon": "heavy_blaster_pistol", "move": 10,
        "force_points": 1, "character_points": 5, "dark_side_points": 0,
        "behavior": "tactical",
    },
    "hunted": {
        "attributes": {"dexterity": "3D+2", "knowledge": "2D+2", "mechanical": "3D",
                       "perception": "3D+2", "strength": "3D+1", "technical": "2D+2"},
        "skills": {"blaster": "6D", "dodge": "5D", "brawling": "4D+2",
                   "melee_combat": "4D+1", "search": "5D", "intimidation": "5D"},
        "weapon": "blaster_rifle", "move": 10,
        "force_points": 1, "character_points": 8, "dark_side_points": 0,
        "behavior": "aggressive",
    },
    "darkest": {
        "attributes": {"dexterity": "4D", "knowledge": "3D", "mechanical": "3D+1",
                       "perception": "4D", "strength": "3D+2", "technical": "3D"},
        "skills": {"blaster": "7D", "dodge": "6D", "brawling": "5D+1",
                   "melee_combat": "5D", "search": "6D", "intimidation": "6D"},
        "weapon": "blaster_rifle", "move": 10,
        "force_points": 2, "character_points": 12, "dark_side_points": 0,
        "behavior": "aggressive",
    },
}


def hunter_combat_sheet(char_id: int, dsp: int) -> dict:
    """char_sheet dict for the spawned hunter, scaled to the quarry's DSP tier.
    Shape mirrors a normal NPC char_sheet (attributes/skills/weapon/move/...)
    so engine.npc_combat_ai.build_npc_character produces a real combatant."""
    tier = _dsp_tier(dsp)
    base = _HUNTER_TIER_SHEET[tier]
    return {
        "attributes": dict(base["attributes"]),
        "skills": dict(base["skills"]),
        "weapon": base["weapon"],
        "move": base["move"],
        "force_points": base["force_points"],
        "character_points": base["character_points"],
        "dark_side_points": base["dark_side_points"],
    }


def hunter_ai_config(char_id: int, quarry_id: int, dsp: int,
                     hunter_name: str) -> dict:
    """ai_config dict for the spawned hunter: hostile + the quarry marker +
    deterministic taunts + an Ollama-only personality brief for the idle bark."""
    tier = _dsp_tier(dsp)
    behavior = _HUNTER_TIER_SHEET[tier]["behavior"]
    h = hunter_name or "The hunter"
    return {
        "personality": (
            f"{h} is a bounty hunter who tracks the dark side itself — drawn to "
            f"the stink of it the way a krayt follows blood. Cold, patient, and "
            f"entirely without mercy now that the trail has ended at this room. "
            f"Speak in short, certain threats; never beg, never bluff."
        ),
        "fallback_lines": [
            f'"{h}: \'End of the trail. Hold still.\'"',
            f"*{h} sights down the weapon, unhurried.*",
            f'"{h}: \'You made yourself easy to find. Now you\'re easy to collect.\'"',
        ],
        "hostile": True,
        "combat_behavior": behavior,
        "weapon": _HUNTER_TIER_SHEET[tier]["weapon"],
        DSP_HUNTER_AI_KEY: int(quarry_id),
        "is_dsp_hunter": True,
    }


def hunter_description(hunter_name: str, dsp: int) -> str:
    h = hunter_name or "A bounty hunter"
    tier = _dsp_tier(dsp)
    edge = {
        "marked": "scarred and businesslike",
        "hunted": "heavily armed and unhurried",
        "darkest": "armored, augmented, and utterly without doubt",
    }[tier]
    return (f"{h} — a bounty hunter, {edge}. There is no warrant being read, no "
            f"offer of surrender. The hunt is over; only the collection remains.")


def arrival_line(hunter_name: str) -> str:
    h = hunter_name or "A bounty hunter"
    return (f"{_RED}{_BOLD}{h} steps out of the press of bodies, weapon already "
            f"drawn. The trail ends here.{_RESET}")


def defeat_line(hunter_name: str, killer_name: str) -> str:
    h = hunter_name or "The hunter"
    k = killer_name or "Someone"
    return (f"{_YELLOW}{k} has put {h} down. The trail goes cold — for now. "
            f"Word of it travels the dark places of the galaxy.{_RESET}")


def collected_line(hunter_name: str) -> str:
    """The quarry slipped the hunter (downed/fled) — the hunt resets and rebuilds."""
    h = hunter_name or "The hunter"
    return (f"{_DIM}{h} loses the quarry in the confusion. The hunt is not over — "
            f"only delayed.{_RESET}")


def hunter_collected_line(hunter_name: str) -> str:
    """The hunter caught and DOWNED its quarry — the bounty is collected, the
    hunter withdraws, and the pursuit resets (a fresh one rebuilds over time
    while the quarry stays on the dark path). Room-facing. Prestige-domain: the
    quarry's standing death penalty applies; the hunter takes no credits here."""
    h = hunter_name or "The hunter"
    return (f"{_RED}{h} stands over the fallen quarry — the bounty is collected."
            f"{_RESET} {_DIM}The hunter melts back into the shadows; the trail "
            f"goes quiet.{_RESET}")
