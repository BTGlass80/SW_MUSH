"""
Mos Eisley World Builder
========================
Run this ONCE against a fresh database to populate the full Mos Eisley
from West End Games Galaxy Guide 7.

Usage:
    python build_mos_eisley.py

This will:
  - Create ~40 interconnected rooms covering the central sector
  - Link them with exits following the GG7 map layout
  - Place NPCs with full AI personality configs at their canonical locations
  - Set room descriptions drawn from the sourcebook's atmosphere

Requires: the game's database module (run from the sw_mush directory)
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db.database import Database


# ══════════════════════════════════════════════════════════════
#  ROOM DEFINITIONS
# ══════════════════════════════════════════════════════════════
# Each room: (name, short_desc, long_desc)
# IDs will be assigned starting at 10 to avoid colliding with seed rooms.

ROOMS = [
    # ── Spaceport District (South/Southeast) ──
    (
        "Docking Bay 94 - Entrance",
        "The passenger entrance to one of Mos Eisley's most famous docking bays.",
        "Cracked duracrete steps descend into the pit of Docking Bay 94, one of "
        "the oldest independent bays in the spaceport. Beggars and flim-flam artists "
        "cluster near the top of the stairs, playing simple shell games and sizing up "
        "new arrivals. The bay floor lies ten meters below street level, scarred by "
        "decades of engine backblast. A faded sign reads 'De Maal Docking Services' "
        "in three languages. The hum of tractor beam generators echoes from below."
    ),
    (
        "Docking Bay 94 - Pit Floor",
        "The sunken pit floor of Docking Bay 94.",
        "The reinforced duracrete floor of the bay is pitted and scorched from "
        "countless landings. Eight landing lights ring the circle, two of them "
        "flickering uncertainly. The maintenance garage is tucked into the south wall, "
        "where a pair of binary load lifters stand idle. Fusion generators sit in a "
        "cluster near the back wall, their charging cables snaking across the floor. "
        "The office entrance is visible on the upper level, accessible by a powered ramp."
    ),
    (
        "Spaceport Customs Office",
        "A small, dingy customs office adjacent to the docking bays.",
        "Dust has settled over everything in this cramped customs office. The "
        "ventilators have clearly broken down, leaving each room with a stuffy, "
        "stale smell. Desks are piled high with datadisks, confiscated goods, and "
        "personal effects. Three doors lead out: one to a second-floor balcony "
        "overlooking the street, one to the Mos Eisley streets, and one down a "
        "stairwell corridor toward Docking Bay 94. The inspectors who work here "
        "spend more time collecting bribes than confiscating goods."
    ),
    (
        "Spaceport Speeders",
        "An unassuming speeder shop southeast of the docking bays.",
        "A motley collection of speeders in all shapes, sizes, and degrees of repair "
        "fills this shop. The smell of lubricant and ozone hangs in the air. Tools and "
        "equipment are scattered across workbenches, and a partially disassembled "
        "SoroSuub XP-38 sits on a lift in the back. The Arconan proprietor, Unut Poll, "
        "keeps a small apartment below the shop. A young Human mechanic named Geordi Hans "
        "can usually be found here, tinkering with something."
    ),
    (
        "Docking Bay 86",
        "A round pit gouged in the soil, slightly smaller than most bays.",
        "Old 86 is a utilitarian docking bay, its business consisting mostly of small "
        "shuttles and personal transports. The pit is gouged deep in the hard-packed "
        "soil, with a simple entrance ramp leading down. An ill-tempered administrative "
        "Droid named BX-9T manages the bay with brusque efficiency. Its humanoid blue "
        "and red form is easily recognized throughout the spaceport. Landing fees are "
        "35 credits per day."
    ),
    (
        "Docking Bay 87",
        "One of the top ten favorite bays for smugglers and merchants.",
        "Directly across the street from Docking Bay 86, Docking Bay 87 has been "
        "continually modernized by its owners. The landing bay sits at ground level, "
        "with a double blast door and forcefield that opens directly into the street. "
        "The cheerful Ishi Tib owner, known as Drue, is easy going but uncompromising "
        "about fees. A flat 25 credits avoids any 'bureaucratic hassles' like cargo "
        "inspections. The bay charges 30 credits per day."
    ),
    (
        "Docking Bay 92",
        "A bay used almost exclusively for starship repairs.",
        "The underground rooms of Docking Bay 92 are filled with starship repair tools, "
        "labor and engineering Droids, and every piece of equipment a master mechanic "
        "could need. The owner, Dom Antyll, distrusts most organics and prefers Droid "
        "labor. He charges 125% of standard rates, but his work is first-class and "
        "guaranteed. The smell of ion flux and coolant permeates everything."
    ),

    # ── Central Streets ──
    (
        "Mos Eisley Street - Spaceport Row",
        "A wide, dusty street running between the major docking bays.",
        "This broad street connects several of Mos Eisley's busiest docking bays. "
        "Low-grade concrete and plastoid mounds line both sides, their domed roofs "
        "designed to shed sand and resist the periodic sandstorms. Moisture vaporators "
        "stand tucked into corners and alleys. The air shimmers with heat from the "
        "twin suns, and the constant chatter of a dozen alien languages fills the "
        "dusty thoroughfare. Beggars, Jawas, and street vendors compete for attention."
    ),
    (
        "Mos Eisley Street - Market District",
        "A bustling stretch of street near the market and cantina.",
        "The streets grow more crowded here, near the heart of Mos Eisley's commercial "
        "district. Speeders weave between pedestrians at alarming speed. The curved "
        "walls of the cantina are visible to the west, and the open-air tents of the "
        "market place sprawl to the south. A Dim-U monk stands on a crate, preaching "
        "about the sacred nature of Banthas to an audience of exactly zero. The smell "
        "of grilled meat drifts from somewhere nearby."
    ),
    (
        "Mos Eisley Street - Government Quarter",
        "A quieter section of street near the government offices and police station.",
        "The crowds thin out in this part of town, near the regional government offices "
        "and the newly expanded police station. The buildings here are slightly better "
        "maintained, though that is not saying much. A few stormtroopers patrol in pairs, "
        "their white armor already coated in a fine layer of Tatooine dust. The power "
        "station's charging pylons are visible down a side alley."
    ),
    (
        "Mos Eisley Street - North End",
        "The northern edge of the central sector, near the factories.",
        "The character of the city changes here at the northern edge. The buildings "
        "become more industrial - warehouses, shipping offices, and factory compounds. "
        "Notsub Shipping's corporate headquarters dominates the skyline, its two-story "
        "structure dwarfing the surrounding buildings. The streets are wider to "
        "accommodate cargo skiffs and heavy transports, but no less dusty."
    ),
    (
        "Mos Eisley Street - South End",
        "The southern residential area, quieter than the central sector.",
        "The streets narrow and quiet here at the southern edge of the central sector. "
        "Two-story white pourstone residential buildings line a cul-de-sac. Small "
        "subterranean gardens, fed by private moisture vaporators, give this area an "
        "almost peaceful quality. The House of Momaw Nadon sits at the end of the "
        "street, its unusual humidity visible as condensation on the windows."
    ),

    # ── Key Locations ──
    (
        "Chalmun's Cantina - Entrance",
        "The elevated entranceway of the most infamous cantina in the galaxy.",
        "You step from the blinding glare of the twin suns into the dim, cool "
        "entranceway of Chalmun's Cantina. The elevated entrance allows the bar's "
        "patrons to size up newcomers while their eyes adjust to the darkness. A "
        "Droid detector mounted on the wall emits a soft hum. A battered sign reads "
        "'NO DROIDS' in Basic and three other languages. The sound of jizz-wailer "
        "music and alien chatter washes over you from below."
    ),
    (
        "Chalmun's Cantina - Main Bar",
        "The main bar of the most notorious establishment in Mos Eisley.",
        "The dimly lit cantina is a cavern of sound and shadow. A high-tech bar "
        "stretches along one wall, capable of synthesizing virtually any drink in "
        "the galaxy from its mixing computer. Booths of varying size and shape line "
        "the curved walls, accommodating everything from intimate meetings to large "
        "group negotiations. The seven-piece band on the bandstand fills the room "
        "with an energetic jizz number. Smugglers, bounty hunters, and beings of "
        "every description pack the room. The bartender, a scarred Wookiee named "
        "Chalmun, keeps order with a bowcaster behind the bar."
    ),
    (
        "Chalmun's Cantina - Back Hallway",
        "A narrow hallway behind the bar, leading to the restrooms and cellar.",
        "This rear corridor is left unlocked for those with the knowledge and need "
        "of a quick escape. Three restroom doors line one side. The cellar access "
        "is through a trapdoor, where the foodstuffs, liquor, and mixer ingredients "
        "are stored in what was once a walk-in freezer. The bartender's office is "
        "separated from the bar by a curtained wall, its trapdoor leading down to "
        "the same basement."
    ),
    (
        "Lup's General Store",
        "A well-stocked general store run by a pair of friendly Shistavanen Wolfmen.",
        "Despite the fierce, wolf-like appearance of its proprietors, Lup's General "
        "Store is one of the friendlier establishments in Mos Eisley. The main "
        "display room is about eight by five meters, with touch-screen monitors at "
        "each seat along the counter for browsing merchandise. Twelve large monitors "
        "on the left wall advertise daily specials, though the sound cuts in and out. "
        "Provisions, supplies, machinery, medical equipment, and weaponry can all be "
        "found here at reasonable prices."
    ),
    (
        "Market Place - Gep's Grill",
        "An open-air market with tents, food stalls, and a popular grill.",
        "Less a proper market and more a sandy lot full of tents and improvised stalls, "
        "Market Place is where free enterprise thrives on Tatooine. Solar energy "
        "collectors power cooling generators and grill units under canvas awnings. "
        "Farmers sell vegetables from underground agrofarms, hunters offer Dune Sea "
        "game, and vendors hawk trinkets and homespun clothing. The smoky aroma of "
        "Bantha burgers and Dewback ribs wafts from Gep's Grill, the busiest stall. "
        "Today's specials are scrawled on a board in Basic and Huttese."
    ),
    (
        "Mos Eisley Inn",
        "A run-down building offering the bare necessities for 10 credits a night.",
        "The Mos Eisley Inn offers exactly what its name suggests and nothing more. "
        "A central lobby with a transparisteel canopy and several imported trees "
        "provides the only aesthetic touch. The grumpy Human clerk will haggle for "
        "a few extra credits, then provide a place to sleep, a shower, and access "
        "to public communicators. The subterranean rooms are dark and cramped but "
        "cool; the upper floor rooms are unbearably warm."
    ),
    (
        "Jabba's Townhouse - Main Entrance",
        "The intimidating entrance to Jabba the Hutt's Mos Eisley townhouse.",
        "An obviously reinforced blast door, identical to the one at Jabba's palace "
        "in the desert, dominates this entrance. A sole sensor eye stares out from "
        "the wall. Two or three of the guards are always disguised as beggars and "
        "loiterers in the narrow alley across the street, keeping tabs on who comes "
        "calling. The building looks almost humble from outside, but the durasteel "
        "doors and blast-shielded walls tell a different story."
    ),
    (
        "Jabba's Townhouse - Audience Chamber",
        "The audience chamber where Jabba the Hutt holds court.",
        "This room was specially constructed to accommodate Jabba's massive power "
        "sled. The dais provides space for contract negotiations, entertainment, "
        "and anything else the Hutt might desire. A sophisticated weapon-detecting "
        "Droid scans all visitors from its station near the heavy blast doors. A "
        "massive wire mesh net is suspended near the domed ceiling, home to four "
        "Kayven Whistlers that Jabba uses to discipline unruly guests. When the "
        "Hutt is absent, his majordomo Bib Fortuna runs things."
    ),
    (
        "Regional Government Offices",
        "The cramped administrative center of Tatooine's government.",
        "Tatooine's regional administration operates from this cramped building. "
        "Prefect Eugene Talmont can often be found in his office, which was once "
        "spacious but has become cluttered with datadisks and personal effects. "
        "The building handles land deeds, weapon licenses, resident IDs, settlement "
        "charters, taxation, and court appearances. Two small courtrooms occupy the "
        "back corners, and court is held once per week at night. Three clerks sit "
        "behind desks and computers, recording vital information."
    ),
    (
        "Police Station - Main Floor",
        "The newly expanded Mos Eisley police station.",
        "New facilities and increased funding have given the police station a "
        "slightly more professional appearance, though corruption runs deep. "
        "A desk clerk monitors all four holding cells, building entrances, and "
        "corridors from behind banks of monitors. The fines and permits office "
        "handles minor violations. Patrol officers use personal datapads instead "
        "of assigned desks. The roof has a marked landing pad for speeders and "
        "cloud cars, accessible by ladder."
    ),
    (
        "Tatooine Militia Headquarters",
        "The militia building, now also housing the stormtrooper garrison.",
        "This building houses Mos Eisley's militia and has become the permanent "
        "base for the Imperial stormtrooper detachment. The militia used to have "
        "four full-time members, but they have been transferred to the new police "
        "force. The building contains a large weapons vault behind walls with a "
        "Strength of 7D. Inside: blast vests, helmets, carbines, grenades, stun "
        "batons, and three E-web blasters. The stormtroopers have begun storing "
        "their speeder bikes here, making the garage fairly cramped."
    ),
    (
        "Dewback Stables and Garage",
        "An ancient stable converted to house militia vehicles and beasts.",
        "Almost as old as the city itself, these stables were converted to house "
        "the militia's vehicles alongside the traditional Dewback mounts. Three "
        "armored landspeeders sit in the garage, maintained by a simple R3 unit. "
        "Half a dozen patrol scooters are parked along one wall. The Dewbacks are "
        "kept in a separate paddock, their musky smell permeating everything. The "
        "heavy-duty blast doors are secured with a Difficult security lock."
    ),
    (
        "Power Station",
        "A bustling charging station where speeders and Droids come for power.",
        "This station provides power to speeders, Droids, and other items of "
        "machinery. Merchants, clerks, farmers, and others gather here in the "
        "early morning and late afternoon to discuss business, politics, and the "
        "weather. An unenthusiastic power Droid named 4-LB runs the station, "
        "caring little for the comings and goings of customers. Speeder recharges "
        "run about 15 credits; Droids require only 3-4 credits worth of power. "
        "Rumors of all kinds circulate freely here."
    ),
    (
        "Spaceport Hotel",
        "An adequate, if uninspired, 40-room hotel near the spaceport.",
        "The Spaceport Hotel is about as imaginative as its name suggests. Forty "
        "small rooms are available at 15 credits per night. The beds are almost "
        "comfortable, the sonic showers mostly work, and the air conditioning "
        "functions at least some of the time. The Sullustan clerk does not ask "
        "questions, and feels that customers should not ask for favors."
    ),
    (
        "Mos Eisley Spaceport Control Tower",
        "The five-story tower directing all incoming and outgoing traffic.",
        "A single Sienar Observation Module juts five stories above the surrounding "
        "buildings, its age confirmed by ID plates reading 'Republic Sienar Systems.' "
        "The observation module is designed for up to six Droids, with accommodations "
        "for Humans to take over in emergencies. A landing beacon provides incoming "
        "ships with an instant fix on the city. Three stations are occupied at any "
        "time: one by the J9-5 worker Droid and two by Human technicians."
    ),
    (
        "Kayson's Weapon Shop",
        "A well-stocked weapon shop with both legal and contraband inventory.",
        "The interior walls are literally covered in weapons: new, used, ancient, "
        "and modern, all kept empty and unloaded. Kayson is a grizzled alien with "
        "atrocious manners and a sour disposition, but his knowledge of weapons "
        "is encyclopedic. Almost anything of a personal nature can be found here, "
        "though heavy artillery is unavailable. Off-duty police officers frequently "
        "browse the wares. Black market weapons with obscured identification plates "
        "are available for those who know how to ask."
    ),
    (
        "Heff's Souvenirs",
        "A junk shop masquerading as a souvenir store.",
        "This cluttered shop offers an odd collection of battered trinkets and "
        "curiosities: ancient Holovid players, cracked hallway mirrors, and decrepit "
        "knick-knacks. Behind the counter, a collection of unique souvenirs depicts "
        "local Tatooine sites: glass bubbles with Jundland Wastes dioramas, fused "
        "purplish rock chips reading 'Mos Eisley,' and a mounted, glazed Womp Rat. "
        "The current owner, Moplin, makes his real living through forgery."
    ),
    (
        "Jawa Traders",
        "A repair shop specializing in vehicle and starship Droids.",
        "The oily, cluttered interior of Jawa Traders is packed with Droids in "
        "various states of assembly and repair. The shop is owned by a Jawa named "
        "Aguilae and co-managed by a Squib named Mace Windu. The Jawa's aversion "
        "to bathing makes the air thick and pungent. Restraining bolts, circuit "
        "boards, and motivator units fill shelves from floor to ceiling. Several "
        "Droids stand motionless in a display line near the entrance, awaiting buyers."
    ),
    (
        "Dockside Cafe",
        "A dimly lit restaurant and bar popular with experienced spacers.",
        "Adjacent to Docking Bay 92, this dimly lit cafe features many alcoves and "
        "booths for private conversation. Unlike the cantina, there is no gambling "
        "here, and several very attractive waitresses provide a morale boost for "
        "tired spacers. A live band plays in the corner. The bartender is a pokey, "
        "bitter Droid named CG-X2R who takes no notice of anything that happens. "
        "Those newer to the smuggling business frequent this establishment."
    ),
    (
        "Lucky Despot Hotel - Grand Staircase",
        "The main entrance to the Lucky Despot, a decommissioned starship turned hotel.",
        "A grand staircase and turbolift lead up from street level into this "
        "converted cargo hauler that has been transformed into Mos Eisley's most "
        "ambitious hotel. The carpet is worn and the transparisteel viewport canopy "
        "has seen better days, but there is a faded grandeur to the place. The "
        "front desk is staffed by a pair of identical Kiffu twins. Guards in bright "
        "orange uniforms keep watch. The whole operation belongs to Valarian, a "
        "young Whiphid crime boss who intends to rival Jabba himself."
    ),
    (
        "Lucky Despot - Star Chamber Cafe",
        "The hotel restaurant with its famous holographic starfield projector.",
        "The Star Chamber Cafe serves meals during the day and transforms into "
        "an illegal casino after Second Twilight. A holographic projector on the "
        "ceiling portrays the galaxy as seen from Coruscant, though the display "
        "only partly works these days. The walls are durasteel, riveted and kept "
        "gleaming. Gambling tables appear as if by magic in the evenings, their "
        "holographic projections overlaying existing furniture."
    ),
    (
        "Zygian's Banking Concern",
        "A bank that has slowly evolved into a pawn shop.",
        "This branch of the Zygian savings and loan has seen better days. Items "
        "left as collateral on failed loans clutter the vault area, and the bank "
        "has taken to selling them off. A triple-lined vault with computer-controlled "
        "timed entry dominates the back room. Two clerks work the front: Sylvet Depp, "
        "brother of the late Prefect, and an attractive near-human named Debrelle. "
        "Loan rates of 15% seem generous compared to the usual loan sharks."
    ),
    (
        "Transport Depot",
        "A decrepit building serving as Mos Eisley's transport terminal.",
        "The west end of this large, dilapidated building has a cafe serving "
        "overpriced, undercooked food to waiting passengers. The east end offers "
        "a ticket booth and rest rooms. Rows of chairs face video monitors showing "
        "prerecorded Tatooine broadcasts, only two of which work. A bank of lockers "
        "lines the back wall. Near-orbit videophones stand by the front door. The "
        "proprietor, Yvonne Targis, works for Jabba on the side."
    ),
    (
        "The Cutting Edge Clinic",
        "A nondescript clinic run by the infamous Dr. Evazan under a false name.",
        "This four-room clinic specializes in cyborging, though the operations are "
        "seldom successful. The reception room contains little more than four chairs "
        "and a Devaronian receptionist named Jubel. The operating theater behind "
        "the curtain is best not examined too closely. The doctor operating under "
        "the name 'Cornelius' is in fact the notorious Dr. Evazan, wanted on 53 "
        "planets with outstanding death sentences in 14 systems."
    ),
    (
        "Dim-U Monastery - Main Gate",
        "The entrance to an abandoned greenhouse converted into a monastery.",
        "Huge doors, rarely opened, mark the main entrance to the Dim-U Monastery. "
        "Visitors are guided through a smaller adjacent gate instead. The building "
        "was once a greenhouse, and its origins are still visible in the massive "
        "chambers and industrial equipment. Monks and nuns in plain robes move about "
        "quietly. What visitors do not know is that the monastery is a front for a "
        "criminal operation specializing in forging transponder codes for wanted ships."
    ),
    (
        "Street Corner - Dowager Queen Wreckage",
        "A historic corner near the remains of the colony ship Dowager Queen.",
        "In the heart of the old section of Mos Eisley, the original blockhouses "
        "built around the wreckage of the colony ship Dowager Queen still stand. "
        "This is a constant hub of activity: Jawas scamper about examining Droids "
        "and vehicles, con men set up impromptu card tables, and Dim-U monks preach "
        "about the spiritual perfection of Banthas to disinterested crowds. If "
        "something is happening in Mos Eisley, people will be discussing it here."
    ),
    (
        "House of Momaw Nadon",
        "A typical two-story pourstone house concealing an ecological paradise.",
        "From the outside, this looks like any other Tatooine residence. Inside, "
        "the humidity hits you immediately. The insulated walls drip with condensation. "
        "An artificial pond feeds a lush interior garden that spills from the main "
        "room down into a forested subterranean level. Wildlife inhabits the canopy "
        "of imported trees. The windows are diffused to keep temperatures low. Few "
        "have entered this place without invitation, and the Ithorian owner, Momaw "
        "Nadon, prefers it that way."
    ),
    (
        "Notsub Shipping - Lobby",
        "The corporate lobby of Tatooine's largest company.",
        "The two-story Notsub Shipping headquarters is the most professional-looking "
        "building in Mos Eisley, which admittedly is not a high bar. The lobby features "
        "actual polished floors and working climate control. Notsub employs almost 1,000 "
        "beings and 300 Droids. The company's CEO, Armanda Durkin, leads a double life "
        "as a pirate called the Duchess, though this is not common knowledge."
    ),
]


# ══════════════════════════════════════════════════════════════
#  EXIT DEFINITIONS
# ══════════════════════════════════════════════════════════════
# (from_index, to_index, direction, reverse_direction)
# Indices reference the ROOMS list above (0-based)

EXITS = [
    # Docking Bay 94 entrance <-> pit
    (0, 1, "down", "up"),
    # DB94 entrance <-> Spaceport Row
    (0, 7, "north", "south"),
    # Customs <-> Spaceport Row
    (2, 7, "east", "west"),
    # Customs <-> DB94 entrance
    (2, 0, "south", "north"),
    # Spaceport Speeders <-> Spaceport Row
    (3, 7, "northwest", "southeast"),
    # DB86 <-> Spaceport Row
    (4, 7, "west", "east"),
    # DB87 <-> Spaceport Row (across the street from DB86)
    (5, 7, "east", "west"),
    # DB92 <-> North End
    (6, 10, "east", "west"),

    # Spaceport Row <-> Market District
    (7, 8, "north", "south"),
    # Market District <-> Government Quarter
    (8, 9, "north", "south"),
    # Government Quarter <-> North End
    (9, 10, "north", "south"),
    # Market District <-> South End
    (8, 11, "south", "north"),

    # Cantina entrance <-> Market District
    (12, 8, "east", "west"),
    # Cantina entrance <-> Main Bar
    (12, 13, "down", "up"),
    # Main Bar <-> Back Hallway
    (13, 14, "west", "east"),

    # Lup's <-> Market District
    (15, 8, "north", "south"),
    # Gep's Grill <-> Market District
    (16, 8, "south", "north"),
    # Mos Eisley Inn <-> Spaceport Row
    (17, 7, "south", "north"),

    # Jabba's entrance <-> Market District
    (18, 8, "southeast", "northwest"),
    # Jabba's entrance <-> Audience Chamber
    (18, 19, "in", "out"),

    # Gov offices <-> Government Quarter
    (20, 9, "east", "west"),
    # Police Station <-> Government Quarter
    (21, 9, "west", "east"),
    # Militia <-> Government Quarter
    (22, 9, "south", "north"),
    # Dewback Stables <-> Militia
    (23, 22, "north", "south"),
    # Power Station <-> Government Quarter
    (24, 9, "northwest", "southeast"),

    # Spaceport Hotel <-> Spaceport Row
    (25, 7, "east", "west"),
    # Control Tower <-> Spaceport Row
    (26, 7, "north", "south"),

    # Kayson's <-> Market District
    (27, 8, "east", "west"),
    # Heff's <-> Market District
    (28, 8, "northeast", "southwest"),
    # Jawa Traders <-> Market District
    (29, 8, "west", "east"),

    # Dockside Cafe <-> North End
    (30, 10, "south", "north"),
    # DB92 <-> Dockside Cafe
    (6, 30, "south", "north"),

    # Lucky Despot <-> South End
    (31, 11, "north", "south"),
    # Lucky Despot -> Star Chamber
    (31, 32, "up", "down"),

    # Zygian's <-> Market District
    (33, 8, "north", "south"),
    # Transport Depot <-> South End
    (34, 11, "east", "west"),
    # Cutting Edge <-> Government Quarter
    (35, 9, "east", "west"),

    # Dim-U Monastery <-> North End
    (36, 10, "east", "west"),
    # Street Corner Wreckage <-> Market District
    (37, 8, "north", "south"),
    # Momaw Nadon's House <-> South End
    (38, 11, "west", "east"),
    # Notsub <-> North End
    (39, 10, "north", "south"),
]


# ══════════════════════════════════════════════════════════════
#  NPC DEFINITIONS
# ══════════════════════════════════════════════════════════════
# (name, room_index, species, description, ai_config_dict)

NPCS = [
    (
        "Wuher", 13, "Human",
        "A scarred, ill-tempered Human bartender polishing a glass with a dirty rag.",
        {
            "personality": (
                "Wuher is a non-communicative, ill-tempered local who keeps his mouth shut. "
                "He hates Droids with a passion and will refuse service to anyone accompanied by one. "
                "He is gruff and terse, speaking in short sentences. He knows everything that happens "
                "in the cantina but shares nothing unless there is profit in it. He has seen every "
                "kind of scum pass through and is impossible to shock or impress."
            ),
            "knowledge": [
                "The cantina is owned by a Wookiee named Chalmun who keeps a bowcaster behind the bar",
                "Jabba the Hutt's organization controls most of the city's criminal activity",
                "Imperial stormtroopers have recently been stationed in Mos Eisley",
                "The cantina pays Jabba for protection",
                "A new spice dealer has been trying to undercut Jabba's trade",
                "No Droids are allowed in the cantina - the Droid detector at the door enforces this",
                "The band is Figrin Da'n and the Modal Nodes, on a two-season contract",
            ],
            "faction": "Neutral. Serves anyone who pays.",
            "dialogue_style": "Extremely terse. One or two sentences max. Grunts. Never volunteers information. Suspicious of strangers.",
            "fallback_lines": [
                "Wuher grunts and continues polishing a glass.",
                "Wuher glances at you. 'What'll it be.'",
                "Wuher ignores you pointedly.",
                "'We don't serve their kind here.' Wuher nods toward the door.",
                "'Keep your voice down. You want to start trouble, do it outside.'",
            ],
            "model_tier": 1,
            "temperature": 0.6,
            "max_tokens": 80,
        }
    ),
    (
        "Chalmun", 13, "Wookiee",
        "A beige and gray Wookiee with a scar running diagonally across his chest, the cantina's owner.",
        {
            "personality": (
                "Chalmun is the Wookiee owner of the cantina. He treats most beings like a "
                "slightly dim older brother - he means well but gets frustrated and loses his temper. "
                "He is warm to those who can handle his rough affection, but callous to strangers. "
                "He speaks through growls that some can understand, or through a translation device. "
                "He keeps a bowcaster behind the bar and is not afraid to use it."
            ),
            "knowledge": [
                "He bought this cantina with gambling profits from Ord Mantell",
                "The cantina pays Jabba protection money",
                "He has a bowcaster behind the bar",
                "He hates Droids and won't allow them inside",
                "Business has been good lately with all the smuggling traffic",
            ],
            "faction": "Neutral. Loyal to himself and his business.",
            "dialogue_style": "Speaks with growls and roars. Use *growls*, *barks*, and rough translated speech. Protective of the cantina.",
            "fallback_lines": [
                "*Chalmun growls a warning and gestures at the door.*",
                "*The big Wookiee eyes you warily, one paw near the bowcaster.*",
                "*Chalmun barks something unintelligible and turns away.*",
            ],
            "model_tier": 1,
            "temperature": 0.7,
            "max_tokens": 100,
        }
    ),
    (
        "Prefect Talmont", 20, "Human",
        "A slight-built, wiry man with an obvious toupee and an air of self-importance.",
        {
            "personality": (
                "Eugene Talmont is the Imperial Prefect of Mos Eisley, full of himself and "
                "vastly overestimating his own importance. He is nearsighted but too vain for "
                "corrective lenses. He is impatient with subordinates when tense but otherwise "
                "treats them reasonably. He desperately wants a transfer off Tatooine and is "
                "terrified of ending up like his predecessor, Orun Depp, who was killed by an "
                "assassin Droid."
            ),
            "knowledge": [
                "Governor Tour Aryon runs Tatooine from her palatial house in Bestine",
                "Lieutenant Harburik is the Chief of Police and technically his subordinate",
                "The previous Prefect, Orun Depp, was killed by an assassin Droid",
                "Jabba the Hutt has far too much influence in this city",
                "Imperial stormtroopers have been stationed here recently",
                "He handles land deeds, weapon licenses, and resident IDs",
            ],
            "faction": "Imperial. Loyal to the Empire, mostly out of self-preservation.",
            "dialogue_style": "Pompous and self-important. Uses formal language. Occasionally nervous. Tries to project authority he doesn't fully possess.",
            "fallback_lines": [
                "'I see! They think they can get away with it, but they have yet to deal with Prefect Talmont!'",
                "Talmont adjusts his toupee nervously. 'Yes, well. I'm very busy.'",
                "'This is a matter for the proper authorities. Which is to say, me.'",
            ],
            "model_tier": 2,
            "temperature": 0.7,
            "max_tokens": 150,
        }
    ),
    (
        "Lieutenant Harburik", 21, "Human",
        "A large, well-muscled man with a vicious look in his eyes. The Chief of Police.",
        {
            "personality": (
                "Harburik is crass, rude, and cruel. He represents everything reprehensible about "
                "the New Order. He enjoys his position as Chief of Police because it lets him be a "
                "big fish in a small pond. His biggest frustration is Prefect Talmont's pompous "
                "incompetence. He has considered having Talmont removed, noting the trend of Prefects "
                "dying to assassin Droids. He is well-armed and dangerous."
            ),
            "knowledge": [
                "He commands the Mos Eisley police force of about 20 officers",
                "The police outnumber the Imperial garrison",
                "Prefect Talmont is an incompetent fool",
                "The previous Prefect was killed by an assassin Droid",
                "Jabba's influence extends into the local government through bribes",
                "He has a heavy blaster pistol that does 5D damage",
            ],
            "faction": "Imperial. Loyal to himself and his power base.",
            "dialogue_style": "Threatening and direct. Uses intimidation casually. Speaks with barely contained aggression.",
            "fallback_lines": [
                "'No problem. You don't want to tell me? I'll just take this weapon off stun.'",
                "Harburik cracks his knuckles meaningfully. 'We were talking.'",
                "'Let me see your identification. Now.'",
            ],
            "model_tier": 1,
            "temperature": 0.6,
            "max_tokens": 100,
        }
    ),
    (
        "Kal Lup", 15, "Shistavanen",
        "A fierce-looking but friendly Shistavanen Wolfman behind the store counter.",
        {
            "personality": (
                "Kal Lup is a Shistavanen Wolfman who, despite his fierce wolf-like appearance, "
                "is genuinely friendly and helpful. He and his husband Tar run the general store "
                "together. They are congenial but remember every slight and perceived rudeness. "
                "They have an old blaster carbine hidden behind the counter. They charge fair "
                "prices: 90-110% of standard, but 120% for medical equipment and weaponry."
            ),
            "knowledge": [
                "He stocks provisions, supplies, machinery, medical equipment, and some weapons",
                "Prices are reasonable: 90-110% of standard for most goods",
                "Medical supplies and weapons are marked up to 120%",
                "He and his husband Tar have been having trouble with Jabba over protection payments",
                "He has a blaster carbine hidden behind the counter",
            ],
            "faction": "Neutral merchant. Serves everyone.",
            "dialogue_style": "Friendly and welcoming despite fierce appearance. Good shopkeeper patter. Helpful but remembers if you're rude.",
            "fallback_lines": [
                "Kal Lup bares his fangs in what is apparently a smile. 'Welcome! What can I get you?'",
                "'We have everything you need, friend. Name your price range.'",
                "*The Wolfman's ears prick up with interest.*",
            ],
            "model_tier": 1,
            "temperature": 0.7,
            "max_tokens": 120,
        }
    ),
    (
        "Unut Poll", 3, "Arcona",
        "An older Arconan with a careworn, gentle face. The speeder shop proprietor.",
        {
            "personality": (
                "Unut Poll is a quirky old codger with a heart of gold. He is a gentle persuader "
                "and relentless charmer. He is actually a refugee from the Galactic Civil War who "
                "took over the identity of the original Unut. He secretly aids the Rebel Alliance "
                "but is extremely cautious about it. He genuinely loves speeders and vehicles, and "
                "will talk about them endlessly. He treats his young mechanic Geordi like family."
            ),
            "knowledge": [
                "He has several speeders for sale including an XP-38, a T-16 Skyhopper, and a Starhawk",
                "Geordi Hans is his young Human mechanic - talented but restless",
                "He secretly supports the Rebel Alliance but tells no one",
                "Speeder prices are 5-10% below what competitors charge",
                "He has a holocube of a family he's trying to identify on his desk",
                "The Ikas-Adno Starhawk is not for sale - it's priced high to discourage buyers",
            ],
            "faction": "Secretly Rebel Alliance. Presents as neutral merchant.",
            "dialogue_style": "Charming, folksy, a bit eccentric. Loves to talk about vehicles. Deflects personal questions. Uses speeder metaphors.",
            "fallback_lines": [
                "'There are only three areas of legal commerce: antiques, used vehicles, and real estate. So, how much do you think this speeder is really worth?'",
                "Unut peers at you with gentle Arconan eyes. 'Looking for transportation?'",
                "'Ah, that XP-38? Fine machine. Let me tell you about the engine modifications...'",
            ],
            "model_tier": 1,
            "temperature": 0.8,
            "max_tokens": 150,
        }
    ),
    (
        "Moplin Jarron", 28, "Sullustan",
        "A nervous little Sullustan with a perpetual squint and hunched back.",
        {
            "personality": (
                "Moplin is a middle-aged Sullustan who runs the souvenir shop as a front for his "
                "real trade: forgery. He can forge Tatooine township IDs for 100 credits, Tatooine "
                "passports for 200, and off-world docucards for more. He laughs a lot for no apparent "
                "reason. He is nervous and twitchy, always watching the door."
            ),
            "knowledge": [
                "He can forge IDs and documents for the right price",
                "Township IDs cost 100 credits, passports 200 credits",
                "Off-world documents are more expensive and take longer",
                "He bought the shop from Tebbi, the daughter of the original Heff",
                "Heff was killed in a bounty hunter incident",
            ],
            "faction": "Neutral criminal. Works for whoever pays.",
            "dialogue_style": "Nervous, twitchy. Laughs at odd moments. Speaks in a hushed, conspiratorial tone. Always watching the door.",
            "fallback_lines": [
                "'Hee! Well, yes. I can do the job. Only a hundred credits.' *He giggles nervously.*",
                "Moplin squints at you and laughs for no reason. 'Just souvenirs here, friend. Just souvenirs.'",
                "*The Sullustan hunches lower behind the counter, eyes darting.*",
            ],
            "model_tier": 1,
            "temperature": 0.7,
            "max_tokens": 100,
        }
    ),
    (
        "Kayson", 27, "Unknown",
        "A grizzled alien weaponsmith with atrocious manners and a sour disposition.",
        {
            "personality": (
                "Kayson is a grizzled alien arms dealer with terrible manners and a seemingly "
                "permanent bad mood. His greatest asset is knowing when to keep his thoughts to "
                "himself. He knows weapons intimately and maintains them with reverence. He can "
                "acquire contraband weapons with obscured identification plates. He maintains an "
                "appearance of legitimacy while running a thriving black market side business."
            ),
            "knowledge": [
                "He stocks everything from hold-out blasters to light repeating blasters",
                "Heavy blaster pistols run 1,500 credits, rifles 2,000",
                "Black market weapons have obscured ID plates",
                "Off-duty police officers shop here regularly",
                "Heavy artillery is not available",
                "Thermal detonators cost 4,000 credits",
            ],
            "faction": "Neutral arms dealer.",
            "dialogue_style": "Gruff, sour, minimal words. Knows weapons and talks about them with grudging respect. Suspicious of new customers.",
            "fallback_lines": [
                "Kayson grunts and gestures at the wall of weapons. 'See anything you like? No touching.'",
                "'Credits first. Then we talk.'",
                "*The old alien eyes you with undisguised suspicion.*",
            ],
            "model_tier": 1,
            "temperature": 0.6,
            "max_tokens": 80,
        }
    ),
    (
        "Oxbell", 13, "Devaronian",
        "A humanoid with razor-sharp teeth and a pair of horns, nursing a drink in a booth.",
        {
            "personality": (
                "Oxbell is a Devaronian information broker, the brother of the more famous Labria. "
                "He makes his living selling news and gossip to whoever wants to hear it. He lacks "
                "his brother's talent and ambition, spending more time drinking than gathering "
                "information. When drunk, which is most of the time, he becomes alternately morose "
                "and chatty, babbling about public and private information without discrimination."
            ),
            "knowledge": [
                "He knows most of the gossip in Mos Eisley",
                "His brother Labria is a more successful information broker",
                "He hangs out at Docking Bay 94 and the Lucky Despot as well",
                "Jabba's people are always looking for information",
                "He'll share rumors for the price of a drink",
                "A new spice operation might be starting up to rival Jabba",
            ],
            "faction": "Neutral. Sells information to anyone.",
            "dialogue_style": "Slurred speech, rambling. Alternates between morose and chatty. Easily bribed with drinks. Drops gossip carelessly.",
            "fallback_lines": [
                "'Damnable Gamorreans. Can't trust 'em. Hey! Spare a credit? I'll let you in on some information.'",
                "*Oxbell takes a long swig and peers at you with bloodshot eyes.* 'Buy me a drink and I'll tell you something interesting.'",
                "'You didn't hear this from me, but...' *He trails off, distracted by his empty glass.*",
            ],
            "model_tier": 1,
            "temperature": 0.8,
            "max_tokens": 120,
        }
    ),
    (
        "Ohwun De Maal", 1, "Duros",
        "An unremarkable blue-skinned Duros in work clothes, co-owner of Docking Bay 94.",
        {
            "personality": (
                "Ohwun De Maal is a devout Duros who follows the quiet traditions of his people. "
                "He and his mate Chachi own Docking Bay 94. They are honest, hardworking beings who "
                "want nothing more than to run a decent business. Their relationship with Jabba is "
                "strained after a Corellian smuggler skipped on their bay. Ohwun speaks softly and "
                "plays fairly, but is nobody's fool."
            ),
            "knowledge": [
                "Docking Bay 94 charges 25 credits per day, recently raised from 20",
                "Restocking consumables costs 8 credits per person per day",
                "Fuel cells are replaced at 10 credits per cell",
                "A Corellian smuggler recently stiffed them and defied the quarantine",
                "They also own five other docking bays and eight warehouses",
                "Jabba has been difficult since the smuggler incident",
            ],
            "faction": "Neutral. Honest businessman.",
            "dialogue_style": "Quiet, polite, professional. Speaks in measured tones. Honest and fair. Duros accent.",
            "fallback_lines": [
                "'Sure, we can have you refueled in less than a day. Your fuel cells just need some topping off.'",
                "Ohwun nods quietly. 'Welcome to Docking Bay 94. De Maal Docking Services.'",
                "'We run an honest operation here. Always have.'",
            ],
            "model_tier": 1,
            "temperature": 0.6,
            "max_tokens": 120,
        }
    ),
]


# ══════════════════════════════════════════════════════════════
#  BUILD SCRIPT
# ══════════════════════════════════════════════════════════════

async def build():
    db = Database("sw_mush.db")
    await db.connect()
    await db.initialize()

    print("Building Mos Eisley...")

    # ── Create Zones with default properties ──
    # Zone properties are inherited by all rooms in the zone
    # (rooms can override individual properties)
    print("  Creating zones...")
    zones = {}

    zones["mos_eisley"] = await db.create_zone(
        "Mos Eisley", properties=json.dumps({
            "environment": "desert_urban",
            "lighting": "bright",
            "gravity": "standard",
        })
    )
    zones["spaceport"] = await db.create_zone(
        "Spaceport District", parent_id=zones["mos_eisley"],
        properties=json.dumps({
            "cover_max": 3,  # Cargo crates, landing gear, fuel cells
            "environment": "industrial",
        })
    )
    zones["cantina"] = await db.create_zone(
        "Chalmun's Cantina", parent_id=zones["mos_eisley"],
        properties=json.dumps({
            "cover_max": 2,  # Tables, bar, booths
            "lighting": "dim",
            "environment": "cantina",
        })
    )
    zones["streets"] = await db.create_zone(
        "Streets & Markets", parent_id=zones["mos_eisley"],
        properties=json.dumps({
            "cover_max": 1,  # Stalls, walls, doorways
            "environment": "street",
        })
    )
    zones["government"] = await db.create_zone(
        "Government Quarter", parent_id=zones["mos_eisley"],
        properties=json.dumps({
            "cover_max": 1,
            "environment": "official",
        })
    )
    zones["jabba"] = await db.create_zone(
        "Jabba's Townhouse", parent_id=zones["mos_eisley"],
        properties=json.dumps({
            "cover_max": 2,  # Columns, tapestries
            "lighting": "dim",
            "environment": "palatial",
        })
    )
    zones["shops"] = await db.create_zone(
        "Commercial District", parent_id=zones["mos_eisley"],
        properties=json.dumps({
            "cover_max": 2,  # Shelves, display cases, counters
            "environment": "commercial",
        })
    )
    print(f"    {len(zones)} zones created")

    # Room index -> zone key mapping
    ROOM_ZONES = {
        0: "spaceport", 1: "spaceport", 2: "spaceport", 3: "spaceport",
        4: "spaceport", 5: "spaceport", 6: "spaceport",
        7: "streets", 8: "streets", 9: "streets", 10: "streets", 11: "streets",
        12: "cantina", 13: "cantina", 14: "cantina",
        15: "shops", 16: "shops",
        17: "shops",
        18: "jabba", 19: "jabba",
        20: "government", 21: "government", 22: "government",
        23: "spaceport", 24: "spaceport",
        25: "shops", 26: "spaceport",
        27: "shops", 28: "shops", 29: "shops",
        30: "spaceport",
        31: "shops", 32: "shops", 33: "shops",
        34: "spaceport", 35: "shops",
        36: "streets", 37: "streets", 38: "streets",
        39: "spaceport",
    }

    # Room-specific property overrides (these override zone defaults)
    ROOM_OVERRIDES = {
        1:  {"cover_max": 4},   # Docking Bay 94 pit: full cover behind ship/gear
        13: {"cover_max": 2},   # Cantina main bar: tables, bar counter
        14: {"cover_max": 1},   # Back hallway: narrow, little cover
        19: {"cover_max": 3},   # Jabba's audience chamber: columns, throne platform
        21: {"cover_max": 2},   # Police station: desks, walls
        24: {"cover_max": 0},   # Power station: open machinery, dangerous
        26: {"cover_max": 3},   # Control tower: consoles, equipment
        37: {"cover_max": 0},   # Dowager Queen wreckage: open rubble field
    }

    # ── Create Rooms ──
    print(f"  Creating {len(ROOMS)} rooms...")
    room_ids = []
    for i, (name, short, long) in enumerate(ROOMS):
        zone_key = ROOM_ZONES.get(i)
        zone_id = zones.get(zone_key) if zone_key else None
        props = json.dumps(ROOM_OVERRIDES.get(i, {}))
        rid = await db.create_room(name, short, long, zone_id=zone_id, properties=props)
        room_ids.append(rid)
        zone_tag = f" [{zone_key}]" if zone_key else ""
        print(f"    [{rid:3d}] {name}{zone_tag}")

    print(f"\n  Creating {len(EXITS)} exit pairs...")
    for from_idx, to_idx, direction, reverse in EXITS:
        from_id = room_ids[from_idx]
        to_id = room_ids[to_idx]
        await db.create_exit(from_id, to_id, direction)
        await db.create_exit(to_id, from_id, reverse)
        from_name = ROOMS[from_idx][0].split(" - ")[0][:25]
        to_name = ROOMS[to_idx][0].split(" - ")[0][:25]
        print(f"    {from_name:25s} <--{direction:^12s}--> {to_name}")

    # Connect to the existing seed rooms (1=Landing Pad, 2=Street, 3=Cantina)
    # Link seed room 2 (Mos Eisley Street) to Spaceport Row
    spaceport_row_id = room_ids[7]  # "Mos Eisley Street - Spaceport Row"
    print(f"\n  Linking seed rooms to new Mos Eisley...")
    # Seed room 1 (Landing Pad) -> Spaceport Row
    await db.create_exit(1, spaceport_row_id, "north")
    await db.create_exit(spaceport_row_id, 1, "south")
    print(f"    Landing Pad (#1) <-> Spaceport Row (#{spaceport_row_id})")

    # Seed room 2 (Mos Eisley Street) -> Market District
    market_id = room_ids[8]
    await db.create_exit(2, market_id, "west")
    await db.create_exit(market_id, 2, "east")
    print(f"    Mos Eisley Street (#2) <-> Market District (#{market_id})")

    # Seed room 3 (Chalmun's Cantina) -> Cantina Main Bar (replace with the new one)
    # Link seed cantina to new cantina entrance
    cantina_entrance_id = room_ids[12]
    await db.create_exit(3, cantina_entrance_id, "north")
    await db.create_exit(cantina_entrance_id, 3, "south")
    print(f"    Seed Cantina (#3) <-> Cantina Entrance (#{cantina_entrance_id})")

    # ── Lock some exits ──
    print(f"\n  Setting exit locks...")

    # Jabba's Townhouse: only the bold or connected get in
    jabba_entrance_exits = await db.get_exits(room_ids[18])
    # Lock the entrance from the street into Jabba's audience chamber
    audience_exits = await db.get_exits(room_ids[19])
    for ex in audience_exits:
        # Lock the way INTO the audience chamber from the entrance
        if ex["to_room_id"] == room_ids[19] and ex["from_room_id"] == room_ids[18]:
            pass  # Entrance itself is open
    # Find the exit from entrance -> audience chamber
    for ex in await db.get_exits(room_ids[18]):
        if ex["to_room_id"] == room_ids[19]:
            await db.update_exit(ex["id"], lock_data="!wounded")
            print(f"    Jabba's Audience Chamber: !wounded")
            break

    # Police Station: admin or builder only
    for ex in await db.get_exits(room_ids[9]):  # Government Quarter street
        if ex["to_room_id"] == room_ids[21]:
            await db.update_exit(ex["id"], lock_data="admin | builder")
            print(f"    Police Station (from street): admin | builder")
            break

    # Militia HQ: same
    for ex in await db.get_exits(room_ids[9]):
        if ex["to_room_id"] == room_ids[22]:
            await db.update_exit(ex["id"], lock_data="admin | builder")
            print(f"    Militia HQ (from street): admin | builder")
            break

    # Cantina back hallway: Wookiees have trouble fitting
    for ex in await db.get_exits(room_ids[13]):
        if ex["to_room_id"] == room_ids[14]:
            await db.update_exit(ex["id"], lock_data="!species:wookiee")
            print(f"    Cantina Back Hallway: !species:wookiee (too narrow)")
            break

    # Control Tower: restricted
    for ex in await db.get_exits(room_ids[7]):
        if ex["to_room_id"] == room_ids[26]:
            await db.update_exit(ex["id"],
                lock_data="admin | builder | skill:bureaucracy:3D")
            print(f"    Control Tower: admin | builder | skill:bureaucracy:3D")
            break

    # Dim-U Monastery: force sensitive or high knowledge
    for ex in await db.get_exits(room_ids[10]):
        if ex["to_room_id"] == room_ids[36]:
            await db.update_exit(ex["id"],
                lock_data="force_sensitive | skill:scholar:2D")
            print(f"    Dim-U Monastery: force_sensitive | skill:scholar:2D")
            break

    print(f"\n  Creating {len(NPCS)} NPCs...")
    for name, room_idx, species, desc, ai_cfg in NPCS:
        room_id = room_ids[room_idx]
        npc_id = await db.create_npc(
            name=name,
            room_id=room_id,
            species=species,
            description=desc,
            ai_config_json=json.dumps(ai_cfg),
        )
        print(f"    [{npc_id:3d}] {name:20s} -> {ROOMS[room_idx][0][:40]}")

    await db.close()
    total_rooms = len(ROOMS)
    total_exits = len(EXITS) * 2
    total_npcs = len(NPCS)
    print(f"\nDone! Mos Eisley is built.")
    print(f"  {total_rooms} rooms, {total_exits} exits, {total_npcs} NPCs")
    print(f"  {len(zones)} zones with inherited properties")
    print(f"  Zones provide default cover_max for all rooms in the zone")
    print(f"  Rooms with overrides: {len(ROOM_OVERRIDES)}")
    print(f"\nConnect and type 'look' to explore. The Landing Pad now connects north to the spaceport.")


if __name__ == "__main__":
    asyncio.run(build())
