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
}

# Rank-0 equipment per faction
RANK_0_EQUIPMENT = {
    "empire":   ["imperial_uniform", "se_14c_pistol"],
    "rebel":    ["encrypted_comlink"],
    "hutt":     [],   # Hutts don't issue gear to associates
    "bh_guild": ["binder_cuffs", "guild_license"],
}

# Rank-1 equipment per faction (adds to rank 0)
RANK_1_EQUIPMENT = {
    "empire":   [],   # Handled by specialization instead
    "rebel":    ["blaster_pistol", "flight_suit"],
    "hutt":     [],
    "bh_guild": ["tracking_fob"],
}

# Imperial specialization equipment
IMPERIAL_SPEC_EQUIPMENT = {
    "stormtrooper":  ["e11_blaster_rifle", "stormtrooper_armor"],
    "tie_pilot":     ["flight_suit_imperial"],
    "naval_officer": ["officers_uniform", "datapad_imperial"],
    "intelligence":  ["civilian_cover", "slicing_kit"],
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


# ── Imperial specialization ───────────────────────────────────────────────────

async def prompt_imperial_specialization(char: dict, db, session) -> bool:
    """
    Present Imperial specialization choice to a newly-joined Imperial character.
    Stores selection in attributes and issues spec equipment.
    Returns True if selection was made.
    """
    if not session:
        return False

    try:
        await session.send_line(
            "\n  \033[1;34m[IMPERIAL ONBOARDING]\033[0m "
            "Select your specialization:\n"
            "  \033[1;33m1\033[0m  Stormtrooper    — Ground combat. E-11 rifle, armor.\n"
            "  \033[1;33m2\033[0m  TIE Pilot       — Space combat. Flight suit, TIE assignment at rank 4.\n"
            "  \033[1;33m3\033[0m  Naval Officer   — Command/support. Uniform, datapad, crew bonuses.\n"
            "  \033[1;33m4\033[0m  Intelligence    — Stealth/slicing. Civilian cover, slicing kit.\n"
            "\n  Type \033[1;33mspecialize <number>\033[0m to select."
        )
        # Specialization is completed via the SpecializeCommand below.
        # Store a pending flag so SpecializeCommand knows to fire equipment.
        a = _get_attrs(char)
        a.setdefault("faction", {})["specialization_pending"] = True
        _set_attrs(char, a)
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))
        return True
    except Exception as e:
        log.exception("[orgs] specialization prompt failed: %s", e)
        return False


async def complete_imperial_specialization(char: dict, db,
                                            choice: int, session=None) -> tuple:
    """
    Process specialization choice (1-4). Issues equipment, stores in attributes.
    Returns (success, message).
    """
    spec_map = {
        1: "stormtrooper",
        2: "tie_pilot",
        3: "naval_officer",
        4: "intelligence",
    }
    spec_labels = {
        "stormtrooper":  "Stormtrooper",
        "tie_pilot":     "TIE Pilot",
        "naval_officer": "Naval Officer",
        "intelligence":  "Intelligence Agent",
    }

    if choice not in spec_map:
        return False, "Invalid choice. Enter 1, 2, 3, or 4."

    a = _get_attrs(char)
    if not a.get("faction", {}).get("specialization_pending"):
        return False, "No pending specialization."

    spec_key = spec_map[choice]
    a.setdefault("faction", {})["specialization"] = spec_key
    a["faction"].pop("specialization_pending", None)
    _set_attrs(char, a)
    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

    # Also update the org_membership specialization field
    org = await db.get_organization("empire")
    if org:
        await db.update_membership(char["id"], org["id"],
                                   specialization=spec_key)

    # Issue spec equipment
    spec_items = IMPERIAL_SPEC_EQUIPMENT.get(spec_key, [])
    await issue_equipment(char, "empire", db, spec_items, session=session)

    label = spec_labels.get(spec_key, spec_key.title())
    return True, (
        f"Specialization set: \033[1;37m{label}\033[0m. "
        f"Equipment issued. Report to your commanding officer."
    )


# ── Seed loader ───────────────────────────────────────────────────────────────

async def seed_organizations(db) -> None:
    """Load organizations.yaml into DB. Safe to call multiple times."""
    import yaml
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    yaml_path = os.path.join(data_dir, "organizations.yaml")
    if not os.path.exists(yaml_path):
        log.warning("[orgs] organizations.yaml not found — skipping seed")
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

    log.info("[orgs] Organizations seeded from YAML")


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

    # Imperial specialization prompt
    if faction_code == "empire":
        await prompt_imperial_specialization(char, db, session)

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
        if new_equip and org_code != "empire":  # Empire uses specialization
            await issue_equipment(char, org_code, db, new_equip)
        elif org_code == "empire" and next_level == 1:
            # Rank 1 Imperial: re-prompt specialization if not yet chosen
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
            equip = json.loads(r.get("equipment", "[]"))
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
    """
    FACTIONS = ["empire", "rebel", "hutt", "bh_guild"]
    result = {}
    try:
        for fc in FACTIONS:
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
