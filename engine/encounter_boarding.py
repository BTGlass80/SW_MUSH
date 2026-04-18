# -*- coding: utf-8 -*-
"""
engine/encounter_boarding.py — NPC Boarding Encounter System

When an NPC pirate (or bounty hunter / patrol) gets to Close range during
space combat, they may initiate a boarding action — creating a boarding
link and spawning hostile ground-combat NPCs on the player's bridge.

This creates the signature SW_MUSH cross-system moment: space combat
transitions to ground combat inside the player's own ship.

Flow:
  1. NPC combat AI at Close range selects "board" action
  2. initiate_npc_boarding() called from NPC combat tick
  3. Boarding link created via engine/boarding.py
  4. Hostile boarding party NPCs spawned in player bridge room
  5. Standard _check_hostile_npcs triggers ground combat
  6. Resolution:
     a. All boarders defeated → link severed, encounter resolved, rewards
     b. Player ship disabled → encounter lost
     c. Link severed (hyperspace/tractor) → boarders cleaned up
  7. Cleanup: spawned NPCs deleted when boarding link severs

NPC templates scale with the pirate's crew_skill to match difficulty.

Integration points:
  - engine/boarding.py sever_boarding_link() — extended with boarder cleanup
  - engine/npc_space_combat_ai.py — new "board" action in _select_action
  - server/game_server.py — registers boarding handlers + tick
"""

import json
import logging
import random
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── ANSI ─────────────────────────────────────────────────────────────────────
AMBER = "\033[1;33m"
CYAN = "\033[0;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
BOLD = "\033[1;37m"
DIM = "\033[2m"
RST = "\033[0m"

# ── Tuning Constants ─────────────────────────────────────────────────────────

# NPC combat AI: minimum actions before attempting to board
MIN_ACTIONS_BEFORE_BOARD = 4

# Chance per eligible tick that NPC decides to board (0.0-1.0)
BOARD_CHANCE = 0.35

# Boarding party sizes by difficulty tier
PARTY_SIZES = {
    "easy":   (1, 2),
    "medium": (2, 3),
    "hard":   (3, 4),
}

# Crew skill → difficulty tier
def _get_tier(crew_skill: str) -> str:
    """Map NPC crew_skill string to boarding difficulty tier."""
    from engine.dice import DicePool
    pool = DicePool.parse(crew_skill)
    pips = pool.total_pips()
    if pips <= 10:      # 3D or less
        return "easy"
    elif pips <= 15:    # 4D-5D
        return "medium"
    else:               # 5D+
        return "hard"


# ── Boarding Party NPC Templates ─────────────────────────────────────────────
# Each tier has a pool of themed pirates. When a boarding party spawns,
# we pick from the pool to create a mixed group.

_BOARDER_TEMPLATES = {
    "easy": [
        {
            "name_pool": ["Pirate Thug", "Pirate Cutthroat", "Raider"],
            "species_pool": ["Human", "Rodian", "Weequay"],
            "description": (
                "A rough-looking spacer in patched flight gear, blaster drawn. "
                "Their eyes dart around the bridge, looking for valuables."
            ),
            "dex": "3D", "blaster": "4D", "dodge": "3D+1",
            "brawling": "3D+1", "str": "3D", "per": "2D+2",
            "weapon": "Blaster Pistol (4D)",
            "behavior": "aggressive",
        },
    ],
    "medium": [
        {
            "name_pool": ["Pirate Marauder", "Corsair Boarder", "Void Raider"],
            "species_pool": ["Human", "Trandoshan", "Nikto", "Weequay"],
            "description": (
                "A battle-scarred spacer in reinforced flight armor, moving "
                "with the practiced ease of a veteran boarder. They sweep "
                "the bridge with their weapon, covering exits."
            ),
            "dex": "3D+1", "blaster": "4D+2", "dodge": "4D",
            "brawling": "4D", "str": "3D+1", "per": "3D",
            "weapon": "Heavy Blaster Pistol (5D)",
            "behavior": "aggressive",
        },
        {
            "name_pool": ["Pirate Brawler", "Boarding Enforcer"],
            "species_pool": ["Gamorrean", "Trandoshan", "Wookiee"],
            "description": (
                "A massive brute wielding a vibroblade, clearly the boarding "
                "party's muscle. They snarl at anyone who makes eye contact."
            ),
            "dex": "2D+2", "blaster": "3D", "dodge": "3D",
            "brawling": "5D", "str": "4D", "per": "2D+1",
            "weapon": "Vibroblade (STR+2D)",
            "behavior": "berserk",
        },
    ],
    "hard": [
        {
            "name_pool": ["Pirate Captain", "Corsair Commander"],
            "species_pool": ["Human", "Chiss", "Twi'lek"],
            "description": (
                "A cold-eyed pirate officer in fitted armor, barking orders "
                "to the boarding party. A well-maintained blaster rifle is "
                "held at the ready."
            ),
            "dex": "3D+2", "blaster": "5D+1", "dodge": "4D+1",
            "brawling": "4D", "str": "3D+1", "per": "3D+2",
            "weapon": "Blaster Rifle (5D)",
            "behavior": "aggressive",
        },
        {
            "name_pool": ["Pirate Shock Trooper", "Corsair Vanguard"],
            "species_pool": ["Human", "Trandoshan", "Barabel"],
            "description": (
                "A heavily-armored boarding specialist carrying a repeating "
                "blaster. Their face is hidden behind a scarred helmet visor."
            ),
            "dex": "3D+1", "blaster": "5D", "dodge": "4D",
            "brawling": "4D+1", "str": "3D+2", "per": "3D",
            "weapon": "Repeating Blaster (6D)",
            "behavior": "aggressive",
        },
        {
            "name_pool": ["Pirate Slasher", "Boarding Berserker"],
            "species_pool": ["Gamorrean", "Trandoshan", "Wookiee"],
            "description": (
                "An enormous brute roaring a battle cry, swinging a massive "
                "vibroaxe. The boarding party gives them a wide berth."
            ),
            "dex": "3D", "blaster": "3D", "dodge": "3D+1",
            "brawling": "5D+2", "str": "4D+1", "per": "2D+1",
            "weapon": "Vibroaxe (STR+3D)",
            "behavior": "berserk",
        },
    ],
}


def _build_boarder_sheet(tmpl: dict) -> dict:
    """Build a char_sheet dict for a boarding party NPC."""
    return {
        "attributes": {
            "dexterity":  tmpl["dex"],
            "knowledge":  "2D",
            "mechanical": "2D",
            "perception": tmpl["per"],
            "strength":   tmpl["str"],
            "technical":  "2D",
        },
        "skills": {
            "blaster":    tmpl["blaster"],
            "dodge":      tmpl["dodge"],
            "brawling":   tmpl["brawling"],
            "search":     "3D",
        },
        "weapon":        tmpl["weapon"],
        "species":       random.choice(tmpl["species_pool"]),
        "wound_level":   0,
        "move":          10,
        "force_points":  0,
        "character_points": 0,
        "dark_side_points": 0,
    }


def _build_boarder_ai(tmpl: dict, pirate_name: str) -> dict:
    """Build an ai_config dict for a boarding party NPC."""
    name = random.choice(tmpl["name_pool"])
    return {
        "personality": (
            f"A pirate boarder from {pirate_name}'s crew. Aggressive, "
            f"focused on controlling the bridge and looting the ship."
        ),
        "fallback_lines": [
            f"{name} snarls, \"Don't move!\"",
            f"{name} sweeps the bridge with their weapon.",
            f"{name} keeps their weapon trained on you.",
        ],
        "hostile":         True,
        "combat_behavior": tmpl["behavior"],
        "weapon":          tmpl["weapon"],
        "is_boarding_npc": True,   # Flag for cleanup when link severs
        "boarding_source": pirate_name,  # Which pirate ship sent them
    }


# ── Core Functions ───────────────────────────────────────────────────────────

async def initiate_npc_boarding(
    npc_combatant,   # SpaceNpcCombatant from npc_space_combat_ai
    db,
    session_mgr,
) -> bool:
    """
    Called by the NPC combat AI when a pirate decides to board.

    Creates a boarding link (using engine/boarding.py) and spawns
    hostile NPCs on the player's bridge for ground combat.

    Returns True if boarding was successfully initiated.
    """
    from engine.boarding import create_boarding_link

    target_ship_id = npc_combatant.target_ship_id
    npc_ship_id = npc_combatant.npc_ship_id
    bridge_room = npc_combatant.target_bridge_room

    # ── Get both ships ──
    target_ship = await db.get_ship(target_ship_id)
    if not target_ship:
        return False
    target_ship = dict(target_ship)

    # Build a minimal NPC ship dict for the boarding link API
    # NPC ships are in-memory (SpaceGrid) so we fabricate a dict
    npc_ship = {
        "id": npc_ship_id,
        "name": npc_combatant.display_name,
        "bridge_room_id": None,  # NPC ships have no physical interior
        "speed": 0,
        "systems": json.dumps({
            "tractor_holding": target_ship_id,
        }),
        "crew": "{}",
    }

    # ── We can't use create_boarding_link() directly since NPC ships
    #    have no bridge room. Instead we spawn boarders directly. ──
    # Store boarding state on the player ship only.
    target_sys_raw = target_ship.get("systems", "{}")
    if isinstance(target_sys_raw, str):
        try:
            target_sys = json.loads(target_sys_raw) if target_sys_raw else {}
        except (json.JSONDecodeError, TypeError):
            target_sys = {}
    else:
        target_sys = target_sys_raw or {}

    # Already being boarded?
    if target_sys.get("boarding_party_active"):
        return False

    # ── Spawn boarding party ──
    tier = _get_tier(npc_combatant.crew_skill)
    party_min, party_max = PARTY_SIZES.get(tier, (1, 2))
    party_size = random.randint(party_min, party_max)

    templates = _BOARDER_TEMPLATES.get(tier, _BOARDER_TEMPLATES["easy"])
    spawned_npc_ids = []

    for i in range(party_size):
        tmpl = random.choice(templates)
        name = random.choice(tmpl["name_pool"])
        # Add numbering if multiple with same name
        if party_size > 1:
            name = f"{name} #{i + 1}"

        char_sheet = _build_boarder_sheet(tmpl)
        ai_config = _build_boarder_ai(tmpl, npc_combatant.display_name)

        try:
            npc_id = await db.create_npc(
                name=name,
                room_id=bridge_room,
                species=char_sheet["species"],
                description=tmpl["description"],
                char_sheet_json=json.dumps(char_sheet),
                ai_config_json=json.dumps(ai_config),
            )
            spawned_npc_ids.append(npc_id)
        except Exception:
            log.warning("[boarding_enc] Failed to create boarder NPC", exc_info=True)

    if not spawned_npc_ids:
        log.warning("[boarding_enc] No boarders spawned for ship %d", target_ship_id)
        return False

    # ── Store boarding party state on the player ship ──
    target_sys["boarding_party_active"] = True
    target_sys["boarding_party_npc_ids"] = spawned_npc_ids
    target_sys["boarding_party_source"] = npc_combatant.display_name
    target_sys["boarding_party_npc_ship"] = npc_ship_id
    await db.update_ship(target_ship_id, systems=json.dumps(target_sys))

    # ── Broadcast boarding alert ──
    boarding_msg = (
        f"\n  {RED}{'━' * 50}{RST}\n"
        f"  {RED}[BOARDING ALERT]{RST} {BOLD}INTRUDER ALERT!{RST}\n"
        f"  {npc_combatant.display_name} has launched a boarding party!\n"
        f"  {RED}{party_size} hostile{'s' if party_size > 1 else ''} "
        f"on the bridge!{RST}\n"
        f"  {AMBER}Repel boarders! Use: attack <target>{RST}\n"
        f"  {RED}{'━' * 50}{RST}\n"
    )
    try:
        await session_mgr.broadcast_to_room(bridge_room, boarding_msg)
    except Exception:
        log.warning("[boarding_enc] Failed to broadcast boarding alert", exc_info=True)

    # ── pose_event: boarding alert as sys-event in pose log ──
    try:
        for sess in session_mgr.sessions_in_room(bridge_room):
            await sess.send_json("pose_event", {
                "event_type": "sys-event",
                "who": "",
                "text": (
                    f"BOARDING ALERT — {npc_combatant.display_name} has launched "
                    f"a boarding party! {party_size} hostile"
                    f"{'s' if party_size > 1 else ''} on the bridge!"
                ),
            })
    except Exception:
        log.warning("[boarding_enc] Failed to send boarding alert pose_event", exc_info=True)

    # ── Send boarding alert JSON to web clients ──
    try:
        sessions = session_mgr.sessions_in_room(bridge_room)
        if sessions:
            for sess in sessions:
                await sess.send_json("boarding_alert", {
                    "pirate_name": npc_combatant.display_name,
                    "boarder_count": party_size,
                    "tier": tier,
                })
    except Exception:
        log.warning("[boarding_enc] Failed to send boarding alert JSON", exc_info=True)

    # ── Trigger hostile NPC check for players already on bridge ──
    await _trigger_combat_with_boarders(bridge_room, spawned_npc_ids, db, session_mgr)

    log.info(
        "[boarding_enc] %s launched boarding party on ship %d bridge %d "
        "(%d NPCs, tier=%s, ids=%s)",
        npc_combatant.display_name, target_ship_id, bridge_room,
        party_size, tier, spawned_npc_ids,
    )
    return True


async def _trigger_combat_with_boarders(
    bridge_room: int,
    npc_ids: list[int],
    db,
    session_mgr,
) -> None:
    """
    Trigger ground combat between players on the bridge and spawned boarders.
    Uses the same pattern as _check_hostile_npcs in builtin_commands.py.
    """
    from engine.npc_combat_ai import build_npc_character, get_npc_behavior
    from engine.character import Character
    from parser.combat_commands import (
        _get_or_create_combat, _npc_behaviors, _broadcast_events,
        _auto_declare_npc_actions,
    )

    # Get players on the bridge
    chars_in_room = await db.get_characters_in_room(bridge_room)
    if not chars_in_room:
        return

    cover_max = await db.get_room_property(bridge_room, "cover_max", 0)
    combat = _get_or_create_combat(bridge_room, cover_max=cover_max)
    new_combat = combat.round_num == 0

    # Add players to combat
    for ch in chars_in_room:
        if not combat.get_combatant(ch["id"]):
            char_obj = Character.from_db_dict(ch)
            combat.add_combatant(char_obj)

    # Add boarder NPCs to combat
    added_names = []
    for npc_id in npc_ids:
        npc_row = await db.get_npc(npc_id)
        if not npc_row:
            continue
        npc_row = dict(npc_row) if not isinstance(npc_row, dict) else npc_row
        if combat.get_combatant(npc_id):
            continue
        npc_char = build_npc_character(npc_row)
        if not npc_char:
            continue
        combatant = combat.add_combatant(npc_char)
        combatant.is_npc = True
        _npc_behaviors[npc_id] = get_npc_behavior(npc_row)
        added_names.append(npc_row["name"])

    if not added_names:
        return

    # Roll initiative if new combat
    if new_combat:
        events = combat.roll_initiative()
        await _broadcast_events(events, session_mgr, bridge_room)

    # Build a minimal context for auto-declaration
    class _MinCtx:
        def __init__(self, db_, session_mgr_):
            self.db = db_
            self.session_mgr = session_mgr_

    await _auto_declare_npc_actions(combat, _MinCtx(db, session_mgr))

    # Prompt players
    for ch in chars_in_room:
        try:
            sessions = session_mgr.sessions_for_character(ch["id"])
            if sessions:
                for sess in sessions:
                    await sess.send_line(
                        f"  {RED}[COMBAT]{RST} Boarders are attacking! "
                        f"Declare: {BOLD}attack/dodge/aim/flee{RST}"
                    )
        except Exception:
            log.warning("[boarding_enc] prompt failed for char %d", ch["id"])


async def cleanup_boarding_party(ship_id: int, db) -> int:
    """
    Remove boarding party NPCs when a boarding link severs or combat ends.

    Called from sever_boarding_link() and from the boarding tick.
    Returns the number of NPCs cleaned up.
    """
    ship = await db.get_ship(ship_id)
    if not ship:
        return 0
    ship = dict(ship)

    sys_raw = ship.get("systems", "{}")
    if isinstance(sys_raw, str):
        try:
            sys = json.loads(sys_raw) if sys_raw else {}
        except (json.JSONDecodeError, TypeError):
            sys = {}
    else:
        sys = sys_raw or {}

    npc_ids = sys.get("boarding_party_npc_ids", [])
    if not npc_ids:
        return 0

    cleaned = 0
    bridge_room = ship.get("bridge_room_id")

    # Remove from active ground combat if present
    if bridge_room:
        try:
            from parser.combat_commands import _active_combats, _npc_behaviors
            combat = _active_combats.get(bridge_room)
            if combat:
                for npc_id in npc_ids:
                    combat.remove_combatant(npc_id)
                    _npc_behaviors.pop(npc_id, None)
                # If combat is now over (only player left), clean it up
                if combat.is_over:
                    _active_combats.pop(bridge_room, None)
        except Exception:
            log.warning("[boarding_enc] combat cleanup error", exc_info=True)

    # Delete the NPCs from the database
    for npc_id in npc_ids:
        try:
            await db._db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
            cleaned += 1
        except Exception:
            log.warning("[boarding_enc] Failed to delete boarder NPC %d", npc_id,
                        exc_info=True)

    if cleaned:
        await db._db.commit()

    # Clear boarding state from ship systems
    sys["boarding_party_active"] = False
    sys["boarding_party_npc_ids"] = []
    sys.pop("boarding_party_source", None)
    sys.pop("boarding_party_npc_ship", None)
    await db.update_ship(ship_id, systems=json.dumps(sys))

    log.info("[boarding_enc] Cleaned up %d boarding NPCs from ship %d",
             cleaned, ship_id)
    return cleaned


async def check_boarding_party_status(ship_id: int, db, session_mgr) -> Optional[str]:
    """
    Check if a boarding party has been defeated (all NPCs dead/gone).

    Called from the boarding encounter tick handler.
    Returns:
      "defeated"   — all boarders dead, player wins
      "active"     — boarders still fighting
      None         — no boarding party on this ship
    """
    ship = await db.get_ship(ship_id)
    if not ship:
        return None
    ship = dict(ship)

    sys_raw = ship.get("systems", "{}")
    if isinstance(sys_raw, str):
        try:
            sys = json.loads(sys_raw) if sys_raw else {}
        except (json.JSONDecodeError, TypeError):
            sys = {}
    else:
        sys = sys_raw or {}

    if not sys.get("boarding_party_active"):
        return None

    npc_ids = sys.get("boarding_party_npc_ids", [])
    if not npc_ids:
        return "defeated"

    # Check if any boarder NPCs are still alive and in the bridge room
    bridge_room = ship.get("bridge_room_id")
    alive_count = 0
    for npc_id in npc_ids:
        npc = await db.get_npc(npc_id)
        if not npc:
            continue
        npc = dict(npc) if not isinstance(npc, dict) else npc
        # Check if NPC is still in the bridge room
        if npc.get("room_id") != bridge_room:
            continue
        # Check combat state — is NPC still able to fight?
        from engine.npc_combat_ai import build_npc_character
        char = build_npc_character(npc)
        if char and char.wound_level.can_act:
            alive_count += 1

    if alive_count == 0:
        return "defeated"
    return "active"


async def handle_boarders_defeated(ship_id: int, db, session_mgr) -> None:
    """
    Called when all boarding party NPCs have been defeated.
    Awards rewards and cleans up.
    """
    ship = await db.get_ship(ship_id)
    if not ship:
        return
    ship = dict(ship)
    bridge_room = ship.get("bridge_room_id")

    sys_raw = ship.get("systems", "{}")
    if isinstance(sys_raw, str):
        try:
            sys = json.loads(sys_raw) if sys_raw else {}
        except (json.JSONDecodeError, TypeError):
            sys = {}
    else:
        sys = sys_raw or {}

    pirate_name = sys.get("boarding_party_source", "the pirates")
    npc_ship_id = sys.get("boarding_party_npc_ship", 0)

    # ── Broadcast victory ──
    victory_msg = (
        f"\n  {GREEN}{'━' * 50}{RST}\n"
        f"  {GREEN}[BOARDING]{RST} {BOLD}BOARDERS REPELLED!{RST}\n"
        f"  All hostiles from {pirate_name} have been defeated!\n"
        f"  {GREEN}{'━' * 50}{RST}\n"
    )
    if bridge_room:
        try:
            await session_mgr.broadcast_to_room(bridge_room, victory_msg)
        except Exception:
            log.warning("[boarding_enc] victory broadcast failed", exc_info=True)

        # pose_event: victory as sys-event in pose log
        try:
            for sess in session_mgr.sessions_in_room(bridge_room):
                await sess.send_json("pose_event", {
                    "event_type": "sys-event",
                    "who": "",
                    "text": f"BOARDERS REPELLED — all hostiles from {pirate_name} defeated!",
                })
        except Exception:
            log.warning("[boarding_enc] victory pose_event failed", exc_info=True)

        # Send JSON for web client
        try:
            sessions = session_mgr.sessions_in_room(bridge_room)
            if sessions:
                for sess in sessions:
                    await sess.send_json("boarding_resolved", {
                        "outcome": "repelled",
                        "pirate_name": pirate_name,
                    })
        except Exception:
            log.warning("[boarding_enc] victory JSON failed", exc_info=True)

    # ── Award CP to players on bridge ──
    CP_REWARD = 2
    CREDIT_REWARD_RANGE = (200, 800)
    if bridge_room:
        try:
            chars = await db.get_characters_in_room(bridge_room)
            credit_reward = random.randint(*CREDIT_REWARD_RANGE)
            credit_reward = int(round(credit_reward / 50) * 50)
            for ch in chars:
                ch = dict(ch)
                # CP
                new_cp = ch.get("character_points", 0) + CP_REWARD
                new_credits = ch.get("credits", 0) + credit_reward
                await db.save_character(
                    ch["id"],
                    character_points=new_cp,
                    credits=new_credits,
                )
                try:
                    sessions = session_mgr.sessions_for_character(ch["id"])
                    if sessions:
                        for sess in sessions:
                            await sess.send_line(
                                f"  {GREEN}[REWARD]{RST} +{CP_REWARD} CP, "
                                f"+{credit_reward:,} credits for repelling boarders!"
                            )
                except Exception:
                    log.warning("[boarding_enc] reward notify failed for char %d",
                                ch["id"])

                # Achievement hook
                try:
                    from engine.achievements import try_award
                    await try_award(ch["id"], "boarders_repelled", db, session_mgr)
                except Exception:
                    log.debug("[boarding_enc] achievement check failed", exc_info=True)
        except Exception:
            log.warning("[boarding_enc] reward distribution failed", exc_info=True)

    # ── Cleanup boarder NPCs ──
    await cleanup_boarding_party(ship_id, db)

    log.info("[boarding_enc] Boarders defeated on ship %d from %s",
             ship_id, pirate_name)


# ── Boarding Encounter Tick ──────────────────────────────────────────────────

async def boarding_encounter_tick(db, session_mgr, **kwargs) -> None:
    """
    Periodic tick to check boarding party status on all ships.

    If all boarders are defeated, triggers rewards and cleanup.
    Registered at interval=5 (every 5 ticks ≈ 5 seconds).
    """
    try:
        # Find all ships with active boarding parties
        rows = await db._db.execute_fetchall(
            "SELECT id, systems FROM ships WHERE systems LIKE '%boarding_party_active%'"
        )
        for row in rows:
            try:
                sys = json.loads(row["systems"] or "{}")
                if not sys.get("boarding_party_active"):
                    continue
                status = await check_boarding_party_status(row["id"], db, session_mgr)
                if status == "defeated":
                    await handle_boarders_defeated(row["id"], db, session_mgr)
            except Exception:
                log.warning("[boarding_enc] tick error for ship %d",
                            row["id"], exc_info=True)
    except Exception:
        log.warning("[boarding_enc] tick error", exc_info=True)


# ── Startup Cleanup ─────────────────────────────────────────────────────────

async def boarding_party_startup_cleanup(db) -> int:
    """
    On server boot, clean up any stale boarding party NPCs.
    Returns number of NPCs cleaned.
    """
    total_cleaned = 0
    try:
        rows = await db._db.execute_fetchall(
            "SELECT id FROM ships WHERE systems LIKE '%boarding_party_active%'"
        )
        for row in rows:
            cleaned = await cleanup_boarding_party(row["id"], db)
            total_cleaned += cleaned
        if total_cleaned > 0:
            log.info("[boarding_enc] Startup cleanup: removed %d stale boarder NPCs",
                     total_cleaned)
    except Exception:
        log.warning("[boarding_enc] Startup cleanup failed", exc_info=True)
    return total_cleaned


# ── NPC Combat AI Integration ────────────────────────────────────────────────

def should_npc_board(combatant, rng) -> bool:
    """
    Determine if an NPC combatant should attempt boarding.

    Called from NPC space combat AI _select_action().
    Requirements:
      - At Close range
      - Aggressive or Pursuit profile
      - Enough actions taken (pacing)
      - Random chance check
    """
    from engine.starships import SpaceRange
    from engine.npc_space_combat_ai import SpaceCombatProfile

    if rng != SpaceRange.CLOSE:
        return False

    # Only aggressive/pursuit profiles board
    if combatant.profile not in (
        SpaceCombatProfile.AGGRESSIVE,
        SpaceCombatProfile.PURSUIT,
    ):
        return False

    # Pacing: don't board too early
    if combatant.actions_taken < MIN_ACTIONS_BEFORE_BOARD:
        return False

    # Don't board if already boarded (checked by target ship systems,
    # but we check a simple flag here)
    if getattr(combatant, '_boarding_attempted', False):
        return False

    # Random chance
    if random.random() > BOARD_CHANCE:
        return False

    return True
