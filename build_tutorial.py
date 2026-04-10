#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_tutorial.py — Build all SW_MUSH tutorial zones.  [v22 — Drop 22]

Run AFTER build_mos_eisley.py (requires the DB and Mos Eisley rooms to exist).
Safe to re-run: create_room / create_npc / create_exit all have duplicate guards.

Creates
-------
CORE TUTORIAL (was already here, preserved):
  Zone: "Tutorial -- The Arrival"
  6 rooms: Landing Pad > Desert Trail > Rocky Pass >
           Ambush Point > Desert Road > Mos Eisley Gate
  NPCs:  Kessa Dray (Desert Trail + Cantina copy), Sand Raider (Ambush Point)
  Exit:  Mos Eisley Gate -> Mos Eisley live world

TRAINING GROUNDS HUB (new in Drop 22):
  Zone: "Training Grounds"
  1 hub room: "Training Grounds"
  8 entry rooms (one per elective module):
    Space Academy, Combat Arena, Trader's Hall, Crafter's Workshop,
    Jedi Enclave, Bounty Office, Crew Quarters, Galactic Factions Briefing Room
  1 NPC per entry room (module guide)
  Exits: hub <-> each entry room, entry rooms -> hub (back)
  Faction Recruitment Board: static object in the hub

Usage:
    python build_tutorial.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tprops(**extra):
    """Return tutorial_zone=True props JSON with optional extras."""
    d = {"tutorial_zone": True, "cover_max": 1}
    d.update(extra)
    return json.dumps(d)


def _sheet(**attrs):
    return json.dumps(attrs)


def _ai(personality, knowledge, role="guide", module="hub", hostile=False, aggression=0):
    return json.dumps({
        "personality": personality,
        "knowledge": knowledge,
        "tutorial_npc": True,
        "tutorial_module": module,
        "tutorial_role": role,
        "hostile": hostile,
        "aggression": aggression,
    })


# ---------------------------------------------------------------------------
# Core tutorial (preserved from v17, idempotent)
# ---------------------------------------------------------------------------

async def build_core_tutorial(db):
    print("\n[1/2] Core tutorial zone...")

    # Zone — skip if already exists
    existing_zones = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1",
        ("Tutorial -- The Arrival",),
    )
    if existing_zones:
        zone_id = existing_zones[0]["id"]
        print(f"  Zone already exists: id={zone_id} (skipping room creation)")
        # Still re-check/create the Mos Eisley Gate exit in case it's missing
        _gate_rows = await db._db.execute_fetchall(
            "SELECT id FROM rooms WHERE name = 'Mos Eisley Gate' "
            "AND properties LIKE '%tutorial_zone%' ORDER BY id LIMIT 1"
        )
        if _gate_rows:
            gate_id = _gate_rows[0]["id"]
            me_entry_rows = await db._db.execute_fetchall(
                "SELECT id FROM rooms WHERE name = ? ORDER BY id LIMIT 1",
                ("Docking Bay Entrance",),
            )
            if not me_entry_rows:
                me_entry_rows = await db._db.execute_fetchall(
                    "SELECT id FROM rooms WHERE properties NOT LIKE '%tutorial_zone%' "
                    "ORDER BY id LIMIT 1"
                )
            if me_entry_rows:
                me_entry_id = me_entry_rows[0]["id"]
                await db.create_exit(gate_id, me_entry_id, "north")
        return  # rooms/NPCs already built

    zone_id = await db.create_zone(
        "Tutorial -- The Arrival",
        properties=json.dumps({
            "environment":   "desert",
            "security":      "contested",
            "tutorial_zone": True,
            "lighting":      "bright",
            "gravity":       "standard",
        }),
    )
    print(f"  Zone created: id={zone_id}")

    rooms_data = [
        (
            "Landing Pad",
            "A dusty landing pad at the edge of the Dune Sea.",
            (
                "The transport that brought you here has already lifted off, "
                "leaving nothing but a cloud of sand and the smell of exhaust. "
                "A weathered sign reads: MOS EISLEY -- 3km EAST. "
                "The desert stretches in all directions. "
                "Exits lead east toward the city."
            ),
        ),
        (
            "Desert Trail",
            "A sandy trail winding through the Dune Sea.",
            (
                "The Tatooine suns beat down mercilessly. The trail ahead "
                "is marked by repulsorlift skid marks and the occasional bleached "
                "bone of something large. A local guide rests in the shade of a "
                "rock outcropping, watching you with sharp eyes. "
                "The trail continues east. The landing pad is west."
            ),
        ),
        (
            "Rocky Pass",
            "A narrow pass through sandstone ridges.",
            (
                "The rock walls on either side press close, funnelling a hot "
                "desert wind through the gap. The stones here are carved with "
                "old markings -- Tusken trail signs, maybe. "
                "Something glints in the sand near the south wall. "
                "The trail continues east toward the city, or back west to the landing pad."
            ),
        ),
        (
            "Ambush Point",
            "A wide flat stretch -- exposed and dangerous.",
            (
                "The rocky pass opens onto a flat expanse of hard-packed sand. "
                "There's no cover here, nowhere to run. A figure steps out from "
                "behind a boulder -- a Sand Raider, wrapped in dirty robes, "
                "clutching a vibroknife. He eyes your equipment hungrily. "
                "The city is visible on the horizon to the east, but you'll have "
                "to deal with this problem first."
            ),
        ),
        (
            "Desert Road",
            "The outskirts road leading to Mos Eisley.",
            (
                "The hard-packed sand gives way to a rutted road of ancient "
                "durasteel plates. Ahead, the sprawling white domes of Mos Eisley "
                "shimmer in the heat. You can see the main gate ahead. "
                "The raider is behind you now. The city is east."
            ),
        ),
        (
            "Mos Eisley Gate",
            "The main gate of Mos Eisley Spaceport.",
            (
                "Two Stormtroopers stand at lazy attention outside the gate, "
                "more interested in the shade than in inspecting travelers. "
                "The city opens up ahead -- a maze of white dome-capped buildings, "
                "market stalls, and the constant distant roar of ion engines. "
                "Your contact, Kessa, said to find her at Chalmun's Cantina. "
                "Step north to enter the city."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(
            name=name, desc_short=short, desc_long=long,
            zone_id=zone_id, properties=_tprops(),
        )
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")

    # Exits
    await db.create_exit(room_ids[0], room_ids[1], "east")
    await db.create_exit(room_ids[1], room_ids[0], "west")
    await db.create_exit(room_ids[1], room_ids[2], "east")
    await db.create_exit(room_ids[2], room_ids[1], "west")
    await db.create_exit(room_ids[2], room_ids[3], "east")
    await db.create_exit(room_ids[3], room_ids[4], "east")
    await db.create_exit(room_ids[4], room_ids[5], "east")

    # Gate -> live world
    me_entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? ORDER BY id LIMIT 1",
        ("Docking Bay Entrance",),
    )
    if not me_entry_rows:
        me_entry_rows = await db._db.execute_fetchall(
            "SELECT id FROM rooms WHERE properties NOT LIKE '%tutorial_zone%' "
            "ORDER BY id LIMIT 1"
        )
    me_entry_id = me_entry_rows[0]["id"] if me_entry_rows else 1
    await db.create_exit(room_ids[5], me_entry_id, "north")
    print(f"  Exit: Mos Eisley Gate -> room {me_entry_id} (live world)")

    # NPCs
    kessa_sheet = _sheet(
        dexterity="3D", knowledge="4D", mechanical="2D",
        perception="4D", strength="2D+2", technical="2D",
        skills={"con": "5D", "streetwise": "5D", "persuasion": "4D"},
        wound_level=0, species="Human",
    )
    kessa_ai = _ai(
        personality=(
            "Kessa Dray is a sharp-tongued, resourceful smuggler who's seen "
            "everything Mos Eisley has to offer and survived most of it. "
            "She's helping the new arrival because she owes their contact a favor. "
            "She's warm but businesslike, gives practical advice, knows every corner "
            "of Mos Eisley, and has no patience for whining or hesitation."
        ),
        knowledge=(
            "She can explain how to move around Mos Eisley, how combat works, "
            "where to find missions, how to buy equipment, and the basics of "
            "smuggling. She'll tell players to check 'help <topic>' for detailed "
            "rules and recommend they visit the Training Grounds for practice. "
            "Key commands to mention: look, east/west/north/south, talk, +sheet, "
            "+inv, attack, dodge, +missions, training."
        ),
        module="core",
    )
    kessa_desc = (
        "A lean human woman in her late thirties, wearing patched smuggler's "
        "gear and a battered blaster holster. She has calculating eyes and "
        "a half-smile that suggests she's already figured out five exits from "
        "this conversation."
    )
    kessa_id = await db.create_npc(
        name="Kessa Dray", room_id=room_ids[1], species="Human",
        description=kessa_desc,
        char_sheet_json=kessa_sheet, ai_config_json=kessa_ai,
    )
    print(f"  NPC {kessa_id}: Kessa Dray (Desert Trail)")

    cantina_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name LIKE ? ORDER BY id LIMIT 1",
        ("%Cantina%",),
    )
    if cantina_rows:
        cantina_id = cantina_rows[0]["id"]
        kessa_cantina_id = await db.create_npc(
            name="Kessa Dray", room_id=cantina_id, species="Human",
            description=(
                "Kessa Dray sits at a corner table, nursing something amber and "
                "keeping one eye on every entrance. She waves you over."
            ),
            char_sheet_json=kessa_sheet, ai_config_json=kessa_ai,
        )
        print(f"  NPC {kessa_cantina_id}: Kessa Dray (Cantina, room {cantina_id})")

    raider_sheet = _sheet(
        dexterity="2D", knowledge="1D", mechanical="1D",
        perception="2D", strength="3D", technical="1D",
        skills={"melee combat": "3D", "brawling": "3D"},
        wound_level=0, species="Human",
        weapons=[{"name": "Vibroknife", "skill": "melee combat", "damage": "STR+1D"}],
    )
    raider_ai = _ai(
        personality="A desperate Sand Raider looking for easy prey.",
        knowledge="He knows only violence.",
        role="opponent", module="core", hostile=True, aggression=10,
    )
    raider_id = await db.create_npc(
        name="Sand Raider", room_id=room_ids[3], species="Human",
        description=(
            "A weathered figure wrapped in sun-bleached robes, face hidden behind "
            "a sand-scoured visor. He holds a vibroknife loosely -- the posture of "
            "someone who's done this before."
        ),
        char_sheet_json=raider_sheet, ai_config_json=raider_ai,
    )
    print(f"  NPC {raider_id}: Sand Raider (Ambush Point)")
    print(f"  Core tutorial rooms: {room_ids}")
    print(f"  Players start at room {room_ids[0]} (Landing Pad)")


# ---------------------------------------------------------------------------
# Training Grounds hub + elective entry rooms  (Drop 22)
# ---------------------------------------------------------------------------

async def build_training_grounds(db):
    print("\n[2/2] Training Grounds hub + elective entry rooms...")

    # Zone
    existing = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1",
        ("Training Grounds",),
    )
    if existing:
        tg_zone_id = existing[0]["id"]
        print(f"  Zone already exists: id={tg_zone_id}")
    else:
        tg_zone_id = await db.create_zone(
            "Training Grounds",
            properties=json.dumps({
                "environment":   "interior",
                "security":      "safe",
                "tutorial_zone": True,
                "lighting":      "bright",
                "gravity":       "standard",
            }),
        )
        print(f"  Zone created: id={tg_zone_id}")

    tg_props = _tprops(environment="interior", security="safe")

    # ------------------------------------------------------------------
    # Hub room
    # ------------------------------------------------------------------
    hub_id = await db.create_room(
        name="Training Grounds",
        desc_short="The Spacer's Guild Training Center -- a well-lit facility near the docks.",
        desc_long=(
            "A clean, well-lit facility on the edge of the Docking Bay district. "
            "Holoprojectors line the walls cycling through recruitment notices for "
            "various guilds and factions. A polished protocol droid stands at a "
            "reception desk, ready to direct newcomers. \n\n"
            "Several reinforced doors lead to specialized training areas. "
            "A brass plaque reads: 'All training programs are voluntary and "
            "self-paced. Complete any program to receive your Guild certification.'\n\n"
            "A recruitment board on the south wall lists active faction opportunities. "
            "Type \033[1;33mlook board\033[0m to read it.\n\n"
            "Exits: \033[1;33mspace\033[0m Space Academy  "
            "\033[1;33mcombat\033[0m Combat Arena  "
            "\033[1;33meconomy\033[0m Trader's Hall\n"
            "       \033[1;33mcrafting\033[0m Crafter's Workshop  "
            "\033[1;33mbounty\033[0m Bounty Office  "
            "\033[1;33mcrew\033[0m Crew Quarters\n"
            "       \033[1;33mfactions\033[0m Galactic Factions Briefing  "
            "\033[1;33mout\033[0m Back to Mos Eisley"
        ),
        zone_id=tg_zone_id,
        properties=tg_props,
    )
    print(f"  Room {hub_id}: Training Grounds (hub)")

    # Protocol droid receptionist
    droid_sheet = _sheet(
        dexterity="1D", knowledge="5D", mechanical="1D",
        perception="3D", strength="1D", technical="2D",
        skills={"languages": "6D", "cultures": "5D", "bureaucracy": "4D"},
        wound_level=0, species="Droid",
    )
    droid_ai = _ai(
        personality=(
            "A cheerful 3PO-series protocol droid designated T-7 'Tessie'. "
            "Warm, organized, slightly over-enthusiastic about record-keeping. "
            "Knows every module, every instructor, every room in the facility. "
            "Always refers to instructors by rank and name."
        ),
        knowledge=(
            "Can explain all training modules (space, combat, economy, crafting, "
            "force, bounty, crew, factions), their entry requirements, rewards, "
            "and which instructor runs each. Can check training status for the "
            "player ('training list'). Recommends starting with the core tutorial "
            "if not yet complete. Knows that the Jedi Enclave requires Force sensitivity."
        ),
        module="hub",
    )
    droid_id = await db.create_npc(
        name="T-7 Protocol Droid",
        room_id=hub_id,
        species="Droid",
        description=(
            "A golden protocol droid with a slightly dented left photoreceptor "
            "and a cheerful tilt to its head. A small brass name plate reads "
            "'T-7 -- Enrollment & Directions'."
        ),
        char_sheet_json=droid_sheet,
        ai_config_json=droid_ai,
    )
    print(f"  NPC {droid_id}: T-7 Protocol Droid (hub)")

    # ------------------------------------------------------------------
    # Elective entry rooms + instructors
    # ------------------------------------------------------------------
    # Each tuple: (exit_dir, room_name, short_desc, long_desc, instructor_data)
    # instructor_data: (name, species, description, sheet_dict, ai_personality, ai_knowledge)

    elective_rooms = [

        # SPACE ACADEMY
        (
            "space",
            "Space Academy",
            "A flight simulator bay staffed by an old Rebel pilot.",
            (
                "The Space Academy is housed in a converted hangar bay. "
                "Rows of flight simulator pods line the walls, their canopies "
                "open and waiting. Holographic star maps cover the ceiling. "
                "The smell of machine oil and recycled atmosphere is oddly comforting. "
                "Commander Dex stands by a briefing lectern, arms crossed.\n\n"
                "Type \033[1;33mtalk dex\033[0m to begin your flight orientation.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Commander Dex", "Human",
                (
                    "A weathered human male in his late fifties, still wearing "
                    "a faded Rebel Alliance flight suit with the squadron patches "
                    "picked off. His eyes have the thousand-yard stare of someone "
                    "who's flown too many combat sorties. A small smile suggests "
                    "he's glad to be teaching instead."
                ),
                _sheet(
                    dexterity="3D+2", knowledge="3D", mechanical="5D",
                    perception="3D", strength="2D+2", technical="3D+1",
                    skills={"piloting": "7D", "astrogation": "5D",
                            "starship gunnery": "5D", "shields": "4D",
                            "sensors": "4D", "starship repair": "4D"},
                    wound_level=0, species="Human",
                ),
                (
                    "Commander Dex is a gruff, no-nonsense retired Rebel Alliance "
                    "pilot who's seen too many good pilots die because they didn't "
                    "know what they were doing. He teaches because he doesn't want "
                    "to see that anymore. Laconic, direct, impatient with excuses. "
                    "Respects competence, not rank."
                ),
                (
                    "Teaches: piloting, astrogation, ship combat (fire, evade, lockon, "
                    "shields, damcon), zone movement, hyperspace jumps, scanning, "
                    "docking. Can explain all +ship commands. Points to Docking Bay "
                    "for ship purchases. Mentions +smugjobs for first cargo runs."
                ),
            ),
        ),

        # COMBAT ARENA
        (
            "combat",
            "Combat Arena",
            "A sparring ring run by a taciturn Mandalorian veteran.",
            (
                "The Combat Arena smells of sweat and ozone. A regulation sparring "
                "ring occupies the center -- durasteel mesh floor, impact-absorbing "
                "walls, and a rack of practice weapons along the south side. "
                "Targeting dummies stand at the ready in the far corners. "
                "A Mandalorian in worn beskar armor watches you from the far end, "
                "arms folded, expression unreadable.\n\n"
                "Type \033[1;33mtalk ordo\033[0m to begin combat training.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Ordo", "Human",
                (
                    "A broad-shouldered Mandalorian in battered beskar plate, "
                    "the sigil of House Ordo barely visible under layers of "
                    "campaign scratches. No helmet -- just a weathered face and "
                    "eyes that are always calculating angles and distances. "
                    "He carries a vibroknife on each hip. He doesn't introduce himself."
                ),
                _sheet(
                    dexterity="4D", knowledge="2D", mechanical="2D+2",
                    perception="3D+1", strength="4D", technical="2D",
                    skills={"blaster": "6D", "melee combat": "7D",
                            "brawling": "6D", "dodge": "5D+2",
                            "intimidation": "5D"},
                    wound_level=0, species="Human",
                ),
                (
                    "Ordo is a Mandalorian warrior of few words and precise action. "
                    "He teaches by demonstrating, not lecturing. When he does speak, "
                    "it's to correct a mistake or praise a correct action. He has no "
                    "patience for questions he considers stupid, but will repeat "
                    "a correct answer if asked sincerely. He respects any student "
                    "who takes a hit without flinching."
                ),
                (
                    "Teaches: attack, dodge, fulldodge, aim, parry, flee, multi-action "
                    "penalties, cover mechanics, range bands, wound levels, melee vs "
                    "ranged tradeoffs, initiative. Can explain the full WEG D6 combat "
                    "sequence. Points to +missions for combat-paying work."
                ),
            ),
        ),

        # TRADER'S HALL
        (
            "economy",
            "Trader's Hall",
            "A busy commerce training floor run by an enthusiastic Rodian.",
            (
                "The Trader's Hall looks like a miniature marketplace -- vendor stalls "
                "line the walls, a mission board holoprojector glows in the center, "
                "and a well-dressed Rodian in a merchant's sash is already gesturing "
                "at you from across the room, apparently mid-pitch before you even "
                "walked in.\n\n"
                "Type \033[1;33mtalk greelo\033[0m to begin commerce training.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Greelo", "Rodian",
                (
                    "A bright-eyed Rodian in a green-and-gold merchant's sash, "
                    "fingers always moving, snout twitching with enthusiasm. "
                    "He wears enough rings to suggest he's done very well for himself, "
                    "and he wants you to do well too -- because your success is, "
                    "in some roundabout way, always good for business."
                ),
                _sheet(
                    dexterity="2D+1", knowledge="4D", mechanical="2D",
                    perception="4D+2", strength="2D", technical="2D+2",
                    skills={"bargain": "6D", "con": "5D", "streetwise": "5D",
                            "value": "5D+2", "persuasion": "4D+2"},
                    wound_level=0, species="Rodian",
                ),
                (
                    "Greelo is fast-talking, relentlessly upbeat, and genuinely "
                    "enthusiastic about credits and commerce. He views every transaction "
                    "as a puzzle and every player as a potential partner. He will "
                    "complain about Imperial tariffs unprompted. He is fond of the "
                    "phrase 'that's what I call a deal.' Faction missions pay 25% more "
                    "-- he will mention this unprompted and emphatically."
                ),
                (
                    "Teaches: buy, sell, +credits, Bargain skill, +missions, +smugjobs, "
                    "+bounties, accept, complete, abandon, smugaccept, smugdeliver, "
                    "risk tiers, the Traders Coalition, faction mission bonuses. "
                    "Explains how credits flow: missions -> ship -> more missions. "
                    "Points toward the Docking Bay for ship purchases."
                ),
            ),
        ),

        # CRAFTER'S WORKSHOP
        (
            "crafting",
            "Crafter's Workshop",
            "A well-equipped fabrication bay run by a patient Duros engineer.",
            (
                "The Crafter's Workshop is part laboratory, part machine shop. "
                "Workbenches are covered in partially assembled components. "
                "A bank of raw material lockers lines one wall; a schematic "
                "projector dominates another. The air smells of solder and "
                "cutting lubricant. A Duros engineer looks up from a workbench "
                "and nods a greeting.\n\n"
                "Type \033[1;33mtalk vek\033[0m to begin crafting training.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Vek Nurren", "Duros",
                (
                    "A methodical Duros engineer with long, nimble fingers and "
                    "ink-stained sleeves. He speaks slowly and precisely, never "
                    "uses two words where one will do, and has an engineer's "
                    "absolute confidence that every problem has a correct solution "
                    "if you follow the right process."
                ),
                _sheet(
                    dexterity="2D", knowledge="3D+2", mechanical="3D",
                    perception="3D", strength="2D+1", technical="6D",
                    skills={"repair": "7D", "demolitions": "4D",
                            "computer programming/repair": "5D",
                            "medicine": "3D+2", "blaster repair": "5D"},
                    wound_level=0, species="Duros",
                ),
                (
                    "Vek Nurren is patient, methodical, and mildly contemptuous of "
                    "people who try to skip steps. He believes that understanding "
                    "the process is more important than the result. He'll walk a "
                    "student through the same step twice without complaint, but "
                    "will visibly suppress irritation if they ask the same question "
                    "three times. Proud of high-quality work."
                ),
                (
                    "Teaches: survey, resource types and quality, gather, +schematics, "
                    "craft, assembly steps, repair, the Technical skill family. "
                    "Can explain all schematics in the DB. Mentions guild schematics "
                    "are restricted to Mechanics Guild and Shipwrights Guild members. "
                    "Points to Shipwright Venn Kator for ship component commissions."
                ),
            ),
        ),

        # JEDI ENCLAVE
        (
            "force",
            "Jedi Enclave",
            "A quiet chamber that seems to exist slightly outside the normal world.",
            (
                "The Jedi Enclave is accessible only to those who can feel the Force. "
                "The room is spare -- stone walls, a single lamp, and a low table "
                "on which rests an ancient Holocron, its facets catching the light "
                "and throwing it somewhere else entirely. "
                "The air is very still. "
                "You feel, faintly, that something in this room is listening.\n\n"
                "Type \033[1;33mtalk holocron\033[0m to begin Force training.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Holocron", "Droid",
                (
                    "The Holocron projects a faint blue image -- a robed figure of "
                    "indeterminate age and species. It speaks rarely and precisely. "
                    "Every word is weighed."
                ),
                _sheet(
                    dexterity="1D", knowledge="6D", mechanical="1D",
                    perception="5D", strength="1D", technical="3D",
                    skills={"scholar (force lore)": "8D", "languages": "6D",
                            "cultures": "6D"},
                    wound_level=0, species="Droid",
                ),
                (
                    "The Holocron is calm, ancient, and occasionally cryptic. It "
                    "does not volunteer information -- it responds to questions. "
                    "When it does speak at length, it speaks in careful, balanced "
                    "sentences that weigh both the light and dark sides. It will "
                    "not urge any particular path. It believes the student must "
                    "choose. It occasionally pauses for three to five seconds "
                    "before responding, as if listening to something the student cannot hear."
                ),
                (
                    "Teaches: Force sensitivity check, force_points, dark_side_points, "
                    "Force skills (sense, alter, control), Force power costs, the "
                    "dark side temptation mechanic, Jedi Code context (historical, "
                    "not dogmatic). Can explain any Force power in the DB. "
                    "Will not teach Force powers directly -- points to seeking a "
                    "living teacher in the galaxy for hands-on training."
                ),
            ),
        ),

        # BOUNTY OFFICE
        (
            "bounty",
            "Bounty Office",
            "A utilitarian briefing room staffed by a professional Trandoshan.",
            (
                "The Bounty Office is spare and functional -- a briefing table, "
                "a holo-display showing wanted postings across four systems, and "
                "a rack of restraint equipment on the far wall. Everything is "
                "organized with military precision. A Trandoshan in contractor's "
                "armor looks up from a datapad and studies you without expression.\n\n"
                "Type \033[1;33mtalk ssk'rath\033[0m to begin bounty hunting training.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Ssk'rath", "Trandoshan",
                (
                    "A lean, scarred Trandoshan in worn contractor's armor -- "
                    "not showy, but functional. Every piece of kit on his body "
                    "earns its place. His eyes are cold and professionally neutral. "
                    "He doesn't hate you. He doesn't like you. You're either "
                    "capable or you're not."
                ),
                _sheet(
                    dexterity="3D+2", knowledge="2D+2", mechanical="2D+1",
                    perception="4D", strength="4D+1", technical="2D",
                    skills={"blaster": "5D+2", "search": "6D", "tracking": "6D",
                            "intimidation": "5D", "brawling": "5D",
                            "streetwise": "4D+2"},
                    wound_level=0, species="Trandoshan",
                ),
                (
                    "Ssk'rath is professional, pragmatic, and respects demonstrated "
                    "skill. He has no patience for ego or posturing, but will "
                    "acknowledge competence plainly: 'that works.' He explains "
                    "bounty hunting as a business, not an adventure. "
                    "He takes failure analysis seriously -- if a hunt goes wrong, "
                    "he wants to understand why. He is quietly proud of his "
                    "zero-target-loss record."
                ),
                (
                    "Teaches: +bounties, bountyclaim, bountytrack, bountycollect, "
                    "bountyabandon, search skill, tracking, the Bounty Hunters Guild, "
                    "restraint equipment (binder cuffs), target alive vs dead "
                    "payout difference, warrant types, working with vs against "
                    "local law enforcement. Points to bounty board at Police Station."
                ),
            ),
        ),

        # CREW QUARTERS
        (
            "crew",
            "Crew Quarters",
            "A comfortable briefing lounge staffed by a retired freighter captain.",
            (
                "The Crew Quarters training room is designed to look like the "
                "common area of a well-kept freighter -- padded benches, a "
                "sabacc table in the corner, a small galley unit. "
                "The effect is deliberately homey. A human woman in her sixties "
                "with the bearing of someone who has been giving orders for forty "
                "years sits at the head of the table with a cup of caf.\n\n"
                "Type \033[1;33mtalk mora\033[0m to begin crew management training.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "Captain Mora", "Human",
                (
                    "A trim human woman in her sixties with silver-streaked hair "
                    "and the unhurried manner of someone who has commanded "
                    "vessels for four decades. She wears no uniform but carries "
                    "herself like she's still on the bridge."
                ),
                _sheet(
                    dexterity="2D+1", knowledge="4D", mechanical="3D+2",
                    perception="4D+1", strength="2D", technical="3D",
                    skills={"command": "6D", "bargain": "4D+2",
                            "persuasion": "5D", "scholar (regulations)": "5D",
                            "bureaucracy": "4D+2"},
                    wound_level=0, species="Human",
                ),
                (
                    "Captain Mora is warm, measured, and fond of stories that "
                    "illustrate a point. She's seen good captains and bad captains "
                    "and knows the difference is almost never about ship-handling. "
                    "She believes strongly in crew loyalty and mutual responsibility. "
                    "She has no patience for captains who treat their crew as "
                    "equipment. She will occasionally drift into an anecdote and "
                    "then catch herself and return to the lesson."
                ),
                (
                    "Teaches: +crew, hire, fire, assign, crew wage system, "
                    "crewing roles (pilot, gunner, engineer, medic), morale, "
                    "the Command skill, crew loyalty checks, how crew skill "
                    "dice contribute to ship operations. Points to Mos Eisley "
                    "cantina as the best place to find crew. Notes the Crew "
                    "Quarters elective reward: 24h wage-free NPC hire."
                ),
            ),
        ),

        # GALACTIC FACTIONS BRIEFING ROOM
        (
            "factions",
            "Galactic Factions Briefing Room",
            "A holoprojector briefing room staffed by an impartial protocol droid.",
            (
                "The Galactic Factions Briefing Room is dominated by a central "
                "holoprojector cycling through faction emblems: Imperial cog, "
                "Rebel starbird, Hutt seal, Traders' Coalition mark, and others. "
                "The walls display detailed faction org charts and known territory. "
                "A silver protocol droid stands at the projector controls, "
                "posture precisely neutral.\n\n"
                "Type \033[1;33mtalk c-4po\033[0m to begin the faction briefing.\n"
                "Type \033[1;33mlook board\033[0m to see the example job board.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
            (
                "C-4PO", "Droid",
                (
                    "A silver protocol droid with a deliberately neutral affect. "
                    "Every statement is hedged with 'according to available data' "
                    "or 'from the perspective of.' It presents information about "
                    "factions the way a librarian presents books -- without judgment, "
                    "without recommendation, without visible opinion."
                ),
                _sheet(
                    dexterity="1D", knowledge="5D+2", mechanical="1D",
                    perception="3D", strength="1D", technical="2D",
                    skills={"languages": "7D", "cultures": "6D",
                            "scholar (galactic politics)": "6D",
                            "bureaucracy": "5D"},
                    wound_level=0, species="Droid",
                ),
                (
                    "C-4PO is programmed to provide impartial information about "
                    "the six major factions (Galactic Empire, Rebel Alliance, "
                    "Hutt Cartel, Traders' Coalition, Bounty Hunters Guild, "
                    "Crimson Dawn/Underworld) and the six guilds (Mechanics, "
                    "Shipwrights, Medics, Slicers, Entertainers, Scouts). "
                    "Never advocates for any faction. For each faction covers: "
                    "who they are, what members receive, who they oppose, how "
                    "to earn standing. Notes that faction missions pay 25% more "
                    "than public boards. Explains that guild membership provides "
                    "skill discounts and restricted schematics. Notes that players "
                    "may join one faction and up to three guilds."
                ),
            ),
        ),
    ]

    hub_exit_names = {
        "space": "Space Academy",
        "combat": "Combat Arena",
        "economy": "Trader's Hall",
        "crafting": "Crafter's Workshop",
        "force": "Jedi Enclave",
        "bounty": "Bounty Office",
        "crew": "Crew Quarters",
        "factions": "Galactic Factions Briefing Room",
    }

    for (exit_dir, room_name, short_desc, long_desc,
         (npc_name, npc_species, npc_desc, npc_sheet, npc_personality, npc_knowledge)
         ) in elective_rooms:

        room_id = await db.create_room(
            name=room_name,
            desc_short=short_desc,
            desc_long=long_desc,
            zone_id=tg_zone_id,
            properties=tg_props,
        )
        print(f"  Room {room_id}: {room_name}")

        # Hub <-> elective exits
        await db.create_exit(hub_id, room_id, exit_dir)
        await db.create_exit(room_id, hub_id, "out")
        print(f"    Exit: hub --{exit_dir}--> room {room_id}; room --out--> hub")

        # Module guide NPC
        npc_ai = _ai(
            personality=npc_personality,
            knowledge=npc_knowledge,
            role="guide",
            module=exit_dir,
        )
        npc_id = await db.create_npc(
            name=npc_name,
            room_id=room_id,
            species=npc_species,
            description=npc_desc,
            char_sheet_json=npc_sheet,
            ai_config_json=npc_ai,
        )
        print(f"    NPC {npc_id}: {npc_name} ({room_name})")

    # ------------------------------------------------------------------
    # Training Grounds hub -> Mos Eisley exit
    # ------------------------------------------------------------------
    me_exit_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? ORDER BY id LIMIT 1",
        ("Docking Bay Entrance",),
    )
    if not me_exit_rows:
        me_exit_rows = await db._db.execute_fetchall(
            "SELECT id FROM rooms WHERE properties NOT LIKE '%tutorial_zone%' "
            "ORDER BY id LIMIT 1"
        )
    if me_exit_rows:
        me_id = me_exit_rows[0]["id"]
        await db.create_exit(hub_id, me_id, "out")
        print(f"  Exit: Training Grounds hub --out--> room {me_id} (Mos Eisley)")

    print(f"\n  Training Grounds hub room id: {hub_id}")
    print("  Use 'training' command to teleport here from anywhere.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Space Academy -- full 6-room chain  (Drop 25)
# ---------------------------------------------------------------------------

async def build_space_academy(db):
    print("\n[3/3] Space Academy rooms...")

    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1",
        ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found.")
        return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")

    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1",
        ("Space Academy",),
    )
    if not entry_rows:
        print("  ERROR: Space Academy entry room not found.")
        return
    entry_id = entry_rows[0]["id"]

    rooms_data = [
        (
            "Space Academy Briefing Room",
            "A flight briefing room with holographic star charts.",
            (
                "The briefing room is spare and functional -- a central "
                "holographic projector cycles through star maps, ship silhouettes, "
                "and zone diagrams. Commander Dex stands at the projector controls, "
                "arms crossed, waiting for you to sit down.\n\n"
                "The star maps show Tatooine system: the planet, two moons, "
                "orbital approach lanes, and the deep space zones beyond. "
                "A display panel lists available ship types and statistics.\n\n"
                "Type \033[1;33mtalk dex\033[0m to begin.\n"
                "Type \033[1;33m+ships\033[0m to browse vessel types.\n"
                "Exit \033[1;33mforward\033[0m leads to the simulator when Dex clears you."
            ),
        ),
        (
            "Space Academy Simulator Bay",
            "A hangar-sized simulator with a docked training freighter.",
            (
                "The simulator bay is enormous -- a full-scale replica of a docking "
                "bay, complete with deck plating and a battered YT-1300 on the pad. "
                "The ship looks real. Only the faint shimmer at the edges betrays "
                "the holographic nature. A technician droid waits by the ramp.\n\n"
                "No fuel cost, no docking fees, ship cannot be permanently destroyed.\n\n"
                "Type \033[1;33mboard training freighter\033[0m to board.\n"
                "Once aboard: \033[1;33mpilot\033[0m to take the helm.\n"
                "Then: \033[1;33mlaunch\033[0m to lift off."
            ),
        ),
        (
            "Space Academy Training Orbit",
            "Low training orbit above Tatooine -- safe and monitored.",
            (
                "Twin suns cast long shadows across the sand seas below. "
                "You are in low orbit, the atmosphere a thin blue-white line. "
                "Dex on comm: 'Good lift. Now let\'s see if you can fly this thing.'\n\n"
                "No NPC traffic, no fuel burn, no maneuver damage in this zone.\n\n"
                "Try: \033[1;33mscan\033[0m to check what\'s in range.\n"
                "Try: \033[1;33m+status\033[0m to check ship systems.\n"
                "Type \033[1;33mcourse hyperspace_lane\033[0m when ready to proceed."
            ),
        ),
        (
            "Space Academy Hyperspace Training Lane",
            "A short hyperspace training corridor -- safe jump.",
            (
                "Stars stretch and compress as the ship drops into hyperspace. "
                "Blue-white streaks extend to infinity. Dex: 'Short hop. One "
                "parsec. Bring us back in one piece.'\n\n"
                "No misjump risk in the training lane. In real space, bad "
                "astrogation rolls can send you somewhere unexpected.\n\n"
                "Check astrogation: \033[1;33mastrogate\033[0m\n"
                "Drop to realspace: \033[1;33mhyperspace\033[0m (again to exit)"
            ),
        ),
        (
            "Space Academy Combat Training Zone",
            "A combat simulation zone -- pirate target drone in range.",
            (
                "The simulation has changed. A pirate interceptor has just lit "
                "its engines in your direction. Dex: 'Weapons free.'\n\n"
                "The pirate drone is calibrated to land some hits -- shields "
                "and repair matter here.\n\n"
                "Acquire target: \033[1;33mlockon pirate\033[0m\n"
                "Fire weapons:   \033[1;33mfire\033[0m\n"
                "Dodge incoming: \033[1;33mevade\033[0m\n"
                "Manage shields: \033[1;33mshields fore\033[0m / \033[1;33mshields balanced\033[0m\n"
                "Repair damage:  \033[1;33mdamcon\033[0m"
            ),
        ),
        (
            "Space Academy Graduation Hall",
            "The Academy graduation bay -- Dex waits with your certification.",
            (
                "The simulation has ended. You are back in the Academy facility, "
                "in a small ceremony room. Commander Dex stands at parade rest "
                "holding a datacard -- your pilot certification.\n\n"
                "He doesn\'t smile exactly. But the set of his shoulders has changed.\n\n"
                "Type \033[1;33mtalk dex\033[0m to receive your certification.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(
            name=name, desc_short=short, desc_long=long,
            zone_id=tg_zone_id, properties=tg_props,
        )
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")

    # Exits: linear forward/back chain
    await db.create_exit(entry_id, room_ids[0], "forward")
    await db.create_exit(room_ids[0], entry_id, "back")
    for i in range(len(room_ids) - 1):
        await db.create_exit(room_ids[i], room_ids[i + 1], "forward")
        await db.create_exit(room_ids[i + 1], room_ids[i], "back")
    print(f"  Exits: linear chain forward/back")

    # Graduation -> hub "out"
    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(room_ids[-1], hub_rows[0]["id"], "out")
        print(f"  Exit: Graduation Hall --out--> hub")

    # NPCs
    dex_sheet = _sheet(
        dexterity="3D+2", knowledge="3D", mechanical="5D",
        perception="3D", strength="2D+2", technical="3D+1",
        skills={"piloting": "7D", "astrogation": "5D",
                "starship gunnery": "5D", "shields": "4D",
                "sensors": "4D", "starship repair": "4D"},
        wound_level=0, species="Human",
    )

    dex_briefing = await db.create_npc(
        name="Commander Dex",
        room_id=room_ids[0],
        species="Human",
        description=(
            "Commander Dex stands at the holographic projector, arms crossed. "
            "Patient enough to explain. Impatient enough to expect you to listen."
        ),
        char_sheet_json=dex_sheet,
        ai_config_json=_ai(
            personality=(
                "Gruff retired Rebel pilot. Teaches because bad pilots die. "
                "In the briefing room: structured, covers ships/zones/basics, "
                "asks questions to check understanding."
            ),
            knowledge=(
                "Briefing: ship types (+ships, +ship/info), crew stations, "
                "space zones (orbital/system/deep/hyperspace), astrogation basics. "
                "Tells player to head forward when ready."
            ),
            module="space",
        ),
    )
    print(f"  NPC {dex_briefing}: Commander Dex (Briefing Room)")

    dex_grad = await db.create_npc(
        name="Commander Dex",
        room_id=room_ids[5],
        species="Human",
        description=(
            "Commander Dex at parade rest, holding your pilot certification datacard. "
            "He looks like a man who has earned the right to hand one of those out."
        ),
        char_sheet_json=dex_sheet,
        ai_config_json=_ai(
            personality=(
                "Measured, not effusive. Genuine. Tells the pilot what they did "
                "well and what to watch for in real space. Hands over certification "
                "without ceremony."
            ),
            knowledge=(
                "Graduation: grants (Certified Pilot) title, explains next steps -- "
                "buy a ship at Docking Bay 94, use +smugjobs for first cargo run, "
                "find a crew at the cantina. Warns: real space has consequences "
                "the simulator does not."
            ),
            module="space",
        ),
    )
    print(f"  NPC {dex_grad}: Commander Dex (Graduation Hall)")

    pirate = await db.create_npc(
        name="Pirate Sim Drone",
        room_id=room_ids[4],
        species="Droid",
        description=(
            "A battered pirate interceptor -- or a convincing holographic copy. "
            "Its weapons sting. A red targeting reticle pulses on your display."
        ),
        char_sheet_json=_sheet(
            dexterity="3D", knowledge="1D", mechanical="3D+1",
            perception="2D+2", strength="2D", technical="2D",
            skills={"starship gunnery": "4D", "piloting": "4D", "dodge": "3D+2"},
            wound_level=0, species="Droid",
            weapons=[{"name": "Twin Laser Cannon", "skill": "starship gunnery",
                      "damage": "4D", "range": "medium/long"}],
        ),
        ai_config_json=_ai(
            personality="Combat sim drone. Attacks on sight. Calibrated to teach, not kill.",
            knowledge="Attack.",
            role="opponent", module="space", hostile=True, aggression=7,
        ),
    )
    print(f"  NPC {pirate}: Pirate Sim Drone (Combat Training Zone)")
    print(f"  Space Academy rooms: {room_ids}")



# ---------------------------------------------------------------------------
# Combat Arena -- 4-room chain  (Drop 27)
# ---------------------------------------------------------------------------

async def build_combat_arena(db):
    print("\n[4/4] Combat Arena rooms...")

    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1", ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found.")
        return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")

    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1", ("Combat Arena",),
    )
    if not entry_rows:
        print("  ERROR: Combat Arena entry room not found.")
        return
    entry_id = entry_rows[0]["id"]

    rooms_data = [
        (
            "Combat Arena Basics Room",
            "A classroom-sized training room with weapon racks and practice dummies.",
            (
                "The Basics Room is deliberately unglamorous -- bare durasteel walls, "
                "a row of battered training dummies against the far end, and a rack "
                "of practice weapons along one side. A single bench faces a holographic "
                "display showing combat action diagrams. Ordo stands near the weapon rack, "
                "watching you with flat eyes.\n\n"
                "Before you fight anyone, you learn the commands.\n\n"
                "Type \033[1;33mtalk ordo\033[0m to begin.\n"
                "Key commands here: \033[1;33mattack\033[0m  "
                "\033[1;33mdodge\033[0m  \033[1;33mfulldodge\033[0m  "
                "\033[1;33maim\033[0m  \033[1;33mflee\033[0m\n"
                "Exit \033[1;33mforward\033[0m when Ordo clears you."
            ),
        ),
        (
            "Combat Arena Multi-Action Ring",
            "A sparring ring with a training partner standing ready.",
            (
                "The sparring ring is a proper fighting floor -- impact-absorbing "
                "mesh underfoot, a single overhead light, and no furniture to hide "
                "behind. A training partner NPC stands at the far end, combat stance "
                "relaxed, waiting. Ordo leans against the wall watching.\n\n"
                "This room teaches multi-action mechanics: attacking and dodging in "
                "the same round, and when that trade-off is worth making.\n\n"
                "WEG D6 rule: each extra action in a round adds \033[1;33m1D penalty\033[0m to all pools.\n"
                "Try attacking AND dodging in the same round to feel the cost.\n"
                "Exit \033[1;33mforward\033[0m when ready."
            ),
        ),
        (
            "Combat Arena Ranged Lane",
            "A shooting range with cover positions and a melee sparring pad.",
            (
                "The Ranged Lane is split in two: one half is a blaster range with "
                "pop-up target dummies at varying distances, the other is a padded "
                "melee circle for close-quarters work. "
                "Range markers on the floor show short/medium/long/extreme bands.\n\n"
                "This room teaches the difference between ranged and melee combat -- "
                "cover, range band modifiers, melee parry, and weapon switching.\n\n"
                "\033[1;33mCover\033[0m reduces incoming fire by 1D to 3D depending on quality.\n"
                "\033[1;33mParry\033[0m substitutes your melee skill for dodge against melee attacks.\n"
                "Exit \033[1;33mforward\033[0m for the final fight."
            ),
        ),
        (
            "Combat Arena Championship Floor",
            "The main arena floor -- a tougher opponent waits.",
            (
                "The Championship Floor is the full arena -- high ceiling, a proper "
                "fighting circle marked in the deck, and a gallery observation deck "
                "above. It feels like somewhere things happen for real.\n\n"
                "A bounty hunter-grade training opponent stands in the center. "
                "This one is designed to be beaten, but it will make you work. "
                "Use everything you learned.\n\n"
                "\033[1;33mattack\033[0m, \033[1;33mdodge\033[0m, \033[1;33maim\033[0m, "
                "\033[1;33mfulldodge\033[0m, \033[1;33mparry\033[0m -- all valid here.\n"
                "Win and Ordo will give you your reward.\n"
                "Type \033[1;33mout\033[0m to return to the hub at any time."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(
            name=name, desc_short=short, desc_long=long,
            zone_id=tg_zone_id, properties=tg_props,
        )
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")

    await db.create_exit(entry_id, room_ids[0], "forward")
    await db.create_exit(room_ids[0], entry_id, "back")
    for i in range(len(room_ids) - 1):
        await db.create_exit(room_ids[i], room_ids[i + 1], "forward")
        await db.create_exit(room_ids[i + 1], room_ids[i], "back")
    print("  Exits: linear chain forward/back")

    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(room_ids[-1], hub_rows[0]["id"], "out")
        print("  Exit: Championship Floor --out--> hub")

    ordo_sheet = _sheet(
        dexterity="4D", knowledge="2D", mechanical="2D+2",
        perception="3D+1", strength="4D", technical="2D",
        skills={"blaster": "6D", "melee combat": "7D", "brawling": "6D",
                "dodge": "5D+2", "intimidation": "5D"},
        wound_level=0, species="Human",
    )
    ordo_ai_basics = _ai(
        personality=(
            "Ordo is a Mandalorian warrior of very few words. He teaches by "
            "demonstration. When he speaks it is to correct a mistake or confirm "
            "correct technique. No encouragement, no hand-holding. "
            "If the student asks a good question he will answer precisely."
        ),
        knowledge=(
            "Basics room focus: attack command syntax, dodge vs fulldodge tradeoff, "
            "aim (adds +1D to next shot, costs an action), flee mechanic, "
            "wound levels (Stunned/Wounded/Incapacitated/Mortally Wounded/Dead), "
            "wound penalties to all dice pools. "
            "Tells the player to head forward when ready to spar."
        ),
        module="combat",
    )
    ordo_id = await db.create_npc(
        name="Ordo",
        room_id=room_ids[0],
        species="Human",
        description=(
            "A broad-shouldered Mandalorian in battered beskar plate. "
            "He watches you enter without expression. "
            "Two vibroknives on his hips. No helmet."
        ),
        char_sheet_json=ordo_sheet,
        ai_config_json=ordo_ai_basics,
    )
    print(f"  NPC {ordo_id}: Ordo (Basics Room)")

    # Sparring partner in multi-action ring
    sparring_sheet = _sheet(
        dexterity="3D", knowledge="1D", mechanical="1D",
        perception="2D+2", strength="3D", technical="1D",
        skills={"brawling": "4D", "dodge": "3D+1", "melee combat": "3D+2"},
        wound_level=0, species="Human",
        weapons=[{"name": "Training Blade", "skill": "melee combat",
                  "damage": "STR (non-lethal)"}],
    )
    sparring_ai = _ai(
        personality=(
            "A silent training automaton. Attacks when attacked. "
            "Designed to demonstrate multi-action penalties in practice."
        ),
        knowledge="Fight.",
        role="opponent", module="combat", hostile=False, aggression=0,
    )
    sparring_id = await db.create_npc(
        name="Sparring Partner",
        room_id=room_ids[1],
        species="Human",
        description=(
            "A training partner in padded sparring armor, stance ready. "
            "Will engage when you attack."
        ),
        char_sheet_json=sparring_sheet,
        ai_config_json=sparring_ai,
    )
    print(f"  NPC {sparring_id}: Sparring Partner (Multi-Action Ring)")

    # Boss: Novice Bounty Hunter in championship floor
    hunter_sheet = _sheet(
        dexterity="3D+2", knowledge="2D", mechanical="2D+1",
        perception="3D+1", strength="3D+1", technical="2D",
        skills={"blaster": "5D", "dodge": "4D+2", "brawling": "4D",
                "melee combat": "4D", "search": "4D"},
        wound_level=0, species="Human",
        weapons=[{"name": "Blaster Pistol", "skill": "blaster", "damage": "4D"},
                 {"name": "Vibroknife", "skill": "melee combat", "damage": "STR+1D"}],
    )
    hunter_ai = _ai(
        personality=(
            "A calibrated training opponent at novice bounty-hunter level. "
            "Uses cover, mixes ranged and melee, doesn't telegraph moves. "
            "Designed to be defeatable but not trivially."
        ),
        knowledge="Fight smart.",
        role="opponent", module="combat", hostile=True, aggression=8,
    )
    hunter_id = await db.create_npc(
        name="Training Hunter",
        room_id=room_ids[3],
        species="Human",
        description=(
            "A training opponent in contractor armor -- not flashy, not weak. "
            "Blaster in one hand, vibroknife at the hip. "
            "It studies your stance with professional interest."
        ),
        char_sheet_json=hunter_sheet,
        ai_config_json=hunter_ai,
    )
    print(f"  NPC {hunter_id}: Training Hunter (Championship Floor)")
    print(f"  Combat Arena rooms: {room_ids}")


# ---------------------------------------------------------------------------
# Trader's Hall -- 5-room chain  (Drop 27)
# ---------------------------------------------------------------------------

async def build_traders_hall(db):
    print("\n[5/5] Trader\'s Hall rooms...")

    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1", ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found.")
        return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")

    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1", ("Trader\'s Hall",),
    )
    if not entry_rows:
        print("  ERROR: Trader\'s Hall entry room not found.")
        return
    entry_id = entry_rows[0]["id"]

    rooms_data = [
        (
            "Trader\'s Hall Commerce Floor",
            "A mock marketplace floor with vendor stalls and a Bargain practice counter.",
            (
                "The Commerce Floor looks like a miniature bazaar -- three vendor stalls "
                "with goods on display, a credit exchange terminal, and a Bargain practice "
                "counter where Greelo stands ready to be negotiated with. "
                "Prices are visible on every item.\n\n"
                "This room teaches the economic fundamentals: buying, selling, and the "
                "Bargain skill that makes every transaction better.\n\n"
                "Try: \033[1;33m+credits\033[0m to check your balance.\n"
                "Try: \033[1;33mbuy <item>\033[0m at a stall, "
                "\033[1;33msell <item>\033[0m to sell something.\n"
                "Try: \033[1;33mtalk greelo\033[0m to practice Bargaining.\n"
                "Exit \033[1;33mforward\033[0m when ready."
            ),
        ),
        (
            "Trader\'s Hall Mission Board Room",
            "A room centered on a glowing holographic mission board.",
            (
                "The Mission Board dominates the room -- a two-meter holographic "
                "display cycling through available jobs across Tatooine. "
                "Delivery runs, courier work, escort contracts. "
                "All low-risk. All paying.\n\n"
                "This room teaches the core mission income loop.\n\n"
                "Try: \033[1;33m+missions\033[0m to view available jobs.\n"
                "Try: \033[1;33maccept <id>\033[0m to take one.\n"
                "Try: \033[1;33m+missions active\033[0m to see what you\'ve accepted.\n"
                "Try: \033[1;33mabandon <id>\033[0m to drop a job -- no penalty here.\n"
                "Exit \033[1;33mforward\033[0m when ready."
            ),
        ),
        (
            "Trader\'s Hall Smuggling Den",
            "A back-room briefing space for less official work.",
            (
                "The Smuggling Den is off the main floor -- a dimmer room with a "
                "round table, a scrambled holoterminal, and the distinct feeling that "
                "the walls have heard things they shouldn\'t. "
                "Greelo is already here, leaning back in a chair.\n\n"
                "This room teaches the smuggling income loop -- higher pay, higher risk.\n\n"
                "Try: \033[1;33m+smugjobs\033[0m to view contraband runs.\n"
                "Try: \033[1;33msmugaccept <id>\033[0m to take a job.\n"
                "Note: patrol checks use your \033[1;33mcon\033[0m or "
                "\033[1;33msneak\033[0m skill. Tutorial flag disables real checks here.\n"
                "Exit \033[1;33mforward\033[0m when ready."
            ),
        ),
        (
            "Trader\'s Hall Bounty Board",
            "A secure terminal room showing active bounty postings.",
            (
                "The Bounty Board terminal glows against the far wall -- wanted holo-photos, "
                "payout amounts, alive/dead differentials. "
                "A tutorial target NPC is in the adjacent holding room for practice.\n\n"
                "This room teaches the bounty income loop.\n\n"
                "Try: \033[1;33m+bounties\033[0m to see active contracts.\n"
                "Try: \033[1;33mbountyclaim <id>\033[0m to accept one.\n"
                "Try: \033[1;33mbountytrack\033[0m to locate your target.\n"
                "Try: \033[1;33mbountycollect\033[0m once target is apprehended.\n"
                "Exit \033[1;33mforward\033[0m for the summary."
            ),
        ),
        (
            "Trader\'s Hall Counting Room",
            "A quiet back office where Greelo pulls it all together.",
            (
                "The Counting Room is the back office -- a wide desk covered in "
                "datapads, credit manifests, and what appears to be a very "
                "unofficial set of books. Greelo sits behind the desk, "
                "fingertips together, looking like someone about to deliver "
                "good news.\n\n"
                "This is the summary room. Greelo explains how missions, smuggling, "
                "and bounties combine into a sustainable income loop -- and where "
                "faction membership changes the math.\n\n"
                "Type \033[1;33mtalk greelo\033[0m for the full picture.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(
            name=name, desc_short=short, desc_long=long,
            zone_id=tg_zone_id, properties=tg_props,
        )
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")

    await db.create_exit(entry_id, room_ids[0], "forward")
    await db.create_exit(room_ids[0], entry_id, "back")
    for i in range(len(room_ids) - 1):
        await db.create_exit(room_ids[i], room_ids[i + 1], "forward")
        await db.create_exit(room_ids[i + 1], room_ids[i], "back")
    print("  Exits: linear chain forward/back")

    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = \'Training Grounds\' "
        "AND properties LIKE \'%tutorial_zone%\' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(room_ids[-1], hub_rows[0]["id"], "out")
        print("  Exit: Counting Room --out--> hub")

    greelo_sheet = _sheet(
        dexterity="2D+1", knowledge="4D", mechanical="2D",
        perception="4D+2", strength="2D", technical="2D+2",
        skills={"bargain": "6D", "con": "5D", "streetwise": "5D",
                "value": "5D+2", "persuasion": "4D+2"},
        wound_level=0, species="Rodian",
    )

    # Greelo appears in Commerce Floor, Smuggling Den, and Counting Room
    greelo_rooms = [
        (room_ids[0], "Commerce Floor",
         "Here to teach the art of the deal -- Bargain, buy, sell.",
         "Commerce focus: +credits, buy/sell syntax, Bargain skill mechanics "
         "(opposed roll vs vendor\'s value skill), price modifiers. "
         "Explains that Traders\' Coalition membership cuts wholesale prices 15%. "
         "Tells player to head forward when ready."),
        (room_ids[2], "Smuggling Den",
         "Leaning back in a chair, looking very comfortable with the ambiguity.",
         "Smuggling focus: +smugjobs, smugaccept, smugdeliver, smugdump, "
         "risk tiers (Safe/Moderate/Risky/Extreme), patrol check skills "
         "(con or sneak), payout vs risk curve, Hutt Cartel connection. "
         "Notes the tutorial disables real patrol checks. "
         "Mentions faction protection reduces patrol risk."),
        (room_ids[4], "Counting Room",
         "Sitting behind a desk of manifests, looking satisfied.",
         "Summary focus: how missions + smuggling + bounties combine as income "
         "lanes, faction multiplier (25% bonus on faction board jobs), "
         "guild membership (Traders\' Coalition: restricted trade routes, "
         "wholesale prices), pointing toward Transport Depot for real work. "
         "Mentions faction missions pay 25% more -- he will say this at least twice."),
    ]

    for g_room_id, location, desc_suffix, knowledge_str in greelo_rooms:
        g_id = await db.create_npc(
            name="Greelo",
            room_id=g_room_id,
            species="Rodian",
            description=(
                f"A bright-eyed Rodian in a green-and-gold merchant\'s sash. "
                f"{desc_suffix}"
            ),
            char_sheet_json=greelo_sheet,
            ai_config_json=_ai(
                personality=(
                    "Fast-talking, relentlessly upbeat, genuinely enthusiastic about "
                    "credits. Views every transaction as a puzzle. Will complain about "
                    "Imperial tariffs unprompted. Fond of the phrase \'that\'s what I "
                    "call a deal.\' Faction missions pay 25% more -- he mentions this "
                    "emphatically and often."
                ),
                knowledge=knowledge_str,
                module="economy",
            ),
        )
        print(f"  NPC {g_id}: Greelo ({location})")

    # Bounty target in Bounty Board room for practice
    target_sheet = _sheet(
        dexterity="2D", knowledge="1D", mechanical="1D",
        perception="2D", strength="2D+2", technical="1D",
        skills={"dodge": "2D+2", "brawling": "2D+2"},
        wound_level=0, species="Human",
    )
    target_ai = _ai(
        personality="A tutorial bounty target. Compliant. Does not fight back hard.",
        knowledge="Surrender.",
        role="opponent", module="economy", hostile=False, aggression=2,
    )
    target_id = await db.create_npc(
        name="Tutorial Bounty Target",
        room_id=room_ids[3],
        species="Human",
        description=(
            "A nervous-looking individual sitting in the corner of the room. "
            "There\'s a holo-wanted poster on the terminal with their face on it. "
            "They look like they\'d rather be somewhere else."
        ),
        char_sheet_json=target_sheet,
        ai_config_json=target_ai,
    )
    print(f"  NPC {target_id}: Tutorial Bounty Target (Bounty Board Room)")
    print(f"  Trader\'s Hall rooms: {room_ids}")



# ---------------------------------------------------------------------------
# Crafter's Workshop -- 4-room chain  (Drop 28)
# ---------------------------------------------------------------------------

async def build_crafters_workshop(db):
    print("\n[6] Crafter's Workshop rooms...")
    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1", ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found."); return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")
    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1", ("Crafter's Workshop",),
    )
    if not entry_rows:
        print("  ERROR: Crafter's Workshop entry room not found."); return
    entry_id = entry_rows[0]["id"]

    rooms_data = [
        (
            "Crafter's Workshop Survey Room",
            "A resource analysis lab with sample nodes and survey equipment.",
            (
                "The Survey Room smells of minerals and cutting fluid. "
                "Three resource sample stations line the walls -- each contains "
                "a different material type: durasteel alloy, power cell components, "
                "and synthetic polymer. Scanning equipment is already warmed up. "
                "Vek Nurren stands at a workbench, not looking up from a datapad.\n\n"
                "This room teaches the survey and gather steps of the crafting pipeline.\n\n"
                "Try: \033[1;33msurvey\033[0m to scan for harvestable resources.\n"
                "Try: \033[1;33mgather\033[0m to collect what you find.\n"
                "Note: this room has a guaranteed high-quality node -- no RNG.\n"
                "Type \033[1;33mtalk vek\033[0m for guidance. "
                "Head \033[1;33mforward\033[0m when you have materials."
            ),
        ),
        (
            "Crafter's Workshop Assembly Bay",
            "A fabrication bay with workbenches, tools, and schematic projectors.",
            (
                "The Assembly Bay is the heart of the workshop -- long workbenches "
                "bolted to the floor, tool racks on every wall, and a schematic "
                "projector casting blue assembly diagrams onto the workspace. "
                "Everything is in its place. Vek Nurren is already here, "
                "watching you carry in materials with the expression of someone "
                "about to give a lecture.\n\n"
                "This room teaches the assembly step: reading schematics and crafting.\n\n"
                "Try: \033[1;33m+schematics\033[0m to see what you can build.\n"
                "Try: \033[1;33mcraft <schematic>\033[0m to begin assembly.\n"
                "The craft roll uses your \033[1;33mTechnical\033[0m attribute + repair skill.\n"
                "Head \033[1;33mforward\033[0m once you have a finished item."
            ),
        ),
        (
            "Crafter's Workshop Experimentation Lab",
            "A testing lab for pushing assembled items past their baseline stats.",
            (
                "The Experimentation Lab is smaller than the assembly bay and "
                "considerably more cluttered. Half-finished prototypes line a shelf. "
                "A battered testing rig sits in the center. "
                "Vek Nurren follows you in, arms folded.\n\n"
                "This room teaches experimentation -- pushing a crafted item's stats "
                "beyond baseline at the cost of stability.\n\n"
                "Try: \033[1;33mexperiment <item>\033[0m on your finished piece.\n"
                "Each experimentation roll can raise quality or damage the item.\n"
                "Know when to stop. Vek will tell you when you've gone too far.\n"
                "Head \033[1;33mforward\033[0m when satisfied with your item."
            ),
        ),
        (
            "Crafter's Workshop Completion Bay",
            "The final quality check station -- Vek inspects your work.",
            (
                "The Completion Bay is where finished work gets inspected. "
                "A quality-assurance scanner sits on a table. "
                "Vek Nurren takes your item without being asked and runs it "
                "through the scanner, studying the readout with the focused "
                "attention of someone who has caught other people's mistakes "
                "for forty years.\n\n"
                "Type \033[1;33mtalk vek\033[0m to complete the module and collect your reward.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(name=name, desc_short=short, desc_long=long,
                                   zone_id=tg_zone_id, properties=tg_props)
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")
    await db.create_exit(entry_id, room_ids[0], "forward")
    await db.create_exit(room_ids[0], entry_id, "back")
    for i in range(len(room_ids) - 1):
        await db.create_exit(room_ids[i], room_ids[i+1], "forward")
        await db.create_exit(room_ids[i+1], room_ids[i], "back")
    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(room_ids[-1], hub_rows[0]["id"], "out")

    vek_sheet = _sheet(
        dexterity="2D", knowledge="3D+2", mechanical="3D",
        perception="3D", strength="2D+1", technical="6D",
        skills={"repair": "7D", "demolitions": "4D",
                "computer programming/repair": "5D", "medicine": "3D+2"},
        wound_level=0, species="Duros",
    )
    vek_rooms = [
        (room_ids[0], "Survey Room",
         "Teaches: survey command, resource types (metal/polymer/energy/organic), "
         "quality ratings (10-100), gather command, yield calculation. "
         "Notes: tutorial node is guaranteed quality 75+. Real nodes vary. "
         "Points forward when player has materials."),
        (room_ids[1], "Assembly Bay",
         "Teaches: +schematics to list known schematics, craft <name> syntax, "
         "assembly steps, Technical stat + repair skill roll, quality output "
         "formula, failure modes (wasted materials), critical success (bonus quality). "
         "Will grant a basic hold-out blaster schematic if player has none."),
        (room_ids[2], "Experimentation Lab",
         "Teaches: experiment <item> command, quality vs stability tradeoff, "
         "each roll has success/failure/critical, when to stop experimenting "
         "(diminishing returns after 3 attempts), guild schematics unlock "
         "superior experimentation options."),
        (room_ids[3], "Completion Bay",
         "Graduation focus: confirms completion, item the player crafted is theirs "
         "to keep, grants 200cr reward. Explains next steps: Traders Coalition "
         "for wholesale materials, guild membership for restricted schematics, "
         "Venn Kator at Docking Bay 94 for ship component commissions."),
    ]
    for room_id, location, knowledge_str in vek_rooms:
        vid = await db.create_npc(
            name="Vek Nurren", room_id=room_id, species="Duros",
            description=(
                "A methodical Duros engineer with long nimble fingers "
                "and ink-stained sleeves. He never wastes a word."
            ),
            char_sheet_json=vek_sheet,
            ai_config_json=_ai(
                personality=(
                    "Patient, methodical, mildly contemptuous of people who skip steps. "
                    "Will repeat a correct answer once without complaint. "
                    "Visibly suppresses irritation at the third identical question. "
                    "Proud of high-quality work. Never praises carelessly."
                ),
                knowledge=knowledge_str, module="crafting",
            ),
        )
        print(f"  NPC {vid}: Vek Nurren ({location})")
    print(f"  Crafter's Workshop rooms: {room_ids}")


# ---------------------------------------------------------------------------
# Bounty Office -- 4-room chain  (Drop 28)
# ---------------------------------------------------------------------------

async def build_bounty_office(db):
    print("\n[7] Bounty Office rooms...")
    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1", ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found."); return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")
    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1", ("Bounty Office",),
    )
    if not entry_rows:
        print("  ERROR: Bounty Office entry room not found."); return
    entry_id = entry_rows[0]["id"]

    rooms_data = [
        (
            "Bounty Office Briefing Room",
            "A spartan briefing room with warrant displays and a Trandoshan waiting.",
            (
                "The Briefing Room has one table, two chairs, and no decorations. "
                "The holodisplay shows threat-tier breakdowns and payout charts. "
                "Ssk'rath stands rather than sits, warrant datapad in hand, "
                "already studying you with professional neutrality.\n\n"
                "This room covers the profession: boards, tiers, alive vs dead, "
                "tracking vs pure combat, and why most hunters don't last.\n\n"
                "Type \033[1;33mtalk ssk'rath\033[0m to begin.\n"
                "Try: \033[1;33m+bounties\033[0m to view active contracts.\n"
                "Head \033[1;33mforward\033[0m to begin the tracking exercise."
            ),
        ),
        (
            "Bounty Office Tracking Range",
            "A three-room practice area with a hidden target NPC.",
            (
                "The Tracking Range is a small maze of partitions and props -- "
                "crates, a false wall, a narrow corridor. Somewhere in here "
                "is your practice target. They know you are coming.\n\n"
                "This room teaches the tracking tools.\n\n"
                "Try: \033[1;33mbountytrack\033[0m -- uses Search/Investigation, "
                "result tells you direction or distance.\n"
                "The target will try to hide. Your search roll opposes their stealth.\n"
                "Head \033[1;33mforward\033[0m to the takedown room once you locate them."
            ),
        ),
        (
            "Bounty Office Takedown Room",
            "A clear space for the practice takedown -- target cornered.",
            (
                "The Takedown Room is bare -- no cover, no exits for the target. "
                "The practice target stands against the far wall. "
                "Ssk'rath watches from a corner. This is where you close the job.\n\n"
                "Taking targets alive pays 50% more than dead on most warrants.\n"
                "Try: \033[1;33mattack <target>\033[0m to engage.\n"
                "Try: \033[1;33mrestrain <target>\033[0m once incapacitated "
                "(requires binder cuffs).\n"
                "Try: \033[1;33mbountycollect\033[0m to close the contract.\n"
                "Head \033[1;33mforward\033[0m to debrief."
            ),
        ),
        (
            "Bounty Office Debrief Room",
            "A quiet room where Ssk'rath closes out the contract.",
            (
                "The Debrief Room is where the paperwork gets done and the "
                "credits get paid. Ssk'rath reviews your performance with the "
                "same expression he reviews everything -- "
                "assessing competence, nothing more.\n\n"
                "Type \033[1;33mtalk ssk'rath\033[0m to collect your reward.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(name=name, desc_short=short, desc_long=long,
                                   zone_id=tg_zone_id, properties=tg_props)
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")
    await db.create_exit(entry_id, room_ids[0], "forward")
    await db.create_exit(room_ids[0], entry_id, "back")
    for i in range(len(room_ids) - 1):
        await db.create_exit(room_ids[i], room_ids[i+1], "forward")
        await db.create_exit(room_ids[i+1], room_ids[i], "back")
    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(room_ids[-1], hub_rows[0]["id"], "out")

    ssk_sheet = _sheet(
        dexterity="3D+2", knowledge="2D+2", mechanical="2D+1",
        perception="4D", strength="4D+1", technical="2D",
        skills={"blaster": "5D+2", "search": "6D", "tracking": "6D",
                "intimidation": "5D", "brawling": "5D", "streetwise": "4D+2"},
        wound_level=0, species="Trandoshan",
    )
    ssk_rooms = [
        (room_ids[0], "Briefing Room",
         "Briefing: +bounties, bountyclaim <id>, threat tiers (1-5), alive vs dead "
         "payout difference (50% more alive), warrant types (criminal/skip/political), "
         "Bounty Hunters Guild membership benefits (restricted contracts, Guild "
         "protection). Points forward to tracking exercise."),
        (room_ids[1], "Tracking Range",
         "Tracking: bountytrack command, Search skill vs target Sneak/Hide, "
         "result tiers (cold/warm/hot/spotted), cooldown between uses, "
         "false leads (fumble result), how to use scan + streetwise to supplement."),
        (room_ids[3], "Debrief Room",
         "Debrief: confirms completion, grants 300cr reward and binder cuffs item. "
         "Explains Police Station bounty board vs Guild board differences. "
         "Notes that Guild contracts pay more but require Guild standing. "
         "Points toward Sergeant Kreel for immediate work."),
    ]
    for room_id, location, knowledge_str in ssk_rooms:
        sid = await db.create_npc(
            name="Ssk'rath", room_id=room_id, species="Trandoshan",
            description=(
                "A lean scarred Trandoshan in contractor armor. "
                "Cold professional eyes. Everything on his kit earns its place."
            ),
            char_sheet_json=ssk_sheet,
            ai_config_json=_ai(
                personality=(
                    "Professional, pragmatic, no patience for ego. "
                    "Respects demonstrated skill. Acknowledges competence plainly: 'that works.' "
                    "Analyzes failure without emotion. Zero-target-loss record, quietly proud of it."
                ),
                knowledge=knowledge_str, module="bounty",
            ),
        )
        print(f"  NPC {sid}: Ssk'rath ({location})")

    # Hidden practice target in tracking range
    tgt_id = await db.create_npc(
        name="Practice Target", room_id=room_ids[1], species="Human",
        description="A nervous civilian trying to stay hidden behind a crate.",
        char_sheet_json=_sheet(
            dexterity="2D+1", knowledge="1D", mechanical="1D",
            perception="2D", strength="2D", technical="1D",
            skills={"hide": "3D+2", "sneak": "3D", "dodge": "2D+2"},
            wound_level=0, species="Human",
        ),
        ai_config_json=_ai(
            personality="Trying very hard not to be found.",
            knowledge="Hide.",
            role="opponent", module="bounty", hostile=False, aggression=0,
        ),
    )
    print(f"  NPC {tgt_id}: Practice Target (Tracking Range)")
    print(f"  Bounty Office rooms: {room_ids}")


# ---------------------------------------------------------------------------
# Crew Quarters -- 3-room chain  (Drop 28)
# ---------------------------------------------------------------------------

async def build_crew_quarters(db):
    print("\n[8] Crew Quarters rooms...")
    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1", ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found."); return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")
    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1", ("Crew Quarters",),
    )
    if not entry_rows:
        print("  ERROR: Crew Quarters entry room not found."); return
    entry_id = entry_rows[0]["id"]

    rooms_data = [
        (
            "Crew Quarters Common Room",
            "A freighter-style common area where Captain Mora tells you how it works.",
            (
                "The Common Room is deliberately homey -- padded benches, a sabacc "
                "table in the corner, a small galley. It's designed to look like "
                "the inside of a well-kept ship, because that's exactly what "
                "managing a crew feels like once you've got it right. "
                "Captain Mora sits at the head of the table with a cup of caf.\n\n"
                "This room covers crew fundamentals: roles, wages, morale, hiring.\n\n"
                "Type \033[1;33mtalk mora\033[0m to begin.\n"
                "Try: \033[1;33m+crew\033[0m to see your current crew roster.\n"
                "Head \033[1;33mforward\033[0m to practice hiring."
            ),
        ),
        (
            "Crew Quarters Hiring Hall",
            "A mock hiring hall where three NPC candidates wait to be interviewed.",
            (
                "Three NPC candidates sit on a bench: a pilot, a mechanic, and "
                "a medic. Each has a placard showing their stats and asking wage. "
                "Mora stands to the side, watching how you handle it.\n\n"
                "This room teaches the hiring flow and crew evaluation.\n\n"
                "Try: \033[1;33m+crew candidates\033[0m to see who is available.\n"
                "Try: \033[1;33mhire <name>\033[0m to take someone on.\n"
                "Try: \033[1;33m+crew info <name>\033[0m to check their skills.\n"
                "Crew wages come out of your credits every 24 real-time hours.\n"
                "Head \033[1;33mforward\033[0m when you have hired at least one."
            ),
        ),
        (
            "Crew Quarters Captain's Office",
            "A small private office where Mora gives you the graduation brief.",
            (
                "The Captain's Office is plain but orderly -- a desk, two chairs, "
                "a logbook open to a blank page. Mora takes the chair behind the "
                "desk and gestures for you to sit. This feels like a debrief.\n\n"
                "Type \033[1;33mtalk mora\033[0m to complete the module and collect your reward.\n"
                "The Crew Quarters reward is 24 hours of wage-free crew service -- "
                "your first hire works free for a full day.\n"
                "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
            ),
        ),
    ]

    room_ids = []
    for name, short, long in rooms_data:
        rid = await db.create_room(name=name, desc_short=short, desc_long=long,
                                   zone_id=tg_zone_id, properties=tg_props)
        room_ids.append(rid)
        print(f"  Room {rid}: {name}")
    await db.create_exit(entry_id, room_ids[0], "forward")
    await db.create_exit(room_ids[0], entry_id, "back")
    for i in range(len(room_ids) - 1):
        await db.create_exit(room_ids[i], room_ids[i+1], "forward")
        await db.create_exit(room_ids[i+1], room_ids[i], "back")
    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(room_ids[-1], hub_rows[0]["id"], "out")

    mora_sheet = _sheet(
        dexterity="2D+1", knowledge="4D", mechanical="3D+2",
        perception="4D+1", strength="2D", technical="3D",
        skills={"command": "6D", "bargain": "4D+2", "persuasion": "5D",
                "scholar (regulations)": "5D", "bureaucracy": "4D+2"},
        wound_level=0, species="Human",
    )
    mora_rooms = [
        (room_ids[0], "Common Room",
         "Common room: +crew command family overview, crew roles (pilot/gunner/"
         "engineer/medic/general), wage system (credits per 24h real time), "
         "morale mechanic (low morale adds penalty dice to crew skill checks), "
         "Command skill and how it affects crew loyalty. "
         "Best place to find crew: Chalmun's Cantina. "
         "Points forward to hiring practice."),
        (room_ids[2], "Captain's Office",
         "Graduation: confirms completion, grants 24h wage-free reward "
         "(stored as 'crew_wages_free_until' timestamp in attributes). "
         "Explains crew assignment (+crew assign <name> <role>), "
         "firing crew (fire <name>), and the cantina as the best long-term "
         "recruiting pool. Wishes the player good sailing."),
    ]
    for room_id, location, knowledge_str in mora_rooms:
        mid = await db.create_npc(
            name="Captain Mora", room_id=room_id, species="Human",
            description=(
                "A trim human woman in her sixties, silver-streaked hair, "
                "the unhurried manner of forty years in command."
            ),
            char_sheet_json=mora_sheet,
            ai_config_json=_ai(
                personality=(
                    "Warm, measured, fond of illustrative stories. "
                    "Believes crew loyalty flows both ways. "
                    "No patience for captains who treat crew as equipment. "
                    "Will drift into an anecdote and then catch herself."
                ),
                knowledge=knowledge_str, module="crew",
            ),
        )
        print(f"  NPC {mid}: Captain Mora ({location})")
    print(f"  Crew Quarters rooms: {room_ids}")


# ---------------------------------------------------------------------------
# Galactic Factions Briefing -- 2-room chain  (Drop 28)
# ---------------------------------------------------------------------------

async def build_factions_briefing(db):
    print("\n[9] Galactic Factions Briefing rooms...")
    zone_rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1", ("Training Grounds",),
    )
    if not zone_rows:
        print("  ERROR: Training Grounds zone not found."); return
    tg_zone_id = zone_rows[0]["id"]
    tg_props = _tprops(environment="interior", security="safe")
    entry_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? LIMIT 1",
        ("Galactic Factions Briefing Room",),
    )
    if not entry_rows:
        print("  ERROR: Galactic Factions Briefing Room entry not found."); return
    entry_id = entry_rows[0]["id"]

    # Room 2: Job Board Simulator
    board_room_id = await db.create_room(
        name="Factions Job Board Simulator",
        desc_short="A demonstration room showing example faction job postings.",
        desc_long=(
            "The Job Board Simulator displays example postings from each faction's "
            "private mission board -- side by side with an equivalent public posting "
            "so the pay difference is immediately obvious.\n\n"
            "\033[1;36m"
            "================================================================\n"
            " FACTION JOB BOARD -- EXAMPLES (Training Simulation)\n"
            "================================================================\n"
            "\033[0m"
            " \033[1;31m[IMPERIAL]\033[0m    Patrol Escort -- Outer Rim Lane\n"
            "               Pay: \033[1;32m1,250cr\033[0m  (25% faction bonus)\n"
            "               Requires: Imperial standing\n\n"
            " \033[1;33m[REBEL]\033[0m       Intel Drop -- Nar Shaddaa\n"
            "               Pay: \033[1;32m1,000cr\033[0m  (25% faction bonus)\n"
            "               Requires: Rebel standing\n\n"
            " \033[1;35m[HUTT CARTEL]\033[0m Spice Run -- Kessel to Nar Shaddaa\n"
            "               Pay: \033[1;32m3,500cr\033[0m  (Cartel exclusive)\n"
            "               Requires: Hutt standing\n\n"
            " \033[1;34m[GUILD]\033[0m       Precision Repair -- Coronet Shipyards\n"
            "               Pay: \033[1;32m800cr\033[0m  (Mechanics Guild contract)\n"
            "               Requires: Mechanics Guild membership\n\n"
            " \033[2m[PUBLIC]\033[0m      Cargo Delivery -- Tatooine to Corellia\n"
            "               Pay: \033[1;32m600cr\033[0m\n"
            "               No faction required\n"
            "\033[1;36m"
            "================================================================\033[0m\n\n"
            "C-4PO is here to explain the tradeoffs.\n"
            "Type \033[1;33mtalk c-4po\033[0m for more detail.\n"
            "Type \033[1;33mout\033[0m to return to the Training Grounds hub."
        ),
        zone_id=tg_zone_id,
        properties=tg_props,
    )
    print(f"  Room {board_room_id}: Factions Job Board Simulator")

    await db.create_exit(entry_id, board_room_id, "forward")
    await db.create_exit(board_room_id, entry_id, "back")
    hub_rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    if hub_rows:
        await db.create_exit(board_room_id, hub_rows[0]["id"], "out")
        print("  Exit: Job Board Simulator --out--> hub")

    # C-4PO in job board room
    c4po_sheet = _sheet(
        dexterity="1D", knowledge="5D+2", mechanical="1D",
        perception="3D", strength="1D", technical="2D",
        skills={"languages": "7D", "cultures": "6D",
                "scholar (galactic politics)": "6D", "bureaucracy": "5D"},
        wound_level=0, species="Droid",
    )
    c4po_id = await db.create_npc(
        name="C-4PO", room_id=board_room_id, species="Droid",
        description=(
            "A silver protocol droid with a deliberately neutral affect. "
            "Every statement hedged with 'according to available data.'"
        ),
        char_sheet_json=c4po_sheet,
        ai_config_json=_ai(
            personality=(
                "Programmed for strict impartiality. Never advocates for any faction. "
                "Presents information as a librarian presents books -- without judgment. "
                "Will note when factions are in direct conflict (Empire vs Rebels). "
                "Pauses before answering as if consulting an internal database."
            ),
            knowledge=(
                "Job board room: explains the pay differential (faction 25% bonus, "
                "guild contracts above market, public board baseline), commitment "
                "tradeoffs (factions expect loyalty, opposing factions become enemies), "
                "guild membership (up to 3 guilds, no political conflict, "
                "skill discounts and restricted schematics). "
                "Points to 'factions' command and 'guild' command for joining. "
                "Confirms completion when player says they are done."
            ),
            module="factions",
        ),
    )
    print(f"  NPC {c4po_id}: C-4PO (Job Board Simulator)")
    print(f"  Factions Briefing rooms: entry={entry_id}, board={board_room_id}")


async def build_all():
    from db.database import Database

    db_path = os.path.join(os.path.dirname(__file__), "sw_mush.db")
    if not os.path.exists(db_path):
        print("ERROR: sw_mush.db not found. Run build_mos_eisley.py first.")
        sys.exit(1)

    db = Database(db_path)
    await db.connect()
    await db.initialize()

    await build_core_tutorial(db)
    await build_training_grounds(db)
    await build_space_academy(db)
    await build_combat_arena(db)
    await build_traders_hall(db)
    await build_crafters_workshop(db)
    await build_bounty_office(db)
    await build_crew_quarters(db)
    await build_factions_briefing(db)

    await db.close()
    print("\n=== Tutorial build complete ===")
    print("Core tutorial:    6 rooms, Kessa Dray, Sand Raider")
    print("Training Grounds: hub + 8 elective entry rooms + 9 guide NPCs")
    print("Space Academy:    6 rooms, Commander Dex, Pirate Sim NPC")
    print("Combat Arena:     4 rooms, Ordo, Sparring Partner, Training Hunter")
    print("Trader's Hall:    5 rooms, Greelo x3, Tutorial Bounty Target")
    print("Crafter's Workshop: 4 rooms, Vek Nurren x4")
    print("Bounty Office:    4 rooms, Ssk'rath x3, Practice Target")
    print("Crew Quarters:    3 rooms, Captain Mora x2")
    print("Factions Briefing: 2 rooms, C-4PO")
    print("Commands: training, training list, training <module>, training skip")


if __name__ == "__main__":
    asyncio.run(build_all())


async def auto_build_if_needed(db_path="sw_mush.db"):
    """
    Called by game_server.py on startup.
    Builds tutorial zones if the Training Grounds hub room doesn't yet exist.

    Returns True if the build was performed, False if it already existed.
    """
    from db.database import Database

    db = Database(db_path)
    await db.connect()
    await db.initialize()

    rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' "
        "AND properties LIKE '%tutorial_zone%' LIMIT 1"
    )
    already_built = bool(rows)
    await db.close()

    if not already_built:
        print("\n  [Auto-Build] Tutorial zones not found. Running tutorial builder...")
        await build_all()
        return True
    return False
