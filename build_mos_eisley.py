# -*- coding: utf-8 -*-
"""
Mos Eisley World Builder v2
============================
Populates the full Mos Eisley from Galaxy Guide 7 with:
  - 40 interconnected rooms with zones
  - Combat-ready NPCs (char_sheet_json + ai_config_json)
  - Hostile NPCs (stormtroopers, thugs) that attack on sight
  - Hireable crew NPCs at cantinas and spaceports
  - Pre-spawned ships docked in bays with bridge rooms

Usage:
  1. Delete sw_mush.db
  2. python main.py  (creates clean DB, Ctrl+C to stop)
  3. python build_mos_eisley.py
  4. python main.py  (full world ready)
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db.database import Database

# ==============================================================
# ROOM DEFINITIONS  (name, short_desc, long_desc)
# IDs assigned starting at 10 to avoid seed room collisions.
# ==============================================================
ROOMS = [
    # 0 -- Spaceport District --
    ("Docking Bay 94 - Entrance",
     "The entrance to one of Mos Eisley's most famous docking bays.",
     "Cracked duracrete steps descend into the pit of Docking Bay 94. "
     "Beggars and flim-flam artists cluster near the stairs, sizing up arrivals. "
     "A faded sign reads 'De Maal Docking Services' in three languages."),
    # 1
    ("Docking Bay 94 - Pit Floor",
     "The sunken pit floor of Docking Bay 94.",
     "The reinforced floor is pitted and scorched from countless landings. "
     "Eight landing lights ring the circle, two flickering. Binary load lifters "
     "stand idle near the maintenance garage. Fuel cells cluster along the back wall."),
    # 2
    ("Spaceport Customs Office",
     "A dingy customs office adjacent to the docking bays.",
     "Dust covers everything in this cramped office. Desks pile high with datadisks "
     "and confiscated goods. The inspectors spend more time collecting bribes than "
     "actually inspecting cargo."),
    # 3
    ("Spaceport Speeders",
     "An unassuming speeder shop southeast of the docking bays.",
     "A motley collection of speeders fills this shop. The smell of lubricant and "
     "ozone hangs in the air. A partially disassembled SoroSuub XP-38 sits on a lift."),
    # 4
    ("Docking Bay 86",
     "A round pit gouged in the soil, slightly smaller than most bays.",
     "Old 86 is utilitarian, mostly serving small shuttles and personal transports. "
     "An ill-tempered admin Droid named BX-9T manages with brusque efficiency. "
     "Landing fees are 35 credits per day."),
    # 5
    ("Docking Bay 87",
     "One of the top favorite bays for smugglers and merchants.",
     "Directly across from Bay 86, this bay has been continually modernized. "
     "A double blast door and forcefield opens into the street. The Ishi Tib owner "
     "Drue charges 30 credits per day, and 25 credits avoids cargo inspections."),
    # 6
    ("Docking Bay 92",
     "A bay used almost exclusively for starship repairs.",
     "Underground rooms filled with repair tools, labor Droids, and engineering "
     "equipment. The owner Dom Antyll charges 125% of standard rates but his work "
     "is first-class. The smell of ion flux permeates everything."),
    # 7 -- Central Streets --
    ("Mos Eisley Street - Spaceport Row",
     "A wide, dusty street running between the major docking bays.",
     "This broad street connects several of the busiest docking bays. Low-grade "
     "concrete mounds line both sides. Moisture vaporators stand in corners. The air "
     "shimmers with heat from the twin suns. Jawas and street vendors compete for attention."),
    # 8
    ("Mos Eisley Street - Market District",
     "A bustling stretch of street near the market and cantina.",
     "The streets grow crowded near the commercial heart. Speeders weave between "
     "pedestrians. The cantina's curved walls are visible to the west. A Dim-U monk "
     "preaches about sacred Banthas to an audience of zero."),
    # 9
    ("Mos Eisley Street - Government Quarter",
     "A quieter section near the government offices and police station.",
     "Crowds thin near the regional offices and the expanded police station. "
     "Buildings are slightly better maintained. Stormtroopers patrol in pairs, "
     "white armor already coated in Tatooine dust."),
    # 10
    ("Mos Eisley Street - North End",
     "The northern edge of the central sector, near the factories.",
     "The city becomes industrial here -- warehouses, shipping offices, factory "
     "compounds. Notsub Shipping's headquarters dominates the skyline. Streets are "
     "wider for cargo skiffs."),
    # 11
    ("Mos Eisley Street - South End",
     "The southern residential area, quieter than the central sector.",
     "Streets narrow and quiet at the southern edge. White pourstone residential "
     "buildings line a cul-de-sac. Small subterranean gardens give this area an "
     "almost peaceful quality."),
    # 12 -- Cantina --
    ("Chalmun's Cantina - Entrance",
     "The elevated entranceway of the most infamous cantina in the galaxy.",
     "You step from blinding glare into dim coolness. The elevated entrance lets "
     "patrons size up newcomers. A Droid detector hums softly. A battered sign reads "
     "'NO DROIDS' in four languages. Jizz music washes over you from below."),
    # 13
    ("Chalmun's Cantina - Main Bar",
     "The main bar of the most notorious establishment in Mos Eisley.",
     "The dimly lit cantina is a cavern of sound and shadow. A high-tech bar stretches "
     "along one wall. Booths line the curved walls. The Modal Nodes play on the bandstand. "
     "Smugglers, bounty hunters, and beings of every description pack the room."),
    # 14
    ("Chalmun's Cantina - Back Hallway",
     "A narrow hallway behind the bar leading to restrooms and cellar.",
     "This rear corridor provides a quick escape for those who know it. Three restroom "
     "doors line one side. The cellar access is through a trapdoor. The bartender's "
     "office is behind a curtained wall."),
    # 15
    ("Lup's General Store",
     "A well-stocked general store run by friendly Shistavanen Wolfmen.",
     "Despite the fierce wolf-like proprietors, this is one of the friendlier shops. "
     "Touch-screen monitors line the counter. Twelve monitors advertise daily specials. "
     "Provisions, supplies, machinery, and weaponry at reasonable prices."),
    # 16
    ("Market Place - Gep's Grill",
     "An open-air market with tents, food stalls, and a popular grill.",
     "A sandy lot full of tents and improvised stalls. Farmers sell underground "
     "vegetables, hunters offer game, vendors hawk trinkets. Bantha burgers and "
     "Dewback ribs smoke on Gep's Grill."),
    # 17
    ("Mos Eisley Inn",
     "A run-down building offering bare necessities for 10 credits a night.",
     "The Inn offers exactly what its name suggests. A central lobby with imported "
     "trees provides the only aesthetic touch. Subterranean rooms are dark but cool; "
     "upper rooms are unbearably warm."),
    # 18
    ("Jabba's Townhouse - Main Entrance",
     "The intimidating entrance to Jabba the Hutt's Mos Eisley townhouse.",
     "A reinforced blast door dominates this entrance. A sensor eye stares from the "
     "wall. Guards disguised as beggars keep tabs on visitors. Durasteel doors and "
     "blast-shielded walls tell the real story."),
    # 19
    ("Jabba's Townhouse - Audience Chamber",
     "The audience chamber where Jabba the Hutt holds court.",
     "Specially constructed to accommodate Jabba's massive power sled. A weapon-detecting "
     "Droid scans all visitors. A wire mesh net near the ceiling houses Kayven Whistlers "
     "for disciplining unruly guests."),
    # 20
    ("Regional Government Offices",
     "The cramped administrative center of Tatooine's government.",
     "Prefect Talmont's office is cluttered with datadisks. The building handles land "
     "deeds, weapon licenses, and court appearances. Three clerks sit behind computers."),
    # 21
    ("Police Station - Main Floor",
     "The newly expanded Mos Eisley police station.",
     "New facilities give a slightly more professional appearance. A desk clerk monitors "
     "holding cells and entrances from banks of monitors. Patrol officers use personal "
     "datapads. The roof has a marked landing pad."),
    # 22
    ("Tatooine Militia Headquarters",
     "The militia building, now also housing the stormtrooper garrison.",
     "Home to the militia and the Imperial stormtrooper detachment. A large weapons "
     "vault with Strength 7D walls holds carbines, grenades, stun batons, and three "
     "E-web blasters. Speeder bikes crowd the garage."),
    # 23
    ("Dewback Stables and Garage",
     "An ancient stable converted to house militia vehicles and beasts.",
     "Three armored landspeeders sit in the garage. Half a dozen patrol scooters line "
     "one wall. Dewbacks are kept in a separate paddock, their musky smell permeating "
     "everything. Heavy blast doors secured with a Difficult lock."),
    # 24
    ("Power Station",
     "A bustling charging station for speeders and Droids.",
     "Merchants and farmers gather here to discuss business, politics, and weather. "
     "An unenthusiastic power Droid named 4-LB runs the station. Speeder recharges "
     "cost 15 credits; Droids need only 3-4 credits. Rumors circulate freely."),
    # 25
    ("Spaceport Hotel",
     "An adequate 40-room hotel near the spaceport.",
     "Forty small rooms at 15 credits per night. Beds are almost comfortable, sonic "
     "showers mostly work, air conditioning functions some of the time. The Sullustan "
     "clerk does not ask questions."),
    # 26
    ("Mos Eisley Spaceport Control Tower",
     "The five-story tower directing all incoming and outgoing traffic.",
     "A Sienar Observation Module juts five stories high. ID plates read 'Republic "
     "Sienar Systems.' Three stations are occupied: one by a J9-5 worker Droid, two "
     "by Human technicians."),
    # 27
    ("Kayson's Weapon Shop",
     "A well-stocked weapon shop with both legal and contraband inventory.",
     "Walls literally covered in weapons: new, used, ancient, modern, all kept empty "
     "and unloaded. Kayson's knowledge of weapons is encyclopedic. Black market weapons "
     "are available for those who know how to ask."),
    # 28
    ("Heff's Souvenirs",
     "A junk shop masquerading as a souvenir store.",
     "Battered trinkets and curiosities fill this cluttered shop. Behind the counter, "
     "unique souvenirs depict local sites. The current owner Moplin makes his real "
     "living through forgery."),
    # 29
    ("Jawa Traders",
     "A repair shop specializing in vehicle and starship Droids.",
     "The oily interior is packed with Droids in various states of assembly. Restraining "
     "bolts, circuit boards, and motivator units fill shelves floor to ceiling. Several "
     "Droids stand motionless in a display line near the entrance."),
    # 30
    ("Dockside Cafe",
     "A dimly lit restaurant and bar popular with experienced spacers.",
     "Adjacent to Bay 92, this cafe features alcoves and booths for private conversation. "
     "No gambling here, unlike the cantina. A Droid bartender named CG-X2R takes no "
     "notice of anything."),
    # 31
    ("Lucky Despot Hotel - Grand Staircase",
     "The entrance to the Lucky Despot, a decommissioned starship turned hotel.",
     "A grand staircase leads into this converted cargo hauler. Faded grandeur remains. "
     "Guards in orange uniforms keep watch. The whole operation belongs to Valarian, "
     "a Whiphid crime boss rivaling Jabba."),
    # 32
    ("Lucky Despot - Star Chamber Cafe",
     "The hotel restaurant with its famous holographic starfield projector.",
     "The Star Chamber serves meals by day and transforms into an illegal casino after "
     "Second Twilight. A holographic projector portrays the galaxy from Coruscant. "
     "Gambling tables appear as if by magic in the evenings."),
    # 33
    ("Zygian's Banking Concern",
     "A bank that has slowly evolved into a pawn shop.",
     "Items left as collateral clutter the vault area. A triple-lined vault with "
     "computer-controlled timed entry dominates the back. Loan rates of 15% seem "
     "generous compared to the usual loan sharks."),
    # 34
    ("Transport Depot",
     "A decrepit building serving as Mos Eisley's transport terminal.",
     "A cafe serves overpriced food to waiting passengers. Rows of chairs face monitors "
     "showing prerecorded broadcasts. A bank of lockers lines the back wall. The "
     "proprietor Yvonne Targis works for Jabba on the side."),
    # 35
    ("The Cutting Edge Clinic",
     "A nondescript clinic run by the infamous Dr. Evazan under a false name.",
     "Four rooms specializing in cyborging, though seldom successful. The 'doctor' "
     "operating as 'Cornelius' is actually Dr. Evazan, wanted on 53 planets with "
     "death sentences in 14 systems."),
    # 36
    ("Dim-U Monastery - Main Gate",
     "The entrance to an abandoned greenhouse converted into a monastery.",
     "Huge doors rarely opened. The building was once a greenhouse. Monks move about "
     "quietly. What visitors don't know: the monastery is a front for forging "
     "transponder codes for wanted ships."),
    # 37
    ("Street Corner - Dowager Queen Wreckage",
     "A historic corner near the remains of the colony ship Dowager Queen.",
     "The original blockhouses built around the wreckage still stand. Jawas examine "
     "Droids, con men set up card tables, monks preach to disinterested crowds. If "
     "something happens in Mos Eisley, people discuss it here."),
    # 38
    ("House of Momaw Nadon",
     "A typical pourstone house concealing an ecological paradise.",
     "Inside, humidity hits immediately. Insulated walls drip with condensation. An "
     "artificial pond feeds a lush garden spilling into a forested subterranean level. "
     "The Ithorian owner prefers privacy."),
    # 39
    ("Notsub Shipping - Lobby",
     "The corporate lobby of Tatooine's largest company.",
     "The most professional-looking building in Mos Eisley. Polished floors, working "
     "climate control. Notsub employs almost 1,000 beings. CEO Armanda Durkin secretly "
     "leads a double life as the pirate Duchess."),
]

# ==============================================================
# EXITS  (from_idx, to_idx, direction, reverse_direction)
# ==============================================================
EXITS = [
    (0, 1, "down", "up"),         (0, 7, "north", "south"),
    (2, 7, "east", "west"),       (2, 0, "south", "north"),
    (3, 7, "northwest", "southeast"), (4, 7, "west", "east"),
    (5, 7, "east", "west"),       (6, 10, "east", "west"),
    (7, 8, "north", "south"),     (8, 9, "north", "south"),
    (9, 10, "north", "south"),    (8, 11, "south", "north"),
    (12, 8, "east", "west"),      (12, 13, "down", "up"),
    (13, 14, "west", "east"),     (15, 8, "north", "south"),
    (16, 8, "south", "north"),    (17, 7, "south", "north"),
    (18, 8, "southeast", "northwest"), (18, 19, "in", "out"),
    (20, 9, "east", "west"),      (21, 9, "west", "east"),
    (22, 9, "south", "north"),    (23, 22, "north", "south"),
    (24, 9, "northwest", "southeast"), (25, 7, "east", "west"),
    (26, 7, "north", "south"),    (27, 8, "east", "west"),
    (28, 8, "northeast", "southwest"), (29, 8, "west", "east"),
    (30, 10, "south", "north"),   (6, 30, "south", "north"),
    (31, 11, "north", "south"),   (31, 32, "up", "down"),
    (33, 8, "north", "south"),    (34, 11, "east", "west"),
    (35, 9, "east", "west"),      (36, 10, "east", "west"),
    (37, 8, "north", "south"),    (38, 11, "west", "east"),
    (39, 10, "north", "south"),
]

# ==============================================================
# ZONE MAPPING
# ==============================================================
ROOM_ZONES = {
    0: "spaceport", 1: "spaceport", 2: "spaceport", 3: "spaceport",
    4: "spaceport", 5: "spaceport", 6: "spaceport",
    7: "streets", 8: "streets", 9: "streets", 10: "streets", 11: "streets",
    12: "cantina", 13: "cantina", 14: "cantina",
    15: "shops", 16: "shops", 17: "shops",
    18: "jabba", 19: "jabba",
    20: "government", 21: "government", 22: "government",
    23: "spaceport", 24: "spaceport", 25: "shops", 26: "spaceport",
    27: "shops", 28: "shops", 29: "shops", 30: "spaceport",
    31: "shops", 32: "shops", 33: "shops", 34: "spaceport",
    35: "shops", 36: "streets", 37: "streets", 38: "streets", 39: "spaceport",
}

ROOM_OVERRIDES = {
    1: {"cover_max": 4}, 13: {"cover_max": 2}, 14: {"cover_max": 1},
    19: {"cover_max": 3}, 21: {"cover_max": 2}, 24: {"cover_max": 0},
    26: {"cover_max": 3}, 37: {"cover_max": 0},
}

# ==============================================================
# HELPER: Build a char_sheet_json for combat-ready NPCs
# ==============================================================
def _sheet(dex="3D", kno="2D", mec="2D", per="3D", stre="3D", tec="2D",
           skills=None, weapon="", species="Human", wound_level=0):
    """Build a char_sheet_json dict for an NPC."""
    return {
        "attributes": {
            "dexterity": dex, "knowledge": kno, "mechanical": mec,
            "perception": per, "strength": stre, "technical": tec,
        },
        "skills": skills or {},
        "weapon": weapon,
        "species": species,
        "wound_level": wound_level,
    }

def _ai(personality="", knowledge=None, faction="Neutral", style="",
        fallbacks=None, hostile=False, behavior="defensive",
        model_tier=1, temperature=0.7, max_tokens=120,
        # NPC crew fields for space combat
        space_skills=None):
    """Build an ai_config_json dict."""
    cfg = {
        "personality": personality,
        "knowledge": knowledge or [],
        "faction": faction,
        "dialogue_style": style,
        "fallback_lines": fallbacks or [],
        "hostile": hostile,
        "combat_behavior": behavior,
        "model_tier": model_tier,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if space_skills:
        cfg["skills"] = space_skills
    return cfg

# ==============================================================
# NPC DEFINITIONS -- COMBAT READY
# (name, room_idx, species, description, char_sheet, ai_config)
# ==============================================================
NPCS = [
    # -- Cantina NPCs --
    ("Wuher", 13, "Human",
     "A scarred, ill-tempered Human bartender polishing a glass with a dirty rag.",
     _sheet(dex="3D+1", per="3D+2", stre="3D+1",
            skills={"blaster": "4D", "dodge": "4D", "brawling": "4D+2",
                    "intimidation": "4D", "bargain": "3D+1"},
            weapon="blaster_pistol"),
     _ai(personality="Wuher is non-communicative and ill-tempered. He hates Droids. "
         "Gruff, terse, speaks in short sentences. Knows everything but shares nothing.",
         knowledge=["Chalmun owns the cantina and keeps a bowcaster behind the bar",
                     "Jabba controls most criminal activity", "No Droids allowed",
                     "The band is Figrin Da'n and the Modal Nodes"],
         style="Extremely terse. Grunts. Never volunteers info.",
         fallbacks=["Wuher grunts and continues polishing a glass.",
                    "Wuher glances at you. 'What'll it be.'",
                    "'We don't serve their kind here.'"],
         behavior="defensive")),

    ("Chalmun", 13, "Wookiee",
     "A beige and gray Wookiee with a scar across his chest, the cantina's owner.",
     _sheet(dex="2D+2", kno="2D+1", per="3D", stre="5D+2", tec="2D",
            skills={"brawling": "6D+1", "intimidation": "4D", "bowcaster": "4D"},
            weapon="bowcaster", species="Wookiee"),
     _ai(personality="Chalmun is a rough-but-warm Wookiee owner. Protective of his bar. "
         "Keeps a bowcaster behind the counter.",
         knowledge=["Bought the cantina with gambling profits from Ord Mantell",
                     "Pays Jabba protection money"],
         style="Growls and roars. Use *growls*, rough translated speech.",
         fallbacks=["*Chalmun growls a warning and gestures at the door.*",
                    "*The big Wookiee eyes you warily, one paw near the bowcaster.*"],
         behavior="aggressive")),

    ("Oxbell", 13, "Devaronian",
     "A horned humanoid with razor teeth, nursing a drink in a booth.",
     _sheet(dex="2D+2", kno="3D+1", per="4D", stre="2D+1",
            skills={"dodge": "3D+2", "streetwise": "5D", "bargain": "4D+1",
                    "con": "4D", "blaster": "3D"},
            weapon="hold_out_blaster"),
     _ai(personality="Oxbell is a Devaronian info broker. Drunk most of the time. "
         "Babbles gossip without discrimination. Will share rumors for a drink.",
         knowledge=["Most gossip in Mos Eisley", "Jabba's people buy info",
                     "A new spice operation might rival Jabba"],
         style="Slurred, rambling. Morose then chatty. Bribed with drinks.",
         fallbacks=["'Buy me a drink and I'll tell you something interesting.'",
                    "*Oxbell takes a long swig and peers at you with bloodshot eyes.*"],
         behavior="cowardly")),

    # -- Cantina Thugs (HOSTILE) --
    ("Ponda Baba's Associate", 13, "Aqualish",
     "A scarred Aqualish thug hunched over a drink, watching the room with hostility.",
     _sheet(dex="3D+2", per="2D+1", stre="4D",
            skills={"blaster": "4D+2", "brawling": "5D", "dodge": "4D",
                    "melee combat": "4D+1", "intimidation": "3D+2"},
            weapon="vibroblade", species="Aqualish"),
     _ai(personality="A violent thug looking for trouble. Quick to pick fights.",
         style="Threatening grunts and snarls.",
         fallbacks=["The Aqualish snarls at you menacingly.",
                    "*He reaches for his weapon.*"],
         hostile=True, behavior="aggressive")),

    # -- Government NPCs --
    ("Prefect Talmont", 20, "Human",
     "A wiry man with an obvious toupee and an air of self-importance.",
     _sheet(dex="2D", kno="3D+2", per="3D+1", stre="2D", tec="2D+1",
            skills={"blaster": "2D+2", "bureaucracy": "5D", "law_enforcement": "4D",
                    "command": "3D+2", "bargain": "4D"}),
     _ai(personality="Eugene Talmont is the Imperial Prefect. Full of himself, "
         "overestimates his importance. Nearsighted but too vain for lenses.",
         knowledge=["Governor Tour Aryon runs Tatooine from Bestine",
                     "Lieutenant Harburik is Chief of Police",
                     "Previous Prefect Orun Depp killed by assassin Droid"],
         faction="Imperial",
         style="Pompous, formal. Projects authority he doesn't possess.",
         fallbacks=["Talmont adjusts his toupee nervously. 'Yes, well. I'm very busy.'",
                    "'This is a matter for the proper authorities. Which is to say, me.'"],
         behavior="cowardly")),

    ("Lieutenant Harburik", 21, "Human",
     "A large, well-muscled man with a vicious look. The Chief of Police.",
     _sheet(dex="3D+2", kno="2D+2", per="3D+2", stre="4D",
            skills={"blaster": "5D+1", "brawling": "5D", "dodge": "4D+2",
                    "intimidation": "5D", "law_enforcement": "4D+1",
                    "melee combat": "4D+2"},
            weapon="heavy_blaster_pistol"),
     _ai(personality="Harburik is crass, rude, and cruel. Enjoys being a big fish. "
         "Well-armed and dangerous.",
         knowledge=["Commands about 20 police officers",
                     "Prefect Talmont is an incompetent fool",
                     "Considers having Talmont removed"],
         faction="Imperial",
         style="Threatening, direct. Barely contained aggression.",
         fallbacks=["'Let me see your identification. Now.'",
                    "Harburik cracks his knuckles meaningfully."],
         behavior="aggressive")),

    # -- Shops --
    ("Kal Lup", 15, "Shistavanen",
     "A fierce-looking but friendly Shistavanen Wolfman behind the counter.",
     _sheet(dex="3D+1", per="3D", stre="4D",
            skills={"blaster": "4D", "dodge": "3D+2", "brawling": "4D+1",
                    "bargain": "4D+2"},
            weapon="blaster_carbine", species="Shistavanen"),
     _ai(personality="Kal Lup is genuinely friendly despite his fierce appearance. "
         "Runs the general store with his husband Tar.",
         knowledge=["Stocks provisions, supplies, machinery, medical equipment, weapons",
                     "Prices 90-110% standard, medical/weapons 120%",
                     "Has a blaster carbine hidden behind the counter"],
         style="Friendly, welcoming. Good shopkeeper patter.",
         fallbacks=["Kal Lup bares his fangs in what is apparently a smile. 'Welcome!'",
                    "'We have everything you need, friend.'"],
         behavior="defensive")),

    ("Unut Poll", 3, "Arcona",
     "An older Arconan with a gentle face. The speeder shop proprietor.",
     _sheet(dex="2D+1", kno="3D", mec="4D+1", per="3D+2", stre="2D", tec="4D",
            skills={"repulsorlift_operation": "5D+2", "repulsorlift_repair": "5D+1",
                    "bargain": "4D+1", "con": "4D", "dodge": "3D"},
            species="Arcona"),
     _ai(personality="Unut Poll is a quirky old charmer. Loves speeders. Secretly "
         "aids the Rebel Alliance but is extremely cautious.",
         knowledge=["Has speeders for sale including an XP-38 and T-16 Skyhopper",
                     "Secretly supports the Rebellion"],
         faction="Secretly Rebel Alliance",
         style="Charming, folksy, eccentric. Deflects personal questions.",
         fallbacks=["'Looking for transportation?'",
                    "'Ah, that XP-38? Fine machine. Let me tell you...'"],
         behavior="cowardly")),

    ("Moplin Jarron", 28, "Sullustan",
     "A nervous little Sullustan with a perpetual squint.",
     _sheet(dex="2D+2", kno="3D", per="3D+1", stre="2D",
            skills={"forgery": "5D+2", "con": "4D+1", "dodge": "3D+1",
                    "hide": "4D", "sneak": "4D"},
            weapon="hold_out_blaster", species="Sullustan"),
     _ai(personality="Moplin runs the souvenir shop as a front for forgery. "
         "Laughs a lot for no reason. Nervous and twitchy.",
         knowledge=["Can forge IDs: township 100 cr, passports 200 cr",
                     "Bought the shop from Tebbi, daughter of original Heff"],
         style="Nervous, twitchy. Laughs at odd moments. Conspiratorial tone.",
         fallbacks=["'Hee! Just souvenirs here, friend. Just souvenirs.'",
                    "*The Sullustan hunches lower behind the counter, eyes darting.*"],
         behavior="cowardly")),

    ("Kayson", 27, "Unknown",
     "A grizzled alien weaponsmith with atrocious manners.",
     _sheet(dex="3D+2", kno="3D", per="2D+2", stre="3D+1", tec="4D",
            skills={"blaster": "5D", "blaster_repair": "5D+2",
                    "melee combat": "4D", "dodge": "4D"},
            weapon="heavy_blaster_pistol"),
     _ai(personality="Grizzled arms dealer with terrible manners. Knows weapons "
         "intimately. Maintains appearance of legitimacy while running black market.",
         knowledge=["Heavy blaster pistols 1,500 cr, rifles 2,000",
                     "Black market weapons available",
                     "Thermal detonators 4,000 cr"],
         style="Gruff, sour, minimal words. Suspicious of new customers.",
         fallbacks=["'Credits first. Then we talk.'",
                    "*The old alien eyes you with undisguised suspicion.*"],
         behavior="aggressive")),

    # -- Docking Bay --
    ("Ohwun De Maal", 1, "Duros",
     "An unremarkable blue-skinned Duros in work clothes, co-owner of Bay 94.",
     _sheet(dex="2D+1", kno="3D", mec="3D+2", per="3D", stre="2D+1", tec="3D+1",
            skills={"bargain": "4D", "space_transports": "4D+1",
                    "starship_repair": "4D"},
            species="Duros"),
     _ai(personality="Ohwun is devout, honest, hardworking. Runs Bay 94 with his "
         "mate Chachi. Nobody's fool.",
         knowledge=["Bay 94 charges 25 cr/day", "Fuel cells 10 cr each",
                     "Owns five other bays and eight warehouses"],
         style="Quiet, polite, professional. Duros accent.",
         fallbacks=["'Welcome to Docking Bay 94. De Maal Docking Services.'",
                    "'We run an honest operation here. Always have.'"],
         behavior="defensive")),

    # -- Stormtroopers (HOSTILE) --
    ("Imperial Stormtrooper", 9, "Human",
     "A stormtrooper in scuffed white armor, blaster rifle at the ready.",
     _sheet(dex="3D+1", kno="2D", mec="2D+1", per="2D+2", stre="3D", tec="2D",
            skills={"blaster": "4D+1", "brawling": "4D", "dodge": "4D",
                    "melee combat": "3D+2"}),
     _ai(personality="Standard Imperial stormtrooper. Follows orders.",
         hostile=True, behavior="aggressive",
         style="Clipped military speech.",
         fallbacks=["'Halt! Show me your identification.'",
                    "'Move along. Move along.'"])),

    ("Imperial Stormtrooper", 22, "Human",
     "A stormtrooper standing guard at the militia headquarters.",
     _sheet(dex="3D+1", kno="2D", mec="2D+1", per="2D+2", stre="3D", tec="2D",
            skills={"blaster": "4D+1", "brawling": "4D", "dodge": "4D",
                    "melee combat": "3D+2"}),
     _ai(personality="Standard Imperial stormtrooper on guard duty.",
         hostile=True, behavior="aggressive",
         style="Military.",
         fallbacks=["'This area is restricted.'",
                    "'Move along.'"])),

    # -- Jabba's Guard (HOSTILE) --
    ("Gamorrean Guard", 19, "Gamorrean",
     "A massive green-skinned Gamorrean guard in crude armor, wielding a vibro-ax.",
     _sheet(dex="2D+1", kno="1D", per="1D+2", stre="5D", tec="1D",
            skills={"melee combat": "5D+2", "brawling": "5D+1", "dodge": "3D"},
            weapon="vibro_ax", species="Gamorrean"),
     _ai(personality="A dim but loyal Gamorrean guard. Attacks intruders on sight.",
         hostile=True, behavior="berserk",
         fallbacks=["*The Gamorrean squeals and charges!*",
                    "*A massive green fist swings toward you!*"])),

    # -- Lucky Despot Bounty Hunter (HOSTILE) --
    ("Valarian's Enforcer", 32, "Whiphid",
     "A hulking Whiphid enforcer with cybernetic tusks, watching the casino floor.",
     _sheet(dex="3D", kno="2D", per="3D+1", stre="5D+1", tec="2D",
            skills={"blaster": "4D+2", "brawling": "6D", "dodge": "4D",
                    "intimidation": "5D", "melee combat": "5D"},
            weapon="vibroblade", species="Whiphid"),
     _ai(personality="Valarian's personal enforcer. Watches for trouble.",
         hostile=True, behavior="aggressive",
         fallbacks=["*The Whiphid rises to its full height, cybernetic tusks gleaming.*",
                    "'You shouldn't be here.'"])),
]

# ==============================================================
# HIREABLE CREW NPCs -- Available at cantina/spaceport
# These have space-relevant skills and are NOT hostile.
# (name, room_idx, species, desc, char_sheet, ai_config)
# ==============================================================
HIREABLE_CREW = [
    ("Kael Voss", 13, "Human",
     "A lean Human pilot with quick eyes and a flight jacket covered in unit patches.",
     _sheet(dex="3D+1", mec="4D+1", per="3D", stre="2D+2", tec="3D",
            skills={"dodge": "4D", "blaster": "4D", "starfighter_piloting": "5D+1",
                    "space_transports": "5D", "starship_gunnery": "4D+2",
                    "astrogation": "4D"}),
     _ai(personality="Kael is a former Republic Navy pilot turned freelancer. "
         "Competent, confident, professional.",
         style="Calm, professional. Military bearing.",
         fallbacks=["'Need a pilot? I've flown worse than whatever you've got.'",
                    "Kael checks instrument readings out of habit."],
         space_skills={"space transports": "5D", "starfighter piloting": "5D+1",
                       "starship gunnery": "4D+2", "astrogation": "4D"})),

    ("Grek Duul", 13, "Rodian",
     "A green-skinned Rodian with a modified targeting visor over one eye.",
     _sheet(dex="4D", mec="3D+1", per="3D+2", stre="2D+1", tec="2D+2",
            skills={"blaster": "5D", "dodge": "4D+2", "starship_gunnery": "5D+2",
                    "sensors": "4D"},
            species="Rodian"),
     _ai(personality="Grek is a crack shot. Talks about weapons obsessively. "
         "Former bounty hunter who decided shooting from a turret was safer.",
         style="Eager, gun-obsessed. Speaks with Rodian accent.",
         fallbacks=["Grek adjusts his targeting visor. 'I never miss. Almost never.'",
                    "'Point me at a turret and watch the fireworks.'"],
         space_skills={"starship gunnery": "5D+2", "sensors": "4D"})),

    ("Mira Tann", 30, "Human",
     "A wiry Human mechanic with grease-stained coveralls and a confident smile.",
     _sheet(dex="2D+2", mec="3D", per="3D", stre="3D+1", tec="4D+2",
            skills={"dodge": "3D+1", "space_transports_repair": "5D+1",
                    "starship_weapon_repair": "4D+2", "droid_repair": "4D",
                    "space_transports": "3D+2"}),
     _ai(personality="Mira keeps ships running with baling wire and ingenuity. "
         "Self-taught. Prefers machines to people.",
         style="Practical, no-nonsense. Talks in technical jargon.",
         fallbacks=["'What'd you do to this poor ship?'",
                    "Mira peers into an access panel, already diagnosing."],
         space_skills={"space transports repair": "5D+1",
                       "starship weapon repair": "4D+2"})),

    ("Tik-So", 30, "Sullustan",
     "A bright-eyed Sullustan navigator with a datapad full of star charts.",
     _sheet(dex="2D+1", kno="3D+2", mec="4D", per="3D", stre="2D", tec="3D+1",
            skills={"astrogation": "5D+2", "space_transports": "4D+1",
                    "sensors": "4D+2", "planetary_systems": "4D+1"},
            species="Sullustan"),
     _ai(personality="Tik-So has memorized half the known hyperlanes. Chatty. "
         "Tells stories about every system he's visited.",
         style="Enthusiastic, chatty. Lots of space trivia.",
         fallbacks=["'I can plot a jump to Kessel in twelve parsecs! Well, fourteen.'",
                    "Tik-So scrolls through star charts eagerly."],
         space_skills={"astrogation": "5D+2", "sensors": "4D+2",
                       "space transports": "4D+1"})),
]

# ==============================================================
# PRE-SPAWNED SHIPS
# (template_key, ship_name, docked_at_room_idx, bridge_desc)
# ==============================================================
SHIPS = [
    # A beat-up YT-1300 in Bay 94 -- the "starter ship" players can buy
    ("yt_1300", "Rusty Mynock", 1,
     "The cockpit of this battered YT-1300 hums with mismatched instruments. "
     "Half the warning lights are on. A co-pilot station sits to the right. "
     "Gunner turret access is through the dorsal hatch."),

    # A Z-95 Headhunter in Bay 86 -- cheap starter fighter
    ("z_95", "Dusty Hawk", 4,
     "The cramped cockpit of this old Z-95 Headhunter smells of coolant and "
     "old sweat. Instruments flicker. The ejection seat looks questionable."),

    # A Ghtroc 720 freighter in Bay 87 -- mid-tier freighter
    ("ghtroc_720", "Krayt's Fortune", 5,
     "The bridge of this Ghtroc 720 is surprisingly spacious for a light freighter. "
     "The Corellian-style controls are worn smooth from years of use. A co-pilot "
     "station and nav computer dominate the right side."),

    # An Imperial Lambda shuttle in Bay 92 -- seized by customs, expensive
    ("lambda_shuttle", "Imperial Surplus 7", 6,
     "The bridge of this Lambda-class shuttle still bears Imperial insignia. "
     "Three crew stations face forward. The controls are military-precise. "
     "Someone has scratched 'SURPLUS - DO NOT REQUISITION' into the console."),
]


# ==============================================================
# BUILD FUNCTION
# ==============================================================

async def build():
    db = Database("sw_mush.db")
    await db.connect()
    await db.initialize()

    print("+============================================+")
    print("|    Building Mos Eisley v2 -- Full World      |")
    print("+============================================+")

    # -- Zones --
    print("\n  Creating zones...")
    zones = {}
    zones["mos_eisley"] = await db.create_zone(
        "Mos Eisley", properties=json.dumps({"environment": "desert_urban",
                                              "lighting": "bright", "gravity": "standard"}))
    zones["spaceport"] = await db.create_zone(
        "Spaceport District", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 3, "environment": "industrial"}))
    zones["cantina"] = await db.create_zone(
        "Chalmun's Cantina", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "lighting": "dim", "environment": "cantina"}))
    zones["streets"] = await db.create_zone(
        "Streets & Markets", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "street"}))
    zones["government"] = await db.create_zone(
        "Government Quarter", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "official"}))
    zones["jabba"] = await db.create_zone(
        "Jabba's Townhouse", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "lighting": "dim", "environment": "palatial"}))
    zones["shops"] = await db.create_zone(
        "Commercial District", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "environment": "commercial"}))
    print(f"    {len(zones)} zones created")

    # -- Rooms --
    print(f"\n  Creating {len(ROOMS)} rooms...")
    room_ids = []
    for i, (name, short, long) in enumerate(ROOMS):
        zone_key = ROOM_ZONES.get(i)
        zone_id = zones.get(zone_key) if zone_key else None
        props = json.dumps(ROOM_OVERRIDES.get(i, {}))
        rid = await db.create_room(name, short, long, zone_id=zone_id, properties=props)
        room_ids.append(rid)
        print(f"    [{rid:3d}] {name}")

    # -- Exits --
    print(f"\n  Creating {len(EXITS)} exit pairs...")
    for from_idx, to_idx, direction, reverse in EXITS:
        from_id = room_ids[from_idx]
        to_id = room_ids[to_idx]
        await db.create_exit(from_id, to_id, direction)
        await db.create_exit(to_id, from_id, reverse)

    # Connect to seed rooms (1=Landing Pad, 2=Mos Eisley Street, 3=Cantina)
    print("\n  Linking seed rooms to new Mos Eisley...")
    spaceport_row_id = room_ids[7]
    market_id = room_ids[8]
    cantina_entrance_id = room_ids[12]

    await db.create_exit(1, spaceport_row_id, "north")
    await db.create_exit(spaceport_row_id, 1, "south")
    await db.create_exit(2, market_id, "north")
    await db.create_exit(market_id, 2, "south")
    await db.create_exit(3, cantina_entrance_id, "east")
    await db.create_exit(cantina_entrance_id, 3, "west")
    print("    Seed rooms linked (Landing Pad, Street, Cantina)")

    # -- NPCs (combat-ready) --
    print(f"\n  Creating {len(NPCS)} combat-ready NPCs...")
    npc_count = 0
    for name, room_idx, species, desc, sheet, ai_cfg in NPCS:
        rid = room_ids[room_idx]
        npc_id = await db.create_npc(
            name=name, room_id=rid, species=species, description=desc,
            char_sheet_json=json.dumps(sheet),
            ai_config_json=json.dumps(ai_cfg),
        )
        hostile_tag = " [HOSTILE]" if ai_cfg.get("hostile") else ""
        print(f"    #{npc_id:3d} {name:30s} in {ROOMS[room_idx][0][:25]}{hostile_tag}")
        npc_count += 1

    # -- Hireable Crew NPCs --
    print(f"\n  Creating {len(HIREABLE_CREW)} hireable crew NPCs...")
    for name, room_idx, species, desc, sheet, ai_cfg in HIREABLE_CREW:
        rid = room_ids[room_idx]
        npc_id = await db.create_npc(
            name=name, room_id=rid, species=species, description=desc,
            char_sheet_json=json.dumps(sheet),
            ai_config_json=json.dumps(ai_cfg),
        )
        print(f"    #{npc_id:3d} {name:30s} [HIREABLE] in {ROOMS[room_idx][0][:25]}")
        npc_count += 1

    # -- Ships --
    print(f"\n  Spawning {len(SHIPS)} ships in docking bays...")
    for template_key, ship_name, bay_idx, bridge_desc in SHIPS:
        bay_room_id = room_ids[bay_idx]
        # Create bridge room
        bridge_id = await db.create_room(
            f"{ship_name} - Bridge",
            f"The bridge of the {ship_name}.",
            bridge_desc,
        )
        # Create the ship record
        cursor = await db._db.execute(
            """INSERT INTO ships (template, name, bridge_room_id, docked_at,
               hull_damage, shield_damage, systems, crew, cargo)
               VALUES (?, ?, ?, ?, 0, 0, '{}', '{}', '[]')""",
            (template_key, ship_name, bridge_id, bay_room_id),
        )
        await db._db.commit()
        ship_id = cursor.lastrowid

        # Create exit from bay to bridge and back
        await db.create_exit(bay_room_id, bridge_id, "board")
        await db.create_exit(bridge_id, bay_room_id, "disembark")

        bay_name = ROOMS[bay_idx][0]
        print(f"    Ship #{ship_id:3d} '{ship_name}' ({template_key}) docked at {bay_name}")

    # -- Summary --
    total_rooms = len(ROOMS) + len(SHIPS)  # rooms + bridge rooms
    total_exits = len(EXITS) * 2 + 6 + len(SHIPS) * 2  # pairs + seed links + ship exits
    print(f"\n  +======================================+")
    print(f"  |  BUILD COMPLETE                      |")
    print(f"  |  Rooms:    {total_rooms:4d}                      |")
    print(f"  |  Exits:    {total_exits:4d}                      |")
    print(f"  |  NPCs:     {npc_count:4d} ({sum(1 for _,_,_,_,_,a in NPCS if a.get('hostile')):d} hostile)           |")
    print(f"  |  Crew:     {len(HIREABLE_CREW):4d} (hireable)           |")
    print(f"  |  Ships:    {len(SHIPS):4d} (docked)              |")
    print(f"  +======================================+")

    await db.close()


if __name__ == "__main__":
    asyncio.run(build())
