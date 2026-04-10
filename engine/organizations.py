# -*- coding: utf-8 -*-
"""
engine/organizations.py — Organizations & Factions system.  [v29]

Handles: join, leave, promote, rep adjustment, equipment issuance/reclamation,
         guild CP bonus, payroll tick, faction_intent migration, seed loading.

v29 additions
=============
- EQUIPMENT_CATALOG: item_key -> {name, description, slot}
- issue_equipment(): issues rank-appropriate gear on join/promote
- reclaim_equipment(): strips issued gear on leave/expulsion
- faction_intent_migration(): auto-joins on login if intent stored in attributes
- faction_payroll_tick(): weekly stipend distribution from treasury
- Imperial specialization prompt wired into join_faction()
- STIPEND_TABLE for weekly payroll
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
    "kill_enemy_faction_npc":       1,
    "complete_bounty":              2,
    "deliver_contraband":           2,
    "crafting_sale":                1,
    "faction_event_attendance":     1,
    "rule_violation":              -5,
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
    ("hutt",     3): 100,
    ("hutt",     4): 250,
    ("hutt",     5): 500,
    # bh_guild: no stipends — bounty income only
}

# Equipment catalog: item_key -> display info
EQUIPMENT_CATALOG = {
    # Imperial
    "imperial_uniform":      {"name": "Imperial Uniform",       "slot": "armor",  "description": "Standard grey Imperial uniform with rank insignia."},
    "se_14c_pistol":         {"name": "SE-14C Blaster Pistol",  "slot": "weapon", "description": "Imperial sidearm. Damage: 3D+2. Range: 10/30/60."},
    "e11_blaster_rifle":     {"name": "E-11 Blaster Rifle",     "slot": "weapon", "description": "Standard stormtrooper rifle. Damage: 5D. Range: 30/100/300."},
    "stormtrooper_armor":    {"name": "Stormtrooper Armor",     "slot": "armor",  "description": "White plastoid composite. +2D physical, +1D energy vs small arms."},
    "improved_armor":        {"name": "Improved Stormtrooper Armor", "slot": "armor", "description": "+2D+2 physical, +1D+2 energy."},
    "officers_sidearm":      {"name": "Officer's Blaster Pistol", "slot": "weapon", "description": "Compact officer's sidearm. Damage: 4D. Range: 10/25/50."},
    "officers_uniform":      {"name": "Imperial Officer Uniform", "slot": "armor", "description": "Grey uniform with rank cylinders. Status item."},
    "flight_suit_imperial":  {"name": "TIE Pilot Flight Suit",  "slot": "armor",  "description": "Sealed pressurized suit. Life support 10 min, +1D vs vacuum."},
    "datapad_imperial":      {"name": "Imperial Datapad",       "slot": "misc",   "description": "Encrypted datapad with Imperial codes. Access to Imperial mission board."},
    "slicing_kit":           {"name": "Intelligence Slicing Kit", "slot": "misc",  "description": "Tools for slicer operations. +1D to Computer Programming/Repair when slicing."},
    "civilian_cover":        {"name": "Civilian Cover Package", "slot": "misc",   "description": "False ID docs, civilian clothing. Makes Imperial affiliation non-obvious."},
    # Rebel
    "encrypted_comlink":     {"name": "Encrypted Comlink",      "slot": "misc",   "description": "Rebel-encrypted comlink. Access to Rebel comms channel."},
    "blaster_pistol":        {"name": "BlasTech DL-18 Pistol",  "slot": "weapon", "description": "Rebel standard sidearm. Damage: 4D. Range: 10/30/60."},
    "flight_suit":           {"name": "Rebel Flight Suit",      "slot": "armor",  "description": "Orange X-Wing pilot suit. Life support 10 min."},
    "heavy_blaster_pistol":  {"name": "DL-44 Heavy Blaster",    "slot": "weapon", "description": "Han Solo's favorite. Damage: 5D. Range: 10/25/50."},
    # Bounty Hunters Guild
    "binder_cuffs":          {"name": "Binder Cuffs",           "slot": "misc",   "description": "Restraint device. Required for live captures. Strength 6D to break."},
    "guild_license":         {"name": "BH Guild License",       "slot": "misc",   "description": "Legal hunting license. Reduces Imperial harassment in most zones."},
    "tracking_fob":          {"name": "Guild Tracking Fob",     "slot": "misc",   "description": "+1D to bountytrack rolls. Requires active bounty contract."},
    # Generic
    "medpac":                {"name": "Medpac",                 "slot": "misc",   "description": "Standard medpac. Heals 1D Stun damage when applied."},
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
            return {}
    return raw if isinstance(raw, dict) else {}


def _set_attrs(char: dict, attrs: dict):
    char["attributes"] = json.dumps(attrs)


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
        props["dues_weekly"] = guild.get("dues_weekly", 0)
        await db.create_organization(
            code=guild["code"],
            name=guild["name"],
            org_type="guild",
            director_managed=False,
            properties=json.dumps(props),
        )

    log.info("[orgs] Seed complete.")


# ── Faction join / leave ──────────────────────────────────────────────────────

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

    # Leave current faction (reclaim equipment)
    current = char.get("faction_id", "independent")
    if current and current != "independent":
        current_org = await db.get_organization(current)
        if current_org:
            await reclaim_equipment(char, current, db, session=session)
            await db.leave_organization(char["id"], current_org["id"])
            await db.log_faction_action(char["id"], current_org["id"], "leave",
                                         f"Left to join {org['name']}")

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
        pass

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
        pass

    return True, (
        f"{char['name']} has been promoted to "
        f"\033[1;37m{next_rank['title']}\033[0m in {org['name']}."
    )


# ── Payroll tick ──────────────────────────────────────────────────────────────

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

            members = await db.get_org_members(org["id"])
            for mem in members:
                if mem.get("standing", "good") not in ("good",):
                    continue  # Probation/expelled get no stipend

                rank_level = mem.get("rank_level", 0)
                stipend = STIPEND_TABLE.get((org_code, rank_level), 0)
                if stipend <= 0:
                    continue
                if treasury < stipend:
                    break  # Treasury depleted

                # Pay the stipend
                await db.save_character(mem["char_id"],
                                         credits=mem.get("credits", 0) + stipend)
                treasury -= stipend
                total_paid += stipend

                # Log
                try:
                    await db.log_faction_action(
                        mem["char_id"], org["id"], "stipend",
                        f"Weekly stipend: {stipend}cr"
                    )
                except Exception:
                    pass

            # Update treasury
            if total_paid > 0:
                try:
                    await db.update_org_treasury(org["id"], -total_paid)
                except Exception:
                    pass  # Method may not exist yet; graceful-drop

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
        pass
    return 1.0


# ── Rep adjustment ────────────────────────────────────────────────────────────

async def adjust_rep(char: dict, faction_code: str, db,
                      action_key: str) -> int:
    """
    Adjust a character's rep score for a faction based on an action.
    Returns new rep score (or 0 on error).
    """
    try:
        delta = REP_GAINS.get(action_key, 0)
        if delta == 0:
            return 0

        org = await db.get_organization(faction_code)
        if not org:
            return 0

        mem = await db.get_membership(char["id"], org["id"])
        if not mem:
            # Update attributes-based faction_rep even for non-members
            a = _get_attrs(char)
            rep_table = a.get("faction_rep", {})
            new_rep = max(0, min(100, rep_table.get(faction_code, 0) + delta))
            rep_table[faction_code] = new_rep
            a["faction_rep"] = rep_table
            _set_attrs(char, a)
            await db.save_character(char["id"], attributes=char.get("attributes", "{}"))
            return new_rep

        # Member: update via DB
        current_rep = mem.get("rep_score", 0)
        new_rep = max(0, min(100, current_rep + delta))
        await db.update_membership(char["id"], org["id"], rep_score=new_rep)
        return new_rep

    except Exception as e:
        log.exception("[orgs] adjust_rep failed: %s", e)
        return 0


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
        lines.append(
            f"  Rank:     {faction_mem['rank_level']}  "
            f"Rep: \033[1;33m{faction_mem.get('rep_score', 0)}/100\033[0m"
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
    await db._db.execute(
        f"UPDATE organizations SET {set_clause} WHERE code = ?",
        vals + [org_code],
    )
    await db._db.commit()
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
            pass

    return True, announcement
