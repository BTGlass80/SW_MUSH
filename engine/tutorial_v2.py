# -*- coding: utf-8 -*-
"""
engine/tutorial_v2.py — Tutorial system for SW_MUSH.  [v21]

Architecture
============
State lives entirely in character attributes JSON (no new tables):

    attributes = {
        "tutorial_core": "not_started" | "in_progress" | "complete",
        "tutorial_step": 0,          # current room-step in core tutorial (0-5)
        "tutorial_electives": {
            "space":    "not_started" | "in_progress" | "complete",
            "combat":   "not_started",
            "economy":  "not_started",
            "crafting": "not_started",
            "force":    "not_started",   # gated on force_sensitive
            "bounty":   "not_started",
            "crew":     "not_started",
            "factions": "not_started",   # [v21] Galactic Factions elective
        },
        "training_return_room": null | <room_id>,
        "starter_quest": 0,          # 0=not started, 1-9=active step, 10=complete
        "planets_visited": [],
        "discovery_quests": {},
        "tutorial_titles": [],
        "faction_intent": null,      # [v21] stored when faction system not yet live
        "faction_intent_set_at": null,
    }

Tutorial zones have room.properties["tutorial_zone"] = true.
This disables: ambient events, world events, NPC traffic, CP tick accrual.

v21 additions
=============
- check_core_tutorial_step()       -- tracks step counter as player walks the 6-room path
- check_all_electives_complete()   -- fires 500cr all-complete bonus
- factions elective support        -- "factions" key in ELECTIVES/LABELS/REWARDS
- Starter quest Step 5.5           -- "The Powers That Be" (factions command intro)
- Updated step count display: /9 (was /8), complete at 10 (was 9)
- store_faction_intent()           -- stores intent when faction system not yet live
"""

import asyncio
import json
import logging
import time

log = logging.getLogger(__name__)

# -- Module names -------------------------------------------------------------
ELECTIVES = ["space", "combat", "economy", "crafting", "force", "bounty", "crew",
             "factions"]
ELECTIVE_LABELS = {
    "space":    "Space Academy",
    "combat":   "Combat Arena",
    "economy":  "Trader's Hall",
    "crafting": "Crafter's Workshop",
    "force":    "Jedi Enclave",
    "bounty":   "Bounty Office",
    "crew":     "Crew Quarters",
    "factions": "Galactic Factions",
}
ELECTIVE_REWARDS = {
    "space":    (500, "(Certified Pilot)"),
    "combat":   (300, None),
    "economy":  (400, None),
    "crafting": (200, None),
    "force":    (0,   "+1 Force Point"),
    "bounty":   (300, None),
    "crew":     (0,   "Free NPC hire"),
    "factions": (100, None),
}
CORE_REWARD_CREDITS = 250
ALL_COMPLETE_BONUS  = 500

# Ordered list of core tutorial room names (must match build_tutorial.py)
CORE_TUTORIAL_ROOMS = [
    "Landing Pad",
    "Desert Trail",
    "Rocky Pass",
    "Ambush Point",
    "Desert Road",
    "Mos Eisley Gate",
]

# Per-room narrative messages shown on first entry during core tutorial
CORE_ROOM_MESSAGES = {
    "Landing Pad": (
        "\n  \033[2;36m[TUTORIAL]\033[0m The transport is gone. "
        "Mos Eisley is 3km east.\n"
        "  Type \033[1;33mlook\033[0m to examine your surroundings, "
        "then \033[1;33meast\033[0m to move."
    ),
    "Desert Trail": (
        "\n  \033[2;36m[TUTORIAL]\033[0m There's a guide here. "
        "Type \033[1;33mtalk kessa\033[0m to get oriented.\n"
        "  Check your character stats with \033[1;33m+sheet\033[0m."
    ),
    "Rocky Pass": (
        "\n  \033[2;36m[TUTORIAL]\033[0m Check what you're carrying: "
        "\033[1;33m+inv\033[0m or \033[1;33minventory\033[0m.\n"
        "  Something glints in the sand. Try: \033[1;33mlook south wall\033[0m"
    ),
    "Ambush Point": (
        "\n  \033[2;36m[TUTORIAL]\033[0m You're not alone here.\n"
        "  Fight back: \033[1;33mattack raider\033[0m  "
        "-- or protect yourself: \033[1;33mdodge\033[0m"
    ),
    "Desert Road": (
        "\n  \033[2;36m[TUTORIAL]\033[0m The city is ahead. You survived the ambush.\n"
        "  Type \033[1;33memote\033[0m to express an action in the world."
    ),
    "Mos Eisley Gate": (
        "\n  \033[2;36m[TUTORIAL]\033[0m You've reached the gate. Almost there.\n"
        "  Check the job board: \033[1;33m+missions\033[0m  "
        "-- then go \033[1;33mnorth\033[0m to enter the city."
    ),
}

# -- Per-session hint task tracking -------------------------------------------
_hint_tasks: dict = {}


# -- State helpers -------------------------------------------------------------

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


def get_tutorial_state(char: dict) -> dict:
    """Return tutorial-relevant state fields from character attributes."""
    a = _get_attrs(char)
    return {
        "core":            a.get("tutorial_core", "not_started"),
        "step":            a.get("tutorial_step", -1),
        "electives":       a.get("tutorial_electives",
                                 {el: "not_started" for el in ELECTIVES}),
        "return_room":     a.get("training_return_room"),
        "starter_quest":   a.get("starter_quest", 0),
        "planets_visited": a.get("planets_visited", []),
        "titles":          a.get("tutorial_titles", []),
        "faction_intent":  a.get("faction_intent"),
    }


def set_tutorial_core(char: dict, state: str, step: int = None):
    """Update tutorial_core state. state: 'in_progress'|'complete'."""
    a = _get_attrs(char)
    a["tutorial_core"] = state
    if step is not None:
        a["tutorial_step"] = step
    _set_attrs(char, a)


def set_elective(char: dict, module: str, state: str):
    """Update an elective state."""
    a = _get_attrs(char)
    electives = a.get("tutorial_electives", {el: "not_started" for el in ELECTIVES})
    electives[module] = state
    a["tutorial_electives"] = electives
    _set_attrs(char, a)


def set_return_room(char: dict, room_id):
    a = _get_attrs(char)
    a["training_return_room"] = room_id
    _set_attrs(char, a)


def is_tutorial_zone(room_props: dict) -> bool:
    """Check if a room is inside a tutorial zone (disables ambient/CP)."""
    return bool(room_props.get("tutorial_zone", False))


def advance_starter_quest(char: dict) -> int:
    """Increment starter quest step. Returns new step number."""
    a = _get_attrs(char)
    step = a.get("starter_quest", 0) + 1
    a["starter_quest"] = step
    _set_attrs(char, a)
    return step


def mark_planet_visited(char: dict, planet: str) -> bool:
    """Mark planet as visited. Returns True if this is the first visit."""
    a = _get_attrs(char)
    visited = a.get("planets_visited", [])
    if planet in visited:
        return False
    visited.append(planet)
    a["planets_visited"] = visited
    _set_attrs(char, a)
    return True


def grant_title(char: dict, title: str):
    a = _get_attrs(char)
    titles = a.get("tutorial_titles", [])
    if title not in titles:
        titles.append(title)
    a["tutorial_titles"] = titles
    _set_attrs(char, a)


def store_faction_intent(char: dict, faction_key: str):
    """
    [v21] Store a faction join intent when the faction system isn't live yet.
    When Priority B (orgs Phase 2) ships, a migration reads these and auto-joins.
    """
    a = _get_attrs(char)
    a["faction_intent"] = faction_key
    a["faction_intent_set_at"] = int(time.time())
    _set_attrs(char, a)


# -- Core tutorial step tracking ----------------------------------------------

async def check_core_tutorial_step(session, db, room_name: str):
    """
    [v21] Call on room entry for any room that may be part of the core tutorial path.
    Advances tutorial_step and displays per-room guidance messages.

    The core path is a linear 6-room sequence. We track the highest step reached
    so the guidance message only fires once per room.
    """
    char = session.character
    ts = get_tutorial_state(char)

    if ts["core"] != "in_progress":
        return

    norm = room_name.strip().lower()
    step_index = None
    for i, rname in enumerate(CORE_TUTORIAL_ROOMS):
        if rname.lower() in norm or norm in rname.lower():
            step_index = i
            break

    if step_index is None:
        return

    # Only show guidance on first visit to this step.
    # tutorial_step is initialised to -1 (unvisited); 0 = Landing Pad visited.
    if step_index <= ts["step"]:
        return

    set_tutorial_core(char, "in_progress", step=step_index)
    try:
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))
    except Exception:
        pass

    msg = CORE_ROOM_MESSAGES.get(CORE_TUTORIAL_ROOMS[step_index])
    if msg:
        try:
            await session.send_line(msg)
        except Exception:
            pass


# -- All-electives completion check -------------------------------------------

async def check_all_electives_complete(session, db):
    """
    [v21] Call after any elective completes. If all applicable electives are done,
    grant the 500cr all-complete bonus and the '(Guild Certified)' title.
    Force elective excluded for non-Force-sensitive characters.
    """
    char = session.character
    ts = get_tutorial_state(char)
    force_sensitive = char.get("force_sensitive", False)
    electives = ts["electives"]

    required = [el for el in ELECTIVES
                if not (el == "force" and not force_sensitive)]

    all_done = all(electives.get(el, "not_started") == "complete"
                   for el in required)

    if not all_done:
        return

    if "(Guild Certified)" in ts.get("titles", []):
        return

    await grant_reward(
        session, db,
        credits=ALL_COMPLETE_BONUS,
        title="(Guild Certified)",
        message=(
            "All training modules complete! "
            "You've earned the '(Guild Certified)' title and a bonus."
        ),
    )

    try:
        from engine.narrative import log_action, ActionType as NT
        await log_action(db, char["id"], NT.TUTORIAL_COMPLETE,
                         "Completed all training modules")
    except Exception:
        pass


# -- Tutorial status display --------------------------------------------------

def format_status(char: dict) -> str:
    """Return a formatted tutorial status string for the 'training list' command."""
    ts = get_tutorial_state(char)

    def _sym(state):
        if state == "complete":    return "\033[1;32m\u2713\033[0m"
        if state == "in_progress": return "\033[1;33m\u25d0\033[0m"
        return "\033[2m\u25cb\033[0m"

    lines = [
        "\033[1;36m==========================================\033[0m",
        "  \033[1;37mTRAINING GROUNDS -- Your Progress\033[0m",
        "\033[1;36m==========================================\033[0m",
        f"  Core Tutorial ........... {_sym(ts['core'])} "
        + ("\033[1;32mComplete\033[0m" if ts['core'] == 'complete'
           else "\033[1;33mIn Progress\033[0m" if ts['core'] == 'in_progress'
           else "\033[2mNot started\033[0m"),
        "\033[1;36m------------------------------------------\033[0m",
    ]

    electives = ts["electives"]
    force_sensitive = char.get("force_sensitive", False)
    for el in ELECTIVES:
        if el == "force" and not force_sensitive:
            continue
        state = electives.get(el, "not_started")
        label = ELECTIVE_LABELS[el].ljust(22)
        lines.append(f"  {label} {_sym(state)} "
                     + ("\033[1;32mComplete\033[0m" if state == 'complete'
                        else "\033[1;33mIn progress\033[0m" if state == 'in_progress'
                        else "\033[2mNot started\033[0m"))

    started_q = ts["starter_quest"]
    lines += [
        "\033[1;36m------------------------------------------\033[0m",
        f"  Starter Quest Chain ..... "
        + ("\033[1;32m\u2713 Complete\033[0m" if started_q >= 10
           else f"\033[1;33m\u25d0 Step {started_q}/9\033[0m" if started_q > 0
           else "\033[2m\u25cb Not started\033[0m"),
        "\033[1;36m------------------------------------------\033[0m",
        "  Type \033[1;33mtraining <module>\033[0m to begin or resume.",
        "\033[1;36m==========================================\033[0m",
    ]
    return "\n".join(lines)


# -- Grant reward helper ------------------------------------------------------

async def grant_reward(session, db, credits: int = 0, item_key: str = None,
                       title: str = None, message: str = None):
    """Grant credits/item/title to a player and persist to DB."""
    char = session.character
    if credits > 0:
        char["credits"] = char.get("credits", 0) + credits
        await db.save_character(char["id"], credits=char["credits"])

    if title:
        grant_title(char, title)

    if message:
        await session.send_line(f"\n  \033[1;33m{message}\033[0m")
    if credits > 0:
        await session.send_line(f"  \033[1;32m+{credits:,} credits.\033[0m")
    if title:
        await session.send_line(f"  \033[1;36mTitle earned: {title}\033[0m")

    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))


# -- Hint system --------------------------------------------------------------

ROOM_HINTS: dict[str, list[str]] = {
    "landing pad": [
        "[TUTORIAL] Type: \033[1;33mlook\033[0m -- to examine your surroundings.",
        "[TUTORIAL] Move east to continue: \033[1;33meast\033[0m",
    ],
    "desert trail": [
        "[TUTORIAL] Talk to the guide: \033[1;33mtalk kessa\033[0m",
        "[TUTORIAL] Check your character stats: \033[1;33m+sheet\033[0m",
    ],
    "rocky pass": [
        "[TUTORIAL] Check your inventory: \033[1;33minventory\033[0m",
        "[TUTORIAL] Move east to continue.",
    ],
    "ambush point": [
        "[TUTORIAL] You're in danger! Type: \033[1;33mattack raider\033[0m",
        "[TUTORIAL] To defend yourself: \033[1;33mdodge\033[0m",
    ],
    "desert road": [
        "[TUTORIAL] Try: \033[1;33memote checks the road ahead\033[0m",
        "[TUTORIAL] Move east toward the city.",
    ],
    "mos eisley gate": [
        "[TUTORIAL] You've made it! Type: \033[1;33mlook\033[0m to survey the city entrance.",
        "[TUTORIAL] Head \033[1;33mnorth\033[0m to enter Mos Eisley.",
    ],
}

HINT_DELAY  = 30    # seconds before first hint
HINT_REPEAT = 60    # seconds between repeated hints


async def _hint_loop(session, room_name: str):
    """Coroutine that fires hints after idle periods in tutorial rooms."""
    hints = ROOM_HINTS.get(room_name.lower(), [])
    if not hints:
        return
    try:
        await asyncio.sleep(HINT_DELAY)
        idx = 0
        while True:
            hint = hints[idx % len(hints)]
            await session.send_line(f"\n  \033[2;36m{hint}\033[0m")
            idx += 1
            await asyncio.sleep(HINT_REPEAT)
    except asyncio.CancelledError:
        pass


def start_hint_timer(session, room_name: str):
    """Start the hint timer for a tutorial room. Cancels any existing timer."""
    cancel_hint_timer(session)
    task = asyncio.create_task(_hint_loop(session, room_name))
    _hint_tasks[id(session)] = task


def cancel_hint_timer(session):
    """Cancel the hint timer for a session (call on any player input)."""
    task = _hint_tasks.pop(id(session), None)
    if task and not task.done():
        task.cancel()


def on_player_input(session):
    """Call from the input handler to cancel any active hint timer."""
    cancel_hint_timer(session)


# -- Starter quest data -------------------------------------------------------
#
# Chain now has 9 steps (was 8). Step 5.5 "The Powers That Be" uses
# trigger="command" with trigger_command="faction".
# Chain marks complete at starter_quest == 10 (was 9).
#
STARTER_QUEST_STEPS = [
    # Step 1 -- Find Kessa in the cantina
    # "Chalmun's Cantina" is substring of "Chalmun's Cantina - Main Bar" v
    {
        "step": 1,
        "target_room_name": "Chalmun's Cantina",
        "trigger": "enter",
        "reward_credits": 50,
        "reward_message": "You found Kessa in the cantina. She buys you a drink.",
        "next_comlink": (
            "Kessa: \"Nice blaster you've got... or not. "
            "Head to Kayson's Weapon Shop in the market district. "
            "Tell Kayson I sent you.\""
        ),
    },
    # Step 2 -- Weapon Shop
    # Actual room: "Kayson's Weapon Shop" -- "Kayson's Weapon" is safe substring v
    {
        "step": 2,
        "target_room_name": "Kayson's Weapon",
        "trigger": "talk",
        "trigger_npc": "kayson",
        "reward_credits": 100,
        "reward_message": "Kayson slides you Kessa's referral bonus.",
        "next_comlink": (
            "Kessa: \"Got your blaster? Good. "
            "If you get shot -- and you will -- Heist at The Cutting Edge Clinic can patch you up.\""
        ),
    },
    # Step 3 -- Clinic
    # "Cutting Edge Clinic" is substring of "The Cutting Edge Clinic" v
    # reward_item stub: 50cr stand-in until item-grant system is live.
    {
        "step": 3,
        "target_room_name": "Cutting Edge Clinic",
        "trigger": "talk",
        "trigger_npc": "heist",
        "reward_credits": 50,
        "reward_message": "Heist presses a medpac into your hand. \"First one's free.\"",
        "next_comlink": (
            "Kessa: \"Getting some credits together? "
            "Zygian's Banking Concern is where the smart money goes. "
            "New customers get a welcome bonus.\""
        ),
    },
    # Step 4 -- Bank
    # "Zygian's Banking" is substring of "Zygian's Banking Concern" v
    # NPC "Zygian Teller" matched by "zygian" substring v
    {
        "step": 4,
        "target_room_name": "Zygian's Banking",
        "trigger": "talk",
        "trigger_npc": "zygian",
        "reward_credits": 50,
        "reward_message": "The Zygian teller credits you a welcome bonus.",
        "next_comlink": (
            "Kessa: \"Need work? The Transport Depot has a mission board. "
            "Dispatch keeps it fresh. Ask about the less-official board too.\""
        ),
    },
    # Step 5 -- Transport Depot (mission board)
    {
        "step": 5,
        "target_room_name": "Transport Depot",
        "trigger": "enter",
        "reward_credits": 100,
        "reward_message": "Kessa comlinks you a finder's fee for checking in.",
        "next_comlink": (
            "Kessa: \"Now that you know where the work is -- "
            "you should know who's hiring. "
            "The major factions all run their own job boards. "
            "Type \033[1;33mfactions\033[0m to see who's operating in this sector. "
            "Knowing who to work for can double your pay.\""
        ),
    },
    # Step 5.5 -- "The Powers That Be" (factions intro) [v21]
    # Triggered by the player using the 'factions' command.
    {
        "step": 6,
        "target_room_name": None,
        "trigger": "command",
        "trigger_command": "faction",
        "reward_credits": 50,
        "reward_message": (
            "Kessa (comlink): \"Now you know who's who. "
            "Pick your allies carefully -- or stay Independent. "
            "Either way, you'll hear from them eventually.\""
        ),
        "next_comlink": (
            "Kessa: \"Last thing -- if you're leaving this dustball, "
            "you'll need a ship. Docking Bay 94. The De Maals run it. "
            "Don't let them overcharge you.\""
        ),
    },
    # Step 6 -- Docking Bay 94
    {
        "step": 7,
        "target_room_name": "Docking Bay 94",
        "trigger": "enter",
        "reward_credits": 200,
        "reward_message": "Kessa comlinks you travel money. \"For fuel,\" she says.",
        "next_comlink": (
            "Kessa: \"One more -- Sergeant Kreel at the Police Station "
            "has pest control work. Good combat pay if you're looking for a fight. "
            "He also runs Imperial liaison work if you're interested in that side of things.\""
        ),
    },
    # Step 7 -- Police Station / Kreel
    {
        "step": 8,
        "target_room_name": "Police Station",
        "trigger": "talk",
        "trigger_npc": "sergeant kreel",
        "reward_credits": 100,
        "reward_message": "Kreel nods at you. \"Another freelancer. Good.\"",
        "next_comlink": (
            "Kessa: \"That's everything I can teach you, kid. "
            "You know the city, you know the people. "
            "Type \033[1;33mtraining\033[0m if you ever want advanced training. "
            "Good luck out there.\""
        ),
    },
    # Step 8 -- Chain complete (auto-fires on final comlink delivery)
    {
        "step": 9,
        "target_room_name": None,
        "trigger": "complete",
        "reward_credits": 200,
        "reward_title": "(Mos Eisley Local)",
        "reward_message": "Starter quest chain complete! Welcome to Mos Eisley.",
        "next_comlink": None,
    },
]

STARTER_QUEST_TOTAL = 9


async def check_starter_quest(session, db, trigger: str,
                               room_name: str = None, npc_name: str = None,
                               command: str = None):
    """
    Call from room-entry, talk-command, and command dispatch handlers.
    trigger: 'enter', 'talk', or 'command'
    command: the command keyword (for trigger='command')
    """
    char = session.character
    ts = get_tutorial_state(char)
    step_num = ts["starter_quest"]

    if step_num == 0:
        return  # Not started yet

    if step_num >= 10:
        return  # Complete

    if step_num > len(STARTER_QUEST_STEPS):
        return

    step = STARTER_QUEST_STEPS[step_num - 1]

    if step["trigger"] != trigger:
        return

    if trigger == "enter" and room_name:
        target = step.get("target_room_name", "")
        if not target or target.lower() not in room_name.lower():
            return

    if trigger == "talk" and npc_name:
        if step.get("trigger_npc", "").lower() not in npc_name.lower():
            return

    if trigger == "command" and command:
        if step.get("trigger_command", "").lower() != command.lower():
            return

    # Complete this step
    new_step = advance_starter_quest(char)
    credits  = step.get("reward_credits", 0)
    title    = step.get("reward_title")
    msg      = step.get("reward_message", "Quest step complete.")

    await grant_reward(session, db, credits=credits, title=title, message=msg)

    next_msg = step.get("next_comlink")
    if next_msg:
        await session.send_line(
            f"\n  \033[1;35m[COMLINK]\033[0m {next_msg}"
        )

    # Auto-complete final step (step 9 has trigger="complete")
    if new_step == 9:
        final = STARTER_QUEST_STEPS[8]
        advance_starter_quest(char)  # -> 10
        await grant_reward(session, db,
                           credits=final.get("reward_credits", 0),
                           title=final.get("reward_title"),
                           message=final.get("reward_message", ""))

    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))


def start_starter_quest(char: dict):
    """Kick off the starter quest chain (call when player leaves core tutorial)."""
    a = _get_attrs(char)
    if a.get("starter_quest", 0) == 0:
        a["starter_quest"] = 1
        _set_attrs(char, a)


# -- Discovery quests ---------------------------------------------------------
#
# [v21] Planet contact welcome messages now include faction flavor lines
# per tutorial_factions_addendum_v2.md section 5.
#

DISCOVERY_QUESTS = {
    "nar_shaddaa": {
        "contact_name": "Zekka Thansen",
        "welcome_msg": (
            "Zekka Thansen (comlink): \"Fresh arrival on the Moon? Smart move picking "
            "Nar Shaddaa. No Imperials, no questions. Head to the Corellian Promenade "
            "and find me -- I'll get you oriented. "
            "The Hutts run everything here -- run their smuggling contracts "
            "and they'll notice fast.\""
        ),
        "title": "(Smuggler's Moon Veteran)",
        "steps": [
            {"step": 1, "target_room": "Nar Shaddaa - Corellian Sector",
             "trigger": "enter", "reward_credits": 100,
             "msg": "Zekka nods. \"Now you know where to find the Guild.\"",
             "next": "Zekka (comlink): \"The Undercity is dangerous but profitable. "
                     "The Floating Market moves between towers -- worth finding.\""},
            {"step": 2, "target_room": "Nar Shaddaa - The Floating Market",
             "trigger": "enter", "reward_credits": 150,
             "msg": "You've found the Floating Market. Credits for the effort.",
             "next": "Zekka (comlink): \"One last stop. The Hutt Tower. "
                     "Know your enemies -- or your employers.\""},
            {"step": 3, "target_room": "Nar Shaddaa - Hutt Emissary Tower",
             "trigger": "enter", "reward_credits": 200,
             "reward_title": "(Smuggler's Moon Veteran)",
             "msg": "Discovery complete. You know the Moon."},
        ],
    },
    "kessel": {
        "contact_name": "Skrizz",
        "welcome_msg": (
            "Skrizz (comlink): \"Psst! New arrival! You made it to Kessel alive -- "
            "most do, most wish they hadn't. Find the black market tunnel if you "
            "want to know how things really work here. "
            "The Empire controls the spice mines -- the Traders' Coalition runs the "
            "legitimate trade. Pick your side carefully.\""
        ),
        "title": "(Kessel Runner)",
        "steps": [
            {"step": 1, "target_room": "Kessel - Black Market Tunnel",
             "trigger": "enter", "reward_credits": 150,
             "msg": "Skrizz greets you with nervous energy. \"You found it!\"",
             "next": "Skrizz (comlink): \"The spice processing facility -- "
                     "don't touch anything, but knowing where it is? Valuable.\""},
            {"step": 2, "target_room": "Kessel - Spice Processing Facility",
             "trigger": "enter", "reward_credits": 200,
             "msg": "You've seen the operation. Knowledge worth having.",
             "next": "Skrizz (comlink): \"Last thing. The smuggler's contact "
                     "behind the hangars. You'll need them.\""},
            {"step": 3, "target_room": "Kessel - Smuggler's Contact Point",
             "trigger": "enter", "reward_credits": 250,
             "reward_title": "(Kessel Runner)",
             "msg": "Discovery complete. You know Kessel's secrets."},
        ],
    },
    "corellia": {
        "contact_name": "Jorek Madine",
        "welcome_msg": (
            "Jorek Madine (comlink): \"Welcome to Corellia, friend. Best planet "
            "in the Core -- don't let anyone tell you different. Find me at the "
            "Corellian Slice cantina on Treasure Ship Row. "
            "Coronet City is officially Imperial territory, but the Corellian spirit "
            "is independent. The Traders' Coalition has their headquarters here -- "
            "and the Rebel sympathizers are careful. CorSec keeps the peace.\""
        ),
        "title": "(Honorary Corellian)",
        "steps": [
            {"step": 1, "target_room": "Corellian Slice Cantina",
             "trigger": "enter", "reward_credits": 100,
             "msg": "Jorek raises a glass. \"Now you're a regular.\"",
             "next": "Jorek (comlink): \"If you're buying a ship, CEC Shipyard "
                     "Visitor Center on the Row. Best ships in the galaxy.\""},
            {"step": 2, "target_room": "Coronet City - CEC Shipyard Visitor Center",
             "trigger": "enter", "reward_credits": 150,
             "msg": "You've seen the ships. Desa will remember you as a prospect.",
             "next": "Jorek (comlink): \"Last stop -- Old Quarter Market. "
                     "Cala knows everything. Tell her I sent you.\""},
            {"step": 3, "target_room": "Coronet City - Old Quarter Market",
             "trigger": "enter", "reward_credits": 200,
             "reward_title": "(Honorary Corellian)",
             "msg": "Discovery complete. Coronet City is yours."},
        ],
    },
}

PLANET_ROOM_PREFIXES = {
    "nar_shaddaa": "nar shaddaa",
    "kessel":      "kessel",
    "corellia":    "coronet",
}


async def on_planet_land(session, db, planet_key: str):
    """
    Call from LandCommand when a player lands on a planet.
    Sends welcome comlink and kicks off discovery quest if first visit.
    """
    char = session.character
    first_visit = mark_planet_visited(char, planet_key)
    if not first_visit:
        return

    quest_data = DISCOVERY_QUESTS.get(planet_key)
    if not quest_data:
        return

    a = _get_attrs(char)
    dq = a.get("discovery_quests", {})
    dq[planet_key] = {"step": 1, "started_at": int(time.time())}
    a["discovery_quests"] = dq
    _set_attrs(char, a)

    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))
    await session.send_line(
        f"\n  \033[1;35m[COMLINK]\033[0m {quest_data['welcome_msg']}"
    )

    try:
        from engine.narrative import log_action, ActionType as NT
        await log_action(db, char["id"], NT.PLANET_VISIT,
                         f"First landing on {planet_key.replace('_', ' ').title()}")
    except Exception:
        pass


async def check_discovery_quest(session, db, room_name: str):
    """Call on room entry. Checks if current room advances a discovery quest."""
    char = session.character
    a = _get_attrs(char)
    dq = a.get("discovery_quests", {})
    if not dq:
        return

    for planet_key, quest_data in DISCOVERY_QUESTS.items():
        state = dq.get(planet_key)
        if not state or state == "complete":
            continue

        step_num = state.get("step", 1)
        steps = quest_data["steps"]
        if step_num > len(steps):
            continue

        step = steps[step_num - 1]
        if step["trigger"] != "enter":
            continue
        if step["target_room"].lower() not in room_name.lower():
            continue

        credits = step.get("reward_credits", 0)
        title   = step.get("reward_title")
        msg     = step.get("msg", "Discovery step complete.")
        await grant_reward(session, db, credits=credits, title=title, message=msg)

        next_msg = step.get("next")
        if next_msg:
            await session.send_line(f"\n  \033[1;35m[COMLINK]\033[0m {next_msg}")

        if step_num >= len(steps):
            dq[planet_key] = "complete"
        else:
            dq[planet_key]["step"] = step_num + 1

        a["discovery_quests"] = dq
        _set_attrs(char, a)
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))


# -- Elective module step tracking --------------------------------------------
#
# Per-module step data. Each entry: (room_name_substring, step_index, message)
# step_index is 0-based. "in_progress" state stores {"step": N, "started_at": T}.
# "complete" is set when the player reaches the final room of a module.
#
# Room name substrings must match exactly one room per module.
#

ELECTIVE_STEPS = {
    "space": [
        # (room_name_substring, step_num, guidance_message)
        (
            "Space Academy Briefing",
            1,
            (
                "\n  \033[2;36m[SPACE ACADEMY]\033[0m Commander Dex briefs you on the basics.\n"
                "  Type \033[1;33mtalk dex\033[0m to get started.\n"
                "  Try: \033[1;33m+ships\033[0m to browse available vessels."
            ),
        ),
        (
            "Simulator Bay",
            2,
            (
                "\n  \033[2;36m[SPACE ACADEMY]\033[0m The simulator bay. Your training ship is ready.\n"
                "  Type \033[1;33mboard training ship\033[0m to enter it.\n"
                "  Then: \033[1;33mpilot\033[0m to take the helm, \033[1;33mlaunch\033[0m to lift off."
            ),
        ),
        (
            "Training Orbit",
            3,
            (
                "\n  \033[2;36m[SPACE ACADEMY]\033[0m You are in training orbit. The galaxy awaits.\n"
                "  Try: \033[1;33mscan\033[0m to check your surroundings.\n"
                "  Try: \033[1;33mcourse <zone>\033[0m to plot a heading."
            ),
        ),
        (
            "Hyperspace Training",
            4,
            (
                "\n  \033[2;36m[SPACE ACADEMY]\033[0m The hyperspace training lane.\n"
                "  Try: \033[1;33mastrogate\033[0m to calculate the jump.\n"
                "  Then: \033[1;33mhyperspace\033[0m to make the jump."
            ),
        ),
        (
            "Combat Training Zone",
            5,
            (
                "\n  \033[2;36m[SPACE ACADEMY]\033[0m A pirate simulation target is in the area.\n"
                "  Try: \033[1;33mlockon\033[0m to acquire a target.\n"
                "  Try: \033[1;33mfire\033[0m to shoot, \033[1;33mevade\033[0m to dodge incoming fire.\n"
                "  Check your shields: \033[1;33mshields\033[0m"
            ),
        ),
        (
            "Academy Graduation",
            6,
            (
                "\n  \033[2;36m[SPACE ACADEMY]\033[0m You have completed flight training.\n"
                "  Talk to Commander Dex for your certification: \033[1;33mtalk dex\033[0m"
            ),
        ),
    ],
    # Stubs for future drops — room name substrings to be filled in
    "combat": [
        (
            "Combat Arena Basics Room",
            1,
            (
                "\n  \033[2;36m[COMBAT ARENA]\033[0m Ordo expects you to know your tools.\n"
                "  Key commands: \033[1;33mattack\033[0m  \033[1;33mdodge\033[0m  "
                "\033[1;33mfulldodge\033[0m  \033[1;33maim\033[0m  \033[1;33mflee\033[0m\n"
                "  Type \033[1;33mtalk ordo\033[0m to begin. Head \033[1;33mforward\033[0m when ready."
            ),
        ),
        (
            "Combat Arena Multi-Action Ring",
            2,
            (
                "\n  \033[2;36m[COMBAT ARENA]\033[0m Multi-action round. Each extra action costs +1D penalty.\n"
                "  Try: \033[1;33mattack\033[0m and \033[1;33mdodge\033[0m in the same round to feel the cost."
            ),
        ),
        (
            "Combat Arena Ranged Lane",
            3,
            (
                "\n  \033[2;36m[COMBAT ARENA]\033[0m Ranged vs melee fundamentals.\n"
                "  Cover reduces incoming dice by 1D-3D. Parry substitutes melee skill for dodge.\n"
                "  Head \033[1;33mforward\033[0m for the final fight."
            ),
        ),
        (
            "Combat Arena Championship Floor",
            4,
            (
                "\n  \033[2;36m[COMBAT ARENA]\033[0m Final test. A real opponent.\n"
                "  Use everything: \033[1;33maim\033[0m first, "
                "\033[1;33mattack\033[0m, manage your wounds.\n"
                "  Win and Ordo will give you your reward."
            ),
        ),
    ],
    "economy": [
        (
            "Trader\'s Hall Commerce Floor",
            1,
            (
                "\n  \033[2;36m[TRADER\'S HALL]\033[0m The basics of commerce.\n"
                "  Try: \033[1;33m+credits\033[0m  \033[1;33mbuy <item>\033[0m  "
                "\033[1;33msell <item>\033[0m\n"
                "  Talk to Greelo to practice Bargaining: \033[1;33mtalk greelo\033[0m"
            ),
        ),
        (
            "Trader\'s Hall Mission Board Room",
            2,
            (
                "\n  \033[2;36m[TRADER\'S HALL]\033[0m The mission board -- your main income loop.\n"
                "  Try: \033[1;33m+missions\033[0m then \033[1;33maccept <id>\033[0m"
            ),
        ),
        (
            "Trader\'s Hall Smuggling Den",
            3,
            (
                "\n  \033[2;36m[TRADER\'S HALL]\033[0m Higher pay, higher risk.\n"
                "  Try: \033[1;33m+smugjobs\033[0m then \033[1;33msmugaccept <id>\033[0m\n"
                "  Patrol checks use \033[1;33mcon\033[0m or \033[1;33msneak\033[0m -- disabled here."
            ),
        ),
        (
            "Trader\'s Hall Bounty Board",
            4,
            (
                "\n  \033[2;36m[TRADER\'S HALL]\033[0m The bounty income loop.\n"
                "  Try: \033[1;33m+bounties\033[0m  \033[1;33mbountyclaim <id>\033[0m  "
                "\033[1;33mbountytrack\033[0m  \033[1;33mbountycollect\033[0m"
            ),
        ),
        (
            "Trader\'s Hall Counting Room",
            5,
            (
                "\n  \033[2;36m[TRADER\'S HALL]\033[0m Trader\'s Hall complete.\n"
                "  Talk to Greelo for the full income-loop picture: \033[1;33mtalk greelo\033[0m\n"
                "  Faction missions pay 25% more. He will tell you this himself."
            ),
        ),
    ],
    "crafting": [
        (
            "Crafter's Workshop Survey Room",
            1,
            (
                "\n  \033[2;36m[CRAFTER'S WORKSHOP]\033[0m The survey and gather steps.\n"
                "  Try: \033[1;33msurvey\033[0m then \033[1;33mgather\033[0m to collect materials.\n"
                "  Type \033[1;33mtalk vek\033[0m for guidance."
            ),
        ),
        (
            "Crafter's Workshop Assembly Bay",
            2,
            (
                "\n  \033[2;36m[CRAFTER'S WORKSHOP]\033[0m The assembly step.\n"
                "  Try: \033[1;33m+schematics\033[0m then \033[1;33mcraft <schematic>\033[0m"
            ),
        ),
        (
            "Crafter's Workshop Experimentation Lab",
            3,
            (
                "\n  \033[2;36m[CRAFTER'S WORKSHOP]\033[0m Experimentation -- push quality past baseline.\n"
                "  Try: \033[1;33mexperiment <item>\033[0m -- but know when to stop."
            ),
        ),
        (
            "Crafter's Workshop Completion Bay",
            4,
            (
                "\n  \033[2;36m[CRAFTER'S WORKSHOP]\033[0m Crafter's Workshop complete.\n"
                "  Type \033[1;33mtalk vek\033[0m to collect your reward and keep your crafted item."
            ),
        ),
    ],
    "force": [],
    "bounty": [
        (
            "Bounty Office Briefing Room",
            1,
            (
                "\n  \033[2;36m[BOUNTY OFFICE]\033[0m Ssk'rath explains the trade.\n"
                "  Try: \033[1;33m+bounties\033[0m to view active contracts.\n"
                "  Type \033[1;33mtalk ssk'rath\033[0m to begin."
            ),
        ),
        (
            "Bounty Office Tracking Range",
            2,
            (
                "\n  \033[2;36m[BOUNTY OFFICE]\033[0m Tracking exercise -- find your target.\n"
                "  Try: \033[1;33mbountytrack\033[0m to locate the target by Search roll."
            ),
        ),
        (
            "Bounty Office Takedown Room",
            3,
            (
                "\n  \033[2;36m[BOUNTY OFFICE]\033[0m Takedown -- close the contract.\n"
                "  \033[1;33mattack\033[0m to engage, \033[1;33mrestrain\033[0m when incapacitated,\n"
                "  then \033[1;33mbountycollect\033[0m to close. Alive pays 50% more."
            ),
        ),
        (
            "Bounty Office Debrief Room",
            4,
            (
                "\n  \033[2;36m[BOUNTY OFFICE]\033[0m Bounty Office complete.\n"
                "  Type \033[1;33mtalk ssk'rath\033[0m to collect 300cr + binder cuffs."
            ),
        ),
    ],
    "crew": [
        (
            "Crew Quarters Common Room",
            1,
            (
                "\n  \033[2;36m[CREW QUARTERS]\033[0m Captain Mora on crew fundamentals.\n"
                "  Try: \033[1;33m+crew\033[0m to see your roster.\n"
                "  Type \033[1;33mtalk mora\033[0m to begin."
            ),
        ),
        (
            "Crew Quarters Hiring Hall",
            2,
            (
                "\n  \033[2;36m[CREW QUARTERS]\033[0m Hiring practice -- three candidates waiting.\n"
                "  Try: \033[1;33m+crew candidates\033[0m then \033[1;33mhire <n>\033[0m"
            ),
        ),
        (
            "Crew Quarters Captain's Office",
            3,
            (
                "\n  \033[2;36m[CREW QUARTERS]\033[0m Crew Quarters complete.\n"
                "  Type \033[1;33mtalk mora\033[0m to collect your reward: 24h wage-free crew service."
            ),
        ),
    ],
    "factions": [
        (
            "Galactic Factions Briefing Room",
            1,
            (
                "\n  \033[2;36m[GALACTIC FACTIONS]\033[0m C-4PO has the briefing.\n"
                "  Type \033[1;33mtalk c-4po\033[0m for impartial faction information.\n"
                "  Head \033[1;33mforward\033[0m to see the job board comparison."
            ),
        ),
        (
            "Factions Job Board Simulator",
            2,
            (
                "\n  \033[2;36m[GALACTIC FACTIONS]\033[0m Galactic Factions module complete.\n"
                "  The pay difference is visible. Type \033[1;33mtalk c-4po\033[0m for full detail.\n"
                "  Type \033[1;33mfactions\033[0m in the live world to see your standings."
            ),
        ),
    ],
}

# Final step index per module (0-based count of steps - 1)
ELECTIVE_FINAL_STEPS = {k: len(v) for k, v in ELECTIVE_STEPS.items()}


def _get_elective_step(char: dict, module: str) -> int:
    """Return the current step number for a module (0 = not started)."""
    a = _get_attrs(char)
    electives = a.get("tutorial_electives", {})
    state = electives.get(module, "not_started")
    if isinstance(state, dict):
        return state.get("step", 0)
    if state == "complete":
        return 9999
    return 0


def _set_elective_step(char: dict, module: str, step: int):
    """Store the current step for a module as in-progress."""
    a = _get_attrs(char)
    electives = a.get("tutorial_electives", {el: "not_started" for el in ELECTIVES})
    electives[module] = {"step": step, "started_at": int(time.time())}
    a["tutorial_electives"] = electives
    _set_attrs(char, a)


async def check_elective_progress(session, db, room_name: str):
    """
    [v25] Call on room entry. Checks if the player has entered a new step room
    in any elective module. Shows guidance text and advances the step counter.
    Marks the module complete when the player reaches the final room.

    Wrapped in try/except — elective tracking is non-critical.
    """
    try:
        char = session.character
        norm = room_name.strip().lower()

        for module, steps in ELECTIVE_STEPS.items():
            if not steps:
                continue

            ts = get_tutorial_state(char)
            module_state = ts["electives"].get(module, "not_started")

            # Skip if already complete
            if module_state == "complete":
                continue

            # Find which step this room corresponds to
            matched_step = None
            for (substring, step_num, msg) in steps:
                if substring.lower() in norm:
                    matched_step = (step_num, msg)
                    break

            if matched_step is None:
                continue

            step_num, msg = matched_step
            current_step = _get_elective_step(char, module)

            # Only advance forward
            if step_num <= current_step:
                continue

            final_step = ELECTIVE_FINAL_STEPS[module]

            if step_num >= final_step:
                # Module complete
                set_elective(char, module, "complete")
                await db.save_character(
                    char["id"], attributes=char.get("attributes", "{}")
                )
                await session.send_line(msg)
                # Grant module reward
                credits, title = ELECTIVE_REWARDS.get(module, (0, None))
                label = ELECTIVE_LABELS.get(module, module.title())
                await grant_reward(
                    session, db,
                    credits=credits,
                    title=title,
                    message=f"\033[1;32m{label} complete!\033[0m",
                )
                # Check all-electives bonus
                await check_all_electives_complete(session, db)
            else:
                # Advance step
                _set_elective_step(char, module, step_num)
                await db.save_character(
                    char["id"], attributes=char.get("attributes", "{}")
                )
                # Mark in_progress if not already
                if module_state == "not_started":
                    pass  # _set_elective_step already set in-progress dict
                await session.send_line(msg)

    except Exception:
        pass  # Non-critical
