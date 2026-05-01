# -*- coding: utf-8 -*-
"""
engine/organizations.py — Organizations & Factions system.  [v31]

Handles: join, leave, promote, rep adjustment, equipment issuance/reclamation,
         guild CP bonus, payroll tick, faction_intent migration, seed loading.

v31 additions (Faction Reputation Drop 4-6)
============================================
- get_char_faction_rep(): unified rep lookup (member or attributes)
- get_all_faction_reps(): all factions overview for HUD/web panel
- get_shop_price_modifier() / get_faction_shop_modifier(): shop discounts/blocks
- get_faction_standing_context(): NPC dialogue injection by rep tier
- Fixed send_json_event → await session.send_json (was silently failing)

v30 additions (Faction Reputation Drop 1-3)
============================================
- adjust_rep() refactored: optional delta, reason, session; rep history; cross-faction
- check_auto_promote(): fires on rep threshold crossing, multi-rank support
- format_reputation_overview(): +reputation display
- format_reputation_detail(): +reputation <faction> detail view
- REP_TIERS / REP_TIER_NAMES / CROSS_FACTION_PENALTIES
- Non-member rep range expanded to -100..+100
- _log_rep_change(): appends to rep_history (capped at 10 per faction)
"""

import json
import logging
import os
import time
from typing import Optional

from engine.json_safe import safe_json_loads

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
FACTION_SWITCH_COOLDOWN = 7 * 24 * 3600   # 7 days
MAX_GUILD_MEMBERSHIPS   = 3
GUILD_CP_DISCOUNT       = 0.20            # 20% off skill training

REP_GAINS = {
    "complete_faction_mission":     3,
    "complete_profession_chain_step": 5,
    "complete_chain_final":        15,
    "kill_enemy_faction_npc":       1,
    "complete_bounty":              2,
    "deliver_contraband":           2,
    "crafting_sale":                1,
    "faction_event_attendance":     1,
    "rule_violation":              -5,
    "territory_claim":              3,
    "territory_defense":            2,
    "trade_with_faction_vendor":    1,
    "hostile_action":              -5,
    "defection":                  -30,
    "cross_faction_kill":           2,
}

# Cross-faction penalties: gaining rep with key triggers penalty for values
CROSS_FACTION_PENALTIES = {
    "empire": {"rebel": -0.5},
    "rebel":  {"empire": -0.5},
    # ── B.1.b.1 (Apr 29 2026) — CW mirror ────────────────────────────
    # Republic and CIS are direct adversaries — gaining rep with one
    # damages standing with the other at the same -0.5 ratio as GCW.
    # Jedi Order does NOT cross-penalize: per CW v3 §3.1 the Jedi
    # serve the Republic but their faction is "a way of life," and
    # joining the Jedi is village-quest-gated, not a political
    # affiliation that can drift via missions.
    "republic": {"cis": -0.5},
    "cis":      {"republic": -0.5},
}

# Rep tier thresholds and names
REP_TIERS = [
    (-100, -50, "hostile",     "\033[1;31m"),
    (-49,  -25, "unfriendly",  "\033[0;31m"),
    (-24,   -1, "wary",        "\033[33m"),
    (0,      9, "unknown",     "\033[2m"),
    (10,    24, "recognized",  "\033[0m"),
    (25,    49, "trusted",     "\033[1;33m"),
    (50,    74, "honored",     "\033[1;36m"),
    (75,    89, "revered",     "\033[1;32m"),
    (90,   100, "exalted",     "\033[1;35m"),
]

REP_TIER_NAMES = {
    "hostile":    "Hostile",
    "unfriendly": "Unfriendly",
    "wary":       "Wary",
    "unknown":    "Unknown",
    "recognized": "Recognized",
    "trusted":    "Trusted",
    "honored":    "Honored",
    "revered":    "Revered",
    "exalted":    "Exalted",
}

# Weekly stipend in credits (faction_code, rank_level) -> amount
STIPEND_TABLE = {
    ("empire",   1): 50,
    ("empire",   2): 100,
    ("empire",   3): 200,
    ("empire",   4): 350,
    ("empire",   5): 500,
    ("empire",   6): 500,
    ("rebel",    1): 25,
    ("rebel",    2): 50,
    ("rebel",    3): 100,
    ("rebel",    4): 200,
    ("rebel",    5): 300,
    ("rebel",    6): 300,
    ("hutt",     1): 75,
    ("hutt",     2): 150,
    ("hutt",     3): 300,
    ("hutt",     4): 500,
    ("hutt",     5): 750,
    ("bh_guild", 1): 25,
    ("bh_guild", 2): 75,
    ("bh_guild", 3): 150,
    ("bh_guild", 4): 300,
    ("bh_guild", 5): 500,
    # ── B.1.b.1 (Apr 29 2026) — CW stipends ──────────────────────────
    # Mirrors the GCW shape per faction archetype:
    #   republic       — lawful state, mirrors empire pay scale
    #   cis            — insurgent, mirrors rebel pay scale
    #   jedi_order     — modest stipend (Order is austere; rank 0 is
    #                    Padawan, rank 1 Knight, rank 2 Master)
    #   hutt_cartel    — direct rename of hutt; same scale
    #   bounty_hunters_guild — direct rename of bh_guild; same scale
    ("republic", 1): 50,
    ("republic", 2): 100,
    ("republic", 3): 200,
    ("republic", 4): 350,
    ("republic", 5): 500,
    ("republic", 6): 500,
    ("cis",      1): 25,
    ("cis",      2): 50,
    ("cis",      3): 100,
    ("cis",      4): 200,
    ("cis",      5): 300,
    ("jedi_order", 1): 50,
    ("jedi_order", 2): 100,
    ("hutt_cartel", 1): 75,
    ("hutt_cartel", 2): 150,
    ("hutt_cartel", 3): 300,
    ("hutt_cartel", 4): 500,
    ("hutt_cartel", 5): 750,
    ("bounty_hunters_guild", 1): 25,
    ("bounty_hunters_guild", 2): 75,
    ("bounty_hunters_guild", 3): 150,
    ("bounty_hunters_guild", 4): 300,
    ("bounty_hunters_guild", 5): 500,
}

# ── Equipment catalog ────────────────────────────────────────────────────────

EQUIPMENT_CATALOG = {
    # Imperial
    "imperial_uniform":      {"name": "Imperial Officer's Uniform", "slot": "armor", "description": "Standard grey-green Imperial uniform."},
    "se_14c_pistol":         {"name": "SE-14C Blaster Pistol",      "slot": "weapon", "description": "Standard Imperial sidearm. 4D damage."},
    "e11_blaster_rifle":     {"name": "E-11 Blaster Rifle",         "slot": "weapon", "description": "Standard stormtrooper weapon. 5D damage."},
    "stormtrooper_armor":    {"name": "Stormtrooper Armor",         "slot": "armor", "description": "Full plastoid composite. +2D physical, +1D energy soak."},
    "improved_armor":        {"name": "Improved Body Armor",        "slot": "armor", "description": "Officer-grade composite. +2D+1 physical, +1D+2 energy soak."},
    "officers_sidearm":      {"name": "Officer's Blaster Pistol",   "slot": "weapon", "description": "DL-44 variant issued to Imperial officers. 5D damage."},
    "officers_uniform":      {"name": "Naval Officer's Uniform",    "slot": "armor", "description": "Crisp black Imperial Navy dress uniform."},
    "datapad_imperial":      {"name": "Imperial Datapad",           "slot": "misc",   "description": "Encrypted military datapad with logistics software."},
    "flight_suit_imperial":  {"name": "TIE Pilot Flight Suit",      "slot": "armor", "description": "Pressure suit with life support. +1D physical soak."},
    "civilian_cover":        {"name": "Civilian Cover Identity",    "slot": "misc",   "description": "Forged credentials and civilian wardrobe for intelligence ops."},
    "slicing_kit":           {"name": "Slicing Kit",                "slot": "misc",   "description": "Electronic intrusion toolkit. +1D to computer slicing."},
    # Rebel
    "encrypted_comlink":     {"name": "Encrypted Comlink",          "slot": "misc",   "description": "Rebel-coded comlink. Secure channel access."},
    "blaster_pistol":        {"name": "DH-17 Blaster Pistol",      "slot": "weapon", "description": "Reliable Rebel sidearm. 4D damage."},
    "flight_suit":           {"name": "Rebel Flight Suit",          "slot": "armor", "description": "Pilot flight suit with survival pack. +1D physical soak."},
    "rebel_combat_vest":     {"name": "Combat Vest",                "slot": "armor", "description": "Reinforced vest. +1D+2 physical soak."},
    "a280_rifle":            {"name": "A280 Blaster Rifle",         "slot": "weapon", "description": "Standard Rebel long arm. 5D+1 damage."},
    # Bounty Hunters
    "binder_cuffs":          {"name": "Binder Cuffs",               "slot": "misc",   "description": "Durasteel restraints. Required for live capture."},
    "guild_license":         {"name": "Guild License",              "slot": "misc",   "description": "Official Bounty Hunters' Guild authorization."},
    "tracking_fob":          {"name": "Tracking Fob",               "slot": "misc",   "description": "Short-range biometric tracker. +1D to Search for targets."},
    # Generic
    "medpac":                {"name": "Medpac",                     "slot": "misc",   "description": "Standard medpac. Heals 1D Stun damage when applied."},
    # ── B.1.b.1 (Apr 29 2026) — CW equipment ─────────────────────────
    # Item codes referenced by data/worlds/clone_wars/organizations.yaml
    # rank equipment lists. Catalog entries supply the display name,
    # slot, and description used by `format_equipment_inventory` and
    # `issue_equipment` narration.
    # Republic
    "republic_uniform":      {"name": "Republic Service Uniform",   "slot": "armor", "description": "Off-white Republic-issue tunic and trousers. Worn by clones and conscripts off-duty."},
    "dc17_pistol":           {"name": "DC-17 Hand Blaster",         "slot": "weapon", "description": "Republic sidearm. 4D damage. Issued to clone troopers and Republic officers."},
    "dc15_blaster_rifle":    {"name": "DC-15A Blaster Rifle",       "slot": "weapon", "description": "Standard clone trooper rifle. 5D damage. Heavier than Imperial E-11; longer range."},
    "republic_light_armor":  {"name": "Republic Combat Plate",      "slot": "armor", "description": "Phase II clone trooper armor segments adapted for non-clone wearers. +1D+2 physical soak."},
    # ── B.1.b.2 (Apr 29 2026) — Republic specialization gear ─────────
    # Mirrors the Imperial spec-equipment shape (flight_suit_imperial,
    # officers_uniform, datapad_imperial) for the Republic clone-pilot
    # and clone-officer specs. The republic_intelligence spec reuses
    # civilian_cover + slicing_kit since those items are era-agnostic
    # spy gear (forged ID, slicing toolkit).
    "flight_suit_republic":  {"name": "Republic Pilot Flight Suit",   "slot": "armor", "description": "Sealed flight suit with life support and Republic comm rig. +1D physical soak."},
    "officers_uniform_republic": {"name": "Republic Officer's Uniform", "slot": "armor", "description": "Pressed Republic Navy dress uniform with junior-officer insignia."},
    "datapad_republic":      {"name": "Republic Datapad",             "slot": "misc",   "description": "Encrypted Republic-issue datapad with logistics and comms software."},
    # CIS / Hutt operatives
    "civilian_gear":         {"name": "Civilian Operative Kit",     "slot": "misc",   "description": "Plain clothes, forged ID chip, and a comm earpiece. Suited to undercover work."},
    "heavy_blaster_pistol":  {"name": "Heavy Blaster Pistol",       "slot": "weapon", "description": "DL-44 or equivalent. 5D damage. Compact stopping power."},
    "smuggler_vest":         {"name": "Smuggler's Vest",            "slot": "armor", "description": "Multi-pocket vest with concealed plating. +1D physical soak; +2 storage."},
    # Jedi Order
    "padawan_robes":         {"name": "Padawan Robes",              "slot": "armor", "description": "Tan and brown Jedi robes worn by apprentices. No armor value; identifies the wearer as a member of the Order."},
    "jedi_utility_belt":     {"name": "Jedi Utility Belt",          "slot": "misc",   "description": "Padawan-issue belt with food capsules, comlink, and a small tool kit."},
    "jedi_robes":            {"name": "Jedi Knight Robes",          "slot": "armor", "description": "The earned robes of a Jedi Knight. Sturdy weave with internal pockets for a lightsaber clip."},
}

# Rank-0 equipment per faction
RANK_0_EQUIPMENT = {
    "empire":   ["imperial_uniform", "se_14c_pistol"],
    "rebel":    ["encrypted_comlink"],
    "hutt":     [],   # Hutts don't issue gear to associates
    "bh_guild": ["binder_cuffs", "guild_license"],
    # ── B.1.b.1 (Apr 29 2026) — CW rank-0 ────────────────────────────
    # Mirrors data/worlds/clone_wars/organizations.yaml::ranks[level=0].equipment.
    # Kept in sync with the YAML so the in-Python issuance path matches
    # the YAML-driven seeding path byte-for-byte.
    "republic":             ["republic_uniform", "dc17_pistol"],
    "cis":                  ["encrypted_comlink"],
    "jedi_order":           ["padawan_robes", "jedi_utility_belt"],
    "hutt_cartel":          ["blaster_pistol"],   # CW Hutts issue a sidearm; YAML differs from GCW empty list
    "bounty_hunters_guild": ["binder_cuffs", "guild_license"],
}

# Rank-1 equipment per faction (adds to rank 0)
RANK_1_EQUIPMENT = {
    "empire":   [],   # Handled by specialization instead
    "rebel":    ["blaster_pistol", "flight_suit"],
    "hutt":     [],
    "bh_guild": ["tracking_fob"],
    # ── B.1.b.1 (Apr 29 2026) — CW rank-1 ────────────────────────────
    # Mirrors data/worlds/clone_wars/organizations.yaml::ranks[level=1].equipment.
    # republic at rank 1 is "Private" (DC-15A + light armor); CIS at
    # rank 1 is "Operative" (sidearm + civvies); jedi rank 1 is the
    # Knight robes; hutt_cartel rank 1 is "Runner" (heavy + vest);
    # bounty_hunters_guild rank 1 is "Journeyman" (tracking fob).
    "republic":             ["dc15_blaster_rifle", "republic_light_armor"],
    "cis":                  ["blaster_pistol", "civilian_gear"],
    "jedi_order":           ["jedi_robes"],
    "hutt_cartel":          ["heavy_blaster_pistol", "smuggler_vest"],
    "bounty_hunters_guild": ["tracking_fob"],
}

# Imperial specialization equipment
IMPERIAL_SPEC_EQUIPMENT = {
    "stormtrooper":  ["e11_blaster_rifle", "stormtrooper_armor"],
    "tie_pilot":     ["flight_suit_imperial"],
    "naval_officer": ["officers_uniform", "datapad_imperial"],
    "intelligence":  ["civilian_cover", "slicing_kit"],
}

# ── B.1.b.2 (Apr 29 2026) — Republic specialization equipment ───────
# Mirrors IMPERIAL_SPEC_EQUIPMENT shape per the Apr 29 design lock-in:
# four Republic specs analogous to the four Imperial ones. Issued by
# `complete_republic_specialization` after a Republic PC selects via
# the `specialize <1-4>` command.
#
# Mapping rationale:
#   clone_trooper        ↔ stormtrooper     (ground combat)
#   clone_pilot          ↔ tie_pilot        (space combat)
#   clone_officer        ↔ naval_officer    (command/support)
#   republic_intelligence↔ intelligence     (stealth/slicing — gear reused)
REPUBLIC_SPEC_EQUIPMENT = {
    "clone_trooper":         ["dc15_blaster_rifle", "republic_light_armor"],
    "clone_pilot":           ["flight_suit_republic"],
    "clone_officer":         ["officers_uniform_republic", "datapad_republic"],
    "republic_intelligence": ["civilian_cover", "slicing_kit"],
}

# Faction → spec table dispatch. Used by the generic
# `prompt_specialization` / `complete_specialization` helpers and by
# any future caller that needs to look up "what's the spec equipment
# for this faction's spec key?" without hardcoding the faction code.
SPEC_EQUIPMENT_BY_FACTION = {
    "empire":   IMPERIAL_SPEC_EQUIPMENT,
    "republic": REPUBLIC_SPEC_EQUIPMENT,
}


# ── Attribute helpers ─────────────────────────────────────────────────────────

def _get_attrs(char: dict) -> dict:
    raw = char.get("attributes", "{}")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            log.warning("_get_attrs: unhandled exception", exc_info=True)
            return {}
    return raw if isinstance(raw, dict) else {}


def _set_attrs(char: dict, attrs: dict):
    char["attributes"] = json.dumps(attrs)


# ── Rep tier helpers ──────────────────────────────────────────────────────────

def get_rep_tier(rep: int) -> tuple:
    """Return (tier_key, tier_name, color_code) for a rep value."""
    for lo, hi, key, color in REP_TIERS:
        if lo <= rep <= hi:
            return key, REP_TIER_NAMES[key], color
    if rep >= 90:
        return "exalted", "Exalted", "\033[1;35m"
    return "hostile", "Hostile", "\033[1;31m"


def _rep_bar(rep: int, width: int = 10) -> str:
    """Render a simple ASCII progress bar for rep (0-100 scale)."""
    clamped = max(0, min(100, rep))
    filled = int(clamped / 100 * width)
    return "\033[1;33m" + "█" * filled + "\033[2m" + "░" * (width - filled) + "\033[0m"


def _rep_bar_signed(rep: int, width: int = 10) -> str:
    """Render a bar for -100..+100 range (non-members)."""
    if rep >= 0:
        return _rep_bar(rep, width)
    # Negative: show red fill from right to left
    clamped = max(-100, rep)
    filled = int(abs(clamped) / 100 * width)
    return "\033[2m" + "░" * (width - filled) + "\033[1;31m" + "█" * filled + "\033[0m"


# ── Equipment issuance ────────────────────────────────────────────────────────

async def issue_equipment(char: dict, org_code: str, db,
                           item_keys: list, session=None) -> list:
    """
    Issue a list of items to a character. Adds to inventory and records in
    issued_equipment table. Returns list of item names issued.
    Graceful-drop: never raises.
    """
    issued_names = []
    try:
        org = await db.get_organization(org_code)
        if not org:
            return issued_names

        for key in item_keys:
            catalog_entry = EQUIPMENT_CATALOG.get(key)
            if not catalog_entry:
                log.warning("[orgs] Unknown equipment key: %s", key)
                continue

            item_name = catalog_entry["name"]
            # Add to inventory
            await db.add_to_inventory(char["id"], {
                "key":         key,
                "name":        item_name,
                "slot":        catalog_entry.get("slot", "misc"),
                "description": catalog_entry.get("description", ""),
                "faction_issued": True,
                "faction_code":   org_code,
            })
            # Record issuance
            await db.issue_equipment(char["id"], org["id"], key, item_name)
            issued_names.append(item_name)

        if issued_names and session:
            items_str = ", ".join(issued_names)
            await session.send_line(
                f"\n  \033[1;36m[{org['name'].upper()}]\033[0m "
                f"Equipment issued: \033[1;33m{items_str}\033[0m"
            )
    except Exception as e:
        log.exception("[orgs] issue_equipment failed: %s", e)
    return issued_names


async def reclaim_equipment(char: dict, org_code: str, db,
                             session=None) -> int:
    """
    Remove all issued equipment for this org from character inventory and
    mark as reclaimed in DB. Returns count reclaimed.
    Graceful-drop: never raises.
    """
    count = 0
    try:
        org = await db.get_organization(org_code)
        if not org:
            return 0

        issued = await db.get_issued_equipment(char["id"], org["id"])
        for item in issued:
            removed = await db.remove_from_inventory(char["id"], item["item_key"])
            if removed:
                count += 1

        if issued:
            await db.reclaim_equipment(char["id"], org["id"])

        if count and session:
            await session.send_line(
                f"\n  \033[2m[{org['name']}] "
                f"Faction-issued equipment reclaimed ({count} item(s)).\033[0m"
            )
    except Exception as e:
        log.exception("[orgs] reclaim_equipment failed: %s", e)
    return count


# ── Faction specialization (Imperial / Republic) ──────────────────────────────

# Per-faction config for the specialization prompt: header label,
# choice index → spec_key, and per-spec display label.
#
# This config drives the generic `prompt_specialization` and
# `complete_specialization` helpers below. The legacy
# `prompt_imperial_specialization` / `complete_imperial_specialization`
# functions are kept as thin shims for byte-equivalence with any
# external caller that imports them by name (notably
# `parser/faction_commands.py::SpecializeCommand`).
_SPEC_CONFIG_BY_FACTION = {
    "empire": {
        "header_color": "\033[1;34m",
        "header_label": "[IMPERIAL ONBOARDING]",
        "menu_lines": [
            "  \033[1;33m1\033[0m  Stormtrooper    — Ground combat. E-11 rifle, armor.",
            "  \033[1;33m2\033[0m  TIE Pilot       — Space combat. Flight suit, TIE assignment at rank 4.",
            "  \033[1;33m3\033[0m  Naval Officer   — Command/support. Uniform, datapad, crew bonuses.",
            "  \033[1;33m4\033[0m  Intelligence    — Stealth/slicing. Civilian cover, slicing kit.",
        ],
        "spec_map": {
            1: "stormtrooper",
            2: "tie_pilot",
            3: "naval_officer",
            4: "intelligence",
        },
        "spec_labels": {
            "stormtrooper":  "Stormtrooper",
            "tie_pilot":     "TIE Pilot",
            "naval_officer": "Naval Officer",
            "intelligence":  "Intelligence Agent",
        },
    },
    # ── B.1.b.2 (Apr 29 2026) — Republic specialization config ───────
    # Mirrors the Imperial four-choice prompt with CW-flavored copy.
    # Republic blue header instead of Imperial blue (same color code
    # since both are state authorities).
    "republic": {
        "header_color": "\033[1;34m",
        "header_label": "[REPUBLIC ONBOARDING]",
        "menu_lines": [
            "  \033[1;33m1\033[0m  Clone Trooper        — Ground combat. DC-15A rifle, combat plate.",
            "  \033[1;33m2\033[0m  Clone Pilot          — Space combat. Republic flight suit.",
            "  \033[1;33m3\033[0m  Clone Officer        — Command/support. Officer's uniform, datapad.",
            "  \033[1;33m4\033[0m  Republic Intelligence — Stealth/slicing. Civilian cover, slicing kit.",
        ],
        "spec_map": {
            1: "clone_trooper",
            2: "clone_pilot",
            3: "clone_officer",
            4: "republic_intelligence",
        },
        "spec_labels": {
            "clone_trooper":         "Clone Trooper",
            "clone_pilot":           "Clone Pilot",
            "clone_officer":         "Clone Officer",
            "republic_intelligence": "Republic Intelligence Agent",
        },
    },
}


def faction_has_specialization(faction_code: str) -> bool:
    """True iff this faction has a specialization-prompt flow on join.

    Used by `join_faction` to decide whether to fire a prompt after
    rank-0 equipment issuance, and by `SpecializeCommand` to gate
    the `specialize` parser command.
    """
    return faction_code in _SPEC_CONFIG_BY_FACTION


def get_specialization_config(faction_code: str) -> dict | None:
    """Return the spec config for a faction, or None if not configured."""
    return _SPEC_CONFIG_BY_FACTION.get(faction_code)


async def prompt_specialization(char: dict, db, session,
                                faction_code: str) -> bool:
    """Generic specialization prompt for any faction with a spec config.

    Sends the per-faction onboarding menu to the player's session, sets
    `attributes.faction.specialization_pending = True`, and persists.
    Returns True if the prompt was sent.

    Falls through to False (no prompt) for factions without a spec
    config — safe to call unconditionally from `join_faction`.
    """
    if not session:
        return False
    cfg = _SPEC_CONFIG_BY_FACTION.get(faction_code)
    if not cfg:
        return False
    try:
        header = f"\n  {cfg['header_color']}{cfg['header_label']}\033[0m " \
                 f"Select your specialization:"
        menu = "\n".join(cfg["menu_lines"])
        footer = "\n  Type \033[1;33mspecialize <number>\033[0m to select."
        await session.send_line(f"{header}\n{menu}{footer}")

        a = _get_attrs(char)
        a.setdefault("faction", {})["specialization_pending"] = True
        _set_attrs(char, a)
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))
        return True
    except Exception as e:
        log.exception("[orgs] %s specialization prompt failed: %s",
                      faction_code, e)
        return False


async def complete_specialization(char: dict, db, choice: int,
                                   faction_code: str,
                                   session=None) -> tuple:
    """Generic specialization completion for any faction with a spec config.

    Looks up the per-faction spec_map and equipment table, stores the
    selection in attributes + org membership, and issues the spec gear.
    Returns (success, message).

    Returns (False, message) for invalid choice, no-pending-spec, or
    unconfigured faction.
    """
    cfg = _SPEC_CONFIG_BY_FACTION.get(faction_code)
    if not cfg:
        return False, f"Faction {faction_code!r} has no specialization."

    spec_map = cfg["spec_map"]
    spec_labels = cfg["spec_labels"]

    if choice not in spec_map:
        valid = "/".join(str(k) for k in sorted(spec_map.keys()))
        return False, f"Invalid choice. Enter {valid}."

    a = _get_attrs(char)
    if not a.get("faction", {}).get("specialization_pending"):
        return False, "No pending specialization."

    spec_key = spec_map[choice]
    a.setdefault("faction", {})["specialization"] = spec_key
    a["faction"].pop("specialization_pending", None)
    _set_attrs(char, a)
    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

    # Update the org_membership specialization field
    org = await db.get_organization(faction_code)
    if org:
        await db.update_membership(char["id"], org["id"],
                                   specialization=spec_key)

    # Issue spec equipment via the per-faction dispatch table
    spec_table = SPEC_EQUIPMENT_BY_FACTION.get(faction_code, {})
    spec_items = spec_table.get(spec_key, [])
    await issue_equipment(char, faction_code, db, spec_items, session=session)

    label = spec_labels.get(spec_key, spec_key.title())
    return True, (
        f"Specialization set: \033[1;37m{label}\033[0m. "
        f"Equipment issued. Report to your commanding officer."
    )


# ── Imperial specialization (legacy named API — preserved for callers) ────────
# These two functions are now thin shims over the generic helpers above.
# Their signatures and behavior on the Imperial path are byte-equivalent
# to pre-B.1.b.2 — `parser/faction_commands.py::SpecializeCommand` and
# any other caller that imports by name continues to work unchanged.

async def prompt_imperial_specialization(char: dict, db, session) -> bool:
    """
    Present Imperial specialization choice to a newly-joined Imperial character.
    Stores selection in attributes and issues spec equipment.
    Returns True if selection was made.

    (Thin shim; delegates to `prompt_specialization(..., "empire")`.)
    """
    return await prompt_specialization(char, db, session, "empire")


async def complete_imperial_specialization(char: dict, db,
                                            choice: int, session=None) -> tuple:
    """
    Process specialization choice (1-4). Issues equipment, stores in attributes.
    Returns (success, message).

    (Thin shim; delegates to `complete_specialization(..., "empire", ...)`.)
    """
    return await complete_specialization(char, db, choice,
                                          faction_code="empire",
                                          session=session)


# ── B.1.b.2 (Apr 29 2026) — Republic specialization (named API) ───────────────
# Symmetric named functions for the Republic faction. New callers can
# either import these by name or use the generic helpers above with
# `faction_code="republic"`. Both paths land in the same generic
# implementation.

async def prompt_republic_specialization(char: dict, db, session) -> bool:
    """
    Present Republic specialization choice to a newly-joined Republic character.
    Stores selection in attributes and issues spec equipment.
    Returns True if selection was made.

    (Thin shim; delegates to `prompt_specialization(..., "republic")`.)
    """
    return await prompt_specialization(char, db, session, "republic")


async def complete_republic_specialization(char: dict, db,
                                            choice: int, session=None) -> tuple:
    """
    Process Republic specialization choice (1-4). Issues equipment,
    stores in attributes. Returns (success, message).

    (Thin shim; delegates to `complete_specialization(..., "republic", ...)`.)
    """
    return await complete_specialization(char, db, choice,
                                          faction_code="republic",
                                          session=session)


# ── Seed loader ───────────────────────────────────────────────────────────────

async def seed_organizations(db, era: str | None = None) -> None:
    """Load organizations.yaml into DB. Safe to call multiple times.

    Args:
        db: Database handle.
        era: Optional era code. If None, resolves from
             `engine.era_state.get_active_era()` (defaults to "gcw" when
             no Config is registered).

    Path resolution:
        - era="gcw"  -> data/organizations.yaml (legacy top-level path,
                       byte-equivalent to pre-B.4 production)
        - other      -> data/worlds/<era>/organizations.yaml

    B.4 (Apr 28 2026): added `era` kwarg + per-era path resolution. Before
    this change, seed_organizations ignored era entirely and always read
    `data/organizations.yaml` (GCW). When the F.6a.6 dev flag flipped era
    to clone_wars, this seeded GCW orgs into a CW DB, which is what made
    `+faction` crash and Tatooine look unchanged.
    """
    import yaml
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()

    project_root = os.path.dirname(os.path.dirname(__file__))
    if era == "gcw":
        # Legacy GCW path. Top-level data/organizations.yaml IS the GCW
        # source of truth — there is no data/worlds/gcw/organizations.yaml.
        yaml_path = os.path.join(project_root, "data", "organizations.yaml")
    else:
        yaml_path = os.path.join(project_root, "data", "worlds", era,
                                 "organizations.yaml")

    if not os.path.exists(yaml_path):
        log.warning("[orgs] organizations.yaml not found at %s — skipping seed (era=%s)",
                    yaml_path, era)
        return

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for faction in data.get("factions", []):
        props = json.dumps(faction.get("properties", {}))
        org_id = await db.create_organization(
            code=faction["code"],
            name=faction["name"],
            org_type="faction",
            director_managed=faction.get("director_managed", True),
            properties=props,
        )
        for rank in faction.get("ranks", []):
            await db.create_org_rank(
                org_id=org_id,
                rank_level=rank["level"],
                title=rank["title"],
                min_rep=rank.get("min_rep", 0),
                permissions=json.dumps(rank.get("permissions", [])),
                equipment=json.dumps(rank.get("equipment", [])),
            )

    for guild in data.get("guilds", []):
        props = guild.get("properties", {})
        if "dues_weekly" in guild:
            props["dues_weekly"] = guild["dues_weekly"]
        await db.create_organization(
            code=guild["code"],
            name=guild["name"],
            org_type="guild",
            director_managed=False,
            properties=json.dumps(props),
        )

    log.info("[orgs] Organizations seeded from %s (era=%s)", yaml_path, era)


# ── Join / leave ─────────────────────────────────────────────────────────────

async def join_faction(char: dict, faction_code: str, db,
                        session=None) -> tuple[bool, str]:
    """
    Join a faction. Issues rank-0 equipment. Prompts Imperial specialization.
    Returns (success, message).
    """
    a = _get_attrs(char)
    last_switch = a.get("faction_switch_ts", 0)
    now = time.time()
    if (now - last_switch < FACTION_SWITCH_COOLDOWN
            and char.get("faction_id", "independent") != "independent"):
        days_left = int((FACTION_SWITCH_COOLDOWN - (now - last_switch)) / 86400) + 1
        return False, f"You must wait {days_left} more day(s) before switching factions."

    org = await db.get_organization(faction_code)
    if not org or org["org_type"] != "faction":
        return False, f"Unknown faction: '{faction_code}'."

    if faction_code == "independent":
        return False, "Independent is the default — just leave your current faction."

    existing = await db.get_membership(char["id"], org["id"])
    if existing:
        return False, f"You're already a member of {org['name']}."

    # ── Same-faction alt prevention (S44) ────────────────────────────────
    # An account may not have two characters in the same faction. Look up
    # siblings via account_id; if any sibling other than the one trying to
    # join is already in this faction, refuse. The check is gated on
    # account_id being truthy (mocked / test characters may omit it) and
    # wrapped in try/except so a missing get_characters method or transient
    # DB error never blocks a legitimate join — better to allow than to
    # lock people out of their own factions.
    account_id = char.get("account_id")
    if account_id:
        try:
            siblings = await db.get_characters(account_id)
            for sibling in (siblings or []):
                if sibling["id"] == char["id"]:
                    continue  # skip self
                if sibling.get("faction_id") == faction_code:
                    return False, (
                        f"Two alts may not share the same faction. Your "
                        f"alternate character {sibling.get('name', '?')} "
                        f"is already in {org['name']}. Have one of them "
                        f"leave first, or pick a different faction."
                    )
        except Exception:
            log.warning("[orgs] same-faction alt check failed", exc_info=True)

    # Leave current faction (reclaim equipment)
    current = char.get("faction_id", "independent")
    if current and current != "independent":
        current_org = await db.get_organization(current)
        if current_org:
            await reclaim_equipment(char, current, db, session=session)
            await db.leave_organization(char["id"], current_org["id"])
            await db.log_faction_action(char["id"], current_org["id"], "leave",
                                         f"Left to join {org['name']}")
            # Defection rep penalty to old faction
            try:
                await adjust_rep(char, current, db,
                                 action_key="defection",
                                 reason=f"Left {current_org['name']}")
            except Exception:
                log.warning("[orgs] defection rep failed", exc_info=True)

    # Join
    await db.join_organization(char["id"], org["id"])
    char["faction_id"] = faction_code
    await db.save_character(char["id"], faction_id=faction_code)

    # Record cooldown
    a["faction_switch_ts"] = now
    _set_attrs(char, a)
    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

    # Log
    await db.log_faction_action(char["id"], org["id"], "join")

    # Issue rank-0 equipment
    rank0_items = RANK_0_EQUIPMENT.get(faction_code, [])
    await issue_equipment(char, faction_code, db, rank0_items, session=session)

    # Specialization prompt — fires for any faction with a spec config.
    # Currently: "empire" (legacy) and "republic" (B.1.b.2). The generic
    # `prompt_specialization` is a no-op for factions without a config,
    # so this call is safe regardless of faction.
    if faction_has_specialization(faction_code):
        await prompt_specialization(char, db, session, faction_code)

    # Clear any stored faction_intent
    a2 = _get_attrs(char)
    if a2.get("faction_intent"):
        a2.pop("faction_intent", None)
        a2.pop("faction_intent_set_at", None)
        _set_attrs(char, a2)
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

    # Narrative hook
    try:
        from engine.narrative import log_action, ActionType as NT
        await log_action(db, char["id"], NT.FACTION_JOIN, f"Joined {org['name']}")
    except Exception:
        log.warning("join_faction: unhandled exception", exc_info=True)
        pass

    # Housing hook: assign faction quarters if qualifying rank
    try:
        from engine.housing import assign_faction_quarters
        mem = await db.get_membership(char["id"], org["id"])
        rank_level = mem["rank_level"] if mem else 0
        await assign_faction_quarters(db, char, faction_code, rank_level,
                                       session=session)
    except Exception as e:
        log.warning("[organizations] housing hook on join error: %s", e)

    return True, f"You have joined the \033[1;37m{org['name']}\033[0m."


async def leave_faction(char: dict, db, session=None) -> tuple[bool, str]:
    """Leave current faction. Reclaims issued equipment."""
    current = char.get("faction_id", "independent")
    if not current or current == "independent":
        return False, "You're not in any faction."

    org = await db.get_organization(current)
    if org:
        await reclaim_equipment(char, current, db, session=session)
        await db.leave_organization(char["id"], org["id"])
        await db.log_faction_action(char["id"], org["id"], "leave",
                                     "Voluntary departure")

    a = _get_attrs(char)
    a["faction_switch_ts"] = time.time()
    _set_attrs(char, a)

    char["faction_id"] = "independent"
    await db.save_character(char["id"], faction_id="independent",
                             attributes=char.get("attributes", "{}"))

    # Defection rep penalty
    try:
        await adjust_rep(char, current, db,
                         action_key="defection",
                         reason=f"Left {org['name']}" if org else "Left faction")
    except Exception:
        log.warning("[orgs] defection rep on leave failed", exc_info=True)

    # Narrative hook
    try:
        from engine.narrative import log_action, ActionType as NT
        await log_action(db, char["id"], NT.FACTION_LEAVE,
                         f"Left {org['name']}" if org else "Left faction")
    except Exception:
        log.warning("leave_faction: unhandled exception", exc_info=True)
        pass

    # Housing hook: revoke faction quarters
    try:
        from engine.housing import revoke_faction_quarters
        await revoke_faction_quarters(db, char, current, session=session)
    except Exception as e:
        log.warning("[organizations] housing hook on leave error: %s", e)

    return True, (
        f"You have left {org['name'] if org else 'the faction'}. "
        "You are now \033[2mIndependent\033[0m."
    )


# ── B.5: Organization-axis legacy rewicker (Apr 29 2026) ──────────────────────
#
# Per architecture v38 §19.7 (B.5: PC `faction_intent` migration). Brian's
# decision: auto-rewicker on login, with a clear in-game notification.
#
# When a PC's stored `faction_id` (canonical column) or
# `attributes.faction_intent` (tutorial-stored intent) references a faction
# code from a prior era's organizations.yaml that doesn't exist in the
# currently-seeded DB, we translate the legacy code to its current-era
# equivalent using the `legacy_rewicker.factions` map at the top of
# `data/worlds/<era>/organizations.yaml`.
#
# This is a SEPARATE namespace from the director-axis rewicker in
# `data/worlds/<era>/director_config.yaml::rewicker.faction_codes`. The
# director rewicker maps director-axis codes (imperial/rebel/criminal/
# independent) used by zone-tone calculations; this one maps organization
# codes (empire/rebel/hutt/bh_guild) used by chargen, faction membership,
# and faction_intent. The two namespaces happened to share `rebel` and
# `independent` but are otherwise distinct — keeping them separate
# prevents zone-tone changes from accidentally rewickering org codes.


async def get_org_rewicker_map(db, era: str | None = None) -> dict:
    """
    Load the organization-axis legacy rewicker map for the active era.

    Returns a dict mapping legacy faction codes -> current era codes.
    For GCW (or any era without a `legacy_rewicker` section in its
    organizations.yaml), returns an empty dict (no-op semantics).

    Never raises. On any I/O or parse error, logs a warning and returns
    an empty dict so the caller can proceed safely.
    """
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()

    # GCW has no rewicker — it IS the legacy era. Returning {} means
    # apply_org_rewicker becomes a no-op when era="gcw", preserving
    # byte-equivalence for production.
    if era == "gcw":
        return {}

    try:
        import yaml
        project_root = os.path.dirname(os.path.dirname(__file__))
        yaml_path = os.path.join(project_root, "data", "worlds", era,
                                 "organizations.yaml")
        if not os.path.exists(yaml_path):
            return {}
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        rewicker = data.get("legacy_rewicker", {}) or {}
        factions = rewicker.get("factions", {}) or {}
        # Sanity: must be a flat str->str map.
        if not isinstance(factions, dict):
            log.warning(
                "[orgs] legacy_rewicker.factions for era=%s is not a dict "
                "(got %s); ignoring.",
                era, type(factions).__name__,
            )
            return {}
        return {str(k): str(v) for k, v in factions.items()}
    except Exception as e:
        log.warning("[orgs] get_org_rewicker_map(era=%s) failed: %s",
                    era, e)
        return {}


async def apply_org_rewicker(char: dict, db, era: str | None = None,
                              session=None) -> dict:
    """
    Migrate a character's stored faction codes from a prior era to the
    current era. Called on login.

    Resolution order:
      1. If `char.faction_id` is set, non-`independent`, and DOES NOT
         exist in the current DB BUT DOES have a rewicker target, swap
         it (and persist via db.save_character).
      2. If `attributes.faction_intent` is set and DOES NOT exist in
         the current DB BUT DOES have a rewicker target, swap it (and
         persist).
      3. Else no-op.

    Returns a summary dict:
      {
        "migrated": bool,
        "faction_id_before": str | None,
        "faction_id_after": str | None,
        "intent_before": str | None,
        "intent_after": str | None,
        "era": str,
      }

    `migrated=True` when at least one of faction_id / faction_intent
    was rewickered. Caller may use this to display a notification.

    Graceful-drop: never raises. On any DB error, logs a warning and
    returns `{"migrated": False, ...}`.

    INVARIANTS:
      - Never rewickers an already-current code (e.g., `republic` in CW
        DB stays `republic`).
      - Never rewickers a code that has no rewicker target (e.g., a
        random unknown code like `'nonexistent'` is left as-is to
        surface via B.6's stale-record advisory).
      - Never crosses the GCW→GCW or CW→CW boundary (the rewicker map
        is empty on GCW, so no-op there).
      - The migration is a single atomic update via save_character;
        if it fails mid-way, the rewicker_map's empty fallback keeps
        the character in a consistent state.
    """
    summary = {
        "migrated": False,
        "faction_id_before": None,
        "faction_id_after": None,
        "intent_before": None,
        "intent_after": None,
        "era": era,
    }

    try:
        if era is None:
            from engine.era_state import get_active_era
            era = get_active_era()
            summary["era"] = era

        rewicker_map = await get_org_rewicker_map(db, era=era)
        if not rewicker_map:
            return summary  # No-op for GCW or eras without a map

        migrated_anything = False

        # ── Step 1: faction_id ───────────────────────────────────────
        fid = char.get("faction_id") or "independent"
        summary["faction_id_before"] = fid

        if fid and fid != "independent":
            current_org = await db.get_organization(fid)
            if not current_org and fid in rewicker_map:
                target = rewicker_map[fid]
                if target == fid:
                    # Identity passthrough (e.g., "independent": "independent");
                    # don't count as a migration.
                    summary["faction_id_after"] = fid
                else:
                    # Verify the target exists in this era's DB before
                    # rewickering. If not (e.g., misconfigured map), leave
                    # the stale code for B.6 to surface.
                    target_org = await db.get_organization(target)
                    if target_org:
                        char["faction_id"] = target
                        await db.save_character(char["id"], faction_id=target)
                        summary["faction_id_after"] = target
                        migrated_anything = True
                        log.info(
                            "[orgs] B.5 rewicker: char %s faction_id "
                            "%r -> %r (era=%s)",
                            char.get("id"), fid, target, era,
                        )
                    else:
                        # Map points at a non-existent target; leave as-is.
                        summary["faction_id_after"] = fid
                        log.warning(
                            "[orgs] B.5 rewicker: target %r for legacy "
                            "%r not in DB (era=%s); leaving stale.",
                            target, fid, era,
                        )
            else:
                summary["faction_id_after"] = fid
        else:
            summary["faction_id_after"] = fid

        # ── Step 2: faction_intent ───────────────────────────────────
        a = _get_attrs(char)
        intent = a.get("faction_intent")
        summary["intent_before"] = intent

        if intent:
            intent_org = await db.get_organization(intent)
            if not intent_org and intent in rewicker_map:
                target = rewicker_map[intent]
                if target == intent:
                    summary["intent_after"] = intent
                else:
                    target_org = await db.get_organization(target)
                    if target_org:
                        a["faction_intent"] = target
                        _set_attrs(char, a)
                        await db.save_character(
                            char["id"],
                            attributes=char.get("attributes", "{}"),
                        )
                        summary["intent_after"] = target
                        migrated_anything = True
                        log.info(
                            "[orgs] B.5 rewicker: char %s faction_intent "
                            "%r -> %r (era=%s)",
                            char.get("id"), intent, target, era,
                        )
                    else:
                        summary["intent_after"] = intent
            else:
                summary["intent_after"] = intent
        else:
            summary["intent_after"] = intent

        summary["migrated"] = migrated_anything

        # ── Notification ────────────────────────────────────────────
        if migrated_anything and session:
            try:
                lines = [
                    "",
                    "  \033[1;35m[FACTION RECORD UPDATED]\033[0m",
                    "  \033[2mYour faction record was carried over from a prior",
                    "  era and has been translated to its current equivalent.\033[0m",
                ]
                if summary["faction_id_before"] != summary["faction_id_after"]:
                    lines.append(
                        f"    Membership: \033[2m{summary['faction_id_before']}"
                        f"\033[0m -> "
                        f"\033[1;37m{summary['faction_id_after']}\033[0m"
                    )
                if (summary["intent_before"]
                        and summary["intent_before"] != summary["intent_after"]):
                    lines.append(
                        f"    Intent:     \033[2m{summary['intent_before']}"
                        f"\033[0m -> "
                        f"\033[1;37m{summary['intent_after']}\033[0m"
                    )
                lines.append(
                    "  \033[2mUse 'faction' to view your current standing.\033[0m"
                )
                for line in lines:
                    await session.send_line(line)
            except Exception:
                # Notification is best-effort; never block on send_line failures.
                log.debug("[orgs] B.5 rewicker notification failed",
                          exc_info=True)

        return summary

    except Exception as e:
        log.exception("[orgs] apply_org_rewicker failed: %s", e)
        return summary


# ── faction_intent migration ──────────────────────────────────────────────────

async def faction_intent_migration(char: dict, db, session=None):
    """
    Call on login. If attributes contains a faction_intent set by the tutorial
    profession chain system, and the character is still Independent, auto-join
    that faction.

    Graceful-drop: never raises or blocks login.
    """
    try:
        if char.get("faction_id", "independent") != "independent":
            return  # Already in a faction

        a = _get_attrs(char)
        intent = a.get("faction_intent")
        if not intent:
            return

        org = await db.get_organization(intent)
        if not org or org["org_type"] != "faction":
            return

        # Auto-join with a brief notification
        if session:
            await session.send_line(
                f"\n  \033[1;35m[FACTION]\033[0m "
                f"Your previous commitment to the \033[1;37m{org['name']}\033[0m "
                "has been recorded. Joining now..."
            )

        ok, msg = await join_faction(char, intent, db, session=session)
        if ok and session:
            await session.send_line(f"  {msg}")

    except Exception as e:
        log.exception("[orgs] faction_intent_migration failed: %s", e)


# ── Guild join / leave ────────────────────────────────────────────────────────

async def join_guild(char: dict, guild_code: str, db) -> tuple[bool, str]:
    """Join a guild. Max 3 guilds per character."""
    org = await db.get_organization(guild_code)
    if not org or org["org_type"] != "guild":
        return False, f"Unknown guild: '{guild_code}'."

    existing = await db.get_membership(char["id"], org["id"])
    if existing:
        return False, f"You're already a member of {org['name']}."

    memberships = await db.get_memberships_for_char(char["id"])
    guild_count = sum(1 for m in memberships if m.get("org_type") == "guild")
    if guild_count >= MAX_GUILD_MEMBERSHIPS:
        return False, f"You're already in {MAX_GUILD_MEMBERSHIPS} guilds (maximum)."

    await db.join_organization(char["id"], org["id"])
    await db.log_faction_action(char["id"], org["id"], "join")
    return True, f"You have joined the \033[1;37m{org['name']}\033[0m."


async def leave_guild(char: dict, guild_code: str, db) -> tuple[bool, str]:
    """Leave a guild."""
    org = await db.get_organization(guild_code)
    if not org or org["org_type"] != "guild":
        return False, f"Unknown guild: '{guild_code}'."

    existing = await db.get_membership(char["id"], org["id"])
    if not existing:
        return False, f"You're not a member of {org['name']}."

    await db.leave_organization(char["id"], org["id"])
    await db.log_faction_action(char["id"], org["id"], "leave", "Voluntary departure")
    return True, f"You have left the {org['name']}."


# ── Promotion ─────────────────────────────────────────────────────────────────

async def promote(char: dict, org_code: str, db,
                   promoter_char: dict = None) -> tuple[bool, str]:
    """Promote a character one rank. Issues new rank's equipment."""
    org = await db.get_organization(org_code)
    if not org:
        return False, f"Unknown organization: '{org_code}'."

    mem = await db.get_membership(char["id"], org["id"])
    if not mem:
        return False, f"{char['name']} is not a member of {org['name']}."

    ranks = await db.get_org_ranks(org["id"])
    current_level = mem["rank_level"]
    next_level = current_level + 1
    next_rank = next((r for r in ranks if r["rank_level"] == next_level), None)

    if not next_rank:
        return False, f"{char['name']} is already at maximum rank."

    if mem["rep_score"] < next_rank["min_rep"]:
        return False, (
            f"{char['name']} needs {next_rank['min_rep']} rep to reach "
            f"{next_rank['title']} (current: {mem['rep_score']})."
        )

    await db.update_membership(char["id"], org["id"], rank_level=next_level)

    details = f"Promoted to {next_rank['title']}"
    if promoter_char:
        details += f" by {promoter_char['name']}"
    await db.log_faction_action(char["id"], org["id"], "promote", details)

    # Issue rank-specific equipment (from YAML equipment field)
    try:
        new_equip = json.loads(next_rank.get("equipment", "[]"))
        # ── B.1.f (Apr 29 2026) — generalize spec-faction gate ──────
        # Pre-drop: hardcoded `org_code == "empire"` literal. Post-drop:
        # `faction_has_specialization(org_code)` so the rank-1 spec
        # re-prompt fires for any spec-eligible faction (Empire in GCW,
        # Republic in CW). GCW Empire path is byte-equivalent because
        # `faction_has_specialization("empire")` returns True.
        if new_equip and not faction_has_specialization(org_code):
            await issue_equipment(char, org_code, db, new_equip)
        elif faction_has_specialization(org_code) and next_level == 1:
            # Rank 1 spec-eligible faction: re-prompt specialization
            # if not yet chosen. Handled separately via SpecializeCommand.
            a = _get_attrs(char)
            if not a.get("faction", {}).get("specialization"):
                pass  # Handled separately via SpecializeCommand
    except Exception:
        log.warning("promote: unhandled exception", exc_info=True)
        pass

    # Housing hook: assign/upgrade faction quarters on promotion
    try:
        from engine.housing import check_faction_quarters_on_rank_change
        await check_faction_quarters_on_rank_change(
            db, char, org_code, next_level, session=None)
    except Exception as e:
        log.warning("[organizations] housing hook on promote error: %s", e)

    return True, (
        f"{char['name']} has been promoted to "
        f"\033[1;37m{next_rank['title']}\033[0m in {org['name']}."
    )


# ── Auto-promotion on rep threshold ──────────────────────────────────────────

async def check_auto_promote(char: dict, faction_code: str, db,
                              session=None) -> bool:
    """
    Check if character qualifies for automatic rank promotion based on rep.
    Loops to handle multi-rank jumps. Returns True if any promotion occurred.
    """
    promoted = False
    try:
        org = await db.get_organization(faction_code)
        if not org:
            return False

        for _ in range(10):  # Safety cap: max 10 promotions per call
            mem = await db.get_membership(char["id"], org["id"])
            if not mem:
                break

            ranks = await db.get_org_ranks(org["id"])
            current_level = mem["rank_level"]
            next_level = current_level + 1
            next_rank = next((r for r in ranks if r["rank_level"] == next_level), None)

            if not next_rank:
                break  # Already max rank

            if mem["rep_score"] < next_rank["min_rep"]:
                break  # Not enough rep

            # Auto-promote
            ok, msg = await promote(char, faction_code, db)
            if not ok:
                break

            promoted = True
            if session:
                await session.send_line(
                    f"\n  \033[1;32m★ RANK UP! ★\033[0m {msg}"
                )
                try:
                    await session.send_json("rank_up", {
                        "faction": faction_code,
                        "new_rank": next_rank["title"],
                        "new_level": next_level,
                    })
                except Exception:
                    pass  # Web event is optional

    except Exception as e:
        log.warning("[orgs] check_auto_promote failed: %s", e)
    return promoted


# ── Rep history ───────────────────────────────────────────────────────────────

def _log_rep_change(char: dict, faction_code: str, delta: int, reason: str):
    """Append a rep change entry to character attributes. Capped at 10 per faction."""
    a = _get_attrs(char)
    history = a.get("rep_history", {})
    if not isinstance(history, dict):
        history = {}

    entries = history.get(faction_code, [])
    if not isinstance(entries, list):
        entries = []

    entries.insert(0, {
        "delta": delta,
        "reason": reason or "Unknown",
        "ts": int(time.time()),
    })
    entries = entries[:10]  # Keep last 10

    history[faction_code] = entries
    a["rep_history"] = history
    _set_attrs(char, a)


# ── Rep adjustment (REFACTORED v30) ──────────────────────────────────────────

async def adjust_rep(char: dict, faction_code: str, db,
                      action_key: str = None,
                      delta: int = None,
                      reason: str = None,
                      session=None) -> int:
    """
    Adjust a character's rep score for a faction.

    Can be called with action_key (looks up delta from REP_GAINS) or
    with an explicit delta override. Returns new rep score (or 0 on error).

    Features:
    - Rep history logging (last 10 per faction in attributes)
    - Cross-faction penalties (Empire <-> Rebel at -50%)
    - Auto-promotion check for members
    - Session notification if session provided
    - Non-member rep stored in attributes.faction_rep (-100..+100)
    """
    try:
        # Determine delta
        if delta is None:
            if action_key is None:
                return 0
            delta = REP_GAINS.get(action_key, 0)
            if delta == 0:
                return 0

        if not reason:
            reason = action_key or "rep_change"

        org = await db.get_organization(faction_code)
        if not org:
            return 0

        mem = await db.get_membership(char["id"], org["id"])
        if not mem:
            # Non-member: update attributes-based faction_rep (-100..+100)
            a = _get_attrs(char)
            rep_table = a.get("faction_rep", {})
            old_rep = rep_table.get(faction_code, 0)
            new_rep = max(-100, min(100, old_rep + delta))
            rep_table[faction_code] = new_rep
            a["faction_rep"] = rep_table
            _log_rep_change(char, faction_code, delta, reason)
            _set_attrs(char, a)
            await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

            # Notification
            if session and delta != 0:
                _tier_key, tier_name, tier_color = get_rep_tier(new_rep)
                sign = "+" if delta > 0 else ""
                await session.send_line(
                    f"  \033[2m[{org['name']}]\033[0m Rep {sign}{delta} "
                    f"({tier_color}{tier_name}\033[0m)"
                )

            return new_rep

        # Member: update via DB (0..100 range)
        current_rep = mem.get("rep_score", 0)
        new_rep = max(0, min(100, current_rep + delta))
        await db.update_membership(char["id"], org["id"], rep_score=new_rep)

        # Log in attributes rep history
        _log_rep_change(char, faction_code, delta, reason)
        a = _get_attrs(char)
        _set_attrs(char, a)
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

        # Notification
        if session and delta != 0:
            _tier_key, tier_name, tier_color = get_rep_tier(new_rep)
            sign = "+" if delta > 0 else ""
            await session.send_line(
                f"  \033[2m[{org['name']}]\033[0m Rep {sign}{delta} → "
                f"{new_rep}/100 ({tier_color}{tier_name}\033[0m)"
            )
            try:
                await session.send_json("rep_change", {
                    "faction": faction_code,
                    "delta": delta,
                    "new_rep": new_rep,
                    "tier": _tier_key,
                    "reason": reason,
                })
            except Exception:
                pass  # Web event is optional

        # Auto-promotion check (only on rep increase for members)
        if delta > 0:
            await check_auto_promote(char, faction_code, db, session=session)

        # Cross-faction penalties
        penalties = CROSS_FACTION_PENALTIES.get(faction_code, {})
        if delta > 0 and penalties:
            for target_faction, ratio in penalties.items():
                cross_delta = int(delta * ratio)
                if cross_delta != 0:
                    # Recursive call but with no further cross-faction
                    # (target factions don't have penalties pointing back)
                    await adjust_rep(char, target_faction, db,
                                     delta=cross_delta,
                                     reason=f"Cross-faction: {faction_code} gain",
                                     session=session)

        return new_rep

    except Exception as e:
        log.exception("[orgs] adjust_rep failed: %s", e)
        return 0


async def faction_payroll_tick(db) -> int:
    """
    Pay weekly stipends to eligible faction members.
    Should be called once per game-day from the tick loop.
    Returns total credits disbursed.
    """
    total_paid = 0
    try:
        orgs = await db.get_all_organizations()
        for org in orgs:
            if org["org_type"] != "faction":
                continue

            org_code = org["code"]
            treasury = org.get("treasury", 0)
            if treasury <= 0:
                continue

            org_paid = 0  # Track per-org disbursement for treasury debit
            members = await db.get_org_members(org["id"])
            for mem in members:
                if mem.get("standing", "good") not in ("good",):
                    continue  # Probation/expelled get no stipend

                rank_level = mem.get("rank_level", 0)
                stipend = STIPEND_TABLE.get((org_code, rank_level), 0)
                if stipend <= 0:
                    continue
                if treasury - org_paid < stipend:
                    break  # Treasury depleted

                # Fetch the character's ACTUAL current credits before updating
                char_row = await db.get_character(mem["char_id"])
                if not char_row:
                    continue
                current_credits = char_row.get("credits", 0)

                # Pay the stipend
                await db.save_character(mem["char_id"],
                                         credits=current_credits + stipend)
                org_paid += stipend
                total_paid += stipend

                # Log
                try:
                    await db.log_faction_action(
                        mem["char_id"], org["id"], "stipend",
                        f"Weekly stipend: {stipend}cr"
                    )
                except Exception:
                    log.warning("faction_payroll_tick: unhandled exception", exc_info=True)
                    pass

            # Update treasury — method is adjust_org_treasury
            if org_paid > 0:
                try:
                    await db.adjust_org_treasury(org["id"], -org_paid)
                except Exception as _te:
                    log.warning("[orgs] Treasury debit failed for %s: %s",
                                org_code, _te)

    except Exception as e:
        log.exception("[orgs] faction_payroll_tick failed: %s", e)
    return total_paid


# ── Guild CP bonus ────────────────────────────────────────────────────────────

async def get_guild_cp_multiplier(char: dict, db) -> float:
    """Returns CP cost multiplier. Guild members get 20% off. Flat rate."""
    try:
        memberships = await db.get_memberships_for_char(char["id"])
        for m in memberships:
            if (m.get("org_type") == "guild"
                    and m.get("standing", "good") != "expelled"):
                return 1.0 - GUILD_CP_DISCOUNT
    except Exception:
        log.warning("get_guild_cp_multiplier: unhandled exception", exc_info=True)
        pass
    return 1.0


# ── Reputation display ────────────────────────────────────────────────────────

async def format_reputation_overview(char: dict, db) -> str:
    """
    Format the +reputation overview showing all faction standings.
    Shows member faction with rank, and non-member factions with attribute-based rep.
    """
    lines = [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;37mFACTION REPUTATION\033[0m",
        "\033[1;36m==========================================\033[0m",
    ]

    orgs = await db.get_all_organizations()
    factions = [o for o in orgs if o["org_type"] == "faction" and o["code"] != "independent"]
    memberships = await db.get_memberships_for_char(char["id"])
    mem_by_org = {m["org_id"]: m for m in memberships if m.get("org_type") == "faction"}

    a = _get_attrs(char)
    non_member_rep = a.get("faction_rep", {})

    for fac in factions:
        mem = mem_by_org.get(fac["id"])
        if mem:
            rep = mem.get("rep_score", 0)
            _tk, tier_name, tier_color = get_rep_tier(rep)
            bar = _rep_bar(rep)
            rank_title = mem.get("title", "Member")
            rank_level = mem.get("rank_level", 0)

            # Find next rank threshold
            ranks = await db.get_org_ranks(fac["id"])
            next_rank = next((r for r in ranks if r["rank_level"] == rank_level + 1), None)
            next_info = ""
            if next_rank:
                needed = next_rank["min_rep"] - rep
                if needed > 0:
                    next_info = f"  → {next_rank['title']} at {next_rank['min_rep']} ({needed} away)"

            lines.append(
                f"  {fac['name']:<25} {bar} {rep:>4}/100  "
                f"[{tier_color}{tier_name}\033[0m]"
            )
            lines.append(
                f"    Rank: {rank_title} ({rank_level}){next_info}"
            )
        else:
            rep = non_member_rep.get(fac["code"], 0)
            _tk, tier_name, tier_color = get_rep_tier(rep)
            bar = _rep_bar_signed(rep)
            lines.append(
                f"  {fac['name']:<25} {bar} {rep:>4}/100  "
                f"[{tier_color}{tier_name}\033[0m]"
            )

    lines += [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;33m+reputation <faction>\033[0m for details.",
    ]
    return "\n".join(lines)


async def format_reputation_detail(char: dict, faction_code: str, db) -> str:
    """Format detailed reputation view for a specific faction."""
    org = await db.get_organization(faction_code)
    if not org:
        return f"  Unknown faction: '{faction_code}'."

    lines = [
        "\033[1;36m==========================================\033[0m",
        f"  \033[1;37m{org['name'].upper()} — REPUTATION\033[0m",
        "\033[1;36m==========================================\033[0m",
    ]

    memberships = await db.get_memberships_for_char(char["id"])
    mem = next((m for m in memberships if m.get("org_id") == org["id"]), None)

    a = _get_attrs(char)
    non_member_rep = a.get("faction_rep", {})

    if mem:
        rep = mem.get("rep_score", 0)
        rank_level = mem.get("rank_level", 0)
        rank_title = mem.get("title", "Member")
    else:
        rep = non_member_rep.get(faction_code, 0)
        rank_level = None
        rank_title = None

    _tk, tier_name, tier_color = get_rep_tier(rep)
    lines.append(f"  Standing:  {rep}/100 [{tier_color}{tier_name}\033[0m]")

    if rank_title is not None:
        lines.append(f"  Rank:      {rank_title} ({rank_level})")

        # Next rank info
        ranks = await db.get_org_ranks(org["id"])
        next_rank = next((r for r in ranks if r["rank_level"] == rank_level + 1), None)
        if next_rank:
            needed = next_rank["min_rep"] - rep
            if needed > 0:
                lines.append(f"  Next Rank: {next_rank['title']} at {next_rank['min_rep']} rep ({needed} away)")
            else:
                lines.append(f"  Next Rank: {next_rank['title']} — eligible for promotion!")
        else:
            lines.append("  Next Rank: \033[2mMaximum rank achieved\033[0m")
    else:
        lines.append("  Status:    \033[2mNon-member\033[0m")

    # Rank thresholds
    ranks = await db.get_org_ranks(org["id"])
    if ranks:
        lines.append("\033[1;36m------------------------------------------\033[0m")
        lines.append("  RANK THRESHOLDS")
        for r in sorted(ranks, key=lambda x: x.get("rank_level", 0)):
            rl = r.get("rank_level", 0)
            title = r.get("title", f"Rank {rl}")
            min_r = r.get("min_rep", 0)
            equip = safe_json_loads(r.get("equipment"), default=[],
                                     context=f"rank {rl} equipment")
            equip_str = ""
            if equip:
                names = [EQUIPMENT_CATALOG.get(e, {}).get("name", e) for e in equip]
                equip_str = f" — {', '.join(names)}"

            if rank_level is not None and rl < rank_level:
                marker = "✓"
            elif rank_level is not None and rl == rank_level:
                marker = "▸"
            else:
                marker = "○"
            lines.append(f"    {marker} {title:<15} ({min_r}){equip_str}")

    # Recent rep changes
    rep_history = a.get("rep_history", {}).get(faction_code, [])
    if rep_history:
        lines.append("\033[1;36m------------------------------------------\033[0m")
        lines.append("  RECENT REP CHANGES")
        now = int(time.time())
        for entry in rep_history[:5]:
            delta = entry.get("delta", 0)
            reason_str = entry.get("reason", "")
            ts = entry.get("ts", 0)
            age = now - ts
            if age < 3600:
                age_str = f"{age // 60}m ago"
            elif age < 86400:
                age_str = f"{age // 3600}h ago"
            else:
                age_str = f"{age // 86400}d ago"
            sign = "+" if delta > 0 else ""
            lines.append(f"    {sign}{delta:>3}  {reason_str:<40} {age_str}")

    lines.append("\033[1;36m==========================================\033[0m")
    return "\n".join(lines)


# ── Status display ────────────────────────────────────────────────────────────

async def is_faction_membership_stale(char: dict, db) -> bool:
    """
    B.6 (defensive): Return True if the character's `faction_id` references
    a faction code that does NOT exist in the current DB (i.e., an orphan
    membership left over from a prior era's organizations.yaml).

    Returns False if:
      - faction_id is missing, empty, or "independent" (no membership claimed)
      - the org row exists in DB (membership is current)

    Never raises. On any DB error, conservatively returns False (the safer
    default — don't surface a "stale" advisory if we can't confirm).
    """
    try:
        fid = char.get("faction_id") or "independent"
        if not fid or fid == "independent":
            return False
        org = await db.get_organization(fid)
        return org is None
    except Exception:
        log.warning("is_faction_membership_stale: unhandled exception",
                    exc_info=True)
        return False


async def format_faction_status(char: dict, db) -> str:
    memberships = await db.get_memberships_for_char(char["id"])

    lines = [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;37mORGANIZATION STATUS\033[0m",
        "\033[1;36m==========================================\033[0m",
    ]

    faction_mem = next((m for m in memberships if m.get("org_type") == "faction"), None)
    if faction_mem:
        lines.append(
            f"  Faction:  \033[1;37m{faction_mem['name']}\033[0m "
            f"({faction_mem.get('title', 'Member')})"
        )
        rep = faction_mem.get('rep_score', 0)
        _tk, tier_name, tier_color = get_rep_tier(rep)
        lines.append(
            f"  Rank:     {faction_mem['rank_level']}  "
            f"Rep: {tier_color}{rep}/100 [{tier_name}]\033[0m"
        )
        if faction_mem.get("specialization"):
            spec = faction_mem["specialization"].replace("_", " ").title()
            lines.append(f"  Spec:     {spec}")

        # Issued equipment summary
        try:
            org = await db.get_organization(faction_mem["code"])
            if org:
                issued = await db.get_issued_equipment(char["id"], org["id"])
                if issued:
                    names = ", ".join(i["item_name"] for i in issued[:4])
                    if len(issued) > 4:
                        names += f" (+{len(issued)-4} more)"
                    lines.append(f"  Issued:   \033[2m{names}\033[0m")
        except Exception:
            log.warning("format_faction_status: unhandled exception", exc_info=True)
            pass
    else:
        # B.6 (defensive): A character may have `faction_id` set to a
        # code that no longer exists in this DB (e.g., GCW PC logging
        # into a CW-seeded DB, or any future faction-table migration).
        # Surface a clear advisory rather than silently displaying
        # "Independent" — the user otherwise has no way to know why
        # `+faction join`/`leave` won't work as expected.
        fid = char.get("faction_id") or "independent"
        if fid and fid != "independent" and await is_faction_membership_stale(char, db):
            lines.append(
                f"  Faction:  \033[1;33m[stale record: '{fid}']\033[0m"
            )
            lines.append(
                "  \033[2mYour faction record references a faction that no longer\033[0m"
            )
            lines.append(
                "  \033[2mexists in this universe. Use 'faction list' to see your\033[0m"
            )
            lines.append(
                "  \033[2moptions and 'faction join <code>' to refresh.\033[0m"
            )
        else:
            lines.append("  Faction:  \033[2mIndependent\033[0m")

    guilds = [m for m in memberships if m.get("org_type") == "guild"]
    lines.append("\033[1;36m------------------------------------------\033[0m")
    if guilds:
        lines.append("  Guilds:")
        for g in guilds:
            lines.append(f"    \033[1;33m*\033[0m {g['name']}")
        lines.append("  \033[2mGuild CP bonus: -20% on all skill training\033[0m")
    else:
        lines.append("  Guilds:   \033[2mNone\033[0m")

    lines += [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;33mfaction list\033[0m / \033[1;33mguild list\033[0m to see options.",
        "  \033[1;33m+reputation\033[0m for detailed faction standings.",
    ]
    return "\n".join(lines)


async def format_faction_list(db) -> str:
    orgs = await db.get_all_organizations()
    factions = [o for o in orgs if o["org_type"] == "faction"]
    lines = [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;37mAVAILABLE FACTIONS\033[0m",
        "\033[1;36m------------------------------------------\033[0m",
    ]
    for f in factions:
        managed = "Director-managed" if f.get("director_managed") else "Player-led"
        lines.append(
            f"  \033[1;33m{f['code']:<15}\033[0m {f['name']}"
            f"  \033[2m({managed})\033[0m"
        )
    lines += [
        "\033[1;36m------------------------------------------\033[0m",
        "  \033[1;33mfaction join <code>\033[0m to join.",
        "\033[1;36m==========================================\033[0m",
    ]
    return "\n".join(lines)


async def format_guild_list(db) -> str:
    orgs = await db.get_all_organizations()
    guilds = [o for o in orgs if o["org_type"] == "guild"]
    lines = [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;37mAVAILABLE GUILDS\033[0m  (max 3 per character)",
        "\033[1;36m------------------------------------------\033[0m",
    ]
    for g in guilds:
        props = g.get("properties", "{}")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except Exception:
                props = {}
        dues = props.get("dues_weekly", 0)
        desc = props.get("description", "")
        lines.append(
            f"  \033[1;33m{g['code']:<20}\033[0m {g['name']}\n"
            f"    \033[2m{desc}  Dues: {dues}cr/week\033[0m"
        )
    lines += [
        "\033[1;36m------------------------------------------\033[0m",
        "  \033[1;33mguild join <code>\033[0m to join.",
        "\033[1;36m==========================================\033[0m",
    ]
    return "\n".join(lines)


# ── Drop 5: Leader / admin engine functions ───────────────────────────────────

async def demote(char: dict, org_code: str, db,
                  promoter_char: dict = None, to_rank: int = None) -> tuple[bool, str]:
    """Demote a character one rank (or to to_rank if specified)."""
    org = await db.get_organization(org_code)
    if not org:
        return False, f"Unknown organization: '{org_code}'."

    mem = await db.get_membership(char["id"], org["id"])
    if not mem:
        return False, f"{char['name']} is not a member of {org['name']}."

    current_level = mem["rank_level"]
    target_level  = to_rank if to_rank is not None else max(0, current_level - 1)

    if target_level >= current_level:
        return False, f"{char['name']} is already at rank {current_level}."

    ranks = await db.get_org_ranks(org["id"])
    target_rank = next((r for r in ranks if r["rank_level"] == target_level), None)
    rank_title = target_rank["title"] if target_rank else f"Rank {target_level}"

    await db.update_membership(char["id"], org["id"], rank_level=target_level)

    details = f"Demoted to {rank_title}"
    if promoter_char:
        details += f" by {promoter_char['name']}"
    await db.log_faction_action(char["id"], org["id"], "demote", details)

    # Housing hook: downgrade or revoke faction quarters on demotion
    try:
        from engine.housing import check_faction_quarters_on_rank_change
        await check_faction_quarters_on_rank_change(
            db, char, org_code, target_level, session=None)
    except Exception as e:
        log.warning("[organizations] housing hook on demote error: %s", e)

    return True, (
        f"{char['name']} has been demoted to "
        f"\033[2m{rank_title}\033[0m in {org['name']}."
    )


async def set_standing(char: dict, org_code: str, standing: str, db,
                        actor_char: dict = None, reason: str = "") -> tuple[bool, str]:
    """
    Set a member's standing: good / probation / expelled.
    On expel: reclaims all faction-issued equipment.
    """
    VALID = {"good", "probation", "expelled"}
    if standing not in VALID:
        return False, f"Invalid standing '{standing}'. Must be: good, probation, expelled."

    org = await db.get_organization(org_code)
    if not org:
        return False, f"Unknown organization: '{org_code}'."

    mem = await db.get_membership(char["id"], org["id"])
    if not mem:
        return False, f"{char['name']} is not a member of {org['name']}."

    await db.update_membership(char["id"], org["id"], standing=standing)

    action_map = {
        "good":       "pardon",
        "probation":  "probation",
        "expelled":   "expel",
    }
    action = action_map[standing]
    detail = reason or f"Set to {standing}"
    if actor_char:
        detail += f" by {actor_char['name']}"
    await db.log_faction_action(char["id"], org["id"], action, detail)

    # On expulsion: reclaim equipment and force-leave
    if standing == "expelled":
        try:
            await reclaim_equipment(char, org_code, db)
        except Exception:
            log.warning("set_standing: unhandled exception", exc_info=True)
            pass

    standing_labels = {
        "good":      "\033[1;32mGood Standing\033[0m",
        "probation": "\033[1;33mProbation\033[0m",
        "expelled":  "\033[1;31mExpelled\033[0m",
    }
    return True, (
        f"{char['name']} standing in {org['name']} set to "
        f"{standing_labels[standing]}."
    )


async def update_org(org_code: str, db, **fields) -> bool:
    """Update arbitrary fields on an organization row."""
    ALLOWED = {"name", "leader_id", "director_managed", "hq_room_id",
               "treasury", "properties"}
    bad = set(fields) - ALLOWED
    if bad:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values())
    await db.execute(
        f"UPDATE organizations SET {set_clause} WHERE code = ?",
        vals + [org_code],
    )
    await db.commit()
    return True


async def handoff_faction_leadership(org_code: str, new_leader: dict, db,
                                      session_mgr=None) -> tuple[bool, str]:
    """
    Transfer faction leadership from Director to a PC.

    Requires new_leader to be rank 5+ with good standing.
    Sets director_managed=0 and leader_id on the organizations row.
    Broadcasts the announcement if session_mgr is provided.
    """
    org = await db.get_organization(org_code)
    if not org:
        return False, f"Unknown organization: '{org_code}'."

    mem = await db.get_membership(new_leader["id"], org["id"])
    if not mem:
        return False, f"{new_leader['name']} is not a member of {org['name']}."
    if mem["rank_level"] < 5:
        return False, (
            f"{new_leader['name']} must be rank 5 or higher to lead {org['name']}. "
            f"(current: rank {mem['rank_level']})"
        )
    if mem["standing"] != "good":
        return False, f"{new_leader['name']} must have Good Standing to assume command."

    await update_org(org_code, db,
                     leader_id=new_leader["id"],
                     director_managed=0)
    await db.log_faction_action(
        new_leader["id"], org["id"], "leadership_handoff",
        f"{new_leader['name']} assumed command. Director management disabled."
    )

    announcement = (
        f"\033[1;37m{new_leader['name']}\033[0m has assumed command of "
        f"\033[1;36m{org['name']}\033[0m."
    )
    if session_mgr:
        try:
            from server.channels import get_channel_manager
            cm = get_channel_manager()
            await cm.broadcast_fcomm(
                session_mgr, f"{org['name']} Command", org_code, announcement
            )
        except Exception:
            log.warning("handoff_faction_leadership: unhandled exception", exc_info=True)
            pass

    return True, announcement


# ── Drop 4: Gameplay Consequences ──────────────────────────────────────────

# Shop discount/markup table by tier key
SHOP_DISCOUNT_BY_TIER = {
    "trusted":     -0.05,   # 5% discount
    "honored":     -0.10,   # 10% discount
    "revered":     -0.15,   # 15% discount
    "exalted":     -0.20,   # 20% discount
    "unfriendly":   0.50,   # 50% markup
    "hostile":      None,   # Access denied
}


async def get_char_faction_rep(char: dict, faction_code: str, db) -> int:
    """
    Return a character's effective rep score with a faction.
    Checks membership first (0..100), then attributes.faction_rep (-100..+100).
    Returns 0 if no data found.
    """
    try:
        org = await db.get_organization(faction_code)
        if not org:
            return 0
        mem = await db.get_membership(char["id"], org["id"])
        if mem:
            return mem.get("rep_score", 0)
        # Non-member: check attributes
        a = _get_attrs(char)
        return a.get("faction_rep", {}).get(faction_code, 0)
    except Exception:
        log.warning("[orgs] get_char_faction_rep failed", exc_info=True)
        return 0


async def get_all_faction_reps(char: dict, db) -> dict:
    """
    Return a dict of {faction_code: {rep, tier_key, tier_name, rank, rank_level, is_member}}
    for all known factions.

    B.6 (defensive): faction codes are now derived from the DB
    (`db.get_all_organizations()` filtered to org_type=='faction') rather
    than hardcoded as `["empire", "rebel", "hutt", "bh_guild"]`. This
    makes the function era-clean: in a CW DB it returns republic/cis/
    jedi_order/etc.; in a GCW DB it returns empire/rebel/hutt/bh_guild
    (byte-equivalent to the prior list because those are exactly the
    non-`independent` factions in `data/organizations.yaml`).
    """
    result = {}
    try:
        all_orgs = await db.get_all_organizations()
        # Filter to faction-type orgs, exclude 'independent' (it's a
        # null faction, not something a player has rep with).
        factions = [
            o["code"] for o in (all_orgs or [])
            if o.get("org_type") == "faction" and o.get("code") != "independent"
        ]
        for fc in factions:
            org = await db.get_organization(fc)
            if not org:
                continue
            mem = await db.get_membership(char["id"], org["id"])
            if mem:
                rep = mem.get("rep_score", 0)
                tier_key, tier_name, _ = get_rep_tier(rep)
                # Get rank info
                rank_title = None
                rank_level = mem.get("rank_level", 0)
                ranks = await db.get_org_ranks(org["id"])
                for r in ranks:
                    if r["rank_level"] == rank_level:
                        rank_title = r["title"]
                        break
                result[fc] = {
                    "rep": rep, "tier_key": tier_key, "tier_name": tier_name,
                    "rank": rank_title, "rank_level": rank_level,
                    "is_member": True,
                }
            else:
                a = _get_attrs(char)
                rep = a.get("faction_rep", {}).get(fc, 0)
                tier_key, tier_name, _ = get_rep_tier(rep)
                result[fc] = {
                    "rep": rep, "tier_key": tier_key, "tier_name": tier_name,
                    "rank": None, "rank_level": None,
                    "is_member": False,
                }
    except Exception:
        log.warning("[orgs] get_all_faction_reps failed", exc_info=True)
    return result


def get_shop_price_modifier(tier_key: str) -> Optional[float]:
    """
    Return the price modifier for a faction rep tier.
    None = access denied (hostile). Float = multiplier offset (e.g. -0.10 = 10% discount).
    Returns 0.0 for tiers with no effect.
    """
    return SHOP_DISCOUNT_BY_TIER.get(tier_key, 0.0)


async def get_faction_shop_modifier(char: dict, faction_code: str, db) -> tuple:
    """
    Check if a character gets a price modifier at a faction-aligned shop.
    Returns (allowed: bool, modifier: float, tier_name: str).
    allowed=False means shop access denied (hostile rep).
    modifier is a price multiplier offset: -0.10 = 10% discount, +0.50 = 50% markup.
    """
    rep = await get_char_faction_rep(char, faction_code, db)
    tier_key, tier_name, _ = get_rep_tier(rep)
    mod = get_shop_price_modifier(tier_key)
    if mod is None:
        return False, 0.0, tier_name
    return True, mod, tier_name


def get_faction_standing_context(npc_faction: str, player_rep: int) -> str:
    """
    Build a FACTION STANDING context string for NPC dialogue prompts.
    Injected alongside persuasion_context in TalkCommand.
    """
    tier_key, tier_name, _ = get_rep_tier(player_rep)

    if tier_key == "hostile":
        return (
            f"FACTION STANDING: The player is {tier_name} ({player_rep}) with your "
            f"faction ({npc_faction}). You view them as a dangerous enemy. "
            f"Be openly hostile, refuse to help, and warn them to leave. "
            f"You may threaten to call guards."
        )
    elif tier_key == "unfriendly":
        return (
            f"FACTION STANDING: The player is {tier_name} ({player_rep}) with your "
            f"faction ({npc_faction}). You are suspicious and unfriendly. "
            f"Give curt, unhelpful answers. Overcharge if selling anything. "
            f"Make it clear they are not welcome."
        )
    elif tier_key == "wary":
        return (
            f"FACTION STANDING: The player is {tier_name} ({player_rep}) with your "
            f"faction ({npc_faction}). You are cautious and reserved. "
            f"Answer briefly but don't volunteer information."
        )
    elif tier_key in ("unknown", "recognized"):
        return ""  # No special context for neutral/low rep
    elif tier_key == "trusted":
        return (
            f"FACTION STANDING: The player is {tier_name} ({player_rep}) with your "
            f"faction ({npc_faction}). You recognize them as a reliable ally. "
            f"Be cooperative and helpful. You may volunteer useful information."
        )
    elif tier_key == "honored":
        return (
            f"FACTION STANDING: The player is {tier_name} ({player_rep}) with your "
            f"faction ({npc_faction}). You hold them in high regard. "
            f"Be respectful and forthcoming. Address them by rank if appropriate. "
            f"Volunteer extra detail and tips."
        )
    elif tier_key in ("revered", "exalted"):
        return (
            f"FACTION STANDING: The player is {tier_name} ({player_rep}) with your "
            f"faction ({npc_faction}). You deeply respect and admire them. "
            f"Be deferential and eager to help. Offer your best deals, insider "
            f"knowledge, and treat them as a hero of the cause."
        )
    return ""
