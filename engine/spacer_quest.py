# -*- coding: utf-8 -*-
"""
engine/spacer_quest.py — "From Dust to Stars" new-player quest chain.

30-step quest chain across 5 phases that takes a player from completing
the starter quest chain to owning a beat-up Ghtroc 720 freighter with
a 10,000cr Hutt debt.

Architecture
============
State lives entirely in character attributes JSON under "spacer_quest":

    attributes = {
        "spacer_quest": {
            "phase": 1,
            "step": 3,
            "started_at": <timestamp>,
            "completed_steps": [1, 2],
            "flags": {
                "met_mak": false,
                "background_written": false,
                "sabacc_played": false,
                "borrowed_ship_id": null,
                "ship_transferred": false,
                "debt_active": false,
                "chain_complete": false,
            },
            "step_data": {}
        }
    }

Runs entirely in the live game world — no tutorial zones.
Prerequisite: starter_quest >= 10 (starter chain complete).

Hook: check_spacer_quest(session, db, trigger, **kw) is called from
command handlers (talk, combat kill, mission complete, etc.).
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# ANSI helpers (matching tutorial_v2.py patterns)
# ═══════════════════════════════════════════════════════════════════════

_COMLINK   = "\033[1;35m[COMLINK]\033[0m"
_QUEST     = "\033[1;33m[QUEST]\033[0m"
_SUCCESS   = "\033[1;32m"
_CYAN      = "\033[1;36m"
_DIM       = "\033[2m"
_BOLD      = "\033[1m"
_RESET     = "\033[0m"

# ═══════════════════════════════════════════════════════════════════════
# Attribute helpers (identical to tutorial_v2.py)
# ═══════════════════════════════════════════════════════════════════════

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


def _get_quest_state(char: dict) -> Optional[dict]:
    """Return spacer_quest dict from character attrs, or None."""
    a = _get_attrs(char)
    return a.get("spacer_quest")


def _set_quest_state(char: dict, qs: dict):
    a = _get_attrs(char)
    a["spacer_quest"] = qs
    _set_attrs(char, a)


def _default_quest_state() -> dict:
    return {
        "phase": 1,
        "step": 1,
        "started_at": int(time.time()),
        "completed_steps": [],
        "flags": {
            "met_mak": False,
            "background_written": False,
            "sabacc_played": False,
            "borrowed_ship_id": None,
            "ship_transferred": False,
            "debt_active": False,
            "chain_complete": False,
        },
        "step_data": {},
    }


# ═══════════════════════════════════════════════════════════════════════
# Step definitions — all 30 steps
# ═══════════════════════════════════════════════════════════════════════
#
# Each step is a dict with:
#   step_id         — 1-30
#   phase           — 1-5
#   title           — short name
#   objective_type  — trigger type that completes it
#   objective_data  — type-specific params (see check_objective)
#   briefing        — comlink text sent when step activates
#   briefing_source — NPC name for the comlink
#   completion_text — comlink text sent on completion
#   reward_credits  — credits to award
#   reward_title    — title string if earned
#   reward_flags    — dict of flags to set on completion
#   hint            — hint text for +quest display
#   phase_gate      — if True, advance phase on completion
#   objective_desc  — one-line description for +quest display
#

QUEST_STEPS = [
    # ── PHASE 1: Earning Your Keep (Steps 1-7) ────────────────────────
    {
        "step_id": 1,
        "phase": 1,
        "title": "The Routine Run",
        "objective_type": "mission",
        "objective_data": {},  # any mission type
        "objective_desc": "Complete any mission from the mission board.",
        "briefing_source": "Kessa",
        "briefing": (
            "You handled those errands well enough, but errands don't pay "
            "rent. Time to hit the mission board for real. Take a delivery "
            "job — they're the simplest, lowest risk. Walk the cargo from "
            "A to B, collect your credits, don't get shot."
        ),
        "completion_text": (
            "Kessa: \"Not bad. You didn't get lost, you didn't get shot, "
            "and you got paid. That puts you ahead of half the spacers "
            "on this rock. Come see me — I've got something more interesting.\""
        ),
        "reward_credits": 200,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Use '+missions' to see the mission board. 'accept <id>' to take one.",
        "phase_gate": False,
    },
    {
        "step_id": 2,
        "phase": 1,
        "title": "Pest Control",
        "objective_type": "combat_kill",
        "objective_data": {},  # any hostile NPC
        "objective_desc": "Defeat any hostile NPC in combat.",
        "briefing_source": "Kessa",
        "briefing": (
            "A friend of mine runs cargo through the Outskirts. Says "
            "there's been trouble — Tusken Raiders getting bolder, raiders "
            "hitting the speeder track. If you can handle yourself in a "
            "fight, there's people who'd pay for that. Head out past "
            "the checkpoint and see what you find."
        ),
        "completion_text": (
            "Kessa: \"Word gets around fast in Mos Eisley. People are "
            "saying there's a new gun in town. Good — you'll need "
            "that reputation for what's coming next.\""
        ),
        "reward_credits": 300,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Hostile NPCs can be found in the Jundland Wastes (east past the Checkpoint) or other Lawless zones.",
        "phase_gate": False,
    },
    {
        "step_id": 3,
        "phase": 1,
        "title": "Smooth Operator",
        "objective_type": "skill_check",
        "objective_data": {"skill": "persuasion", "difficulty": 10,
                           "trigger_npc": "kayson",
                           "prompt": "You lean on the supplier about the power pack shortage.",
                           "success_text": "The supplier backs down. Kayson nods approvingly.",
                           "fail_text": "He's not convinced. Try again in a minute."},
        "objective_desc": "Talk to Kayson and persuade his supplier (Persuasion vs 10).",
        "briefing_source": "Kessa",
        "briefing": (
            "Not everything in this town gets solved with a blaster. "
            "Old Kayson at the weapon shop says a supplier is shortchanging "
            "him on power packs. I told him I knew someone who could have "
            "a... persuasive conversation. Head to the weapon shop, talk "
            "to Kayson, and sort it out."
        ),
        "completion_text": (
            "Kessa: \"Kayson says the power packs are flowing again. "
            "No blaster shots, no hospital bills. That's the smart way "
            "to do business.\""
        ),
        "reward_credits": 250,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Go to Kayson's Weapon Shop and 'talk kayson'.",
        "phase_gate": False,
    },
    {
        "step_id": 4,
        "phase": 1,
        "title": "The Investigation",
        "objective_type": "skill_check",
        "objective_data": {"skill": "search", "difficulty": 12,
                           "trigger_room_substr": "Warehouse",
                           "auto_on_enter": True,
                           "prompt": "You notice signs of forced entry. Search the room for clues.",
                           "success_text": "You find Jawa tracks and a dropped restraining bolt — the break-in was Jawas.",
                           "fail_text": "You don't spot anything useful. Look more carefully."},
        "objective_desc": "Search the warehouse near the spaceport for clues (Search vs 12).",
        "briefing_source": "Kessa",
        "briefing": (
            "Different job. A warehouse near the spaceport got broken "
            "into last night — cargo missing, door cut clean. The owner's "
            "offering 400 credits for whoever figures out who did it. "
            "Head over there and use your eyes, not your blaster."
        ),
        "completion_text": (
            "Kessa: \"Jawas, huh? Figures. The owner's happy, you're "
            "richer, and now people know you can find things. That's a "
            "useful reputation.\""
        ),
        "reward_credits": 400,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Head to the Warehouse near the spaceport. Use 'search' when you arrive.",
        "phase_gate": False,
    },
    {
        "step_id": 5,
        "phase": 1,
        "title": "Diversify",
        "objective_type": "mission_count",
        "objective_data": {"target": 3},
        "objective_desc": "Complete 3 missions of any type.",
        "briefing_source": "Kessa",
        "briefing": (
            "One-off jobs are fine, but I need to know you can handle "
            "volume. Hit the board, take three jobs — delivery, combat, "
            "investigation, whatever's up there. Finish all three and "
            "I'll introduce you to someone important."
        ),
        "completion_text": (
            "Kessa: \"Three for three. You're consistent — that's worth "
            "more than talent around here. Time you met someone who can "
            "open real doors for you.\""
        ),
        "reward_credits": 800,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Complete any 3 missions from the mission board. Progress: {missions_done}/{target}",
        "phase_gate": False,
    },
    {
        "step_id": 6,
        "phase": 1,
        "title": "The Sabacc Table",
        "objective_type": "sabacc",
        "objective_data": {},
        "objective_desc": "Play a hand of sabacc in the cantina.",
        "briefing_source": "Kessa",
        "briefing": (
            "Before I introduce you to my contact, there's something you "
            "need to understand about how Mos Eisley really works. Half "
            "the deals in this town get made over sabacc cards. Head to "
            "the cantina, put some credits on the table, play a hand. "
            "I don't care if you win or lose — just learn the game. "
            "Type 'sabacc' when you're in the cantina."
        ),
        "completion_text": (
            "Kessa: \"So? Win or lose? ...Doesn't matter. The point is "
            "you sat at the table. In this town, that means you're in "
            "the game. Now head to Docking Bay 94 — there's someone "
            "you need to meet.\""
        ),
        "reward_credits": 100,
        "reward_title": None,
        "reward_flags": {"sabacc_played": True},
        "hint": "Go to Chalmun's Cantina and type 'sabacc' to play.",
        "phase_gate": False,
    },
    {
        "step_id": 7,
        "phase": 1,
        "title": "The Old Captain",
        "objective_type": "talk",
        "objective_data": {"npc": "mak torvin", "room_substr": "Docking Bay 94"},
        "objective_desc": "Talk to Mak Torvin at Docking Bay 94.",
        "briefing_source": "Kessa",
        "briefing": (
            "His name is Mak Torvin. Old freighter captain — been running "
            "the Outer Rim since before the Clone Wars. His ship's in dry "
            "dock, his knees are shot, but he knows more about the spacer's "
            "life than anyone I've ever met. He's at Docking Bay 94. Tell "
            "him I sent you."
        ),
        "completion_text": (
            "Kessa: \"Good. Mak's the real deal — if he decides to "
            "mentor you, you're set. Listen to what he says.\""
        ),
        "reward_credits": 250,
        "reward_title": None,
        "reward_flags": {"met_mak": True},
        "hint": "Go to Docking Bay 94 and 'talk mak'.",
        "phase_gate": True,  # → Phase 2
    },

    # ── PHASE 2: The Wider Galaxy (Steps 8-14) ────────────────────────
    {
        "step_id": 8,
        "phase": 2,
        "title": "The Powers That Be",
        "objective_type": "use_command",
        "objective_data": {"command": "faction"},
        "objective_desc": "Use the 'factions' command to learn who runs this galaxy.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Before you go anywhere, you need to understand who runs this "
            "galaxy. It's not just the Empire — there are factions, guilds, "
            "cartels, all of them pulling strings. Type 'factions' and "
            "read up. Knowing who to work for can double your pay."
        ),
        "completion_text": (
            "Mak: \"Good. Most rookies never bother learning the political "
            "landscape until they're already in trouble. You're smarter "
            "than most.\""
        ),
        "reward_credits": 150,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Type 'factions' to see who operates in this sector.",
        "phase_gate": False,
    },
    {
        "step_id": 9,
        "phase": 2,
        "title": "Your First Bounty",
        "objective_type": "bounty",
        "objective_data": {},  # any tier
        "objective_desc": "Complete a bounty from the bounty board.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Time to try bounty hunting. Check the bounty board — "
            "'+bounties' — and pick a target you think you can handle. "
            "Start with the lower tiers. You'll need to track them down "
            "first — that's a Search or Streetwise check — and then take "
            "them down. Alive pays more than dead, but dead's a lot safer."
        ),
        "completion_text": (
            "Mak: \"Not bad for your first hunt. The Bounty Hunters' "
            "Guild keeps records — they noticed you. Keep collecting "
            "and the Guild might come knocking with better contracts.\""
        ),
        "reward_credits": 500,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Use '+bounties' to see targets. 'bountytrack <id>' to track, then fight and 'bountycollect'.",
        "phase_gate": False,
    },
    {
        "step_id": 10,
        "phase": 2,
        "title": "The Underworld Economy",
        "objective_type": "smuggling",
        "objective_data": {"min_tier": 0},
        "objective_desc": "Complete a smuggling run (any tier).",
        "briefing_source": "Kessa",
        "briefing": (
            "You want to see how the real money moves on Tatooine? Check "
            "'+smugjobs'. There are cargo runs the mission board won't "
            "touch — medical supplies, restricted tech, things that fall "
            "off the back of a transport. Tier 0 is almost legal. Almost. "
            "Take one, deliver it, and try not to get caught."
        ),
        "completion_text": (
            "Kessa: \"The Hutts take note of reliable runners. You're "
            "building a useful network — whether you meant to or not.\""
        ),
        "reward_credits": 400,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Use '+smugjobs' to see available runs. 'smugaccept <id>' to take one.",
        "phase_gate": False,
    },
    {
        "step_id": 11,
        "phase": 2,
        "title": "Write Your Story",
        "objective_type": "use_command",
        "objective_data": {"command": "+background"},
        "objective_desc": "Write your character's backstory using +background.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Here's something most spacers never bother with, but the "
            "smart ones do. Write down who you are. Where you came from. "
            "What you want. Type '+background' and put something down — "
            "it doesn't have to be a novel. The NPCs around here pay "
            "attention to your story. It shapes how they talk to you."
        ),
        "completion_text": (
            "Mak: \"Good. A spacer without a story is just cargo with "
            "legs. Now, about getting you off-world...\""
        ),
        "reward_credits": 200,
        "reward_title": None,
        "reward_flags": {"background_written": True},
        "hint": "Type '+background' and write at least a sentence about your character.",
        "phase_gate": False,
    },
    {
        "step_id": 12,
        "phase": 2,
        "title": "Check Your Progress",
        "objective_type": "use_command",
        "objective_data": {"command": "cpstatus"},
        "objective_desc": "Check your advancement progress with 'cpstatus'.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "You've been fighting, running jobs, talking your way through "
            "deals. All that experience adds up. Type 'cpstatus' — it'll "
            "show you how close you are to earning a Character Point. "
            "When you get one, you can 'train' a skill and improve it "
            "permanently. That's how you go from a kid with a blaster "
            "to someone worth hiring."
        ),
        "completion_text": (
            "Mak: \"See those ticks adding up? Every mission, every "
            "fight, every RP scene contributes. When you've got a CP "
            "saved up, pick a skill and type 'train <skill>'. Now — "
            "let's talk about getting you to Nar Shaddaa.\""
        ),
        "reward_credits": 100,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Type 'cpstatus' to see your Character Point progress.",
        "phase_gate": False,
    },
    {
        "step_id": 13,
        "phase": 2,
        "title": "Passage to Nar Shaddaa",
        "objective_type": "room",
        "objective_data": {"room_id_range": [54, 83]},  # Nar Shaddaa rooms
        "objective_desc": "Travel to Nar Shaddaa. Use 'travel narshaddaa' at a docking bay.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "I called in a favor with a freighter crew heading to Nar "
            "Shaddaa. They've got a spare bunk. Nar Shaddaa is nothing "
            "like Tatooine — bigger, dirtier, more dangerous, and ten "
            "times the money. Go there, look around, meet some people, "
            "and come back alive. That's the test. Type 'travel narshaddaa' "
            "at any docking bay."
        ),
        "completion_text": (
            "Mak (comlink): \"You made it. Welcome to the Smuggler's "
            "Moon. Look around, don't trust anyone. I want you to meet "
            "a few people while you're there.\""
        ),
        "reward_credits": 500,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Go to a Docking Bay on Tatooine and type 'travel narshaddaa'.",
        "phase_gate": False,
    },
    {
        "step_id": 14,
        "phase": 2,
        "title": "Making Contacts",
        "objective_type": "talk_multi",
        "objective_data": {"npcs": ["zekka", "renna", "myrra"], "target": 3},
        "objective_desc": "Talk to 3 contacts on Nar Shaddaa: Zekka Thansen, Renna Dox, and Doc Myrra.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Three people I want you to find on Nar Shaddaa. First: "
            "Zekka Thansen in the Corellian Sector — she runs a smuggler "
            "network. Second: Renna Dox at the shipwright's — tell her "
            "I sent you. Third: Doc Myrra in the Undercity — best medic "
            "on the moon. Find all three, introduce yourself."
        ),
        "completion_text": (
            "Mak: \"Good. You've got contacts on two planets now. That's "
            "the start of a real network. Head back to Tatooine — I think "
            "you're ready to learn how to fly. Use 'travel tatooine' at "
            "a Nar Shaddaa docking area.\""
        ),
        "reward_credits": 600,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Find and talk to: {contacts_status}",
        "phase_gate": True,  # → Phase 3
    },

    # ── PHASE 3: Off-World (Steps 15-20) ──────────────────────────────
    {
        "step_id": 15,
        "phase": 3,
        "title": "Your First Launch",
        "objective_type": "space_action",
        "objective_data": {"action": "launch"},
        "objective_desc": "Launch from Tatooine in Mak's ship.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "This is the moment, kid. That's my ship over there — the "
            "Rusty Mynock. She's old, she's ugly, and the hyperdrive "
            "protests every jump. But she flies. I'm lending her to you "
            "— not giving, lending. You scratch her, you pay for repairs. "
            "Now get in the cockpit and take her up. Type 'board' to get "
            "aboard, then 'launch' when you're ready."
        ),
        "completion_text": (
            "Mak (comlink): \"She's up! Don't let the engine rattle "
            "scare you — that's just her way of saying hello. Now set "
            "a course and get a feel for the controls.\""
        ),
        "reward_credits": 200,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Go to Docking Bay 94, type 'board' to enter the ship, then 'launch'.",
        "phase_gate": False,
    },
    {
        "step_id": 16,
        "phase": 3,
        "title": "Star Roads",
        "objective_type": "space_action",
        "objective_data": {"action": "hyperspace"},
        "objective_desc": "Make a hyperspace jump to any planet.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Orbit's nice, but it doesn't pay the bills. Time to see "
            "what's past the atmosphere. Pick a destination and punch "
            "the hyperdrive. Type 'hyperspace <destination>' when you're "
            "in orbit. The Mynock's hyperdrive has... opinions."
        ),
        "completion_text": (
            "Mak: \"Stars turned to lines, right? That feeling never "
            "gets old. Now land wherever you are and look around.\""
        ),
        "reward_credits": 300,
        "reward_title": None,
        "reward_flags": {},
        "hint": "In orbit, type 'hyperspace narshaddaa' (or kessel, corellia) to jump.",
        "phase_gate": False,
    },
    {
        "step_id": 17,
        "phase": 3,
        "title": "Touch Down",
        "objective_type": "space_action",
        "objective_data": {"action": "land"},
        "objective_desc": "Land on any planet other than Tatooine.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Navigate to orbit around your destination, then type 'land'. "
            "Each planet has its own docking bay, its own rules, its own "
            "prices. Notice the docking fee when you land — that's a "
            "cost of doing business."
        ),
        "completion_text": (
            "Mak: \"Solid landing. Every port is different — learn what "
            "each one offers and you'll always know where to go.\""
        ),
        "reward_credits": 200,
        "reward_title": None,
        "reward_flags": {},
        "hint": "In orbit around a planet, type 'land' to dock.",
        "phase_gate": False,
    },
    {
        "step_id": 18,
        "phase": 3,
        "title": "Your First Cargo Run",
        "objective_type": "trade",
        "objective_data": {},  # any buy or sell
        "objective_desc": "Buy or sell trade goods. Buy low on one planet, sell high on another.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Here's where a ship starts paying for itself. Every planet "
            "produces goods that are cheap locally and expensive elsewhere. "
            "Type 'trade list' to see what's available. Buy low, fly "
            "somewhere that wants it, sell high. Corellia sells luxury "
            "goods cheap, and Tatooine can't get enough of them."
        ),
        "completion_text": (
            "Mak: \"Now you understand why every spacer in the galaxy "
            "wants a freighter with cargo space. You're not just a gun "
            "for hire anymore — you're a trader.\""
        ),
        "reward_credits": 500,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Use 'trade list' at any planet to see goods. 'trade buy <good> <tons>' then fly and 'trade sell'.",
        "phase_gate": False,
    },
    {
        "step_id": 19,
        "phase": 3,
        "title": "When Things Break",
        "objective_type": "use_command",
        "objective_data": {"command": "damcon"},
        "objective_desc": "Run ship diagnostics or attempt a repair with 'damcon'.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Here's a lesson every freighter captain learns: things break. "
            "The Mynock's always got something rattling loose. While "
            "you're aboard, type 'damcon' to run diagnostics. If something's "
            "damaged, 'damcon <system>' to attempt a repair. You'll need "
            "Space Transports Repair skill — even a basic roll helps."
        ),
        "completion_text": (
            "Mak: \"Every credit you save on repairs is a credit in your "
            "pocket. A captain who can't fix their own ship is just a "
            "passenger with a title.\""
        ),
        "reward_credits": 300,
        "reward_title": None,
        "reward_flags": {},
        "hint": "While aboard your ship, type 'damcon' to check systems.",
        "phase_gate": False,
    },
    {
        "step_id": 20,
        "phase": 3,
        "title": "The Grand Tour",
        "objective_type": "visit_planets",
        "objective_data": {"planets": ["tatooine", "nar_shaddaa", "kessel", "corellia"],
                           "target": 4},
        "objective_desc": "Land on all 4 planets: Tatooine, Nar Shaddaa, Kessel, Corellia.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Almost there. I want you to visit every planet we've got "
            "routes to — Tatooine, Nar Shaddaa, Kessel, and Corellia. "
            "Land on each one. A good spacer knows every port in their "
            "territory."
        ),
        "completion_text": (
            "Mak: \"Four planets. Four docking bays. You know the territory "
            "now, kid. Head back to Tatooine — we need to talk about "
            "your future.\""
        ),
        "reward_credits": 500,
        "reward_title": "(Outer Rim Traveler)",
        "reward_flags": {},
        "hint": "Land on each planet. Visited: {planets_visited_status}",
        "phase_gate": True,  # → Phase 4
    },

    # ── PHASE 4: A Spacer's Reputation (Steps 21-26) ──────────────────
    {
        "step_id": 21,
        "phase": 4,
        "title": "The Artisan's Edge",
        "objective_type": "craft",
        "objective_data": {},
        "objective_desc": "Craft any item using the crafting system.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Every spacer I've ever admired could do more than just fly "
            "and shoot. The best ones can build things. Head to wherever "
            "you've got resources stockpiled and try your hand at crafting. "
            "If you need materials, use 'survey' to gather them. Check "
            "'schematics' to see what you can build."
        ),
        "completion_text": (
            "Mak: \"Not bad for a first attempt. Crafted goods carry "
            "your name on them — that's your reputation in physical form.\""
        ),
        "reward_credits": 400,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Use 'survey' for resources, 'schematics' for blueprints, 'craft <schematic>' to build.",
        "phase_gate": False,
    },
    {
        "step_id": 22,
        "phase": 4,
        "title": "Faction Flavors",
        "objective_type": "multi_any2",
        "objective_data": {"sub_types": ["bounty", "smuggling", "mission"]},
        "objective_desc": "Complete any 2 of: a bounty, a smuggling run, or a mission.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "The factions are watching. The Bounty Hunters' Guild tracks "
            "your kills. The Hutts track your deliveries. The Empire and "
            "the Rebellion track your mission history. Do any two of these: "
            "a bounty hunt, a smuggling run, or a mission. Show the galaxy "
            "you're not a one-trick spacer."
        ),
        "completion_text": (
            "Mak: \"Two out of three. The factions are definitely watching "
            "now. When you've got your own ship, some of them will come "
            "to you with exclusive contracts.\""
        ),
        "reward_credits": 800,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Complete 2 of: bounty, smuggling, mission. Done: {multi_status}",
        "phase_gate": False,
    },
    {
        "step_id": 23,
        "phase": 4,
        "title": "Safe Harbor",
        "objective_type": "use_command",
        "objective_data": {"command": "housing"},
        "objective_desc": "Check housing options with the 'housing' command.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Where do you sleep? Docking bays are fine for a night, but "
            "if you're going to be based somewhere, you need a home. "
            "Type 'housing' to see what's available in your area. You "
            "don't have to buy anything now — just know it exists. Safe "
            "storage, trophies, a permanent address."
        ),
        "completion_text": (
            "Mak: \"When you've got credits to spare, a place of your "
            "own is worth the investment. Cheapest on Tatooine, nicest "
            "on Corellia.\""
        ),
        "reward_credits": 200,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Type 'housing' to see options in your current area.",
        "phase_gate": False,
    },
    {
        "step_id": 24,
        "phase": 4,
        "title": "The Crew Question",
        "objective_type": "talk",
        "objective_data": {"npc": "venn kator"},
        "objective_desc": "Talk to a shipwright about NPC crew: Venn Kator (Corellia) or Renna Dox (Nar Shaddaa).",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Something to think about: crew. A ship can run solo, but it "
            "runs better with help. An NPC gunner on the turret while you "
            "pilot. An engineer who can handle repairs mid-fight. They "
            "cost wages, but a good crew member can save your life. Talk "
            "to Venn Kator on Corellia or Renna Dox on Nar Shaddaa."
        ),
        "completion_text": (
            "Mak: \"Good. When you're ready to hire, type 'hire' at any "
            "spaceport to see who's available. Check their skills — a 2D "
            "gunner isn't worth the wages.\""
        ),
        "reward_credits": 300,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Travel to Corellia and 'talk venn' or Nar Shaddaa and 'talk renna'.",
        "phase_gate": False,
    },
    {
        "step_id": 25,
        "phase": 4,
        "title": "The Big Job",
        "objective_type": "multi_all3",
        "objective_data": {"sub_types": ["mission", "smuggling", "bounty"]},
        "objective_desc": "Complete 1 mission + 1 smuggling run + 1 bounty.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Here's the final test. I want you to do three things: run "
            "a mission, deliver a smuggling cargo, and collect a bounty. "
            "Three different kinds of work, three different skill sets. "
            "That's what life as a freighter captain looks like."
        ),
        "completion_text": (
            "Mak: \"Three jobs, three flavors. You handled it. Kid... "
            "you're ready. Come see me at the bay. There's something I've "
            "been wanting to talk to you about.\""
        ),
        "reward_credits": 1000,
        "reward_title": "(Versatile Spacer)",
        "reward_flags": {},
        "hint": "Complete all 3: mission, smuggling, bounty. Done: {multi_status}",
        "phase_gate": False,
    },
    {
        "step_id": 26,
        "phase": 4,
        "title": "The Proposition",
        "objective_type": "talk",
        "objective_data": {"npc": "mak torvin", "room_substr": "Docking Bay 94"},
        "objective_desc": "Talk to Mak Torvin at Docking Bay 94.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Come to Docking Bay 94. There's something I've been wanting "
            "to talk to you about. Something big."
        ),
        "completion_text": (
            "Mak: \"The Rusty Mynock — she's mine, but I can't fly her "
            "anymore. My hands shake, my eyes aren't what they were. "
            "I'll sell her to you for 8,000 credits — my retirement fund. "
            "The other 10,000 goes to Drago the Hutt who holds the note. "
            "You pay that off over time, 500 a week. Talk to Lira Shan "
            "on Corellia for the paperwork, then Grek on Nar Shaddaa "
            "about the debt. What do you say?\""
        ),
        "reward_credits": 0,
        "reward_title": None,
        "reward_flags": {},
        "hint": "Go to Docking Bay 94 on Tatooine and 'talk mak'.",
        "phase_gate": True,  # → Phase 5
    },

    # ── PHASE 5: The Captain's Chair (Steps 27-30) ────────────────────
    {
        "step_id": 27,
        "phase": 5,
        "title": "The Down Payment",
        "objective_type": "talk_with_credits",
        "objective_data": {"npc": "lira", "room_substr": "Coronet",
                           "cost": 8000},
        "objective_desc": "Talk to Lira Shan on Corellia with 8,000 credits to buy the ship.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "Head to Corellia. Find Lira Shan at the Coronet Starport. "
            "She's got the title and registration ready. You'll need "
            "8,000 credits for the purchase price — that's my cut. "
            "If you don't have it yet, go earn it. I'll wait."
        ),
        "completion_text": (
            "Mak (comlink): \"Lira tells me it's done. She's yours now, "
            "kid. Take care of her — she took care of me for twenty "
            "years. Now go see Grek about the debt.\""
        ),
        "reward_credits": 0,  # net negative — player pays 8000
        "reward_title": None,
        "reward_flags": {"ship_transferred": True},
        "hint": "Fly to Corellia. You need at least 8,000 credits. 'talk lira' at Coronet Starport.",
        "phase_gate": False,
    },
    {
        "step_id": 28,
        "phase": 5,
        "title": "Settling Accounts",
        "objective_type": "talk",
        "objective_data": {"npc": "grek"},
        "objective_desc": "Talk to Grek on Nar Shaddaa about the Hutt debt.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "The fun part. Grek is Drago's man on Nar Shaddaa — he "
            "handles the Hutt's lending operation. Find him in the "
            "Undercity. He'll set up the repayment terms. Don't try "
            "to negotiate — the terms are what they are."
        ),
        "completion_text": (
            "Mak: \"Grek's set up? Good. 500 a week is manageable if "
            "you're flying steady. The debt is a leash, but it's a long "
            "one — and when it's paid off, you're truly free.\""
        ),
        "reward_credits": 0,
        "reward_title": None,
        "reward_flags": {"debt_active": True},
        "hint": "Fly to Nar Shaddaa and find Grek in the Undercity. 'talk grek'.",
        "phase_gate": False,
    },
    {
        "step_id": 29,
        "phase": 5,
        "title": "Name Her",
        "objective_type": "use_command",
        "objective_data": {"command": "shipname"},
        "objective_desc": "Name your ship with the 'shipname' command.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "One last thing. She needs a name. A real name — not 'Rusty "
            "Mynock,' that was mine. Type 'shipname <name>' and give "
            "her something she deserves. A ship's name is her soul."
        ),
        "completion_text": (
            "Mak: \"A good name. She'll wear it well.\""
        ),
        "reward_credits": 500,
        "reward_title": "(Captain)",
        "reward_flags": {},
        "hint": "While aboard your ship, type 'shipname <name>' to name her.",
        "phase_gate": False,
    },
    {
        "step_id": 30,
        "phase": 5,
        "title": "First Solo Jump",
        "objective_type": "space_action",
        "objective_data": {"action": "hyperspace"},
        "objective_desc": "Make your first hyperspace jump as captain of your own ship.",
        "briefing_source": "Mak Torvin",
        "briefing": (
            "There's nothing more I can teach you. The galaxy's out "
            "there — your galaxy, now. Take your ship, pick a direction, "
            "and go. Your first jump as captain. Make it count."
        ),
        "completion_text": None,  # special handling — grand completion
        "reward_credits": 1000,
        "reward_title": "(Spacer)",
        "reward_flags": {"chain_complete": True},
        "hint": "Launch your ship, enter orbit, and 'hyperspace <destination>'.",
        "phase_gate": False,
    },
]

# Build a lookup dict for fast access
_STEPS_BY_ID = {s["step_id"]: s for s in QUEST_STEPS}


def get_step(step_id: int) -> Optional[dict]:
    return _STEPS_BY_ID.get(step_id)


# ═══════════════════════════════════════════════════════════════════════
# Reward granting (mirrors tutorial_v2.grant_reward)
# ═══════════════════════════════════════════════════════════════════════

async def _grant_reward(session, db, credits: int = 0,
                        title: str = None, message: str = None):
    """Grant credits/title and persist."""
    char = session.character
    if credits > 0:
        char["credits"] = char.get("credits", 0) + credits
        await db.save_character(char["id"], credits=char["credits"])

    if title:
        # Store in tutorial_titles for consistency
        a = _get_attrs(char)
        titles = a.get("tutorial_titles", [])
        if title not in titles:
            titles.append(title)
        a["tutorial_titles"] = titles
        _set_attrs(char, a)

    if message:
        await session.send_line(f"\n  {_QUEST} {message}")
    if credits > 0:
        await session.send_line(f"  {_SUCCESS}+{credits:,} credits.{_RESET}")
    if title:
        await session.send_line(f"  {_CYAN}Title earned: {title}{_RESET}")

    await db.save_character(char["id"], attributes=char.get("attributes", "{}"))


async def _send_comlink(session, source: str, text: str):
    """Send an IC comlink message from a quest NPC."""
    await session.send_line(f"\n  {_COMLINK} {source}: \"{text}\"")


# ═══════════════════════════════════════════════════════════════════════
# Step completion logic
# ═══════════════════════════════════════════════════════════════════════

async def _complete_step(session, db, qs: dict, step: dict):
    """Complete a quest step: award rewards, advance state, send messages."""
    char = session.character
    step_id = step["step_id"]

    # Record completion
    if step_id not in qs["completed_steps"]:
        qs["completed_steps"].append(step_id)

    # Set any reward flags
    for k, v in step.get("reward_flags", {}).items():
        qs["flags"][k] = v

    # Clear step_data for this step
    qs["step_data"].pop(str(step_id), None)

    # Award credits & title
    credits = step.get("reward_credits", 0)
    title = step.get("reward_title")

    await _grant_reward(session, db,
                        credits=credits,
                        title=title,
                        message=f"Quest step complete: {step['title']}")

    # Send completion comlink
    comp_text = step.get("completion_text")
    if comp_text:
        await session.send_line(f"\n  {_COMLINK} {comp_text}")

    # Special: Phase 3 Step 15 — create the loaner Ghtroc 720
    if step_id == 15:
        ship_id = await _create_borrowed_ship(session, db)
        if ship_id:
            await session.send_line(
                f"  \033[1;36m[SHIP]\033[0m The Rusty Mynock is docked at "
                f"Docking Bay 94. Type 'board' to get aboard."
            )
        else:
            await session.send_line(
                "  \033[1;33m[QUEST]\033[0m Ship creation failed — "
                "contact an admin or relog to retry Step 15."
            )

    # Special: Phase 5 Step 27 — deduct 8000 credits for ship purchase
    if step_id == 27:
        cost = step["objective_data"].get("cost", 8000)
        char["credits"] = char.get("credits", 0) - cost
        await db.save_character(char["id"], credits=char["credits"])
        await session.send_line(
            f"  \033[1;31m-{cost:,} credits (ship purchase).{_RESET}")
        transferred = await _transfer_ship_ownership(session, db)
        if transferred:
            await session.send_line(
                "  \033[1;32m[SHIP]\033[0m The Rusty Mynock is now yours. "
                "Lira has filed the registration. She's all yours."
            )

    # Special: Phase 5 Step 28 — activate debt
    if step_id == 28:
        a = _get_attrs(char)
        a["hutt_debt"] = {
            "principal": 10000,
            "weekly_payment": 500,
            "next_payment_due": int(time.time()) + 604800,
            "payments_missed": 0,
            "total_paid": 0,
        }
        _set_attrs(char, a)
        await session.send_line(
            f"\n  {_QUEST} Hutt debt activated: 10,000cr at 500cr/week.")
        await session.send_line(
            f"  {_DIM}Type 'debt' to check your balance.{_RESET}")

    # Special: Step 30 — grand completion
    if step_id == 30:
        await _grand_completion(session, db, qs)

    # Advance to next step
    if step_id < 30:
        next_step_id = step_id + 1
        qs["step"] = next_step_id
        next_step = get_step(next_step_id)

        # Phase gate
        if step.get("phase_gate"):
            qs["phase"] = next_step["phase"] if next_step else qs["phase"] + 1

        # Save state BEFORE sending briefing (so state is consistent)
        _set_quest_state(char, qs)
        await db.save_character(char["id"],
                                attributes=char.get("attributes", "{}"))

        # Send next step briefing
        if next_step:
            await _send_comlink(session,
                                next_step.get("briefing_source", "Kessa"),
                                next_step["briefing"])
    else:
        # Chain complete
        qs["step"] = 30
        _set_quest_state(char, qs)
        await db.save_character(char["id"],
                                attributes=char.get("attributes", "{}"))


async def _grand_completion(session, db, qs):
    """Display the grand completion banner for Step 30."""
    char = session.character
    ship_name = qs["flags"].get("ship_name", "your ship")

    banner = (
        f"\n{'='*63}\n"
        f"  \033[1;33m★  FROM DUST TO STARS — COMPLETE  ★{_RESET}\n"
        f"{'='*63}\n"
        f"\n"
        f"  You arrived on Tatooine with nothing but a blaster and\n"
        f"  a prayer. Now you've got a ship, a name, a network across\n"
        f"  four planets, and a Hutt who expects 500 credits a week.\n"
        f"\n"
        f"  Welcome to the spacer's life, Captain.\n"
        f"\n"
        f"  {_CYAN}Rewards:{_RESET} \"(Spacer)\" title, \"(Captain)\" title, +1 CP\n"
        f"  {_CYAN}Your ship:{_RESET} {ship_name} (Ghtroc 720 Light Freighter)\n"
        f"  {_CYAN}Debt remaining:{_RESET} 10,000cr to Drago the Hutt\n"
        f"\n"
        f"  The profession chains are now available:\n"
        f"    Smuggler's Run  ·  Hunter's Mark  ·  Artisan's Forge\n"
        f"    Rebel Cell  ·  Imperial Service  ·  Underworld\n"
        f"\n"
        f"{'='*63}"
    )
    await session.send_line(banner)

    # Award +1 CP
    try:
        char["character_points"] = char.get("character_points", 0) + 1
        await db.save_character(char["id"],
                                character_points=char["character_points"])
        await session.send_line(
            f"  {_SUCCESS}+1 Character Point awarded!{_RESET}")
    except Exception:
        log.warning("_grand_completion: CP award failed", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════
# Objective checking — the core dispatch
# ═══════════════════════════════════════════════════════════════════════

def _init_step_data(qs: dict, step: dict) -> dict:
    """Ensure step_data entry exists for steps that need counters."""
    sid = str(step["step_id"])
    if sid not in qs["step_data"]:
        otype = step["objective_type"]
        if otype == "mission_count":
            qs["step_data"][sid] = {"missions_done": 0}
        elif otype == "talk_multi":
            qs["step_data"][sid] = {"contacts_made": []}
        elif otype == "visit_planets":
            qs["step_data"][sid] = {"planets_landed": []}
        elif otype in ("multi_any2", "multi_all3"):
            qs["step_data"][sid] = {"completed": []}
    return qs["step_data"].get(sid, {})


# ═══════════════════════════════════════════════════════════════════════
# Drop 5 — Borrowed Ship System
# ═══════════════════════════════════════════════════════════════════════

_GHTROC_QUIRKS = [
    "The port engine makes a grinding noise during acceleration.",
    "The cockpit lighting flickers when the shields activate.",
    "The cargo bay door sticks and requires a solid kick to close.",
    "The hyperdrive emits a high-pitched whine for the first 10 seconds of every jump.",
    "The previous owner painted a mynock on the starboard hull. Badly.",
]


async def _create_borrowed_ship(session, db) -> int:
    """Create the Ghtroc 720 loaner ship for Step 15. Returns ship_id or 0."""
    import json as _json
    char = session.character

    try:
        bays = await db.find_rooms("Docking Bay 94 - Pit Floor")
        bay_room_id = bays[0]["id"] if bays else None
        if not bay_room_id:
            bays = await db.find_rooms("Docking Bay 94")
            bay_room_id = bays[0]["id"] if bays else None
    except Exception:
        bay_room_id = None

    if not bay_room_id:
        await session.send_line(
            "  [QUEST] Unable to locate Docking Bay 94. "
            "Contact an admin — quest ship could not be created."
        )
        return 0

    try:
        bridge_id = await db.create_room(
            "The Rusty Mynock - Bridge",
            "The cramped bridge of an aging Ghtroc 720 freighter.",
            "The cockpit of the Rusty Mynock smells of burnt electronics and old caf. "
            "Mismatched readout screens line the console, half showing correct data, "
            "half showing whatever they feel like. A cracked pilot's seat sits centre "
            "stage, taped together with cargo webbing. Through the viewport: Tatooine's "
            "twin suns blaze over the Mos Eisley skyline.",
        )
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("_create_borrowed_ship: bridge room: %s", e)
        return 0

    systems = _json.dumps({
        "engines": True, "weapons": True, "shields": True,
        "hyperdrive": True, "sensors": True,
        "condition": 65, "weapon_condition": 50,
        "quest_ship": True,
        "quirks": _GHTROC_QUIRKS,
    })

    try:
        cursor = await db.execute(
            """INSERT INTO ships
               (template, name, owner_id, bridge_room_id, docked_at,
                hull_damage, shield_damage, systems, crew, cargo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("ghtroc_720", "The Rusty Mynock", char["id"],
             bridge_id, bay_room_id, 2, 0, systems, "{}", "[]"),
        )
        await db.commit()
        ship_id = cursor.lastrowid
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("_create_borrowed_ship: ship insert: %s", e)
        return 0

    try:
        await db.create_exit(bay_room_id, bridge_id, "board", "Board ship")
        await db.create_exit(bridge_id, bay_room_id, "disembark", "Disembark")
    except Exception as _e:
        log.debug("silent except in engine/spacer_quest.py:1203: %s", _e, exc_info=True)

    qs = _get_quest_state(char)
    if qs:
        qs["flags"]["borrowed_ship_id"] = ship_id
        _set_quest_state(char, qs)
        await db.save_character(char["id"], attributes=char.get("attributes", "{}"))

    return ship_id


async def _transfer_ship_ownership(session, db) -> bool:
    """Strip quest_ship flag — ship is now fully owned (Step 27)."""
    import json as _json
    char = session.character
    qs = _get_quest_state(char)
    if not qs:
        return False
    ship_id = qs["flags"].get("borrowed_ship_id")
    if not ship_id:
        return False
    try:
        ship = await db.get_ship(ship_id)
        if not ship:
            return False
        systems = _json.loads(ship.get("systems") or "{}")
        systems.pop("quest_ship", None)
        systems["owned"] = True
        await db.update_ship(ship_id, systems=_json.dumps(systems))
        return True
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("_transfer_ship_ownership: %s", e)
        return False


async def return_borrowed_ship(db, char) -> None:
    """Reclaim/delete the loaner ship on quest abandon."""
    import json as _json
    qs = _get_quest_state(char)
    if not qs:
        return
    ship_id = qs["flags"].get("borrowed_ship_id")
    if not ship_id:
        return
    try:
        ship = await db.get_ship(ship_id)
        if not ship:
            return
        systems = _json.loads(ship.get("systems") or "{}")
        if not systems.get("quest_ship"):
            return  # already transferred — don't delete player's ship
        bridge_id = ship.get("bridge_room_id")
        await db.execute("DELETE FROM ships WHERE id = ?", (ship_id,))
        if bridge_id:
            await db.execute(
                "DELETE FROM exits WHERE from_room_id = ? OR to_room_id = ?",
                (bridge_id, bridge_id)
            )
            await db.execute("DELETE FROM rooms WHERE id = ?", (bridge_id,))
        await db.commit()
        qs["flags"]["borrowed_ship_id"] = None
        _set_quest_state(char, qs)
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("return_borrowed_ship: %s", e)


async def check_quest_ship_sale(session, db, ship_id: int) -> bool:
    """Return True (and inform player) if ship is a quest loaner."""
    import json as _json
    try:
        ship = await db.get_ship(ship_id)
        if ship:
            systems = _json.loads(ship.get("systems") or "{}")
            if systems.get("quest_ship"):
                await session.send_line(
                    "  You can't sell or transfer this ship — it belongs to Mak Torvin. "
                    "Finish the quest chain first."
                )
                return True
    except Exception as _e:
        log.debug("silent except in engine/spacer_quest.py:1285: %s", _e, exc_info=True)
    return False


async def check_spacer_quest(session, db, trigger: str, **kw):
    """
    Universal hook — call from command handlers.

    trigger: 'talk', 'mission', 'combat_kill', 'bounty', 'smuggling',
             'trade', 'craft', 'sabacc', 'space_action', 'use_command',
             'room_enter'
    kw: trigger-specific data (npc_name=, room_id=, room_name=,
        mission_type=, action=, command=, etc.)
    """
    char = session.character
    qs = _get_quest_state(char)

    if qs is None:
        # Check if we should auto-start the chain
        await _maybe_start_chain(session, db, trigger, **kw)
        return

    if qs["flags"].get("chain_complete"):
        return  # Already done

    step_id = qs.get("step", 1)
    step = get_step(step_id)
    if not step:
        return

    otype = step["objective_type"]
    odata = step.get("objective_data", {})

    # Initialize step_data counters if needed
    sdata = _init_step_data(qs, step)

    matched = False

    # ── talk ──────────────────────────────────────────────────────────
    if otype == "talk" and trigger == "talk":
        target_npc = odata.get("npc", "")
        npc_name = kw.get("npc_name", "").lower()
        if target_npc.lower() in npc_name or npc_name in target_npc.lower():
            room_substr = odata.get("room_substr")
            if room_substr:
                room_name = kw.get("room_name", "")
                if room_substr.lower() not in room_name.lower():
                    return  # wrong room
            matched = True

    # ── talk_with_credits ─────────────────────────────────────────────
    elif otype == "talk_with_credits" and trigger == "talk":
        target_npc = odata.get("npc", "")
        npc_name = kw.get("npc_name", "").lower()
        if target_npc.lower() in npc_name or npc_name in target_npc.lower():
            cost = odata.get("cost", 0)
            if char.get("credits", 0) >= cost:
                matched = True
            else:
                await session.send_line(
                    f"  {_QUEST} You need at least {cost:,} credits. "
                    f"You have {char.get('credits', 0):,}.")

    # ── talk_multi ────────────────────────────────────────────────────
    elif otype == "talk_multi" and trigger == "talk":
        npc_name = kw.get("npc_name", "").lower()
        sid = str(step_id)
        contacts = sdata.get("contacts_made", [])
        target_npcs = odata.get("npcs", [])
        for tnpc in target_npcs:
            if tnpc.lower() in npc_name and tnpc not in contacts:
                contacts.append(tnpc)
                qs["step_data"][sid]["contacts_made"] = contacts
                remaining = [n for n in target_npcs if n not in contacts]
                if remaining:
                    await session.send_line(
                        f"  {_QUEST} Contact made! Still need: "
                        f"{', '.join(remaining)}")
                break
        target = odata.get("target", len(target_npcs))
        if len(contacts) >= target:
            matched = True

    # ── mission / mission_count ───────────────────────────────────────
    elif otype == "mission" and trigger == "mission":
        matched = True

    elif otype == "mission_count" and trigger == "mission":
        sid = str(step_id)
        count = sdata.get("missions_done", 0) + 1
        qs["step_data"][sid]["missions_done"] = count
        target = odata.get("target", 3)
        if count >= target:
            matched = True
        else:
            await session.send_line(
                f"  {_QUEST} Mission progress: {count}/{target}")

    # ── combat_kill ───────────────────────────────────────────────────
    elif otype == "combat_kill" and trigger == "combat_kill":
        matched = True

    # ── bounty ────────────────────────────────────────────────────────
    elif otype == "bounty" and trigger == "bounty":
        matched = True

    # ── smuggling ─────────────────────────────────────────────────────
    elif otype == "smuggling" and trigger == "smuggling":
        min_tier = odata.get("min_tier", 0)
        tier = kw.get("tier", 0)
        if tier >= min_tier:
            matched = True

    # ── trade ─────────────────────────────────────────────────────────
    elif otype == "trade" and trigger == "trade":
        matched = True

    # ── craft ─────────────────────────────────────────────────────────
    elif otype == "craft" and trigger == "craft":
        matched = True

    # ── sabacc ────────────────────────────────────────────────────────
    elif otype == "sabacc" and trigger == "sabacc":
        matched = True

    # ── space_action ──────────────────────────────────────────────────
    elif otype == "space_action" and trigger == "space_action":
        target_action = odata.get("action", "")
        action = kw.get("action", "")
        if target_action == action or not target_action:
            matched = True

    # ── use_command ───────────────────────────────────────────────────
    elif otype == "use_command" and trigger == "use_command":
        target_cmd = odata.get("command", "").lower()
        cmd = kw.get("command", "").lower()
        # Match on prefix: "+background" matches "+background",
        # "faction" matches "faction" or "factions"
        if cmd.startswith(target_cmd) or target_cmd.startswith(cmd):
            matched = True

    # ── room (enter specific room) ────────────────────────────────────
    elif otype == "room" and trigger == "room_enter":
        room_id = kw.get("room_id", -1)
        id_range = odata.get("room_id_range")
        if id_range and len(id_range) == 2:
            if id_range[0] <= room_id <= id_range[1]:
                matched = True

    # ── skill_check ───────────────────────────────────────────────────
    elif otype == "skill_check" and trigger == "talk":
        # Skill checks fire when talking to a specific NPC
        trigger_npc = odata.get("trigger_npc", "")
        npc_name = kw.get("npc_name", "").lower()
        if trigger_npc.lower() in npc_name:
            # Fire the skill check
            matched = await _do_skill_check(session, db, char, odata)

    elif otype == "skill_check" and trigger == "use_command":
        # Some skill checks fire on 'search' command
        cmd = kw.get("command", "").lower()
        if cmd == "search" and odata.get("auto_on_enter"):
            matched = await _do_skill_check(session, db, char, odata)

    # ── visit_planets ─────────────────────────────────────────────────
    elif otype == "visit_planets" and trigger == "space_action":
        action = kw.get("action", "")
        planet = kw.get("planet", "")
        if action == "land" and planet:
            sid = str(step_id)
            visited = sdata.get("planets_landed", [])
            if planet.lower() not in [p.lower() for p in visited]:
                visited.append(planet.lower())
                qs["step_data"][sid]["planets_landed"] = visited
                target = odata.get("target", 4)
                remaining = target - len(visited)
                if remaining > 0:
                    await session.send_line(
                        f"  {_QUEST} Planet visited! {remaining} more to go.")
                else:
                    matched = True

    # ── multi_any2 ────────────────────────────────────────────────────
    elif otype == "multi_any2":
        sub_types = odata.get("sub_types", [])
        if trigger in sub_types:
            sid = str(step_id)
            completed = sdata.get("completed", [])
            if trigger not in completed:
                completed.append(trigger)
                qs["step_data"][sid]["completed"] = completed
                if len(completed) >= 2:
                    matched = True
                else:
                    await session.send_line(
                        f"  {_QUEST} Progress: {len(completed)}/2 "
                        f"({', '.join(completed)})")

    # ── multi_all3 ────────────────────────────────────────────────────
    elif otype == "multi_all3":
        sub_types = odata.get("sub_types", [])
        if trigger in sub_types:
            sid = str(step_id)
            completed = sdata.get("completed", [])
            if trigger not in completed:
                completed.append(trigger)
                qs["step_data"][sid]["completed"] = completed
                remaining = [s for s in sub_types if s not in completed]
                if not remaining:
                    matched = True
                else:
                    await session.send_line(
                        f"  {_QUEST} Progress: {len(completed)}/{len(sub_types)} "
                        f"(need: {', '.join(remaining)})")

    # ── Save counter changes even if not matched ──────────────────────
    if not matched:
        _set_quest_state(char, qs)
        await db.save_character(char["id"],
                                attributes=char.get("attributes", "{}"))
        return

    # ── MATCHED — complete the step ───────────────────────────────────
    await _complete_step(session, db, qs, step)


async def _do_skill_check(session, db, char, odata: dict) -> bool:
    """Fire a skill check for a quest step. Returns True on success."""
    skill = odata.get("skill", "perception")
    difficulty = odata.get("difficulty", 10)
    prompt = odata.get("prompt", "You attempt the check...")
    success_text = odata.get("success_text", "Success!")
    fail_text = odata.get("fail_text", "You failed. Try again.")

    await session.send_line(f"\n  {_QUEST} {prompt}")

    try:
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(char, skill, difficulty)
        roll = result.roll if hasattr(result, 'roll') else result.get("roll", 0)
        success = result.success if hasattr(result, 'success') else result.get("success", False)
        pool_str = result.pool_str if hasattr(result, 'pool_str') else result.get("pool_str", "?D")

        await session.send_line(
            f"  {skill.title()} [{pool_str}]: "
            f"Roll {roll} vs Difficulty {difficulty}")

        if success:
            await session.send_line(f"  {_SUCCESS}{success_text}{_RESET}")
            return True
        else:
            await session.send_line(f"  {fail_text}")
            return False
    except Exception:
        log.warning("_do_skill_check failed", exc_info=True)
        await session.send_line(
            f"  {_DIM}(Skill check system unavailable — step auto-completing.){_RESET}")
        return True  # graceful fallthrough


# ═══════════════════════════════════════════════════════════════════════
# Chain auto-start
# ═══════════════════════════════════════════════════════════════════════

async def _maybe_start_chain(session, db, trigger: str, **kw):
    """Check if we should auto-start the quest chain."""
    if trigger not in ("room_enter", "talk"):
        return

    char = session.character
    a = _get_attrs(char)

    # Prerequisite: starter quest complete
    starter = a.get("starter_quest", 0)
    if starter < 10:
        return

    # Already started or completed
    if "spacer_quest" in a:
        return

    # Start the chain
    qs = _default_quest_state()
    a["spacer_quest"] = qs
    _set_attrs(char, a)
    await db.save_character(char["id"],
                            attributes=char.get("attributes", "{}"))

    step1 = get_step(1)
    await _send_comlink(session, "Kessa",
        "You've proven you can handle yourself in Mos Eisley. That's "
        "step one. But if you want to make it as a real spacer — not "
        "just another blaster-for-hire scraping by on the mission board "
        "— you've got a long road ahead. Stick with me and I'll show "
        "you how to earn a ship of your own."
    )
    await session.send_line(
        f"\n  {_QUEST} {_BOLD}Quest chain started: "
        f"\"From Dust to Stars\"{_RESET}")
    await session.send_line(
        f"  {_DIM}Type '+quest' to see your current objective.{_RESET}")

    if step1:
        await _send_comlink(session, step1["briefing_source"],
                            step1["briefing"])


# ═══════════════════════════════════════════════════════════════════════
# Display helpers (for +quest command)
# ═══════════════════════════════════════════════════════════════════════

PHASE_NAMES = {
    1: "Earning Your Keep",
    2: "The Wider Galaxy",
    3: "Off-World",
    4: "A Spacer's Reputation",
    5: "The Captain's Chair",
}


def format_quest_display(char: dict) -> str:
    """Build the +quest display string."""
    qs = _get_quest_state(char)
    if qs is None:
        return (
            "  You haven't started the spacer quest chain yet.\n"
            "  Complete the starter quest chain first (talk to Kessa "
            "in Chalmun's Cantina)."
        )

    if qs["flags"].get("chain_complete"):
        return (
            f"{'='*63}\n"
            f"  {_BOLD}FROM DUST TO STARS — COMPLETE{_RESET}\n"
            f"{'='*63}\n"
            f"  You earned your ship and your freedom.\n"
            f"  Check out the profession chains for your next adventure."
        )

    step_id = qs.get("step", 1)
    step = get_step(step_id)
    if not step:
        return "  Quest data error. Contact an admin."

    phase = qs.get("phase", 1)
    phase_name = PHASE_NAMES.get(phase, "Unknown")
    completed = len(qs.get("completed_steps", []))

    # Calculate credits earned
    total_credits = sum(
        get_step(s).get("reward_credits", 0)
        for s in qs.get("completed_steps", [])
        if get_step(s)
    )

    # Progress bar
    pct = completed / 30
    filled = int(pct * 24)
    bar = f"{'█' * filled}{'░' * (24 - filled)}"

    # Hint with interpolation
    hint = step.get("hint", "")
    sdata = qs.get("step_data", {}).get(str(step_id), {})
    if "{missions_done}" in hint:
        done = sdata.get("missions_done", 0)
        target = step.get("objective_data", {}).get("target", 3)
        hint = hint.replace("{missions_done}", str(done))
        hint = hint.replace("{target}", str(target))
    if "{contacts_status}" in hint:
        contacts = sdata.get("contacts_made", [])
        target_npcs = step.get("objective_data", {}).get("npcs", [])
        status = ", ".join(
            f"{'✓' if n in contacts else '○'} {n.title()}"
            for n in target_npcs
        )
        hint = hint.replace("{contacts_status}", status)
    if "{planets_visited_status}" in hint:
        visited = sdata.get("planets_landed", [])
        all_planets = step.get("objective_data", {}).get("planets", [])
        status = ", ".join(
            f"{'✓' if p in visited else '○'} {p.replace('_', ' ').title()}"
            for p in all_planets
        )
        hint = hint.replace("{planets_visited_status}", status)
    if "{multi_status}" in hint:
        done = sdata.get("completed", [])
        hint = hint.replace("{multi_status}", ", ".join(done) if done else "none yet")

    lines = [
        f"{'='*63}",
        f"  {_BOLD}FROM DUST TO STARS{_RESET} — Phase {phase}: {phase_name}",
        f"  Step {step_id} of 30: \"{step['title']}\"",
        f"{'='*63}",
        f"",
        f"  {step.get('objective_desc', '')}",
    ]
    if hint:
        lines.append(f"  {_DIM}Hint: {hint}{_RESET}")
    lines.extend([
        f"",
        f"  Progress:  {bar}  {completed}/30 (Phase {phase}/5)",
        f"  Credits earned: {total_credits:,}",
        f"{'='*63}",
    ])
    return "\n".join(lines)


def format_quest_log(char: dict) -> str:
    """Build the +quest log display."""
    qs = _get_quest_state(char)
    if qs is None:
        return "  No quest history."

    completed = qs.get("completed_steps", [])
    if not completed:
        return "  No steps completed yet."

    lines = [f"  {_BOLD}Quest Log — From Dust to Stars{_RESET}", ""]
    for sid in completed:
        step = get_step(sid)
        if step:
            cr = step.get("reward_credits", 0)
            cr_str = f" (+{cr:,}cr)" if cr > 0 else ""
            lines.append(
                f"  {_SUCCESS}✓{_RESET} Step {sid}: {step['title']}{cr_str}")
    return "\n".join(lines)
