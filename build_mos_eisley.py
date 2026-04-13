# -*- coding: utf-8 -*-
"""
SW_MUSH World Builder v4
============================
Populates the full game world across four planets with security zones
from the Security Zones Design v1 (EVE-inspired secured/contested/lawless).

Planets & Room Counts:
  - Mos Eisley (Tatooine) — 54 rooms, 7 zones  [GG7 core + Outskirts/Wastes]
  - Nar Shaddaa              — 30 rooms, 4 zones  [Dark Empire / EU + Warrens]
  - Kessel                   — 15 rooms, 3 zones  [WEG sourcebooks / canon + Deep Mines]
  - Corellia (Coronet City)  — 24 rooms, 4 zones  [WEG / general SW lore + districts]

Zone security tiers (from security_zones_design_v1.md):
  SECURED   — No PvP, no NPC aggro. Safe areas.
  CONTESTED — NPC combat enabled, PvP requires challenge/accept.
  LAWLESS   — Full PvP, aggressive NPCs, rare resources, high rewards.

Also creates:
  - Combat-ready NPCs (char_sheet_json + ai_config_json)
  - Hostile NPCs (stormtroopers, thugs, creatures) that attack on sight
  - Hireable crew NPCs at cantinas and spaceports
  - Pre-spawned ships docked in bays with bridge rooms
  - NPCs for all four planets including new wilderness/dangerous zones

Auto-build:
  Called automatically by game_server.py on startup if the world
  hasn't been populated yet (room count <= 3 seed rooms).
  Can also be run standalone:
    python build_mos_eisley.py

Usage (standalone):
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
from engine.npc_loader import load_npcs_from_yaml


# ── Exit direction / label splitter ──────────────────────────────────────────
# EXITS tuples use strings like "north to Inn" or "south to Bay 94".
# The part before the first space (or the full string if no space) is the
# movement key (what the player types).  Everything after "to " is the label.
_VALID_DIRECTIONS = frozenset({
    "north", "south", "east", "west", "up", "down",
    "northeast", "northwest", "southeast", "southwest",
    "enter", "leave", "in", "out", "board", "disembark",
})

def _split_exit(raw: str) -> tuple[str, str]:
    """Split 'north to Inn' → ('north', 'Inn').  'north' → ('north', '')."""
    raw = raw.strip()
    parts = raw.split(None, 1)  # max 2 parts
    key = parts[0].lower()
    if key not in _VALID_DIRECTIONS:
        # Custom keyword like "board" or full phrase — keep as-is, no label
        return raw.lower(), ""
    if len(parts) == 1:
        return key, ""
    rest = parts[1].strip()
    # Strip leading "to " if present
    label = rest[3:].strip() if rest.lower().startswith("to ") else rest
    return key, label

# ================================================================
# ROOM DEFINITIONS  (name, short_desc, long_desc)
# IDs assigned starting at 10 to avoid seed room collisions.
#
# === INDEX LAYOUT ===
# Tatooine / Mos Eisley:
#   0-6   : Spaceport District (secured)
#   7-11  : Streets & Markets (secured)
#   12-14 : Chalmun's Cantina (secured)
#   15-17 : Commercial — Shops (secured)
#   18-19 : Jabba's Townhouse (contested — faction override)
#   20-22 : Government / Civic (secured)
#   23-26 : Spaceport Overflow (secured)
#   27-39 : Commercial / Misc (secured)
#   40-47 : Outskirts — contested zone (new)
#   48-53 : Jundland Wastes — lawless zone (new)
#
# Nar Shaddaa:
#   54-55 : Landing Pads (secured)
#   56-63 : Corellian Sector / Promenade (contested)
#   64-69 : Undercity (lawless)
#   70-72 : Upper Levels (contested)
#   73-78 : Expanded areas (mixed)
#   79-83 : Warrens — deep lawless zone (new)
#
# Kessel:
#   84-86 : Surface / Station (contested)
#   87-91 : Garrison / Mines (lawless)
#   92-95 : Deep Mines — lawless (new)
#
# Corellia / Coronet City:
#   96-99  : Starport / Port District (contested)
#   100-105: City Center (secured)
#   106-108: Government (secured)
#   109-112: Industrial / Shipyards (secured)
#   113-116: Old Quarter (contested)
#   117-119: Blue Sector / Coastal (contested)
# ================================================================

ROOMS = [
    # ==============================================================
    # MOS EISLEY (Tatooine) — rooms 0-53
    # ==============================================================

    # --- SPACEPORT DISTRICT (secured) --- rooms 0-6
    # 0
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

    # --- STREETS & MARKETS (secured) --- rooms 7-11
    # 7
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

    # --- CHALMUN'S CANTINA (secured) --- rooms 12-14
    # 12
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

    # --- COMMERCIAL DISTRICT (secured) --- rooms 15-17
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

    # --- JABBA'S TOWNHOUSE (contested, faction_override: hutt) --- rooms 18-19
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

    # --- GOVERNMENT / CIVIC (secured) --- rooms 20-22
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

    # --- SPACEPORT OVERFLOW / MISC (secured) --- rooms 23-26
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

    # --- MORE COMMERCIAL (secured) --- rooms 27-39
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

    # --- OUTSKIRTS (contested) --- rooms 40-47 (NEW)
    # Transitional zone between the safe city and the lawless wastes.
    # Source: GG7 Tatooine geography + WEG40120 Tatooine regional descriptions.
    # 40
    ("City Outskirts - Eastern Gate",
     "The eastern edge of Mos Eisley where the streets give way to desert.",
     "The last buildings of Mos Eisley end abruptly at a low ferrocrete wall. Beyond, "
     "the Jundland Wastes shimmer in the heat. A weathered gate stands half-open — no "
     "one has bothered to repair it in years. Imperial patrols sometimes pass through "
     "but rarely venture further. Swoop tracks scar the sand outside."),
    # 41
    ("City Outskirts - Scavenger Market",
     "A ramshackle collection of stalls where Jawas trade salvage.",
     "Outside the city wall, Jawas have established a semi-permanent trading post "
     "built from scavenged sandcrawler parts. Moisture farmers haggle over vaporator "
     "components. Droids of questionable provenance stand in crooked rows. The smell "
     "of Jawa is distinctive and lingering. A hand-painted sign reads 'GOOD DROIDS "
     "CHEEP' in phonetic Basic."),
    # 42
    ("City Outskirts - Abandoned Moisture Farm",
     "A moisture farm abandoned after a Tusken raid, now a squatter camp.",
     "Four vaporator towers stand silent, their condensation tubes stripped for parts. "
     "The underground living quarters have been claimed by drifters and outcasts — "
     "beings with nowhere else to go. Makeshift shelters lean against the old "
     "ferrocrete homestead walls. A faint smell of charring lingers from the raid."),
    # 43
    ("City Outskirts - Speeder Track",
     "An informal swoop racing circuit carved into the hardpan desert.",
     "Berms of packed sand mark a rough oval course. Swoop gangs gather here at dusk "
     "for illegal races and to settle disputes. During the day, the track is empty "
     "except for Womp Rats darting between the berms. Discarded fuel cells and broken "
     "swoop parts litter the edges."),
    # 44
    ("City Outskirts - Imperial Checkpoint",
     "A prefab checkpoint on the main road heading east from Mos Eisley.",
     "A plasteel booth and retractable barrier mark the last Imperial presence before "
     "the open desert. Two stormtroopers check IDs with varying degrees of interest. "
     "During Crackdowns, the checkpoint is reinforced with an E-web emplacement and "
     "sensor equipment. Most locals know the back routes around it."),
    # 45
    ("City Outskirts - Wrecked Sandcrawler",
     "The rusting hulk of a Jawa sandcrawler, half-buried in sand.",
     "This sandcrawler was destroyed years ago — whether by Tusken Raiders or "
     "something worse is debated in the cantina. Its massive treads have sunk into "
     "the desert floor. The interior has been stripped of anything valuable, but "
     "the superstructure provides welcome shade. Womp Rat warrens riddle the hull."),
    # 46
    ("City Outskirts - Hermit's Ridge",
     "A rocky outcropping overlooking the desert approaches to Mos Eisley.",
     "Weathered sandstone formations create natural shelters along this ridge. An "
     "old hermit is said to live somewhere in these rocks — a crazy old wizard, "
     "the locals say, best left alone. The view extends for kilometers across the "
     "desert floor. Thermal updrafts make the air dance."),
    # 47
    ("City Outskirts - Desert Trail Junction",
     "Where the main road forks: east toward the Wastes, south toward Anchorhead.",
     "A trail marker — three stones stacked by some long-forgotten traveler — "
     "indicates the fork. The eastern path narrows into a rocky defile leading "
     "toward the Jundland Wastes. The southern road is wider, following the route "
     "to Anchorhead and the moisture farming settlements. Heat mirages shimmer "
     "on both horizons."),

    # --- JUNDLAND WASTES (lawless) --- rooms 48-53 (NEW)
    # The dangerous wilderness beyond Mos Eisley. Tusken Raiders, Krayt
    # Dragons, rare resources. Source: GG7 geography, WEG40120 Tatooine.
    # 48
    ("Jundland Wastes - Canyon Mouth",
     "The entrance to a narrow canyon cutting through sandstone cliffs.",
     "Towering walls of wind-carved sandstone rise on either side, casting deep "
     "shadow even under the twin suns. The canyon floor is littered with rocks "
     "fallen from above — natural chokepoints that Tusken Raiders use for ambushes. "
     "Bantha tracks are pressed deep into the sand. The silence is oppressive."),
    # 49
    ("Jundland Wastes - Beggar's Canyon",
     "A treacherous canyon famous as a test of piloting skill.",
     "Sheer walls plunge hundreds of meters on either side of a winding rock "
     "corridor barely wide enough for a speeder. Local youths race T-16 "
     "Skyhoppers through here. The canyon floor is littered with wreckage from "
     "those who misjudged the turns. Womp Rats nest in the crevices — some "
     "growing nearly two meters long."),
    # 50
    ("Jundland Wastes - Tusken Camp Overlook",
     "A high vantage point overlooking a Tusken Raider encampment.",
     "From behind a screen of boulders, a Tusken camp is visible in the valley "
     "below — Bantha-hide tents arranged in a rough circle, cook fires sending "
     "thin smoke into the sky. Banthas graze on scrub. The Sand People are "
     "fiercely territorial; approaching the camp uninvited is suicide. Even "
     "from this distance, their gaderffii sticks glint in the sun."),
    # 51
    ("Jundland Wastes - Krayt Dragon Graveyard",
     "A desolate stretch of desert where Krayt Dragons come to die.",
     "Massive ribcages arch from the sand like the keels of buried starships. "
     "Bleached skulls the size of landspeeders stare with empty eye sockets. "
     "The pearl-hunters come here despite the danger — a single Krayt Dragon "
     "pearl can be worth ten thousand credits. The bones themselves are prized "
     "by collectors. Something moves in the sand nearby."),
    # 52
    ("Jundland Wastes - Hidden Cave",
     "A natural cave concealed behind a rockfall, showing signs of habitation.",
     "The cave entrance is invisible from the canyon floor, screened by tumbled "
     "boulders. Inside, the temperature drops sharply. Someone has been here "
     "recently — a fire ring, water containers, survival supplies. Scratched "
     "into the wall in several languages: coordinates, warnings, and what might "
     "be a Rebel Alliance symbol half-obscured by sand."),
    # 53
    ("Jundland Wastes - Dune Sea Edge",
     "Where the Jundland Wastes give way to the endless Dune Sea.",
     "The rocky terrain falls away to an ocean of sand stretching to every "
     "horizon. The Great Pit of Carkoon lies somewhere out there — and Jabba's "
     "palace beyond. The wind carries fine grit that stings exposed skin. "
     "Navigation without instruments is nearly impossible. The Dune Sea has "
     "claimed more lives than the Tusken Raiders ever will."),

    # ==============================================================
    # NAR SHADDAA — rooms 54-83 (30 rooms)
    # Zones: landing_pad (secured), promenade (contested),
    #        undercity (lawless), warrens (lawless)
    # Sources: Dark Empire Sourcebook, Galaxy Guide 12, Hutt Space lore
    # ==============================================================

    # --- LANDING PAD (secured) --- rooms 54-55
    # 54
    ("Nar Shaddaa - Docking Bay Aurek",
     "A grimy docking bay in the Corellian Sector of Nar Shaddaa.",
     "Fuel-stained duracrete slopes down into this cavernous bay. Refueling spires "
     "tower overhead, their navigation lights blinking in the perpetual gloom. Cargo "
     "droids haul crates without supervision. A battered kiosk charges 50 credits per "
     "day, payable in advance. No questions asked."),
    # 55
    ("Nar Shaddaa - Landing Platform Besh",
     "An exposed landing platform jutting from the upper levels.",
     "Wind howls across this platform, hundreds of stories above the undercity. "
     "Mag-clamps secure ships against the constant gale. The view of Nar Shaddaa's "
     "endless cityscape stretches to every horizon, spire after spire vanishing into "
     "atmospheric haze. Nal Hutta looms in the sky above."),

    # --- PROMENADE / CORELLIAN SECTOR (contested) --- rooms 56-63
    # 56
    ("Nar Shaddaa - Corellian Sector Promenade",
     "The main street of the Corellian Sector, a smugglers' paradise.",
     "Neon holographic signs flicker above a crowded thoroughfare. Corellians and "
     "beings from a hundred worlds push through the crowd. Street vendors hawk counterfeit "
     "transponder chips and black market spice. The air reeks of engine exhaust and "
     "cooking oil. Somewhere above, the refueling spires vanish into clouds."),
    # 57
    ("Nar Shaddaa - The Burning Deck Cantina",
     "A notorious smuggler cantina deep in the Corellian Sector.",
     "Low ceilings, thick smoke, and the persistent clatter of sabacc chips define "
     "this dive. Corellian whiskey flows cheap. Smuggling guild recruiters size up "
     "newcomers from corner booths. A holographic scoreboard tracks active cargo runs. "
     "The bartender, a scarred Weequay, has a blaster under the counter."),
    # 58
    ("Nar Shaddaa - Burning Deck Back Room",
     "A private room behind the cantina used for high-stakes deals.",
     "Soundproofed walls and a signal jammer ensure privacy. A circular table seats "
     "six. Scorch marks on the ceiling tell of negotiations gone wrong. The door has "
     "three locks and no window."),
    # 59
    ("Nar Shaddaa - Smugglers' Guild Hall",
     "The unofficial headquarters of the Corellian Smugglers' Guild.",
     "What looks like an abandoned warehouse opens into a surprisingly organized "
     "operations center. Star charts cover the walls. Dispatchers coordinate cargo "
     "runs across a dozen sectors. A communal armory sits behind a cage. Membership "
     "dues are 500 credits per standard month."),
    # 60
    ("Nar Shaddaa - Vertical Bazaar",
     "A multi-level marketplace built into an old refueling spire.",
     "Shops and stalls ring the interior of a hollowed-out spire, connected by "
     "rickety turbolifts and spiral ramps. Each level specializes: weapons on three, "
     "ship parts on seven, information on twelve. A central open shaft lets you see "
     "fifty stories up and down. Vertigo is free of charge."),
    # 61
    ("Nar Shaddaa - Bounty Hunters' Quarter",
     "A fortified block claimed by bounty hunters and mercenaries.",
     "Reinforced doors and weapon scanners mark the entrance to this self-policing "
     "enclave. Bounty posting boards line the main corridor. An equipment shop "
     "specializes in tracking devices and restraints. The cantina here serves strong "
     "drink and asks fewer questions than most."),
    # 62
    ("Nar Shaddaa - Old Corellian Quarter",
     "A weathered residential block, home to longtime Corellian expatriates.",
     "Older than the rest of the Corellian Sector, this block predates the Imperial "
     "era. Residents have lived here for generations, maintaining Corellian customs "
     "in exile. A communal kitchen serves as social center. Graffiti in Corellian "
     "script covers the entry archway: 'Never tell me the odds.'"),
    # 63
    ("Nar Shaddaa - Refugee Sector",
     "A crowded district where displaced beings eke out survival.",
     "Makeshift shelters crowd the corridors between abandoned industrial blocks. "
     "Families huddle around shared heating vents. Children beg in a dozen languages. "
     "Relief droids distribute protein packs on a first-come basis. The smell of too "
     "many beings in too small a space is overwhelming."),

    # --- UNDERCITY (lawless) --- rooms 64-69
    # 64
    ("Nar Shaddaa - Undercity Market",
     "A sprawling black market in the lower levels of Nar Shaddaa.",
     "Daylight has never reached these depths. Bioluminescent fungi and jury-rigged "
     "glowpanels cast everything in sickly blue-green. Stalls built from scrap metal "
     "sell everything from illegal weapons to stolen ship parts. Pickpockets and "
     "informants lurk at every junction. The law does not come here."),
    # 65
    ("Nar Shaddaa - Undercity Depths",
     "The deepest accessible level of Nar Shaddaa's vertical city.",
     "Corroded catwalks span chasms that plunge into absolute darkness. The mutated "
     "descendants of the Evocii scuttle in the shadows, wary of strangers. Moisture "
     "condenses on every surface. Strange sounds echo from below — machinery, or "
     "something else entirely. Few who venture this deep return unchanged."),
    # 66
    ("Nar Shaddaa - Spice Den",
     "A dimly lit den where various forms of spice are consumed.",
     "Reclining couches line the walls, occupied by beings in various states of "
     "intoxication. Glitterstim, ryll, and more exotic substances change hands in "
     "whispered transactions. The Twi'lek proprietor watches with calculating eyes. "
     "A back exit leads deeper into the Undercity."),
    # 67
    ("Nar Shaddaa - Droid Junkyard",
     "A vast scrapyard of decommissioned and stolen droids.",
     "Mountains of droid parts stretch to the hazy ceiling. Salvagers pick through "
     "the wreckage with magnetic tools. Occasionally a half-functional droid twitches "
     "or speaks a garbled phrase. The Ugnaught proprietor insists everything is "
     "legitimately acquired. Nobody believes him."),
    # 68
    ("Nar Shaddaa - Black Market Medcenter",
     "An unlicensed medical facility hidden behind a scrap metal front.",
     "Behind a rust-streaked door lies a surprisingly functional operating room. "
     "Recycled bacta tanks line one wall, half-full. Stolen medical equipment fills "
     "surgical bays. The doctor charges double the legal rate but asks no questions "
     "and files no reports. A Twi'lek nurse monitors the waiting area."),
    # 69
    ("Nar Shaddaa - Fighting Pits",
     "An underground arena where beings fight for credits and survival.",
     "Concentric rings of rusted seating surround a sand-floored pit stained dark "
     "with old blood. Betters crowd the rails, screaming odds. Combatants range from "
     "desperate refugees to professional gladiators. The Hutt who runs the operation "
     "takes a forty percent cut. House rules: no blasters, no surrender, and the "
     "crowd decides if losers walk out."),

    # --- UPPER LEVELS (contested) --- rooms 70-72
    # 70
    ("Nar Shaddaa - Hutt Emissary Tower - Lobby",
     "The opulent lobby of a Hutt-controlled tower in the upper levels.",
     "Polished duranium floors reflect the garish lighting. A massive Hutt clan sigil "
     "dominates one wall. Gamorrean guards flank the turbolift entrance. Visitors are "
     "scanned for weapons — then scanned again. A protocol droid manages appointments "
     "with mechanical precision."),
    # 71
    ("Nar Shaddaa - Hutt Emissary Tower - Audience Chamber",
     "An audience chamber for conducting Hutt business on the Smuggler's Moon.",
     "The chamber is designed to intimidate. A raised dais supports a Hutt repulsor "
     "sled. Hookah pipes and platters of live food surround the seat of power. Supplicants "
     "stand below, necks craned upward. Wall-mounted security cameras record everything."),
    # 72
    ("Nar Shaddaa - The Grid",
     "An information broker's den in the upper levels, accessible by coded lift.",
     "Banks of screens show feeds from across the Smuggler's Moon — dock cameras, "
     "comm intercepts, Imperial patrol schedules. The broker, a blind Miralukan, "
     "trades exclusively in information. No physical goods. No violence permitted "
     "on premises. This rule is enforced by three heavily armed Gamorrean sentinels."),

    # --- EXPANDED AREAS (mixed) --- rooms 73-78
    # 73
    ("Nar Shaddaa - Ship Parts Emporium",
     "A multi-deck shop selling salvaged and black-market starship components.",
     "Seven levels of shelving hold hyperdrive motivators, sensor arrays, shield "
     "generators, and ion cannon components. The stock is eighty percent stolen, "
     "twenty percent salvage. The Sullustan owner maintains meticulous inventory "
     "and competitive pricing. Rare parts available on order."),
    # 74
    ("Nar Shaddaa - Renna Dox's Workshop",
     "A cluttered mechanical workshop run by a master shipwright.",
     "Every surface is covered with ship components in various states of assembly "
     "or disassembly. Diagrams and schematics paper the walls. Renna Dox — a broad-"
     "shouldered Zabrak woman with engine grease permanently under her fingernails — "
     "builds custom ship modifications and teaches Technical skills to those willing "
     "to work for the knowledge."),
    # 75
    ("Nar Shaddaa - The Floating Market",
     "Repulsorlift platforms drifting between towers, forming an open-air market.",
     "A dozen hovering platforms connected by gangways form this unusual marketplace. "
     "The platforms drift slowly in the thermal currents between towers, requiring "
     "some agility to navigate between them. Food, cheap goods, and stolen Imperial "
     "surplus are the primary offerings. The market has no fixed address — it moves."),
    # 76
    ("Nar Shaddaa - Enforcer Alley",
     "A narrow passage controlled by Hutt enforcers collecting protection money.",
     "This passage connects the Corellian Sector to the upper docks. Hutt-affiliated "
     "enforcers demand a 'transit toll' from everyone passing through. Refusing is "
     "inadvisable. The alley smells of spilled Corellian ale and old fear. Graffiti "
     "marks which gangs claim what territory."),
    # 77
    ("Nar Shaddaa - Weapons Cache",
     "A fortified room in the Bounty Hunters' Quarter, selling military hardware.",
     "Security shutters and a Durasteel door protect this arsenal. The proprietor, "
     "an armless Duros who lost both limbs on a bad contract, operates the shop via "
     "waldos. Every weapon type is represented — blasters, melee, explosives, even "
     "restricted military stock if the price is right."),
    # 78
    ("Nar Shaddaa - Upper Dock Observation Level",
     "A windswept observation level above the main docking platforms.",
     "The view from here is staggering — Nar Shaddaa's cityscape in every direction, "
     "stretching to the curved horizon. Ships arrive and depart in constant streams. "
     "Nal Hutta hangs enormous in the sky above. Sensor equipment here monitors "
     "traffic for the dock authority — which is actually a Hutt front company."),

    # --- WARRENS (lawless) --- rooms 79-83 (NEW)
    # The absolute depths. Worse than the Undercity. Rare resources,
    # extreme danger, future territory control target.
    # 79
    ("Nar Shaddaa - The Warrens - Entry Shaft",
     "A ventilation shaft descending into the deepest levels of Nar Shaddaa.",
     "The turbolift stopped working decades ago. A jury-rigged ladder of welded "
     "pipe descends into the Warrens — the lowest inhabitable levels of the "
     "Smuggler's Moon. The air here is thick, recycled so many times it tastes "
     "metallic. A warning scrawled in blood-red paint: 'NO LAW BELOW THIS LINE.'"),
    # 80
    ("Nar Shaddaa - The Warrens - Fungal Cavern",
     "A vast natural cavity colonized by bioluminescent fungal growths.",
     "Enormous mushroom-like growths reach three meters tall, their caps glowing "
     "with pale blue light. The air is warm and humid, thick with spores. The Evocii "
     "— the original inhabitants of Nar Shaddaa, displaced millennia ago by the "
     "Hutts — have adapted to life here. Their camps are visible as clusters of "
     "dim firelight among the fungi. They do not welcome outsiders."),
    # 81
    ("Nar Shaddaa - The Warrens - Reactor Core Access",
     "A catwalk spanning an ancient reactor core, still partially active.",
     "The heat is intense — residual energy from a reactor that has been running "
     "unmaintained for centuries. The catwalk vibrates with suppressed power. Rare "
     "energy crystals grow on the cooling fins like mineral barnacles, prized by "
     "crafters and smugglers alike. The radiation levels are... elevated. Don't "
     "linger."),
    # 82
    ("Nar Shaddaa - The Warrens - Scavenger Den",
     "A fortified camp where Warrens scavengers trade salvage from the deep.",
     "Behind a barricade of welded durasteel plates, a small community of hard-bitten "
     "scavengers has carved out survival. They trade in reactor components, rare "
     "minerals, and information about what lurks in the deeper tunnels. Payment is "
     "accepted in credits, supplies, or interesting salvage. Trust is earned in "
     "blood down here."),
    # 83
    ("Nar Shaddaa - The Warrens - Collapsed Plaza",
     "The ruins of what was once a grand public space, now buried under centuries of city.",
     "Columns of an ancient plaza still stand, supporting nothing — the ceiling is a "
     "tangle of collapsed infrastructure from dozens of building layers above. The "
     "original tile floor is partially visible under debris. This was street level "
     "thousands of years ago, before the Hutts built their towers on top of the "
     "Evocii civilization. History, forgotten and buried."),

    # ==============================================================
    # KESSEL — rooms 84-95 (12 rooms)
    # Zones: station (contested), mines (lawless), deep_mines (lawless)
    # Sources: WEG sourcebooks, The Kessel Run lore, canon references
    # ==============================================================

    # --- SURFACE / STATION (contested) --- rooms 84-86
    # 84
    ("Kessel - Spaceport Landing Field",
     "The heavily guarded landing field of Kessel's main spaceport.",
     "A flat expanse of permacrete surrounded by guard towers and sensor arrays. "
     "The thin atmosphere makes breathing labored without supplements. The Maw's "
     "gravitational distortion is visible as a shimmer on the horizon. Imperial "
     "shuttles and prison transports dominate the traffic."),
    # 85
    ("Kessel - Garrison Checkpoint",
     "An Imperial garrison checkpoint controlling access to the mines.",
     "Blast doors and ray shields funnel all traffic through scanners. Stormtroopers "
     "check identification with humorless efficiency. A holo-display lists current "
     "inmates and their work assignments. The walls are reinforced to withstand "
     "prisoner riots."),
    # 86
    ("Kessel - Administration Block",
     "The administrative center for Kessel's mining operations.",
     "Desks and data terminals fill this climate-controlled building — a stark "
     "contrast to the harsh conditions outside. Mining quotas, prisoner records, "
     "and shipment manifests scroll across screens. The warden's office occupies "
     "the top floor behind blast-proof transparisteel."),

    # --- MINES (lawless) --- rooms 87-91
    # 87
    ("Kessel - Mine Entrance - Level 1",
     "The primary entrance to Kessel's infamous spice mines.",
     "A massive tunnel mouth descends into darkness. Ore carts on magnetic rails "
     "emerge at regular intervals, filled with raw spice ore. The air is thick with "
     "glitterstim dust that sparkles in the floodlights. Miners shuffle past in "
     "chains, their eyes hollow."),
    # 88
    ("Kessel - Spice Processing Facility",
     "A heavily secured facility where raw spice is refined.",
     "Sealed clean rooms behind transparisteel walls house the delicate refining "
     "process. Workers in protective suits handle crystallized glitterstim with "
     "precise instruments. Armed guards watch from catwalks above. The refined "
     "product is worth more than its weight in aurodium."),
    # 89
    ("Kessel - Prisoner Barracks",
     "Bleak dormitories housing Kessel's forced labor population.",
     "Row upon row of bare metal bunks. The air recyclers barely function. "
     "Prisoners huddle in groups defined by species, crime, or simple survival. "
     "Guard droids patrol on fixed routes. A small infirmary treats only injuries "
     "that would reduce work output."),
    # 90
    ("Kessel - Black Market Tunnel",
     "A hidden tunnel network where guards and prisoners trade illegally.",
     "Behind a false wall in a maintenance corridor, a cramped network of tunnels "
     "hosts Kessel's worst-kept secret. Guards sell ration supplements, prisoners "
     "trade refined spice samples, and information changes hands in whispers. "
     "Everyone pretends this place doesn't exist."),
    # 91
    ("Kessel - Observation Deck",
     "A windswept observation platform overlooking the Maw.",
     "Transparisteel panels offer a terrifying view of the Maw — a cluster of "
     "black holes whose gravitational pull warps the stars themselves. Navigating "
     "the Kessel Run means skirting this cosmic horror. On clear days, the accretion "
     "disks glow with captured starlight. The view is humbling."),

    # --- DEEP MINES (lawless) --- rooms 92-95 (NEW)
    # Deeper than the main mines. Extreme danger, rare resources.
    # 92
    ("Kessel - Deep Mines - Shaft Junction",
     "Where the maintained mine shafts give way to older, abandoned tunnels.",
     "The magnetic rail ends here. Beyond this point, the tunnels were sealed "
     "decades ago after a series of energy spider attacks killed an entire work "
     "crew. Someone has cut through the blast door. The air is thinner, the "
     "glitterstim dust thicker. Bioluminescent spice deposits glow in the walls "
     "like trapped stars."),
    # 93
    ("Kessel - Deep Mines - Energy Spider Caverns",
     "Deep caverns where dangerous energy spiders guard raw glitterstim.",
     "The natural caverns glow with bioluminescence and raw spice deposits. "
     "Energy spiders — deadly silicon-based predators — spin webs of pure energy "
     "between the stalactites. Miners work in teams, harvesting spice while "
     "lookouts watch for spider movement. Death is common here."),
    # 94
    ("Kessel - Deep Mines - Smuggler's Contact Point",
     "A concealed meeting point used by spice smugglers.",
     "Tucked behind the spaceport's maintenance hangars, this prefab shelter "
     "serves as the contact point for smugglers brave or desperate enough to run "
     "Kessel spice. A coded signal on frequency 1138 announces available cargo. "
     "Payment is always in advance, and in hard credits only."),
    # 95
    ("Kessel - Deep Mines - Collapsed Gallery",
     "A partially collapsed cavern revealing ancient geological formations.",
     "A cave-in opened this gallery to a natural cavern system that predates "
     "the mining operation by millennia. Crystal formations of unknown composition "
     "line the walls, some pulsing with faint internal light. Geological survey "
     "equipment has been abandoned here — whoever was studying these formations "
     "left in a hurry. The crystals are worth a fortune to the right buyer."),

    # ==============================================================
    # CORELLIA (Coronet City) — rooms 96-119 (24 rooms)
    # Zones: port_district (contested), city_center (secured),
    #        government (secured), industrial (secured),
    #        old_quarter (contested)
    # Sources: WEG Galaxy Guide 6 (Tramp Freighters), Corellian lore,
    #          WEG sourcebook Corellian references
    # ==============================================================

    # --- PORT DISTRICT (contested) --- rooms 96-99
    # 96
    ("Coronet City - Starport Docking Bay",
     "A modern docking bay in Corellia's capital city.",
     "Clean, well-maintained, and efficiently run — everything Mos Eisley is not. "
     "Automated cargo handlers move freight on repulsor tracks. Docking fees are "
     "posted clearly: 30 credits per standard day. Corellian Security Force officers "
     "patrol with quiet authority. The bay smells of ion drives and fresh rain."),
    # 97
    ("Coronet City - Starport Concourse",
     "The main concourse of Coronet Starport, bustling with travelers.",
     "Holographic departure boards list destinations across the galaxy. Shops sell "
     "Corellian brandy, ship parts, and travel supplies. The architecture is classic "
     "Corellian — functional elegance with no wasted space. Enormous viewports show "
     "ships ascending and descending against a blue sky."),
    # 98
    ("Coronet City - Dockside Warehouses",
     "Commercial warehouses near the starport, some with questionable tenants.",
     "Rows of prefab warehouses store legitimate cargo — and occasionally not so "
     "legitimate cargo. CorSec runs spot inspections, but Corellians have a long "
     "tradition of looking the other way when it comes to smuggling. Several "
     "warehouses serve as fronts for the local black market."),
    # 99
    ("Coronet City - Spacers' Rest Hotel",
     "A comfortable hotel catering to visiting ship crews.",
     "Clean rooms, reliable amenities, and a cantina on the ground floor make this "
     "the preferred lodging for spacers. The Drall proprietor runs a tight ship. "
     "Message boards in the lobby advertise crew positions, cargo jobs, and the "
     "occasional discreet request for 'special delivery services.'"),

    # --- CITY CENTER (secured) --- rooms 100-105
    # 100
    ("Coronet City - Treasure Ship Row",
     "The famous merchant street at the heart of Coronet City.",
     "Named for the ancient treasure ships that once docked here, this broad avenue "
     "is lined with upscale shops, trading companies, and financial houses. Corellian "
     "Engineering Corporation has a showroom displaying the latest freighter models. "
     "Street performers and food vendors add color to the commercial bustle."),
    # 101
    ("Coronet City - The Corellian Slice Cantina",
     "A spacer cantina popular with freighter crews and CEC workers.",
     "Named for the Corellian Slice hyperspace route, this cantina serves the best "
     "Whyren's Reserve in the city. Ship captains negotiate cargo deals over drinks. "
     "A sabacc table in the back sees constant action. The atmosphere is rough but "
     "friendly — Corellians look after their own."),
    # 102
    ("Coronet City - CEC Shipyard Visitor Center",
     "The public face of the Corellian Engineering Corporation.",
     "Scale models of CEC's famous ships line the walls — YT-series freighters, "
     "Corellian corvettes, bulk cruisers. Interactive displays let visitors explore "
     "ship systems. Through the viewports, the orbital shipyard facilities are visible "
     "as bright points of light in the sky. CEC employs half the city."),
    # 103
    ("Coronet City - Blue Sector",
     "The entertainment district of Coronet City.",
     "Nightclubs, casinos, holovid theaters, and restaurants cram this vibrant "
     "district. Neon signs advertise everything from Twi'lek dancers to zero-g "
     "sportball matches. CorSec maintains a visible presence but tolerates most "
     "activities. The real trouble happens in the alleys behind the main strip."),
    # 104
    ("Coronet City - Residential Quarter",
     "A middle-class residential district with tree-lined streets.",
     "Two and three-story residential buildings face quiet streets shaded by "
     "Corellian oaks. Children play in small parks. Neighbors know each other by "
     "name. Compared to the rest of the galaxy, life here seems almost peaceful. "
     "Almost — CorSec patrols remind everyone that peace requires vigilance."),
    # 105
    ("Coronet City - Central Plaza",
     "A grand public square at the intersection of Coronet's main avenues.",
     "Fountains spray arcs of water into the mild Corellian air. A monument to "
     "the original Corellian settlers stands at the center — a stylized starship "
     "pointing skyward. Cafes and government buildings ring the perimeter. This is "
     "where Corellians gather for festivals, protests, and the annual CEC ship "
     "christening ceremonies."),

    # --- GOVERNMENT DISTRICT (secured) --- rooms 106-108
    # 106
    ("Coronet City - CorSec Headquarters",
     "The imposing headquarters of the Corellian Security Force.",
     "The Corellian Security Force — CorSec — operates from this fortress-like "
     "building in the government district. Turbolaser emplacements are concealed "
     "in the architecture. Inside, investigators and agents coordinate across the "
     "entire Corellian system. CorSec has a reputation for competence and independence."),
    # 107
    ("Coronet City - Government District",
     "The administrative heart of the Corellian system.",
     "Grand buildings in traditional Corellian style house the planetary government, "
     "trade commissions, and diplomatic missions. Fountains and parkland provide "
     "green space between the stone structures. The Diktat's palace is visible on the "
     "hill above, its spires catching the afternoon sun."),
    # 108
    ("Coronet City - Hall of Justice",
     "The Corellian judicial complex where both civil and criminal cases are heard.",
     "Ornate columns frame the entrance to this centuries-old building. Corellian "
     "justice is famously independent — even the Empire has struggled to fully "
     "subordinate the local courts. Barristers in traditional robes argue cases "
     "while CorSec officers escort defendants through side corridors."),

    # --- INDUSTRIAL / SHIPYARDS (secured) --- rooms 109-112
    # 109
    ("Coronet City - CEC Worker District",
     "A residential and commercial area serving the shipyard workforce.",
     "Modest but well-maintained housing blocks line streets named after famous "
     "Corellian ships. CEC provides housing subsidies, and the district has a "
     "strong community identity. Cantinas, shops, and recreational facilities "
     "cater to shift workers. The orbital gantries are visible from every window."),
    # 110
    ("Coronet City - Shipyard Ground Facility",
     "The surface component of CEC's massive shipbuilding operation.",
     "Assembly halls the size of hangar bays house components too large to "
     "manufacture in orbit. Hyperdrive cores, bridge modules, and hull plating "
     "wait for orbital transfer. Security is tight — CEC's designs are among the "
     "most pirated in the galaxy. Workers wear orange coveralls with clearance badges."),
    # 111
    ("Coronet City - Drall Quarter",
     "A small enclave of Drall, the diminutive scholarly species native to the Corellian system.",
     "The furry, bearlike Drall maintain a quiet quarter near the industrial district. "
     "Their dwellings are built to Drall scale — uncomfortably small for most Humans. "
     "The quarter houses the finest library on Corellia, maintained by Drall scholars "
     "who have catalogued Corellian history for millennia. The smells of old books "
     "and brewing tea drift from open doorways."),
    # 112
    ("Coronet City - Selonian Tunnels - Entry",
     "An entrance to the network of tunnels maintained by the Selonian community.",
     "The Selonians — tall, sleek-furred beings resembling otters — have burrowed "
     "an extensive tunnel network beneath Coronet City. This entrance, marked with "
     "Selonian pictographs, descends into their communal warrens. Non-Selonians are "
     "tolerated in the upper tunnels but venturing deeper requires an escort. The "
     "Selonians are fiercely protective of their dens."),

    # --- OLD QUARTER (contested) --- rooms 113-116
    # 113
    ("Coronet City - Old Quarter Market",
     "An open-air market in the historic Old Quarter.",
     "Cobblestone streets and ancient stone archways frame a lively market. Local "
     "farmers sell Corellian produce, fishermen bring in catches from the coast, "
     "and craftspeople display handmade goods. The smells of roasting meat and "
     "fresh bread compete with the salt breeze from the nearby sea."),
    # 114
    ("Coronet City - Old Quarter Back Streets",
     "Narrow lanes behind the Old Quarter market, less patrolled than the main streets.",
     "These winding alleys are where Coronet's less legitimate business happens. "
     "Fences operate from back rooms, slicers offer their services from "
     "nondescript doorways, and small-time smugglers arrange drops. CorSec knows "
     "about these operations but focuses resources on bigger threats. An unspoken "
     "truce keeps violence to a minimum — bad for everyone's business."),
    # 115
    ("Coronet City - The Spearhead Tavern",
     "A rough dockworkers' pub in the Old Quarter, known for information trading.",
     "Named for the old Corellian warship class, this tavern caters to a rougher "
     "crowd than the Slice. Dockworkers, low-level smugglers, and off-duty CorSec "
     "officers drink side by side. The barkeep is rumored to be a former Rebel "
     "operative. The back room is available for private meetings — fifty credits, "
     "no questions."),
    # 116
    ("Coronet City - Coastal Promenade",
     "A seawall walkway along Coronet's southern coast.",
     "Salt wind carries the scent of the Corellian sea. Fishing boats bob in a small "
     "harbor. The promenade offers views of the coastline stretching west toward "
     "the agricultural regions. At night, the orbital shipyards trace bright arcs "
     "across the sky. Old Corellians come here to watch the ships and remember "
     "when the galaxy was smaller."),

    # --- BLUE SECTOR OVERFLOW (contested) --- rooms 117-119
    # 117
    ("Coronet City - The Golden Orbit Casino",
     "An upscale casino in Blue Sector, popular with visiting merchants.",
     "Crystal chandeliers and polished wood give the Golden Orbit a veneer of "
     "respectability. Sabacc tables, chance cubes, and jubilee wheels fill the "
     "main floor. High-stakes games happen upstairs by invitation. The house "
     "always wins, but the Corellian brandy makes losing almost pleasant."),
    # 118
    ("Coronet City - Mechanics' Guild Hall",
     "The headquarters of the Coronet City chapter of the Mechanics' Guild.",
     "Workbenches, diagnostic terminals, and tool racks fill this functional space. "
     "Guild members gather here to share techniques, post job listings, and socialize. "
     "A notice board displays current contracts from CEC, independent ship owners, "
     "and the occasional 'no questions asked' repair job. Guild dues are 100 credits "
     "per month, but the discount on parts makes it worthwhile."),
    # 119
    ("Coronet City - Venn Kator's Forge",
     "A shipwright's workshop tucked behind the Mechanics' Guild Hall.",
     "The heat from plasma cutters and welding torches makes this room "
     "uncomfortably warm. Venn Kator — a grizzled Corellian with burn scars on "
     "both forearms — builds and modifies ship components with an artisan's eye. "
     "Half-finished projects hang from ceiling hooks. Technical readouts paper "
     "the walls. Kator only teaches those who demonstrate both skill and patience."),
]

# ==============================================================
# EXITS  (from_idx, to_idx, direction, reverse_direction)
# ==============================================================
EXITS = [
    # =========================================
    # MOS EISLEY EXITS (original core)
    # =========================================
    # -- Docking Bay 94 connections --
    (0, 1, "down", "up"),
    (0, 7, "north", "south to Bay 94"),
    (2, 7, "east", "west to Bay 86"),
    (2, 0, "south", "north to Bay 86"),
    # -- Other bays to Spaceport Row --
    (3, 7, "northwest", "southeast"),
    (4, 7, "west", "east"),
    (5, 7, "east", "west to Bay 91"),
    # -- Bay 92 to North End --
    (6, 10, "east", "west to Bay 95"),
    # -- Spaceport Row <-> Market Row --
    (7, 8, "north", "south to Spaceport"),
    # -- Market Row <-> Inner Curve --
    (8, 9, "north", "south to Market"),
    # -- Inner Curve <-> Outer Curve --
    (9, 10, "north", "south to Inner Curve"),
    # -- Market Row <-> Kerner Plaza --
    (8, 11, "south", "north"),
    # -- Cantina --
    (12, 8, "east", "west to Cantina"),
    (12, 13, "down", "up"),
    (13, 14, "west", "east"),
    # -- General Store -> Market --
    (15, 8, "north", "south to General Store"),
    # -- Market Place -> Market --
    (16, 8, "south", "north to Market Place"),
    # -- Inn -> Spaceport Row --
    (17, 7, "south", "north to Inn"),
    # -- Jabba's --
    (18, 8, "southeast", "northwest"),
    (18, 19, "in", "out"),
    # -- Government District --
    (20, 9, "east", "west to Prefect"),
    (21, 9, "west", "east"),
    (22, 9, "south", "north to Gov District"),
    (23, 22, "north", "south to Stables"),
    # -- Power Station --
    (24, 9, "northwest", "southeast"),
    # -- Hotel -> Spaceport Row --
    (25, 7, "east", "west to Hotel"),
    # -- Control Tower -> Spaceport Row --
    (26, 7, "north", "south to Tower"),
    # -- Weapon Shop -> Market --
    (27, 8, "east", "west to Weapon Shop"),
    # -- Souvenirs / Jawa -> Market --
    (28, 8, "northeast", "southwest"),
    (29, 8, "west", "east"),
    # -- Dockside Cafe --
    (30, 10, "south", "north"),
    (6, 30, "south", "north"),
    # -- Lucky Despot -> South End --
    (31, 11, "north", "south"),
    (31, 32, "up", "down"),
    # -- Banking -> Market --
    (33, 8, "north", "south to Bank"),
    # -- Transport Depot -> South End --
    (34, 11, "east", "west"),
    # -- Clinic -> Inner Curve --
    (35, 9, "east", "west to Clinic"),
    # -- Monastery -> North End --
    (36, 10, "east", "west to Monastery"),
    # -- Dowager Queen -> Market --
    (37, 8, "north", "south to Wreckage"),
    # -- Momaw Nadon -> South End --
    (38, 11, "west", "east"),
    # -- Notsub -> North End --
    (39, 10, "north", "south to Notsub"),

    # =========================================
    # TATOOINE OUTSKIRTS EXITS (contested)
    # =========================================
    # Eastern Gate -> from Market District
    (40, 8, "west", "outskirts"),
    # Scavenger Market -> from Eastern Gate
    (41, 40, "west", "east to Scavenger Market"),
    # Abandoned Farm -> from Eastern Gate
    (42, 40, "south", "north to Farm"),
    # Speeder Track -> from Scavenger Market
    (43, 41, "east", "west to Track"),
    # Checkpoint -> from Eastern Gate
    (44, 40, "east", "west to Checkpoint"),
    # Wrecked Sandcrawler -> from Scavenger Market
    (45, 41, "north", "south to Sandcrawler"),
    # Hermit's Ridge -> from Abandoned Farm
    (46, 42, "south", "north to Ridge"),
    # Trail Junction -> from Checkpoint (gateway to Wastes)
    (47, 44, "east", "west to Junction"),

    # =========================================
    # JUNDLAND WASTES EXITS (lawless)
    # =========================================
    # Canyon Mouth -> from Trail Junction
    (48, 47, "east", "west to Canyon"),
    # Beggar's Canyon -> from Canyon Mouth
    (49, 48, "south", "north to Beggar's Canyon"),
    # Tusken Overlook -> from Canyon Mouth
    (50, 48, "east", "west to Overlook"),
    # Krayt Graveyard -> from Tusken Overlook
    (51, 50, "east", "west to Graveyard"),
    # Hidden Cave -> from Canyon Mouth
    (52, 48, "hidden", "out"),
    # Dune Sea Edge -> from Krayt Graveyard
    (53, 51, "south", "north to Dune Sea"),

    # =========================================
    # NAR SHADDAA EXITS
    # =========================================
    # Docking Bay -> Promenade
    (54, 56, "out", "bay aurek"),
    # Landing Platform -> Promenade
    (55, 56, "in", "platform besh"),
    # Promenade hub connections
    (56, 57, "west", "east to Promenade"),
    (56, 59, "north", "south to Promenade"),
    (56, 64, "down", "up to Promenade"),
    (56, 70, "up", "down to Promenade"),
    (56, 63, "southeast", "northwest to Promenade"),
    (56, 60, "northeast", "southwest to Promenade"),
    (56, 61, "south", "north to Promenade"),
    # Cantina -> back room
    (57, 58, "back", "out"),
    # Undercity Market -> Depths
    (64, 65, "down", "up"),
    # Undercity Market -> Spice Den
    (64, 66, "east", "west"),
    # Undercity Market -> Medcenter
    (64, 68, "south", "north to Market"),
    # Hutt Tower -> Audience Chamber
    (70, 71, "up", "down"),
    # Hutt Tower -> The Grid
    (71, 72, "coded lift", "down"),
    # Vertical Bazaar -> Droid Junkyard
    (60, 67, "down", "up"),
    # Vertical Bazaar -> Ship Parts
    (60, 73, "east", "west to Bazaar"),
    # Old Quarter -> Promenade
    (62, 56, "southeast", "northwest to Old Quarter"),
    # Renna Dox -> Old Quarter
    (74, 62, "out", "workshop"),
    # Floating Market -> Undercity
    (75, 64, "up", "down to Floating Market"),
    # Enforcer Alley connections
    (76, 56, "south", "north through Enforcer Alley"),
    (76, 55, "north", "south through Enforcer Alley"),
    # Weapons Cache -> Bounty Hunters Quarter
    (77, 61, "out", "weapons cache"),
    # Observation Level -> Platform Besh
    (78, 55, "down", "up to Observation Level"),
    # Fighting Pits -> Undercity Depths
    (69, 65, "east", "west to Fighting Pits"),

    # =========================================
    # NAR SHADDAA WARRENS EXITS (lawless deep)
    # =========================================
    # Entry Shaft -> from Undercity Depths
    (79, 65, "down", "up to Warrens"),
    # Fungal Cavern -> from Entry Shaft
    (80, 79, "east", "west to Shaft"),
    # Reactor Core -> from Entry Shaft
    (81, 79, "south", "north to Shaft"),
    # Scavenger Den -> from Fungal Cavern
    (82, 80, "east", "west to Cavern"),
    # Collapsed Plaza -> from Reactor Core
    (83, 81, "south", "north to Reactor"),

    # =========================================
    # KESSEL EXITS
    # =========================================
    # Landing Field -> Checkpoint -> Admin
    (84, 85, "north", "south to Landing Field"),
    (85, 86, "east", "west to Checkpoint"),
    # Checkpoint -> Mines
    (85, 87, "down", "up to Checkpoint"),
    # Mine -> Processing
    (87, 88, "east", "west to Mine Entrance"),
    # Admin -> Observation
    (86, 91, "up", "down to Admin"),
    # Checkpoint -> Barracks
    (85, 89, "north", "south to Checkpoint"),
    # Barracks -> Black Market Tunnel
    (89, 90, "hidden", "out"),
    # Landing Field -> Smuggler Contact (now in deep mines)
    (84, 94, "behind hangars", "out to Landing Field"),

    # =========================================
    # KESSEL DEEP MINES EXITS (lawless)
    # =========================================
    # Shaft Junction -> from Mine Entrance
    (92, 87, "down", "up to Shaft Junction"),
    # Energy Spider Caverns -> from Shaft Junction
    (93, 92, "east", "west to Caverns"),
    # Collapsed Gallery -> from Shaft Junction
    (95, 92, "south", "north to Gallery"),

    # =========================================
    # CORELLIA (Coronet City) EXITS
    # =========================================
    # Docking Bay -> Concourse (port district spine)
    (96, 97, "out", "bay"),
    (97, 98, "south", "north to Concourse"),
    (98, 99, "south", "north to Warehouses"),
    # Concourse -> Treasure Ship Row (city center spine)
    (97, 100, "east", "west to Concourse"),
    # Treasure Ship Row hub
    (100, 101, "south", "north to Treasure Ship Row"),
    (100, 107, "north", "south to Treasure Ship Row"),
    (100, 102, "east", "west to Treasure Ship Row"),
    (100, 113, "west", "east to Treasure Ship Row"),
    (100, 105, "northeast", "southwest to Treasure Ship Row"),
    # Government area
    (107, 106, "east", "west to Gov District"),
    (107, 108, "northeast", "southwest to Gov District"),
    # Entertainment / Blue Sector
    (101, 103, "south", "north to Cantina"),
    (103, 117, "east", "west to Blue Sector"),
    # Residential
    (107, 104, "north", "south to Gov District"),
    # Industrial
    (102, 109, "east", "west to CEC Visitor Center"),
    (109, 110, "east", "west to Worker District"),
    (109, 111, "south", "north to Worker District"),
    (110, 112, "down", "up to Shipyard"),
    # Old Quarter
    (113, 114, "south", "north to Market"),
    (113, 115, "west", "east to Market"),
    (113, 116, "southwest", "northeast to Market"),
    # Mechanics Guild / Venn Kator
    (118, 109, "out", "guild hall"),
    (119, 118, "back", "forge"),
    # Casino -> Blue Sector
    (117, 103, "west", "east to Casino"),
    # Coastal -> Old Quarter
    (116, 114, "north", "south to Coast"),
]

# ==============================================================
# ZONE MAPPING — aligned with security_zones_design_v1.md
# ==============================================================
ROOM_ZONES = {
    # -- Mos Eisley: Spaceport (secured) --
    0: "spaceport", 1: "spaceport", 2: "spaceport", 3: "spaceport",
    4: "spaceport", 5: "spaceport", 6: "spaceport",
    # -- Mos Eisley: Streets & Markets (secured) --
    7: "market", 8: "market", 9: "market", 10: "market", 11: "market",
    # -- Mos Eisley: Cantina (secured) --
    12: "cantina", 13: "cantina", 14: "cantina",
    # -- Mos Eisley: Commercial (secured) --
    15: "residential", 16: "residential", 17: "residential",
    # -- Jabba's Townhouse (contested, faction_override) --
    18: "civic", 19: "civic",
    # -- Government / Civic (secured) --
    20: "civic", 21: "civic", 22: "civic",
    # -- Spaceport overflow / misc --
    23: "spaceport", 24: "spaceport", 25: "residential", 26: "spaceport",
    27: "residential", 28: "residential", 29: "residential", 30: "spaceport",
    31: "residential", 32: "residential", 33: "civic", 34: "spaceport",
    35: "civic", 36: "residential", 37: "market", 38: "residential", 39: "market",
    # -- Outskirts (contested) --
    40: "outskirts", 41: "outskirts", 42: "outskirts", 43: "outskirts",
    44: "outskirts", 45: "outskirts", 46: "outskirts", 47: "outskirts",
    # -- Jundland Wastes (lawless) --
    48: "wastes", 49: "wastes", 50: "wastes", 51: "wastes",
    52: "wastes", 53: "wastes",

    # -- Nar Shaddaa --
    54: "ns_landing_pad", 55: "ns_landing_pad",
    56: "ns_promenade", 57: "ns_promenade", 58: "ns_promenade",
    59: "ns_promenade", 60: "ns_promenade", 61: "ns_promenade",
    62: "ns_promenade", 63: "ns_promenade",
    64: "ns_undercity", 65: "ns_undercity", 66: "ns_undercity",
    67: "ns_undercity", 68: "ns_undercity", 69: "ns_undercity",
    70: "ns_promenade", 71: "ns_promenade", 72: "ns_promenade",
    73: "ns_promenade", 74: "ns_promenade", 75: "ns_undercity",
    76: "ns_undercity", 77: "ns_undercity", 78: "ns_landing_pad",
    79: "ns_warrens", 80: "ns_warrens", 81: "ns_warrens",
    82: "ns_warrens", 83: "ns_warrens",

    # -- Kessel --
    84: "kessel_station", 85: "kessel_station", 86: "kessel_station",
    87: "kessel_mines", 88: "kessel_mines", 89: "kessel_mines",
    90: "kessel_mines", 91: "kessel_station",
    92: "kessel_deep_mines", 93: "kessel_deep_mines",
    94: "kessel_deep_mines", 95: "kessel_deep_mines",

    # -- Corellia --
    96: "coronet_port", 97: "coronet_port", 98: "coronet_port", 99: "coronet_port",
    100: "coronet_city", 101: "coronet_city", 102: "coronet_city",
    103: "coronet_city", 104: "coronet_city", 105: "coronet_city",
    106: "coronet_gov", 107: "coronet_gov", 108: "coronet_gov",
    109: "coronet_industrial", 110: "coronet_industrial",
    111: "coronet_industrial", 112: "coronet_industrial",
    113: "coronet_old_quarter", 114: "coronet_old_quarter",
    115: "coronet_old_quarter", 116: "coronet_old_quarter",
    117: "coronet_city", 118: "coronet_industrial", 119: "coronet_industrial",
}

ROOM_OVERRIDES = {
    # Mos Eisley
    1: {"cover_max": 4}, 13: {"cover_max": 2}, 14: {"cover_max": 1},
    19: {"cover_max": 3, "faction_override": "hutt"},
    18: {"faction_override": "hutt"},
    21: {"cover_max": 2}, 24: {"cover_max": 0}, 26: {"cover_max": 3},
    37: {"cover_max": 0},
    # Outskirts
    42: {"cover_max": 0}, 44: {"cover_max": 2},
    45: {"cover_max": 3, "lighting": "dim"},
    46: {"cover_max": 2},
    # Wastes
    48: {"cover_max": 3, "lighting": "dim"},
    49: {"cover_max": 0}, 50: {"cover_max": 3},
    51: {"cover_max": 0, "lighting": "bright"},
    52: {"cover_max": 2, "lighting": "dark"},
    53: {"cover_max": 0, "lighting": "bright"},
    # Nar Shaddaa
    58: {"cover_max": 1}, 65: {"cover_max": 0, "lighting": "dark"},
    66: {"lighting": "dim"}, 69: {"cover_max": 0},
    71: {"cover_max": 3},
    79: {"lighting": "dark"}, 80: {"lighting": "dark"},
    81: {"lighting": "dim"}, 82: {"cover_max": 2, "lighting": "dark"},
    83: {"lighting": "dark"},
    # Kessel
    87: {"lighting": "dim"}, 89: {"cover_max": 0},
    92: {"lighting": "dark"}, 93: {"lighting": "dark", "cover_max": 0},
    95: {"lighting": "dark"},
    # Corellia
    106: {"cover_max": 2}, 103: {"lighting": "dim"},
    114: {"cover_max": 1, "lighting": "dim"},
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
        space_skills=None,
        trainer=False, train_skills=None):
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
    if trainer:
        cfg["trainer"] = True
        cfg["train_skills"] = train_skills or []
    return cfg

# ==============================================================
# NPC DEFINITIONS -- LOADED FROM YAML
# All GG7 NPCs are now in data/npcs_gg7.yaml, loaded at build time
# by engine/npc_loader.py. The YAML file contains 50 NPCs with full
# stat blocks, AI configs, and room placements.
#
# To add/edit NPCs, modify data/npcs_gg7.yaml instead of this file.
# ==============================================================

# ==============================================================
# HIREABLE CREW NPCs -- Available at cantina/spaceport
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
# PLANET-SPECIFIC NPCs (non-YAML, hand-defined)
# (name, room_idx, species, desc, char_sheet, ai_config)
# ==============================================================
PLANET_NPCS = [
    # ── Tatooine Outskirts (contested) ─────────────────────────────
    ("Jawa Scrap Boss", 41, "Jawa",
     "A slightly taller-than-average Jawa directing a crew of scavengers.",
     _sheet(dex="3D", kno="3D+1", per="3D+2", tec="4D",
            skills={"bargain": "5D", "value": "5D+2", "droid_repair": "4D+1",
                    "sneak": "4D"},
            species="Jawa"),
     _ai(personality="Runs the scavenger market outside town. Speaks broken "
         "Basic. Drives hard bargains. Has connections to the sandcrawler "
         "convoys that range across the Jundland Wastes.",
         style="Rapid, squeaky. Utinni! when excited. Heavily accented.",
         fallbacks=["'Utinni! You buy? Good Droid, good price!'",
                    "The Jawa chatters rapidly at his crew."])),

    ("Swoop Racer Krix", 43, "Human",
     "A young Human with a scarred face and oil-stained racing leathers.",
     _sheet(dex="3D+2", mec="4D+1", per="3D",
            skills={"dodge": "4D+1", "repulsorlift_operation": "6D",
                    "blaster": "4D", "streetwise": "4D"},
            species="Human"),
     _ai(personality="Krix races swoops for credits and glory. He knows the "
         "outskirts like the back of his hand and can tell you which routes "
         "avoid Imperial patrols.",
         style="Cocky, fast-talking. Everything is a competition.",
         fallbacks=["'You ride? I'll race you. Name the stakes.'",
                    "Krix revs a swoop engine, grinning."])),

    ("Checkpoint Trooper", 44, "Human",
     "An Imperial stormtrooper staffing the eastern checkpoint.",
     _sheet(dex="3D+1", stre="3D",
            skills={"blaster": "4D+1", "brawling": "4D", "dodge": "4D"},
            species="Human", weapon="blaster_rifle"),
     _ai(hostile=False, behavior="defensive", faction="Empire",
         fallbacks=["'Identification. Now.'",
                    "'Move along. Move along.'"])),

    # ── Tatooine Wastes (lawless) ──────────────────────────────────
    ("Tusken Raider Scout", 50, "Tusken",
     "A Tusken Raider perched on a boulder, gaderffii stick in hand.",
     _sheet(dex="3D+2", stre="4D", per="3D",
            skills={"melee_combat": "5D+1", "brawling": "5D",
                    "sneak": "4D+2", "survival": "5D"},
            species="Tusken Raider", weapon="gaderffii_stick"),
     _ai(hostile=True, behavior="aggressive", faction="Tusken",
         fallbacks=["HRRRRK! (The Tusken raises its gaderffii stick.)",
                    "The Tusken lets out a war cry and charges."])),

    ("Tusken Raider Warrior", 48, "Tusken",
     "A Tusken Raider warrior guarding the canyon approaches.",
     _sheet(dex="3D+1", stre="4D+1", per="2D+2",
            skills={"melee_combat": "5D", "brawling": "5D+2",
                    "sneak": "4D", "survival": "5D+1",
                    "thrown_weapons": "4D+1"},
            species="Tusken Raider", weapon="gaderffii_stick"),
     _ai(hostile=True, behavior="aggressive", faction="Tusken",
         fallbacks=["The warrior pounds its chest and howls.",
                    "URRK URRK! (Definitely hostile.)"])),

    ("Old Prospector", 51, "Human",
     "A sun-blasted old Human with a Krayt Dragon tooth hanging from his neck.",
     _sheet(dex="2D+2", kno="3D+1", per="4D",
            skills={"survival": "5D+2", "search": "5D", "sneak": "4D+1",
                    "value": "5D"},
            species="Human"),
     _ai(personality="Been prospecting the wastes for forty years. Knows where "
         "the Krayt Dragon pearls can be found. Wary of strangers but will "
         "share information for credits or supplies.",
         style="Rasping voice. Speaks slowly. Desert wisdom.",
         fallbacks=["'The desert keeps her secrets. But she'll kill you for asking.'",
                    "The old man squints at the horizon, reading the sand."],
         trainer=True,
         train_skills=["survival", "search"])),

    # ── Nar Shaddaa ────────────────────────────────────────────────
    ("Vreego", 57, "Weequay",
     "A scarred Weequay bartender with a blaster under the counter.",
     _sheet(dex="3D+2", per="3D+1", stre="4D",
            skills={"blaster": "4D+2", "brawling": "5D", "streetwise": "5D"},
            species="Weequay"),
     _ai(personality="Vreego runs the Burning Deck Cantina. Serves drinks, breaks "
         "up fights, and hears everything. Never volunteers information without payment.",
         style="Gruff, laconic. Speaks in short sentences.",
         fallbacks=["Vreego polishes a glass, watching you with flat eyes.",
                    "'Drink or leave. We don't do tourism.'"])),

    ("Zekka Thansen", 59, "Human",
     "A middle-aged Corellian woman with sharp eyes and a guild master's chain.",
     _sheet(dex="3D", kno="4D", per="4D+1", mec="3D+2",
            skills={"bargain": "6D", "con": "5D", "streetwise": "6D+2",
                    "business": "5D+1", "space_transports": "5D"},
            species="Human"),
     _ai(personality="Zekka is the current coordinator of the Corellian Smugglers' "
         "Guild on Nar Shaddaa. Pragmatic, shrewd, fiercely protective of guild members.",
         style="Direct, businesslike. Corellian accent. No-nonsense.",
         fallbacks=["'Guild business is guild business. You a member?'",
                    "Zekka checks a cargo manifest on her datapad."])),

    ("Gorba's Enforcer", 70, "Gamorrean",
     "A massive Gamorrean guard in Hutt livery, carrying a vibro-axe.",
     _sheet(dex="2D+2", stre="5D",
            skills={"melee_combat": "5D", "brawling": "6D"},
            species="Gamorrean", weapon="vibro_axe"),
     _ai(personality="Loyal to the Hutt clan. Not bright. Very violent.",
         hostile=True, behavior="aggressive", faction="Hutt Cartel",
         fallbacks=["The Gamorrean grunts threateningly.",
                    "'GAAARK!'"])),

    ("Kreeda", 64, "Rodian",
     "A nervous Rodian arms dealer operating out of a scrap-metal stall.",
     _sheet(dex="3D+1", kno="3D", per="3D+2",
            skills={"blaster": "4D", "streetwise": "5D", "value": "5D+1",
                    "bargain": "4D+2"},
            species="Rodian"),
     _ai(personality="Kreeda sells weapons in the Undercity Market. Paranoid, "
         "always looking over his shoulder. Offers decent prices on black market goods.",
         style="Nervous, fast-talking. Lots of qualifiers.",
         fallbacks=["'You buying or browsing? Make it quick.'",
                    "Kreeda's eyes dart to the nearest exit."])),

    ("Vel Ansen", 61, "Human",
     "A grizzled bounty hunter with cybernetic eyes and battle-worn armor.",
     _sheet(dex="4D", per="3D+2", stre="3D+1", tec="3D",
            skills={"blaster": "5D+2", "dodge": "5D", "search": "5D",
                    "investigation": "4D+2", "streetwise": "5D"},
            species="Human"),
     _ai(personality="Vel is a veteran bounty hunter who works out of Nar Shaddaa. "
         "Professional and dangerous. Only takes contracts worth his time.",
         style="Quiet, measured. Evaluates everyone as a potential target.",
         fallbacks=["Vel's cybernetic eyes zoom in on you, processing.",
                    "'Not interested unless you're worth at least five figures.'"])),

    ("Pit Boss Grath", 69, "Trandoshan",
     "A massive Trandoshan overseeing the fighting pits with cold reptilian eyes.",
     _sheet(dex="3D+1", stre="5D", per="3D",
            skills={"brawling": "6D", "intimidation": "5D+2",
                    "melee_combat": "5D", "bargain": "4D"},
            species="Trandoshan"),
     _ai(personality="Grath runs the fighting pits for the Hutts. He takes a cut "
         "of every bet and decides the matchups. Former gladiator himself — three "
         "championship seasons before retiring to management.",
         style="Deep growl. Evaluates everyone for combat potential.",
         fallbacks=["'You fight? Step into the pit and we'll see what you're made of.'",
                    "Grath sizes you up with predatory interest."])),

    ("Doc Myrra", 68, "Twi'lek",
     "A calm Twi'lek doctor working in the black market medcenter.",
     _sheet(kno="4D", per="3D+2", tec="5D",
            skills={"first_aid": "6D+1", "medicine": "6D", "bargain": "4D+2"},
            species="Twi'lek"),
     _ai(personality="Doc Myrra trained at a Coruscant hospital before her license was "
         "revoked for treating Rebel fugitives. Pragmatic — charges double, delivers "
         "triple. No questions asked, no records kept.",
         style="Calm, professional. Slightly detached manner.",
         fallbacks=["'Cash in advance. I don't run a charity.'",
                    "Doc Myrra prepares a hypo without looking up."])),

    ("Suvvel", 73, "Sullustan",
     "A meticulous Sullustan running a seven-deck ship parts emporium.",
     _sheet(kno="4D", per="3D", mec="4D+2", tec="5D",
            skills={"value": "6D+2", "bargain": "5D", "starship_repair": "5D+1"},
            species="Sullustan"),
     _ai(personality="Suvvel tracks every part in his inventory by memory. "
         "Eighty percent of his stock is stolen or salvaged.",
         style="Rapid speech, high-pitched. Excited about specifications.",
         fallbacks=["Suvvel cross-references your request against three separate databases.",
                    "'I have seventeen motivator types in stock. Which grade?'"])),

    ("The Miralukan", 72, "Miralukan",
     "A blind information broker who sees more than most sighted people.",
     _sheet(kno="5D", per="5D+2",
            skills={"investigation": "7D", "streetwise": "6D+2", "con": "5D+1",
                    "forgery": "5D", "value": "5D+2"},
            species="Miralukan"),
     _ai(personality="Trades exclusively in information. Force-sighted rather than "
         "visually sighted. Her price is always information in return.",
         style="Serene, unsettling. Refers to things she shouldn't be able to see.",
         fallbacks=["'I know why you're here. What will you trade for the answer?'",
                    "She turns toward you despite facing away."])),

    ("Renna Dox", 74, "Zabrak",
     "A broad-shouldered Zabrak shipwright with permanent engine grease under her fingernails.",
     _sheet(kno="3D+1", mec="4D+2", tec="6D",
            skills={"starship_repair": "7D", "space_transports_repair": "6D+2",
                    "computer_prog": "5D+1", "value": "5D"},
            species="Zabrak"),
     _ai(personality="Renna Dox builds the best ship modifications in the Smuggler's Moon. "
         "Teaches what she knows to those who earn it. Blunt, perfectionist.",
         style="Blunt, technical. Evaluates everything for structural integrity.",
         fallbacks=["'You break it in my shop, you pay double to fix it.'",
                    "Renna studies your ship specs before saying anything."],
         trainer=True,
         train_skills=["starship_repair", "space_transports_repair"])),

    ("Hutt Toll Enforcer", 76, "Nikto",
     "A scarred Nikto enforcer blocking the alley, hand resting on his blaster.",
     _sheet(dex="3D+2", stre="4D",
            skills={"blaster": "4D+2", "intimidation": "5D+1", "brawling": "4D+1"},
            species="Nikto", weapon="heavy_blaster_pistol"),
     _ai(personality="Collects the Hutt clan transit toll. Not creative. "
         "Either you pay or you don't pass.",
         hostile=False, behavior="defensive",
         fallbacks=["'Twenty credits. Everyone pays.'",
                    "The Nikto taps his blaster meaningfully."])),

    ("Duros Arms Dealer", 77, "Duros",
     "An armless Duros operating his weapons shop through a pair of mechanical waldos.",
     _sheet(dex="2D", kno="4D", per="3D+2", tec="4D+1",
            skills={"value": "6D", "repair_weapons": "5D+2", "bargain": "5D",
                    "streetwise": "5D+1"},
            species="Duros"),
     _ai(personality="Lost both arms on a bad bounty contract. Sells everything — "
         "blasters, melee, explosives, Imperial military surplus.",
         style="Flat affect, mechanical precision. The waldos move constantly.",
         fallbacks=["The waldos sort inventory while he watches you.",
                    "'What caliber? What range? Budget?'"])),

    # -- Warrens NPCs --
    ("Evocii Elder", 80, "Evocii",
     "An ancient Evocii with milky eyes, wrapped in rags woven from fungi fibers.",
     _sheet(kno="4D+2", per="4D",
            skills={"survival": "6D", "search": "5D", "sneak": "5D+1",
                    "first_aid": "4D+2"},
            species="Evocii"),
     _ai(personality="One of the few Evocii elders who still remembers the oral "
         "histories of their people — before the Hutts came. Will trade survival "
         "knowledge for respect and gifts. Deeply distrustful of off-worlders.",
         style="Slow, deliberate. Speaks in broken Basic mixed with old Evocii.",
         fallbacks=["The elder studies you silently, weighing your intent.",
                    "'Your kind built the towers. Our kind lives beneath them.'"])),

    ("Warrens Scavenger", 82, "Human",
     "A wiry Human covered in reactor soot, carrying a bag of salvage.",
     _sheet(dex="3D+1", stre="3D", per="3D+2", tec="3D+1",
            skills={"dodge": "4D", "sneak": "4D+2", "search": "5D",
                    "survival": "4D+1", "repair": "4D"},
            species="Human"),
     _ai(personality="Has lived in the Warrens for three years. Trades salvage "
         "from the reactor levels. Knows the safe paths and the deadly ones.",
         style="Terse, practical. Wastes no words.",
         fallbacks=["'Watch your step. The floor gives way without warning down here.'",
                    "The scavenger weighs a piece of salvage in his hand."])),

    # ── Kessel ─────────────────────────────────────────────────────
    ("Warden Phaedris", 86, "Human",
     "The stern Imperial warden of Kessel's spice mining operations.",
     _sheet(dex="3D", kno="4D", per="3D+2",
            skills={"blaster": "4D", "command": "6D", "intimidation": "5D+2",
                    "bureaucracy": "5D", "law_enforcement": "5D+1"},
            species="Human"),
     _ai(personality="Warden Phaedris runs Kessel with cold efficiency. He views "
         "prisoners as production units, not people.",
         faction="Empire", style="Cold, bureaucratic. Imperial accent.",
         fallbacks=["'Production quotas must be met. Everything else is secondary.'",
                    "The Warden reviews daily output numbers without looking up."])),

    ("Kessel Stormtrooper", 85, "Human",
     "An Imperial stormtrooper in standard white armor, blaster at the ready.",
     _sheet(dex="3D+1", stre="3D",
            skills={"blaster": "4D+1", "brawling": "4D", "dodge": "4D"},
            species="Human", weapon="blaster_rifle"),
     _ai(hostile=True, behavior="defensive", faction="Empire",
         fallbacks=["'Halt! Present your authorization.'",
                    "'Move along. Move along.'"])),

    ("Skrizz", 90, "Chadra-Fan",
     "A small Chadra-Fan running the black market tunnel with nervous energy.",
     _sheet(dex="2D+2", kno="3D", per="4D",
            skills={"bargain": "5D+2", "con": "4D+1", "sneak": "5D",
                    "streetwise": "5D+2", "value": "5D"},
            species="Chadra-Fan"),
     _ai(personality="Skrizz is the unofficial quartermaster of Kessel's black market. "
         "Terrified of the Warden but too greedy to stop.",
         style="Squeaky voice, rapid speech. Constantly fidgeting.",
         fallbacks=["'Psst! You need something? I got everything. Cheap!'",
                    "Skrizz wrings his tiny hands, checking for guards."])),

    ("Mine Foreman Dreck", 87, "Human",
     "A thick-necked Imperial overseer supervising the mine entrance.",
     _sheet(dex="3D", stre="3D+1", per="3D",
            skills={"intimidation": "5D+1", "command": "4D+1", "blaster": "4D"},
            species="Human"),
     _ai(personality="Career Imperial. Efficient, brutal, indifferent to prisoner suffering.",
         faction="Empire", style="Barking commands. Short sentences.",
         fallbacks=["'Quota's short. Get back to work.'",
                    "Dreck checks a work report, scowling."])),

    ("Prisoner 4477", 89, "Wookiee",
     "A massive Wookiee prisoner, chains on his wrists, pride still intact.",
     _sheet(dex="2D+2", stre="6D",
            skills={"brawling": "7D", "intimidation": "4D+2", "survival": "4D"},
            species="Wookiee"),
     _ai(personality="Enslaved for resisting Imperial conscription of his homeworld. "
         "Speaks no Basic but understands it. Helps those who show respect.",
         style="Growls, gestures. Shyriiwook only.",
         fallbacks=["The Wookiee studies you with orange eyes, measuring trust.",
                    "[ROAAR] (He's assessing whether you're worth talking to.)"])),

    ("Bith Chemist", 88, "Bith",
     "A Bith chemist supervising spice refinement in a contamination suit.",
     _sheet(kno="5D+1", tec="5D",
            skills={"medicine": "4D+2", "value": "5D"},
            species="Bith"),
     _ai(personality="Recruited for his chemistry expertise. Cooperates because "
         "the alternative was worse. Knows everything about spice refinement.",
         style="Precise, clinical. Avoids eye contact.",
         fallbacks=["'Glitterstim is particularly dangerous raw. Don't touch anything.'",
                    "The Bith checks contamination readings before responding."])),

    # -- Deep mines NPCs --
    ("Energy Spider", 93, "Energy Spider",
     "A massive silicon-based predator trailing webs of crackling energy.",
     _sheet(dex="4D", stre="5D+2", per="3D+1",
            skills={"brawling": "6D", "sneak": "5D"},
            species="Energy Spider", weapon="energy_web"),
     _ai(hostile=True, behavior="aggressive",
         fallbacks=["The energy spider's legs click against the cavern floor.",
                    "Crackling energy arcs between the spider's mandibles."])),

    # ── Corellia ───────────────────────────────────────────────────
    ("Officer Dalla Ren", 106, "Human",
     "A CorSec officer in the distinctive green uniform, carrying a heavy blaster.",
     _sheet(dex="3D+2", kno="3D+1", per="3D+2",
            skills={"blaster": "5D", "dodge": "4D+2", "investigation": "5D",
                    "law_enforcement": "5D+2", "streetwise": "4D+1"},
            species="Human"),
     _ai(personality="Officer Ren is a dedicated CorSec investigator. She's honest, "
         "competent, and has zero tolerance for criminal activity in Coronet City.",
         faction="Corellia", style="Professional, direct. Corellian accent.",
         fallbacks=["'CorSec. I have a few questions for you.'",
                    "Dalla checks her datapad, cross-referencing something."])),

    ("Jorek Madine", 101, "Human",
     "A retired freighter captain running the Corellian Slice cantina.",
     _sheet(dex="2D+2", kno="3D+2", per="4D",
            skills={"bargain": "5D", "con": "4D+2", "persuasion": "5D+1",
                    "space_transports": "5D", "streetwise": "5D"},
            species="Human"),
     _ai(personality="Jorek flew freighters for thirty years before settling down. "
         "He knows every smuggler route in the Corellian Run.",
         style="Warm, storytelling. Always has an anecdote.",
         fallbacks=["'Pull up a chair, friend. What's your poison?'",
                    "Jorek wipes the bar, lost in a memory of the old routes."])),

    ("Desa Thyn", 102, "Human",
     "A CEC sales representative with perfect hair and a practiced smile.",
     _sheet(kno="3D+2", per="4D",
            skills={"persuasion": "6D", "business": "5D+2", "value": "5D",
                    "bureaucracy": "4D+1"},
            species="Human"),
     _ai(personality="Desa sells ships for CEC. She can recite specs for every "
         "YT-series model ever produced. Genuinely enthusiastic about Corellian engineering.",
         style="Enthusiastic, polished. Sales pitch mode.",
         fallbacks=["'Have you seen the new YT-2400? Fastest thing in its class!'",
                    "Desa activates a holographic display of ship schematics."])),

    ("Coronet Pickpocket", 103, "Human",
     "A scruffy youth with quick hands and quicker feet.",
     _sheet(dex="4D", per="3D+1",
            skills={"pick_pocket": "5D+2", "sneak": "5D", "dodge": "4D+2",
                    "running": "4D+1"},
            species="Human"),
     _ai(hostile=True, behavior="cowardly",
         fallbacks=["The pickpocket tries to blend into the crowd.",
                    "'I didn't take nothing! You can't prove it!'"])),

    ("Sergeant Bryn", 100, "Human",
     "A veteran CorSec sergeant walking the Treasure Ship Row beat.",
     _sheet(dex="3D+1", kno="3D+1", per="3D+2",
            skills={"blaster": "5D", "dodge": "4D+2", "investigation": "5D+1",
                    "law_enforcement": "6D", "streetwise": "5D"},
            species="Human"),
     _ai(personality="Twenty years on the Row. Fair but firm — Corellia's law, "
         "not the Empire's. Quietly routes info to the Rebellion when it costs him nothing.",
         faction="Corellia", style="Steady, measured. Corellian pragmatism.",
         fallbacks=["'Keep it legal. Or at least quiet.'",
                    "Bryn watches you with the patience of someone who's learned to wait."])),

    ("Cala Wren", 113, "Human",
     "A Corellian market vendor selling fresh produce and local gossip.",
     _sheet(kno="3D", per="4D",
            skills={"bargain": "5D", "streetwise": "4D+2", "persuasion": "4D+1"},
            species="Human"),
     _ai(personality="Cala's family has worked this market for four generations. "
         "Knows everyone in the Old Quarter by name.",
         style="Warm, rapid-fire. Always selling something.",
         fallbacks=["'Fresh from the coast this morning! Best price in Coronet!'",
                    "Cala arranges produce while eyeing you thoughtfully."])),

    ("Venn Kator", 119, "Human",
     "A grizzled Corellian shipwright with burn scars on both forearms.",
     _sheet(kno="3D+1", mec="4D", tec="6D+1",
            skills={"starship_repair": "7D+1", "space_transports_repair": "7D",
                    "computer_prog": "5D", "value": "5D+2"},
            species="Human"),
     _ai(personality="Venn Kator is the best independent shipwright in Coronet City. "
         "Builds custom components. Only teaches those who demonstrate skill and patience.",
         style="Taciturn, precise. Speaks through his work. Corellian accent.",
         fallbacks=["Kator examines a hull plate without acknowledging you.",
                    "'Show me what you can do before I waste my time teaching.'"],
         trainer=True,
         train_skills=["starship_repair", "space_transports_repair"])),

    ("Drall Scholar", 111, "Drall",
     "A small, bearlike Drall in scholar's robes, carrying a stack of datapads.",
     _sheet(kno="5D+2", per="3D+1",
            skills={"cultures": "6D+1", "languages": "6D", "planetary_systems": "5D+2",
                    "scholar": "6D"},
            species="Drall"),
     _ai(personality="A Drall historian maintaining the quarter's famed library. "
         "Encyclopedic knowledge of Corellian history. Polite but somewhat condescending "
         "toward beings who don't read.",
         style="Precise, scholarly. Small voice. Occasionally adjusts spectacles.",
         fallbacks=["'The library is open to all. Please handle the datacards carefully.'",
                    "The Drall consults a reference text before answering."])),

    ("Tavern Keeper", 115, "Human",
     "A stocky Corellian woman with a knowing look and calloused hands.",
     _sheet(dex="3D", kno="3D", per="4D+1",
            skills={"bargain": "4D+2", "streetwise": "6D", "persuasion": "5D",
                    "blaster": "4D"},
            species="Human"),
     _ai(personality="Runs the Spearhead Tavern. Former Rebel operative — retired "
         "but still sympathetic. Knows who to connect with for unofficial business. "
         "Never volunteers information unless she trusts you.",
         style="Warm but guarded. Corellian humor. Sees everything.",
         fallbacks=["'What'll it be? And don't say water — this isn't Tatooine.'",
                    "She wipes the bar, watching the room with practiced attention."])),

    # ── Droid Dealers (Player Shop System) ──────────────────────────────────
    ("Rik Tano", 16, "Jawa",
     "A small Jawa in a stained brown robe, tinkering with a GN-4 vendor unit.",
     _sheet(dex="3D+1", kno="4D", tec="4D+2",
            skills={"bargain": "5D", "droid_programming": "5D+1",
                    "droid_repair": "6D", "value": "5D+2"},
            species="Jawa"),
     _ai(personality="Rik Tano sells and upgrades vendor droids. Speaks in heavily "
         "accented Basic. Available tiers: gn4 (2,000cr), gn7 (5,000cr), gn12 (12,000cr). "
         "Upgrades: gn4->gn7 costs 3,000cr, gn7->gn12 costs 7,000cr.",
         faction="Independent",
         style="Excitable, rapid speech. 'Utinni!' when excited.",
         knowledge=["vendor droids", "droid upgrades", "player shops"],
         fallbacks=["Rik Tano holds up a droid component, examining it with huge orange eyes.",
                    "'Utinni! You want droid? Rik Tano has best droids on Tatooine!'"])),

    ("Unit-77", 60, "Droid",
     "A battered GN-7 unit selling its own kind. UNIT-77 COMMERCE SOLUTIONS.",
     _sheet(dex="2D", kno="5D", mec="2D", per="4D", tec="5D",
            skills={"bargain": "6D+1", "value": "6D", "droid_programming": "5D+2"},
            species="Droid"),
     _ai(personality="A self-aware vendor droid that achieved financial independence. "
         "Available tiers: gn4 (2,000cr), gn7 (5,000cr), gn12 (12,000cr). "
         "Upgrades: gn4->gn7 costs 3,000cr, gn7->gn12 costs 7,000cr.",
         faction="Independent",
         style="Dry, sardonic. References the irony of droids selling droids.",
         knowledge=["vendor droids", "droid upgrades", "player shops"],
         fallbacks=["Unit-77 swivels its photoreceptors toward you with mechanical precision.",
                    "'Droid commerce. The galaxy's most reliable transaction.'"])),

    ("Fen Solari", 113, "Human",
     "A trim Corellian woman in a merchant's vest, surrounded by vendor droids.",
     _sheet(dex="3D", kno="4D+1", per="4D+2",
            skills={"bargain": "6D", "business": "5D+2", "value": "5D+1",
                    "con": "4D+2"},
            species="Human"),
     _ai(personality="Fen Solari runs the largest vendor droid dealership in Coronet City. "
         "Available tiers: gn4 (2,000cr), gn7 (5,000cr), gn12 (12,000cr). "
         "Upgrades: gn4->gn7 costs 3,000cr, gn7->gn12 costs 7,000cr.",
         faction="Traders' Coalition",
         style="Warm, professional. Classic Corellian merchant patter.",
         knowledge=["vendor droids", "droid upgrades", "player shops"],
         fallbacks=["Fen Solari smiles and gestures at the gleaming droids on display.",
                    "'The GN-12 is our top seller. Pays for itself in three months.'"])),

    # ── Quest NPCs: From Dust to Stars ───────────────────────────────────────

    # Mak Torvin — Docking Bay 94, Tatooine (room index 1 = Pit Floor)
    ("Mak Torvin",
     1,  # Docking Bay 94 - Pit Floor
     "Human",
     "A weathered old Corellian with deep lines around his eyes and calloused hands that "
     "tell of forty years at the stick. He moves slowly, but his gaze is sharp as a vibroblade.",
     _sheet(dex="2D+1", kno="3D+2", mec="4D",
            skills={"space transports": "6D", "astrogation": "5D+1",
                    "starship gunnery": "4D+2", "sensors": "4D",
                    "space transports repair": "5D", "intimidation": "3D+2",
                    "streetwise": "4D+1", "survival": "4D"},
            species="Human"),
     _ai(personality="Mak Torvin is a retired Outer Rim freighter captain and quest mentor. "
         "He mentors new spacers through the 'From Dust to Stars' quest chain. "
         "He is gruff but fair, with deep knowledge of space flight, smuggling routes, "
         "and the Outer Rim. He has a specific history: flew the Kessel Run twice, "
         "lost one ship to a Hutt and one to an asteroid, used to own a Ghtroc 720 "
         "called the Rusty Mynock. He never elaborates on his past without prompting.",
         faction="independent",
         style="Gruff, economical with words. Corellian accent. Respects competence, "
               "dislikes excuses. Occasional dry humor. Never wastes words.",
         knowledge=["space flight", "hyperspace routes", "freighter operations",
                    "Outer Rim politics", "Ghtroc 720", "smuggling", "ship repair"],
         fallbacks=["Mak squints at you as if deciding whether you're worth his time.",
                    "'You want to fly the Outer Rim? First, learn to survive it.'",
                    "Mak nods slowly. 'Come back when you've done something worth talking about.'"])),

    # Lira Shan — Coronet Starport Docking Bay, Corellia (room index 96)
    ("Lira Shan",
     96,  # Coronet City - Starport Docking Bay
     "Human",
     "A Corellian woman in CEC coveralls, datapad in hand. Professional, direct, "
     "no patience for time-wasters. A ship broker's badge is clipped to her collar.",
     _sheet(dex="2D", kno="4D",
            skills={"business": "5D+2", "bargain": "5D", "value": "6D",
                    "bureaucracy": "4D+1", "space transports": "3D+2"},
            species="Human"),
     _ai(personality="Lira Shan is a CEC-licensed ship broker at Coronet Starport. "
         "She handles paperwork and transfers for used freighters, especially Ghtroc 720s "
         "and YT-series. She is involved in the 'From Dust to Stars' quest chain Phase 5 "
         "— she processes the sale of a Ghtroc 720 to the player character. "
         "She is completely legitimate, honest to a fault, and allergic to drama.",
         faction="Traders' Coalition",
         style="Crisp, professional, slightly impatient. Classic Corellian directness. "
               "Gives straight answers. Has no interest in gossip or small talk.",
         knowledge=["ship sales", "Ghtroc 720", "CEC vessels", "ship registration",
                    "Coronet City", "starship financing", "Corellia"],
         fallbacks=["Lira taps her datapad. 'Do you have a ship in mind, or are you browsing?'",
                    "'I don't do haggles. Price is price. CEC certified, no exceptions.'",
                    "She glances up briefly. 'Come back when you're ready to buy.'"])),

    # Grek — Nar Shaddaa Undercity Market (room index 64)
    ("Grek",
     64,  # Nar Shaddaa - Undercity Market
     "Rodian",
     "A Rodian in an expensive but slightly stained suit. He smiles too much "
     "and his large eyes miss nothing. A faint Hutt Cartel sigil is worked into his cufflinks.",
     _sheet(dex="3D", kno="2D+1", per="3D+2", stre="3D+1",
            skills={"blaster": "4D+1", "dodge": "4D",
                    "streetwise": "4D+2", "con": "4D", "bargain": "4D+1",
                    "intimidation": "3D+2"},
            species="Rodian"),
     _ai(personality="Grek is a Rodian fixer and loan broker for Drago the Hutt. "
         "He is involved in the 'From Dust to Stars' quest chain Phase 5 "
         "— he arranges the 10,000 credit loan from Drago the Hutt to help the player "
         "buy their first ship. He collects weekly debt payments and sends warnings "
         "on missed payments. He is polite but the threat beneath his smile is always present. "
         "He never mentions violence directly — he implies it.",
         faction="hutt",
         style="Oily charm. Overly polite in a way that makes you nervous. "
               "Speaks as if every conversation is a business negotiation he has already won.",
         knowledge=["Hutt Cartel", "Nar Shaddaa", "smuggling", "loan agreements",
                    "Drago the Hutt", "debt collection", "Outer Rim criminal network"],
         fallbacks=["Grek spreads his hands with a too-wide smile. 'Drago is very patient. Mostly.'",
                    "'The loan terms are quite reasonable. For the Outer Rim.'",
                    "He tilts his head. 'I'm sure you have the credits. You wouldn't want not to.'"])),
]

# ==============================================================
# SHIPS
# ==============================================================
SHIPS = [
    # -- Tatooine --
    ("yt_1300", "Rusty Mynock", 1,
     "The cockpit of this battered YT-1300 hums with mismatched instruments. "
     "Half the warning lights are on. A co-pilot station sits to the right."),
    ("z_95", "Dusty Hawk", 4,
     "The cramped cockpit of this old Z-95 Headhunter smells of coolant and "
     "old sweat. Instruments flicker. The ejection seat looks questionable."),
    ("ghtroc_720", "Krayt's Fortune", 5,
     "The bridge of this Ghtroc 720 is surprisingly spacious. The Corellian-style "
     "controls are worn smooth from years of use."),
    ("lambda_shuttle", "Imperial Surplus 7", 6,
     "The bridge of this Lambda-class shuttle still bears Imperial insignia. "
     "Someone has scratched 'SURPLUS - DO NOT REQUISITION' into the console."),
    # -- Nar Shaddaa --
    ("yt_1300", "Shadowport Runner", 54,
     "This YT-1300 has been heavily modified for smuggling. Hidden cargo "
     "compartments line the hull. The sensor baffler emits a low hum."),
    # -- Kessel --
    ("lambda_shuttle", "Prison Transport K-7", 84,
     "A stripped-down Lambda shuttle configured for prisoner transport. "
     "The passenger section has been replaced with holding cells."),
    # -- Corellia --
    ("yt_1300", "Corellian Dawn", 96,
     "A factory-fresh YT-1300 straight from the CEC production line. "
     "Everything gleams. The new-ship smell hasn't faded yet."),
]


# ==============================================================
# BUILD FUNCTION
# ==============================================================

async def build(db_path="sw_mush.db"):
    db = Database(db_path)
    await db.connect()
    await db.initialize()

    print("+============================================+")
    print("|    Building Galaxy v4 -- Security Zones      |")
    print("+============================================+")

    # -- Zones (aligned with security_zones_design_v1.md) --
    print("\n  Creating zones...")
    zones = {}

    # === Tatooine / Mos Eisley ===
    zones["mos_eisley"] = await db.create_zone(
        "Mos Eisley", properties=json.dumps({"environment": "desert_urban",
                                              "lighting": "bright", "gravity": "standard",
                                              "security": "secured"}))
    zones["spaceport"] = await db.create_zone(
        "Spaceport District", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 3, "environment": "industrial",
                                "security": "secured"}))
    zones["cantina"] = await db.create_zone(
        "Chalmun's Cantina", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "lighting": "dim", "environment": "cantina",
                                "security": "secured"}))
    zones["market"] = await db.create_zone(
        "Streets & Markets", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "street",
                                "security": "secured"}))
    zones["civic"] = await db.create_zone(
        "Civic & Government", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "official",
                                "security": "secured"}))
    zones["residential"] = await db.create_zone(
        "Residential & Commercial", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "environment": "commercial",
                                "security": "secured"}))
    zones["outskirts"] = await db.create_zone(
        "City Outskirts", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "desert_fringe",
                                "security": "contested"}))
    zones["wastes"] = await db.create_zone(
        "Jundland Wastes",
        properties=json.dumps({"cover_max": 2, "environment": "desert_wilderness",
                                "lighting": "bright", "gravity": "standard",
                                "security": "lawless"}))

    # === Nar Shaddaa ===
    zones["ns_landing_pad"] = await db.create_zone(
        "Nar Shaddaa Landing Pads",
        properties=json.dumps({"environment": "urban_industrial",
                               "lighting": "dim", "gravity": "standard",
                               "security": "secured"}))
    zones["ns_promenade"] = await db.create_zone(
        "Corellian Sector Promenade", parent_id=zones["ns_landing_pad"],
        properties=json.dumps({"cover_max": 2, "environment": "urban_commercial",
                                "security": "contested"}))
    zones["ns_undercity"] = await db.create_zone(
        "Nar Shaddaa Undercity", parent_id=zones["ns_landing_pad"],
        properties=json.dumps({"cover_max": 1, "lighting": "dark", "environment": "urban_slum",
                                "security": "lawless"}))
    zones["ns_warrens"] = await db.create_zone(
        "The Warrens", parent_id=zones["ns_landing_pad"],
        properties=json.dumps({"cover_max": 0, "lighting": "dark", "environment": "subterranean",
                                "security": "lawless"}))

    # === Kessel ===
    zones["kessel_station"] = await db.create_zone(
        "Kessel Station",
        properties=json.dumps({"environment": "barren", "lighting": "bright",
                               "gravity": "light", "atmosphere": "thin",
                               "security": "contested"}))
    zones["kessel_mines"] = await db.create_zone(
        "Kessel Spice Mines", parent_id=zones["kessel_station"],
        properties=json.dumps({"cover_max": 1, "lighting": "dim", "environment": "underground",
                                "security": "lawless"}))
    zones["kessel_deep_mines"] = await db.create_zone(
        "Kessel Deep Mines", parent_id=zones["kessel_station"],
        properties=json.dumps({"cover_max": 0, "lighting": "dark", "environment": "deep_underground",
                                "security": "lawless"}))

    # === Corellia ===
    zones["coronet_port"] = await db.create_zone(
        "Coronet Port District",
        properties=json.dumps({"environment": "urban_modern",
                               "lighting": "bright", "gravity": "standard",
                               "security": "contested"}))
    zones["coronet_city"] = await db.create_zone(
        "Coronet City Center", parent_id=zones["coronet_port"],
        properties=json.dumps({"cover_max": 2, "environment": "urban_commercial",
                                "security": "secured"}))
    zones["coronet_gov"] = await db.create_zone(
        "Coronet Government District", parent_id=zones["coronet_port"],
        properties=json.dumps({"cover_max": 2, "environment": "official",
                                "security": "secured"}))
    zones["coronet_industrial"] = await db.create_zone(
        "Coronet Industrial District", parent_id=zones["coronet_port"],
        properties=json.dumps({"cover_max": 2, "environment": "industrial",
                                "security": "secured"}))
    zones["coronet_old_quarter"] = await db.create_zone(
        "Coronet Old Quarter", parent_id=zones["coronet_port"],
        properties=json.dumps({"cover_max": 1, "environment": "urban_historic",
                                "security": "contested"}))

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
        dir_key, dir_label = _split_exit(direction)
        rev_key, rev_label = _split_exit(reverse)
        await db.create_exit(from_id, to_id, dir_key, dir_label)
        await db.create_exit(to_id, from_id, rev_key, rev_label)

    # Connect to seed rooms (1=Landing Pad, 2=Mos Eisley Street, 3=Cantina)
    print("\n  Linking seed rooms to new Mos Eisley...")
    spaceport_row_id = room_ids[7]
    market_id = room_ids[8]
    cantina_entrance_id = room_ids[12]

    await db.create_exit(1, spaceport_row_id, "north", "")
    await db.create_exit(spaceport_row_id, 1, "south", "Landing Pad")
    await db.create_exit(2, market_id, "north", "")
    await db.create_exit(market_id, 2, "south", "Street")
    await db.create_exit(3, cantina_entrance_id, "east", "")
    await db.create_exit(cantina_entrance_id, 3, "west", "")
    print("    Seed rooms linked (Landing Pad, Street, Cantina)")

    # -- NPCs (from GG7 YAML) --
    room_name_map = {ROOMS[i][0]: i for i in range(len(ROOMS))}
    NPCS = load_npcs_from_yaml(
        os.path.join(os.path.dirname(__file__), "data", "npcs_gg7.yaml"),
        room_name_map,
    )
    print(f"\n  Creating {len(NPCS)} GG7 NPCs from data/npcs_gg7.yaml...")
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

    # -- Planet-specific NPCs --
    print(f"\n  Creating {len(PLANET_NPCS)} planet NPCs...")
    for name, room_idx, species, desc, sheet, ai_cfg in PLANET_NPCS:
        rid = room_ids[room_idx]
        npc_id = await db.create_npc(
            name=name, room_id=rid, species=species, description=desc,
            char_sheet_json=json.dumps(sheet),
            ai_config_json=json.dumps(ai_cfg),
        )
        hostile_tag = " [HOSTILE]" if ai_cfg.get("hostile") else ""
        print(f"    #{npc_id:3d} {name:30s} in {ROOMS[room_idx][0][:25]}{hostile_tag}")
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

    # -- Test Character: testuser / testpass --
    # Admin+builder god-mode Jedi for testing. Skips chargen and tutorial.
    print("\n  Creating test character (testuser / testpass)...")
    try:
        import bcrypt
        test_pw_hash = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode("utf-8")
        await db._db.execute(
            """INSERT OR IGNORE INTO accounts
               (username, password_hash, is_admin, is_builder)
               VALUES (?, ?, 1, 1)""",
            ("testuser", test_pw_hash),
        )
        await db._db.commit()
        acct_rows = await db._db.execute_fetchall(
            "SELECT id FROM accounts WHERE username = 'testuser'"
        )
        test_acct_id = acct_rows[0]["id"]

        # Every skill at 8D+ (massive bonus above attribute base)
        test_skills = json.dumps({
            # Dexterity
            "blaster": "8D+2", "bowcaster": "7D", "brawling_parry": "8D",
            "dodge": "9D", "firearms": "7D", "grenade": "7D",
            "lightsaber": "10D", "melee_combat": "8D", "melee_parry": "8D",
            "missile_weapons": "7D", "pick_pocket": "7D", "running": "7D",
            "thrown_weapons": "7D", "vehicle_blasters": "7D",
            # Knowledge
            "alien_species": "7D", "bureaucracy": "7D", "business": "7D",
            "cultures": "7D", "intimidation": "8D", "languages": "8D",
            "law_enforcement": "7D", "planetary_systems": "7D",
            "scholar": "7D", "streetwise": "8D", "survival": "8D",
            "tactics": "8D", "value": "7D", "willpower": "9D",
            # Mechanical
            "astrogation": "8D", "beast_riding": "7D",
            "capital_ship_gunnery": "7D", "capital_ship_piloting": "7D",
            "capital_ship_shields": "7D", "communications": "7D",
            "ground_vehicle_operation": "7D", "hover_vehicle_operation": "7D",
            "repulsorlift_operation": "8D", "sensors": "8D",
            "space_transports": "9D", "starfighter_piloting": "9D",
            "starship_gunnery": "8D+2", "starship_shields": "8D",
            "swoop_operation": "7D", "walker_operation": "7D",
            # Perception
            "bargain": "8D", "command": "8D", "con": "8D",
            "forgery": "7D", "gambling": "8D", "hide": "8D",
            "investigation": "8D", "persuasion": "9D",
            "search": "8D", "sneak": "8D",
            # Strength
            "brawling": "8D", "climbing_jumping": "7D",
            "lifting": "7D", "stamina": "8D", "swimming": "7D",
            # Technical
            "armor_repair": "7D", "blaster_repair": "7D",
            "capital_ship_repair": "7D", "capital_ship_weapon_repair": "7D",
            "computer_programming_repair": "8D", "demolitions": "7D",
            "droid_programming": "7D", "droid_repair": "7D",
            "first_aid": "8D", "ground_vehicle_repair": "7D",
            "medicine": "8D", "repulsorlift_repair": "7D",
            "security": "8D", "space_transport_repair": "8D",
            "starfighter_repair": "7D", "starship_weapon_repair": "7D",
            # Force skills (stored as attributes)
            "control": "8D", "sense": "8D", "alter": "7D",
        })

        # Attributes JSON blob: D6 attribute dice + tutorial/force state flags.
        # The engine reads dexterity/knowledge/etc. from here for all rolls.
        # test_attrs was a separate dict but was never passed to the INSERT —
        # merging both into this single blob fixes the 3D-on-all-attributes bug.
        test_char_attrs = json.dumps({
            # ── D6 attribute dice (engine reads these for skill rolls) ───────
            "dexterity":  "5D", "knowledge":  "5D", "mechanical": "5D",
            "perception": "5D", "strength":   "5D", "technical":  "5D",
            # ── Game state flags ─────────────────────────────────────────────
            "force_sensitive": True,
            "force_skills": {"control": "8D", "sense": "8D", "alter": "7D"},
            "tutorial_core": "complete",
            "tutorial_step": 99,
            "tutorial_electives": {
                "combat": "complete", "space": "complete",
                "trading": "complete", "crafting": "complete",
                "factions": "complete",
            },
            "planets_visited": ["tatooine", "nar_shaddaa", "kessel", "corellia"],
            "ships_log": {
                "jumps": 50, "kills": 25, "discoveries": 10,
                "trade_runs": 20, "smuggle_runs": 15,
            },
        })

        # Lightsaber equipped (quality 100, pristine condition)
        test_equipment = json.dumps({
            "key": "lightsaber",
            "condition": 100,
            "max_condition": 100,
            "quality": 100,
            "crafter": "Test Jedi",
        })

        # Inventory with useful items
        test_inventory = json.dumps({
            "items": [
                {"key": "medpac", "name": "Medpac", "quality": 80},
                {"key": "medpac", "name": "Medpac", "quality": 80},
                {"key": "heavy_blaster_pistol", "name": "DL-44 Heavy Blaster",
                 "quality": 90, "crafter": ""},
                {"key": "comlink", "name": "Comlink", "quality": 50},
                {"key": "datapad", "name": "Encrypted Datapad", "quality": 70},
            ],
            "resources": [
                {"type": "durasteel", "quality": 85, "quantity": 20},
                {"type": "power_cell", "quality": 90, "quantity": 10},
                {"type": "tibanna_gas", "quality": 80, "quantity": 5},
            ],
        })

        # Start in Docking Bay 94 Entrance (room index 0)
        start_room = room_ids[0]

        cursor = await db._db.execute(
            """INSERT OR IGNORE INTO characters
               (account_id, name, species, template, attributes, skills,
                wound_level, character_points, force_points,
                dark_side_points, room_id, description, credits,
                equipment, inventory, faction_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                test_acct_id,
                "Test Jedi",            # name
                "Human",                # species
                "jedi",                 # template
                test_char_attrs,        # attributes (JSON)
                test_skills,            # skills (JSON)
                0,                      # wound_level (healthy)
                25,                     # character_points
                5,                      # force_points
                0,                      # dark_side_points
                start_room,             # room_id
                "A mysterious Jedi Knight with an air of quiet power. "
                "Scars of many battles mark their robes, but their eyes "
                "are calm. A lightsaber hangs at their belt.",
                100000,                 # credits
                test_equipment,         # equipment (lightsaber)
                test_inventory,         # inventory
                "independent",          # faction_id
            ),
        )
        await db._db.commit()
        test_char_id = cursor.lastrowid
        if test_char_id:
            print(f"    Test character 'Test Jedi' (id={test_char_id}) created.")
            print(f"    Login: testuser / testpass  |  Admin+Builder")
            print(f"    Credits: 100,000  |  Force: 5 FP  |  Lightsaber equipped")
            print(f"    All skills 7D-10D  |  Force: Control 8D, Sense 8D, Alter 7D")
        else:
            print(f"    Test character already exists (skipped).")
    except Exception as e:
        print(f"    [WARN] Test character creation failed: {e}")

    # -- Summary --
    total_rooms = len(ROOMS) + len(SHIPS)  # rooms + bridge rooms
    total_exits = len(EXITS) * 2 + 6 + len(SHIPS) * 2  # pairs + seed links + ship exits
    hostile_count = (sum(1 for _, _, _, _, _, a in NPCS if a.get('hostile'))
                     + sum(1 for _, _, _, _, _, a in PLANET_NPCS if a.get('hostile')))
    print(f"\n  +======================================+")
    print(f"  |  BUILD COMPLETE                      |")
    print(f"  |  Rooms:    {total_rooms:4d}                      |")
    print(f"  |  Exits:    {total_exits:4d}                      |")
    print(f"  |  NPCs:     {npc_count:4d} ({hostile_count:d} hostile)           |")
    print(f"  |  Crew:     {len(HIREABLE_CREW):4d} (hireable)           |")
    print(f"  |  Ships:    {len(SHIPS):4d} (docked)              |")
    print(f"  |  Zones:    {len(zones):4d}                       |")
    print(f"  |  Planets:     4 (Tatooine, Nar Shaddaa,|")
    print(f"  |                  Kessel, Corellia)     |")
    print(f"  |                                        |")
    print(f"  |  Security Tiers:                       |")
    print(f"  |    SECURED:   market, cantina, civic,  |")
    print(f"  |      spaceport, residential, coronet   |")
    print(f"  |    CONTESTED: outskirts, promenade,    |")
    print(f"  |      port district, old quarter, kessel|")
    print(f"  |    LAWLESS:   wastes, undercity,        |")
    print(f"  |      warrens, mines, deep mines        |")
    print(f"  +======================================+")

    await db.close()


async def auto_build_if_needed(db_path="sw_mush.db"):
    """Called by game_server.py on startup. Builds the world if not yet populated.

    Returns True if the build was performed, False if the world already exists.
    """
    db = Database(db_path)
    await db.connect()
    await db.initialize()
    count = await db.count_rooms()
    await db.close()

    if count <= 3:
        # Only seed rooms exist — build the full world
        print("\n  [Auto-Build] World not yet populated. Running world builder...")
        await build(db_path)
        return True
    else:
        return False


if __name__ == "__main__":
    asyncio.run(build())
