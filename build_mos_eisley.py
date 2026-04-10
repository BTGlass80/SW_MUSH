# -*- coding: utf-8 -*-
"""
SW_MUSH World Builder v3
============================
Populates the full game world across four planets:
  - Mos Eisley (Tatooine) — 40 rooms, 7 zones  [original GG7 content]
  - Nar Shaddaa              — 25 rooms, 4 zones  [Dark Empire / EU]
  - Kessel                   — 18 rooms, 3 zones  [WEG sourcebooks / canon]
  - Corellia (Coronet City)  — 20 rooms, 3 zones  [general SW lore]

Also creates:
  - Combat-ready NPCs (char_sheet_json + ai_config_json)
  - Hostile NPCs (stormtroopers, thugs) that attack on sight
  - Hireable crew NPCs at cantinas and spaceports
  - Pre-spawned ships docked in bays with bridge rooms
  - NPCs for the three new planets

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

# ================================================================
# ROOM DEFINITIONS  (name, short_desc, long_desc)
# IDs assigned starting at 10 to avoid seed room collisions.
#
# Indices 0-39:  Mos Eisley (Tatooine) — original build
# Indices 40-64: Nar Shaddaa  (25 rooms)
# Indices 65-82: Kessel       (18 rooms)
# Indices 83-102: Corellia    (20 rooms)
# ================================================================
ROOMS = [
    # ==============================================================
    # MOS EISLEY (Tatooine) — rooms 0-39
    # ==============================================================
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

    # ==============================================================
    # NAR SHADDAA — rooms 40-64  (25 rooms)
    # ==============================================================
    # 40
    ("Nar Shaddaa - Docking Bay Aurek",
     "A grimy docking bay in the Corellian Sector of Nar Shaddaa.",
     "Fuel-stained duracrete slopes down into this cavernous bay. Refueling spires "
     "tower overhead, their navigation lights blinking in the perpetual gloom. Cargo "
     "droids haul crates without supervision. A battered kiosk charges 50 credits per "
     "day, payable in advance. No questions asked."),
    # 41
    ("Nar Shaddaa - Corellian Sector Promenade",
     "The main street of the Corellian Sector, a smugglers' paradise.",
     "Neon holographic signs flicker above a crowded thoroughfare. Corellians and "
     "beings from a hundred worlds push through the crowd. Street vendors hawk counterfeit "
     "transponder chips and black market spice. The air reeks of engine exhaust and "
     "cooking oil. Somewhere above, the refueling spires vanish into clouds."),
    # 42
    ("Nar Shaddaa - The Burning Deck Cantina",
     "A notorious smuggler cantina deep in the Corellian Sector.",
     "Low ceilings, thick smoke, and the persistent clatter of sabacc chips define "
     "this dive. Corellian whiskey flows cheap. Smuggling guild recruiters size up "
     "newcomers from corner booths. A holographic scoreboard tracks active cargo runs. "
     "The bartender, a scarred Weequay, has a blaster under the counter."),
    # 43
    ("Nar Shaddaa - Burning Deck Back Room",
     "A private room behind the cantina used for high-stakes deals.",
     "Soundproofed walls and a signal jammer ensure privacy. A circular table seats "
     "six. Scorch marks on the ceiling tell of negotiations gone wrong. The door has "
     "three locks and no window."),
    # 44
    ("Nar Shaddaa - Smugglers' Guild Hall",
     "The unofficial headquarters of the Corellian Smugglers' Guild.",
     "What looks like an abandoned warehouse opens into a surprisingly organized "
     "operations center. Star charts cover the walls. Dispatchers coordinate cargo "
     "runs across a dozen sectors. A communal armory sits behind a cage. Membership "
     "dues are 500 credits per standard month."),
    # 45
    ("Nar Shaddaa - Undercity Market",
     "A sprawling black market in the lower levels of Nar Shaddaa.",
     "Daylight has never reached these depths. Bioluminescent fungi and jury-rigged "
     "glowpanels cast everything in sickly blue-green. Stalls built from scrap metal "
     "sell everything from illegal weapons to stolen ship parts. Pickpockets and "
     "informants lurk at every junction. The law does not come here."),
    # 46
    ("Nar Shaddaa - Undercity Depths",
     "The deepest accessible level of Nar Shaddaa's vertical city.",
     "Corroded catwalks span chasms that plunge into absolute darkness. The mutated "
     "descendants of the Evocii scuttle in the shadows, wary of strangers. Moisture "
     "condenses on every surface. Strange sounds echo from below — machinery, or "
     "something else entirely. Few who venture this deep return unchanged."),
    # 47
    ("Nar Shaddaa - Hutt Emissary Tower - Lobby",
     "The opulent lobby of a Hutt-controlled tower in the upper levels.",
     "Polished duranium floors reflect the garish lighting. A massive Hutt clan sigil "
     "dominates one wall. Gamorrean guards flank the turbolift entrance. Visitors are "
     "scanned for weapons — then scanned again. A protocol droid manages appointments "
     "with mechanical precision."),
    # 48
    ("Nar Shaddaa - Hutt Emissary Tower - Audience Chamber",
     "An audience chamber for conducting Hutt business on the Smuggler's Moon.",
     "The chamber is designed to intimidate. A raised dais supports a Hutt repulsor "
     "sled. Hookah pipes and platters of live food surround the seat of power. Supplicants "
     "stand below, necks craned upward. Wall-mounted security cameras record everything."),
    # 49
    ("Nar Shaddaa - Refugee Sector",
     "A crowded district where displaced beings eke out survival.",
     "Makeshift shelters crowd the corridors between abandoned industrial blocks. "
     "Families huddle around shared heating vents. Children beg in a dozen languages. "
     "Relief droids distribute protein packs on a first-come basis. The smell of too "
     "many beings in too small a space is overwhelming."),
    # 50
    ("Nar Shaddaa - Vertical Bazaar",
     "A multi-level marketplace built into an old refueling spire.",
     "Shops and stalls ring the interior of a hollowed-out spire, connected by "
     "rickety turbolifts and spiral ramps. Each level specializes: weapons on three, "
     "ship parts on seven, information on twelve. A central open shaft lets you see "
     "fifty stories up and down. Vertigo is free of charge."),
    # 51
    ("Nar Shaddaa - Droid Junkyard",
     "A vast scrapyard of decommissioned and stolen droids.",
     "Mountains of droid parts stretch to the hazy ceiling. Salvagers pick through "
     "the wreckage with magnetic tools. Occasionally a half-functional droid twitches "
     "or speaks a garbled phrase. The Ugnaught proprietor insists everything is "
     "legitimately acquired. Nobody believes him."),
    # 52
    ("Nar Shaddaa - Spice Den",
     "A dimly lit den where various forms of spice are consumed.",
     "Reclining couches line the walls, occupied by beings in various states of "
     "intoxication. Glitterstim, ryll, and more exotic substances change hands in "
     "whispered transactions. The Twi'lek proprietor watches with calculating eyes. "
     "A back exit leads deeper into the Undercity."),
    # 53
    ("Nar Shaddaa - Bounty Hunters' Quarter",
     "A fortified block claimed by bounty hunters and mercenaries.",
     "Reinforced doors and weapon scanners mark the entrance to this self-policing "
     "enclave. Bounty posting boards line the main corridor. An equipment shop "
     "specializes in tracking devices and restraints. The cantina here serves strong "
     "drink and asks fewer questions than most."),
    # 54
    ("Nar Shaddaa - Landing Platform Besh",
     "An exposed landing platform jutting from the upper levels.",
     "Wind howls across this platform, hundreds of stories above the undercity. "
     "Mag-clamps secure ships against the constant gale. The view of Nar Shaddaa's "
     "endless cityscape stretches to every horizon, spire after spire vanishing into "
     "atmospheric haze. Nal Hutta looms in the sky above."),
    # 55  NEW
    ("Nar Shaddaa - Black Market Medcenter",
     "An unlicensed medical facility hidden behind a scrap metal front.",
     "Behind a rust-streaked door lies a surprisingly functional operating room. "
     "Recycled bacta tanks line one wall, half-full. Stolen medical equipment fills "
     "surgical bays. The doctor charges double the legal rate but asks no questions "
     "and files no reports. A Twi'lek nurse monitors the waiting area."),
    # 56  NEW
    ("Nar Shaddaa - Weapons Cache",
     "A fortified room in the Bounty Hunters' Quarter, selling military hardware.",
     "Security shutters and a Durasteel door protect this arsenal. The proprietor, "
     "an armless Duros who lost both limbs on a bad contract, operates the shop via "
     "waldos. Every weapon type is represented — blasters, melee, explosives, even "
     "restricted military stock if the price is right."),
    # 57  NEW
    ("Nar Shaddaa - Ship Parts Emporium",
     "A multi-deck shop selling salvaged and black-market starship components.",
     "Seven levels of shelving hold hyperdrive motivators, sensor arrays, shield "
     "generators, and ion cannon components. The stock is eighty percent stolen, "
     "twenty percent salvage. The Sullustan owner maintains meticulous inventory "
     "and competitive pricing. Rare parts available on order."),
    # 58  NEW
    ("Nar Shaddaa - The Undercity Clinic",
     "A charity clinic operated by a disgraced Rebel-aligned medic.",
     "Sparse but functional. Dr. Voss Tresk lost his medical license on Coruscant "
     "for treating Rebel sympathizers. He now treats the Refugee Sector's sick for "
     "whatever they can pay — sometimes nothing. His diagnostic skills remain sharp "
     "despite outdated equipment. A hand-painted sign reads 'All Welcome.'"),
    # 59  NEW
    ("Nar Shaddaa - The Grid",
     "An information broker's den in the upper levels, accessible by coded lift.",
     "Banks of screens show feeds from across the Smuggler's Moon — dock cameras, "
     "comm intercepts, Imperial patrol schedules. The broker, a blind Miralukan, "
     "trades exclusively in information. No physical goods. No violence permitted "
     "on premises. This rule is enforced by three heavily armed Gamorrean sentinels."),
    # 60  NEW
    ("Nar Shaddaa - Old Corellian Quarter",
     "A weathered residential block, home to longtime Corellian expatriates.",
     "Older than the rest of the Corellian Sector, this block predates the Imperial "
     "era. Residents have lived here for generations, maintaining Corellian customs "
     "in exile. A communal kitchen serves as social center. Graffiti in Corellian "
     "script covers the entry archway: 'Never tell me the odds.'"),
    # 61  NEW
    ("Nar Shaddaa - Renna Dox's Workshop",
     "A cluttered mechanical workshop run by a master shipwright.",
     "Every surface is covered with ship components in various states of assembly "
     "or disassembly. Diagrams and schematics paper the walls. Renna Dox — a broad-"
     "shouldered Zabrak woman with engine grease permanently under her fingernails — "
     "builds custom ship modifications and teaches Technical skills to those willing "
     "to work for the knowledge."),
    # 62  NEW
    ("Nar Shaddaa - The Floating Market",
     "Repulsorlift platforms drifting between towers, forming an open-air market.",
     "A dozen hovering platforms connected by gangways form this unusual marketplace. "
     "The platforms drift slowly in the thermal currents between towers, requiring "
     "some agility to navigate between them. Food, cheap goods, and stolen Imperial "
     "surplus are the primary offerings. The market has no fixed address — it moves."),
    # 63  NEW
    ("Nar Shaddaa - Enforcer Alley",
     "A narrow passage controlled by Hutt enforcers collecting protection money.",
     "This passage connects the Corellian Sector to the upper docks. Hutt-affiliated "
     "enforcers demand a 'transit toll' from everyone passing through. Refusing is "
     "inadvisable. The alley smells of spilled Corellian ale and old fear. Graffiti "
     "marks which gangs claim what territory."),
    # 64  NEW
    ("Nar Shaddaa - Upper Dock Observation Level",
     "A windswept observation level above the main docking platforms.",
     "The view from here is staggering — Nar Shaddaa's cityscape in every direction, "
     "stretching to the curved horizon. Ships arrive and depart in constant streams. "
     "Nal Hutta hangs enormous in the sky above. Sensor equipment here monitors "
     "traffic for the dock authority — which is actually a Hutt front company."),

    # ==============================================================
    # KESSEL — rooms 65-82  (18 rooms)
    # ==============================================================
    # 55
    ("Kessel - Spaceport Landing Field",
     "The heavily guarded landing field of Kessel's main spaceport.",
     "A flat expanse of permacrete surrounded by guard towers and sensor arrays. "
     "The thin atmosphere makes breathing labored without supplements. The Maw's "
     "gravitational distortion is visible as a shimmer on the horizon. Imperial "
     "shuttles and prison transports dominate the traffic."),
    # 56
    ("Kessel - Garrison Checkpoint",
     "An Imperial garrison checkpoint controlling access to the mines.",
     "Blast doors and ray shields funnel all traffic through scanners. Stormtroopers "
     "check identification with humorless efficiency. A holo-display lists current "
     "inmates and their work assignments. The walls are reinforced to withstand "
     "prisoner riots."),
    # 57
    ("Kessel - Administration Block",
     "The administrative center for Kessel's mining operations.",
     "Desks and data terminals fill this climate-controlled building — a stark "
     "contrast to the harsh conditions outside. Mining quotas, prisoner records, "
     "and shipment manifests scroll across screens. The warden's office occupies "
     "the top floor behind blast-proof transparisteel."),
    # 58
    ("Kessel - Mine Entrance - Level 1",
     "The primary entrance to Kessel's infamous spice mines.",
     "A massive tunnel mouth descends into darkness. Ore carts on magnetic rails "
     "emerge at regular intervals, filled with raw spice ore. The air is thick with "
     "glitterstim dust that sparkles in the floodlights. Miners shuffle past in "
     "chains, their eyes hollow."),
    # 59
    ("Kessel - Spice Processing Facility",
     "A heavily secured facility where raw spice is refined.",
     "Sealed clean rooms behind transparisteel walls house the delicate refining "
     "process. Workers in protective suits handle crystallized glitterstim with "
     "precise instruments. Armed guards watch from catwalks above. The refined "
     "product is worth more than its weight in aurodium."),
    # 60
    ("Kessel - Prisoner Barracks",
     "Bleak dormitories housing Kessel's forced labor population.",
     "Row upon row of bare metal bunks. The air recyclers barely function. "
     "Prisoners huddle in groups defined by species, crime, or simple survival. "
     "Guard droids patrol on fixed routes. A small infirmary treats only injuries "
     "that would reduce work output."),
    # 61
    ("Kessel - Black Market Tunnel",
     "A hidden tunnel network where guards and prisoners trade illegally.",
     "Behind a false wall in a maintenance corridor, a cramped network of tunnels "
     "hosts Kessel's worst-kept secret. Guards sell ration supplements, prisoners "
     "trade refined spice samples, and information changes hands in whispers. "
     "Everyone pretends this place doesn't exist."),
    # 62
    ("Kessel - Observation Deck",
     "A windswept observation platform overlooking the Maw.",
     "Transparisteel panels offer a terrifying view of the Maw — a cluster of "
     "black holes whose gravitational pull warps the stars themselves. Navigating "
     "the Kessel Run means skirting this cosmic horror. On clear days, the accretion "
     "disks glow with captured starlight. The view is humbling."),
    # 63
    ("Kessel - Smuggler's Contact Point",
     "A concealed meeting point used by spice smugglers.",
     "Tucked behind the spaceport's maintenance hangars, this prefab shelter "
     "serves as the contact point for smugglers brave or desperate enough to run "
     "Kessel spice. A coded signal on frequency 1138 announces available cargo. "
     "Payment is always in advance, and in hard credits only."),
    # 64
    ("Kessel - Energy Spider Caverns",
     "Deep caverns where dangerous energy spiders guard raw glitterstim.",
     "The natural caverns glow with bioluminescence and raw spice deposits. "
     "Energy spiders — deadly silicon-based predators — spin webs of pure energy "
     "between the stalactites. Miners work in teams, harvesting spice while "
     "lookouts watch for spider movement. Death is common here."),

    # ==============================================================
    # CORELLIA (Coronet City) — rooms 65-76
    # ==============================================================
    # 65
    ("Coronet City - Starport Docking Bay",
     "A modern docking bay in Corellia's capital city.",
     "Clean, well-maintained, and efficiently run — everything Mos Eisley is not. "
     "Automated cargo handlers move freight on repulsor tracks. Docking fees are "
     "posted clearly: 30 credits per standard day. Corellian Security Force officers "
     "patrol with quiet authority. The bay smells of ion drives and fresh rain."),
    # 66
    ("Coronet City - Starport Concourse",
     "The main concourse of Coronet Starport, bustling with travelers.",
     "Holographic departure boards list destinations across the galaxy. Shops sell "
     "Corellian brandy, ship parts, and travel supplies. The architecture is classic "
     "Corellian — functional elegance with no wasted space. Enormous viewports show "
     "ships ascending and descending against a blue sky."),
    # 67
    ("Coronet City - Treasure Ship Row",
     "The famous merchant street at the heart of Coronet City.",
     "Named for the ancient treasure ships that once docked here, this broad avenue "
     "is lined with upscale shops, trading companies, and financial houses. Corellian "
     "Engineering Corporation has a showroom displaying the latest freighter models. "
     "Street performers and food vendors add color to the commercial bustle."),
    # 68
    ("Coronet City - The Corellian Slice Cantina",
     "A spacer cantina popular with freighter crews and CEC workers.",
     "Named for the Corellian Slice hyperspace route, this cantina serves the best "
     "Whyren's Reserve in the city. Ship captains negotiate cargo deals over drinks. "
     "A sabacc table in the back sees constant action. The atmosphere is rough but "
     "friendly — Corellians look after their own."),
    # 69
    ("Coronet City - CorSec Headquarters",
     "The imposing headquarters of the Corellian Security Force.",
     "The Corellian Security Force — CorSec — operates from this fortress-like "
     "building in the government district. Turbolaser emplacements are concealed "
     "in the architecture. Inside, investigators and agents coordinate across the "
     "entire Corellian system. CorSec has a reputation for competence and independence."),
    # 70
    ("Coronet City - Government District",
     "The administrative heart of the Corellian system.",
     "Grand buildings in traditional Corellian style house the planetary government, "
     "trade commissions, and diplomatic missions. Fountains and parkland provide "
     "green space between the stone structures. The Diktat's palace is visible on the "
     "hill above, its spires catching the afternoon sun."),
    # 71
    ("Coronet City - CEC Shipyard Visitor Center",
     "The public face of the Corellian Engineering Corporation.",
     "Scale models of CEC's famous ships line the walls — YT-series freighters, "
     "Corellian corvettes, bulk cruisers. Interactive displays let visitors explore "
     "ship systems. Through the viewports, the orbital shipyard facilities are visible "
     "as bright points of light in the sky. CEC employs half the city."),
    # 72
    ("Coronet City - Blue Sector",
     "The entertainment district of Coronet City.",
     "Nightclubs, casinos, holovid theaters, and restaurants cram this vibrant "
     "district. Neon signs advertise everything from Twi'lek dancers to zero-g "
     "sportball matches. CorSec maintains a visible presence but tolerates most "
     "activities. The real trouble happens in the alleys behind the main strip."),
    # 73
    ("Coronet City - Residential Quarter",
     "A middle-class residential district with tree-lined streets.",
     "Two and three-story residential buildings face quiet streets shaded by "
     "Corellian oaks. Children play in small parks. Neighbors know each other by "
     "name. Compared to the rest of the galaxy, life here seems almost peaceful. "
     "Almost — CorSec patrols remind everyone that peace requires vigilance."),
    # 74
    ("Coronet City - Old Quarter Market",
     "An open-air market in the historic Old Quarter.",
     "Cobblestone streets and ancient stone archways frame a lively market. Local "
     "farmers sell Corellian produce, fishermen bring in catches from the coast, "
     "and craftspeople display handmade goods. The smells of roasting meat and "
     "fresh bread compete with the salt breeze from the nearby sea."),
    # 75
    ("Coronet City - Dockside Warehouses",
     "Commercial warehouses near the starport, some with questionable tenants.",
     "Rows of prefab warehouses store legitimate cargo — and occasionally not so "
     "legitimate cargo. CorSec runs spot inspections, but Corellians have a long "
     "tradition of looking the other way when it comes to smuggling. Several "
     "warehouses serve as fronts for the local black market."),
    # 76
    ("Coronet City - Spacers' Rest Hotel",
     "A comfortable hotel catering to visiting ship crews.",
     "Clean rooms, reliable amenities, and a cantina on the ground floor make this "
     "the preferred lodging for spacers. The Drall proprietor runs a tight ship. "
     "Message boards in the lobby advertise crew positions, cargo jobs, and the "
     "occasional discreet request for 'special delivery services.'"),
]

# ==============================================================
# EXITS  (from_idx, to_idx, direction, reverse_direction)
# ==============================================================
EXITS = [
    # =========================================
    # MOS EISLEY EXITS (original)
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
    # -- Bay 95 to Outer Curve --
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
    # -- Dim-U Monastery -> Market --
    (16, 8, "south", "north to Monastery"),
    # -- Spacers Quarters -> Spaceport Row --
    (17, 7, "south", "north to Quarters"),
    # -- Jabba's --
    (18, 8, "southeast", "northwest"),
    (18, 19, "in", "out"),
    # -- Government District --
    (20, 9, "east", "west to Prefect"),
    (21, 9, "west", "east"),
    (22, 9, "south", "north to Gov District"),
    (23, 22, "north", "south to Bay 35"),
    # -- Tower --
    (24, 9, "northwest", "southeast"),
    # -- Med Center -> Spaceport Row --
    (25, 7, "east", "west to Med Center"),
    # -- Warehouse Row -> Spaceport Row --
    (26, 7, "north", "south to Warehouses"),
    # -- Arms Dealer -> Market --
    (27, 8, "east", "west to Arms Dealer"),
    # -- Scrap Yard / Dewback Stable -> Market --
    (28, 8, "northeast", "southwest"),
    (29, 8, "west", "east"),
    # -- Docking Bay 96 <-> Outer Curve --
    (30, 10, "south", "north"),
    (6, 30, "south", "north"),
    # -- Lucky Despot -> Kerner Plaza --
    (31, 11, "north", "south"),
    (31, 32, "up", "down"),
    # -- Repair Shop -> Market --
    (33, 8, "north", "south to Repair Shop"),
    # -- Bay 92 -> Kerner Plaza --
    (34, 11, "east", "west"),
    # -- Jawa Trader -> Inner Curve --
    (35, 9, "east", "west to Jawa Trader"),
    # -- Alley -> Outer Curve --
    (36, 10, "east", "west to Alley"),
    # -- Desert Edge -> Market --
    (37, 8, "north", "south to Desert"),
    # -- Ithorian Garden -> Kerner Plaza --
    (38, 11, "west", "east"),
    # -- Notsub Shipping -> Outer Curve --
    (39, 10, "north", "south to Notsub"),

    # =========================================
    # NAR SHADDAA EXITS
    # =========================================
    # Docking Bay -> Promenade
    (40, 41, "out", "bay aurek"),
    # Promenade hub connections
    (41, 42, "west", "east to Promenade"),
    (41, 44, "north", "south to Promenade"),
    (41, 45, "down", "up to Promenade"),
    (41, 47, "up", "down to Promenade"),
    (41, 49, "southeast", "northwest to Promenade"),
    (41, 50, "northeast", "southwest to Promenade"),
    (41, 53, "south", "north to Promenade"),
    # Cantina -> back room
    (42, 43, "back", "out"),
    # Undercity Market -> Depths
    (45, 46, "down", "up"),
    # Undercity Market -> Spice Den
    (45, 52, "east", "west"),
    # Hutt Tower -> Audience Chamber
    (47, 48, "up", "down"),
    # Vertical Bazaar -> Droid Junkyard
    (50, 51, "down", "up"),
    # Landing Platform Besh -> Promenade
    (54, 41, "in", "platform besh"),

    # =========================================
    # KESSEL EXITS
    # =========================================
    # Landing Field -> Checkpoint -> Admin
    (55, 56, "north", "south to Landing Field"),
    (56, 57, "east", "west to Checkpoint"),
    # Checkpoint -> Mines
    (56, 58, "down", "up to Checkpoint"),
    # Mine -> Processing / Caverns
    (58, 59, "east", "west to Mine Entrance"),
    (58, 64, "down", "up to Mine Entrance"),
    # Admin -> Observation
    (57, 62, "up", "down to Admin"),
    # Checkpoint -> Barracks
    (56, 60, "north", "south to Checkpoint"),
    # Barracks -> Black Market Tunnel
    (60, 61, "hidden", "out"),
    # Landing Field -> Smuggler Contact
    (55, 63, "behind hangars", "out to Landing Field"),

    # =========================================
    # CORELLIA (Coronet City) EXITS
    # =========================================
    # Docking Bay -> Concourse -> Treasure Ship Row (main spine)
    (65, 66, "out", "bay"),
    (66, 67, "east", "west to Concourse"),
    # Treasure Ship Row hub
    (67, 68, "south", "north to Treasure Ship Row"),
    (67, 70, "north", "south to Treasure Ship Row"),
    (67, 71, "east", "west to Treasure Ship Row"),
    (67, 74, "west", "east to Treasure Ship Row"),
    (67, 75, "southwest", "northeast to Treasure Ship Row"),
    # Government area
    (70, 69, "east", "west to Gov District"),
    # Entertainment
    (68, 72, "south", "north to Cantina"),
    # Residential
    (70, 73, "north", "south to Gov District"),
    # Warehouses -> Hotel
    (75, 76, "south", "north to Warehouses"),

    # =========================================
    # NAR SHADDAA EXPANDED (rooms 77-86)
    # =========================================
    (77, 45, "out", "medcenter"),           # Black Market Medcenter -> Undercity Market
    (78, 53, "out", "weapons cache"),        # Weapons Cache -> Bounty Hunters Quarter
    (79, 50, "out", "ship parts"),           # Ship Parts Emporium -> Vertical Bazaar
    (80, 46, "out", "clinic"),               # Undercity Clinic -> Undercity Depths
    (81, 48, "coded lift", "down"),          # The Grid -> Hutt Tower upper
    (82, 41, "southeast", "northwest to Old Quarter"),  # Old Corellian Quarter -> Promenade
    (83, 82, "out", "workshop"),             # Renna Dox's Workshop -> Old Quarter
    (84, 45, "up", "down to Floating Market"),          # Floating Market -> Undercity
    (85, 41, "south", "north through Enforcer Alley"),  # Enforcer Alley -> Promenade
    (85, 54, "north", "south through Enforcer Alley"),  # Enforcer Alley -> Landing Platform
    (86, 54, "down", "up to Observation Level"),        # Observation Level -> Platform Besh
]

# ==============================================================
# ZONE MAPPING
# ==============================================================
ROOM_ZONES = {
    # -- Mos Eisley --
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
    # -- Nar Shaddaa --
    40: "ns_docks", 41: "ns_corellian", 42: "ns_corellian", 43: "ns_corellian",
    44: "ns_corellian", 45: "ns_undercity", 46: "ns_undercity",
    47: "ns_upper", 48: "ns_upper",
    49: "ns_corellian", 50: "ns_corellian", 51: "ns_undercity",
    52: "ns_undercity", 53: "ns_corellian", 54: "ns_docks",
    # -- Kessel --
    55: "kessel_surface", 56: "kessel_garrison", 57: "kessel_garrison",
    58: "kessel_mines", 59: "kessel_mines", 60: "kessel_garrison",
    61: "kessel_mines", 62: "kessel_surface", 63: "kessel_surface",
    64: "kessel_mines",
    # -- Corellia --
    65: "coronet_port", 66: "coronet_port", 67: "coronet_city",
    68: "coronet_city", 69: "coronet_gov", 70: "coronet_gov",
    71: "coronet_city", 72: "coronet_city", 73: "coronet_city",
    74: "coronet_city", 75: "coronet_port", 76: "coronet_port",
    # -- Nar Shaddaa expanded (rooms 77-86, physically appended to ROOMS list) --
    77: "ns_undercity",   # Black Market Medcenter
    78: "ns_undercity",   # Weapons Cache
    79: "ns_corellian",   # Ship Parts Emporium
    80: "ns_undercity",   # The Undercity Clinic
    81: "ns_upper",       # The Grid
    82: "ns_corellian",   # Old Corellian Quarter
    83: "ns_corellian",   # Renna Dox's Workshop
    84: "ns_undercity",   # The Floating Market
    85: "ns_undercity",   # Enforcer Alley
    86: "ns_upper",       # Upper Dock Observation Level
}

ROOM_OVERRIDES = {
    # Mos Eisley
    1: {"cover_max": 4}, 13: {"cover_max": 2}, 14: {"cover_max": 1},
    19: {"cover_max": 3}, 21: {"cover_max": 2}, 24: {"cover_max": 0},
    26: {"cover_max": 3}, 37: {"cover_max": 0},
    # Nar Shaddaa
    43: {"cover_max": 1}, 46: {"cover_max": 0, "lighting": "dark"},
    48: {"cover_max": 3}, 52: {"lighting": "dim"},
    # Kessel
    58: {"lighting": "dim"}, 60: {"cover_max": 0},
    64: {"lighting": "dark", "cover_max": 0},
    # Corellia
    69: {"cover_max": 2}, 72: {"lighting": "dim"},
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
        space_skills=None,
        # Skill trainer fields
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
# by engine/npc_loader.py. The YAML file contains 40 NPCs with full
# stat blocks, AI configs, and room placements.
#
# To add/edit NPCs, modify data/npcs_gg7.yaml instead of this file.
# ==============================================================

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
# PLANET-SPECIFIC NPCs (non-YAML, hand-defined)
# (name, room_idx, species, desc, char_sheet, ai_config)
# ==============================================================
PLANET_NPCS = [
    # --- Nar Shaddaa ---
    ("Vreego", 42, "Weequay",
     "A scarred Weequay bartender with a blaster under the counter.",
     _sheet(dex="3D+2", per="3D+1", stre="4D",
            skills={"blaster": "4D+2", "brawling": "5D", "streetwise": "5D"},
            species="Weequay"),
     _ai(personality="Vreego runs the Burning Deck Cantina. Serves drinks, breaks "
         "up fights, and hears everything. Never volunteers information without payment.",
         style="Gruff, laconic. Speaks in short sentences.",
         fallbacks=["Vreego polishes a glass, watching you with flat eyes.",
                    "'Drink or leave. We don't do tourism.'"])),

    ("Zekka Thansen", 44, "Human",
     "A middle-aged Corellian woman with sharp eyes and a guild master's chain.",
     _sheet(dex="3D", kno="4D", per="4D+1", mec="3D+2",
            skills={"bargain": "6D", "con": "5D", "streetwise": "6D+2",
                    "business": "5D+1", "space_transports": "5D"},
            species="Human"),
     _ai(personality="Zekka is the current coordinator of the Corellian Smugglers' "
         "Guild on Nar Shaddaa. Pragmatic, shrewd, fiercely protective of guild members. "
         "She despises the Hutts but does business with them when necessary.",
         style="Direct, businesslike. Corellian accent. No-nonsense.",
         fallbacks=["'Guild business is guild business. You a member?'",
                    "Zekka checks a cargo manifest on her datapad."])),

    ("Gorba's Enforcer", 47, "Gamorrean",
     "A massive Gamorrean guard in Hutt livery, carrying a vibro-axe.",
     _sheet(dex="2D+2", stre="5D",
            skills={"melee_combat": "5D", "brawling": "6D"},
            species="Gamorrean", weapon="vibro_axe"),
     _ai(personality="Loyal to the Hutt clan. Not bright. Very violent.",
         hostile=True, behavior="aggressive", faction="Hutt Cartel",
         fallbacks=["The Gamorrean grunts threateningly.",
                    "'GAAARK!'"])),

    ("Kreeda", 45, "Rodian",
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

    ("Vel Ansen", 53, "Human",
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

    # --- Kessel ---
    ("Warden Phaedris", 57, "Human",
     "The stern Imperial warden of Kessel's spice mining operations.",
     _sheet(dex="3D", kno="4D", per="3D+2",
            skills={"blaster": "4D", "command": "6D", "intimidation": "5D+2",
                    "bureaucracy": "5D", "law_enforcement": "5D+1"},
            species="Human"),
     _ai(personality="Warden Phaedris runs Kessel with cold efficiency. He views "
         "prisoners as production units, not people. Corruption is rampant under his watch "
         "but he maintains plausible deniability.",
         faction="Empire", style="Cold, bureaucratic. Imperial accent.",
         fallbacks=["'Production quotas must be met. Everything else is secondary.'",
                    "The Warden reviews daily output numbers without looking up."])),

    ("Kessel Stormtrooper", 56, "Human",
     "An Imperial stormtrooper in standard white armor, blaster at the ready.",
     _sheet(dex="3D+1", stre="3D",
            skills={"blaster": "4D+1", "brawling": "4D", "dodge": "4D"},
            species="Human", weapon="blaster_rifle"),
     _ai(hostile=True, behavior="defensive", faction="Empire",
         fallbacks=["'Halt! Present your authorization.'",
                    "'Move along. Move along.'"])),

    ("Skrizz", 61, "Chadra-Fan",
     "A small Chadra-Fan running the black market tunnel with nervous energy.",
     _sheet(dex="2D+2", kno="3D", per="4D",
            skills={"bargain": "5D+2", "con": "4D+1", "sneak": "5D",
                    "streetwise": "5D+2", "value": "5D"},
            species="Chadra-Fan"),
     _ai(personality="Skrizz is the unofficial quartermaster of Kessel's black market. "
         "He trades in everything from ration packs to refined spice samples. "
         "Terrified of the Warden but too greedy to stop.",
         style="Squeaky voice, rapid speech. Constantly fidgeting.",
         fallbacks=["'Psst! You need something? I got everything. Cheap!'",
                    "Skrizz wrings his tiny hands, checking for guards."])),

    # --- Corellia ---
    ("Officer Dalla Ren", 69, "Human",
     "A CorSec officer in the distinctive green uniform, carrying a heavy blaster.",
     _sheet(dex="3D+2", kno="3D+1", per="3D+2",
            skills={"blaster": "5D", "dodge": "4D+2", "investigation": "5D",
                    "law_enforcement": "5D+2", "streetwise": "4D+1"},
            species="Human"),
     _ai(personality="Officer Ren is a dedicated CorSec investigator. She's honest, "
         "competent, and has zero tolerance for criminal activity in Coronet City. "
         "She's tracking a spice ring operating through the starport warehouses.",
         faction="Corellia", style="Professional, direct. Corellian accent.",
         fallbacks=["'CorSec. I have a few questions for you.'",
                    "Dalla checks her datapad, cross-referencing something."])),

    ("Jorek Madine", 68, "Human",
     "A retired freighter captain running the Corellian Slice cantina.",
     _sheet(dex="2D+2", kno="3D+2", per="4D",
            skills={"bargain": "5D", "con": "4D+2", "persuasion": "5D+1",
                    "space_transports": "5D", "streetwise": "5D"},
            species="Human"),
     _ai(personality="Jorek flew freighters for thirty years before settling down. "
         "He knows every smuggler route in the Corellian Run. Friendly to spacers, "
         "suspicious of Imperials. Distantly related to General Madine.",
         style="Warm, storytelling. Always has an anecdote.",
         fallbacks=["'Pull up a chair, friend. What's your poison?'",
                    "Jorek wipes the bar, lost in a memory of the old routes."])),

    ("Desa Thyn", 71, "Human",
     "A CEC sales representative with perfect hair and a practiced smile.",
     _sheet(kno="3D+2", per="4D",
            skills={"persuasion": "6D", "business": "5D+2", "value": "5D",
                    "bureaucracy": "4D+1"},
            species="Human"),
     _ai(personality="Desa sells ships for CEC. She can recite specs for every "
         "YT-series model ever produced. Genuinely enthusiastic about Corellian "
         "engineering. Offers financing for qualified buyers.",
         style="Enthusiastic, polished. Sales pitch mode.",
         fallbacks=["'Have you seen the new YT-2400? Fastest thing in its class!'",
                    "Desa activates a holographic display of ship schematics."])),

    ("Coronet Pickpocket", 72, "Human",
     "A scruffy youth with quick hands and quicker feet.",
     _sheet(dex="4D", per="3D+1",
            skills={"pick_pocket": "5D+2", "sneak": "5D", "dodge": "4D+2",
                    "running": "4D+1"},
            species="Human"),
     _ai(hostile=True, behavior="cowardly",
         fallbacks=["The pickpocket tries to blend into the crowd.",
                    "'I didn't take nothing! You can't prove it!'"])),

    # --- Nar Shaddaa Expanded (rooms 77-86) ---
    ("Doc Myrra", 77, "Twi'lek",
     "A calm Twi'lek doctor working in the black market medcenter.",
     _sheet(kno="4D", per="3D+2", tec="5D",
            skills={"first_aid": "6D+1", "medicine": "6D", "bargain": "4D+2"},
            species="Twi'lek"),
     _ai(personality="Doc Myrra trained at a Coruscant hospital before her license was "
         "revoked for treating Rebel fugitives. She's pragmatic — charges double, delivers "
         "triple. No questions asked, no records kept.",
         style="Calm, professional. Slightly detached manner.",
         fallbacks=["'Cash in advance. I don't run a charity.'",
                    "Doc Myrra prepares a hypo without looking up."])),

    ("Duros Arms Dealer", 78, "Duros",
     "An armless Duros operating his weapons shop through a pair of mechanical waldos.",
     _sheet(dex="2D", kno="4D", per="3D+2", tec="4D+1",
            skills={"value": "6D", "repair_weapons": "5D+2", "bargain": "5D",
                    "streetwise": "5D+1"},
            species="Duros"),
     _ai(personality="Lost both arms on a bad bounty contract. Sells everything — "
         "blasters, melee, explosives, Imperial military surplus. No questions if you can pay.",
         style="Flat affect, mechanical precision. The waldos move constantly.",
         fallbacks=["The waldos sort inventory while he watches you.",
                    "'What caliber? What range? Budget?'"])),

    ("Suvvel", 79, "Sullustan",
     "A meticulous Sullustan running a seven-deck ship parts emporium.",
     _sheet(kno="4D", per="3D", mec="4D+2", tec="5D",
            skills={"value": "6D+2", "bargain": "5D", "starship_repair": "5D+1"},
            species="Sullustan"),
     _ai(personality="Suvvel tracks every part in his inventory by memory. "
         "Eighty percent of his stock is stolen or salvaged. Knows where to find "
         "rare components if standard stock doesn't cover it.",
         style="Rapid speech, high-pitched. Excited about specifications.",
         fallbacks=["Suvvel cross-references your request against three separate databases.",
                    "'I have seventeen motivator types in stock. Which grade?'"])),

    ("Dr. Voss Tresk", 80, "Human",
     "A gaunt human doctor with kind eyes and outdated equipment.",
     _sheet(kno="4D+2", per="3D+1", tec="5D",
            skills={"first_aid": "7D", "medicine": "6D+2", "persuasion": "4D"},
            species="Human"),
     _ai(personality="Tresk lost his medical license treating Rebel wounded. "
         "Runs a charity clinic in the undercity. Treats anyone, charges what they can pay.",
         style="Tired but warm. Gentle. Moves with care.",
         fallbacks=["'Sit down. Let me take a look at you.'",
                    "Dr. Tresk washes his hands before examining you."])),

    ("The Miralukan", 81, "Miralukan",
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

    ("Renna Dox", 83, "Zabrak",
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

    ("Hutt Toll Enforcer", 85, "Nikto",
     "A scarred Nikto enforcer blocking the alley, hand resting on his blaster.",
     _sheet(dex="3D+2", stre="4D",
            skills={"blaster": "4D+2", "intimidation": "5D+1", "brawling": "4D+1"},
            species="Nikto", weapon="heavy_blaster_pistol"),
     _ai(personality="Collects the Hutt clan transit toll. Not creative. "
         "Either you pay or you don't pass.",
         hostile=False, behavior="defensive",
         fallbacks=["'Twenty credits. Everyone pays.'",
                    "The Nikto taps his blaster meaningfully."])),

    # --- Kessel additions ---
    ("Mine Foreman Dreck", 58, "Human",
     "A thick-necked Imperial overseer supervising the mine entrance.",
     _sheet(dex="3D", stre="3D+1", per="3D",
            skills={"intimidation": "5D+1", "command": "4D+1", "blaster": "4D"},
            species="Human"),
     _ai(personality="Career Imperial. Efficient, brutal, indifferent to prisoner "
         "suffering. Tracks output quotas obsessively.",
         faction="Empire", style="Barking commands. Short sentences.",
         fallbacks=["'Quota's short. Get back to work.'",
                    "Dreck checks a work report, scowling."])),

    ("Prisoner 4477", 60, "Wookiee",
     "A massive Wookiee prisoner, chains on his wrists, pride still intact.",
     _sheet(dex="2D+2", stre="6D",
            skills={"brawling": "7D", "intimidation": "4D+2", "survival": "4D"},
            species="Wookiee"),
     _ai(personality="Enslaved for resisting Imperial conscription of his homeworld. "
         "Speaks no Basic but understands it. Helps those who show respect.",
         style="Growls, gestures. Shyriiwook only.",
         fallbacks=["The Wookiee studies you with orange eyes, measuring trust.",
                    "[ROAAR] (He's assessing whether you're worth talking to.)"])),

    ("Bith Chemist", 59, "Bith",
     "A Bith chemist supervising spice refinement in a contamination suit.",
     _sheet(kno="5D+1", tec="5D",
            skills={"medicine": "4D+2", "value": "5D"},
            species="Bith"),
     _ai(personality="Recruited for his chemistry expertise. Cooperates because "
         "the alternative was worse. Knows everything about spice refinement.",
         style="Precise, clinical. Avoids eye contact.",
         fallbacks=["'Glitterstim is particularly dangerous raw. Don't touch anything.'",
                    "The Bith checks contamination readings before responding."])),

    # --- Corellia additions ---
    ("Cala Wren", 74, "Human",
     "A Corellian market vendor selling fresh produce and local gossip.",
     _sheet(kno="3D", per="4D",
            skills={"bargain": "5D", "streetwise": "4D+2", "persuasion": "4D+1"},
            species="Human"),
     _ai(personality="Cala's family has worked this market for four generations. "
         "Knows everyone in the Old Quarter by name and most of their business.",
         style="Warm, rapid-fire. Always selling something.",
         fallbacks=["'Fresh from the coast this morning! Best price in Coronet!'",
                    "Cala arranges produce while eyeing you thoughtfully."])),

    ("Sergeant Bryn", 67, "Human",
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
]
# ==============================================================
SHIPS = [
    # -- Tatooine --
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

    # -- Nar Shaddaa --
    ("yt_1300", "Shadowport Runner", 40,
     "This YT-1300 has been heavily modified for smuggling. Hidden cargo "
     "compartments line the hull. The sensor baffler emits a low hum. "
     "Corellian guild markings are painted over but still visible."),

    # -- Kessel --
    ("lambda_shuttle", "Prison Transport K-7", 55,
     "A stripped-down Lambda shuttle configured for prisoner transport. "
     "The passenger section has been replaced with holding cells. "
     "Imperial military transponder codes cycle on the display."),

    # -- Corellia --
    ("yt_1300", "Corellian Dawn", 65,
     "A factory-fresh YT-1300 straight from the CEC production line. "
     "Everything gleams. The new-ship smell hasn't faded yet. A CEC "
     "quality sticker is affixed to the nav console."),
]


# ==============================================================
# BUILD FUNCTION
# ==============================================================

async def build(db_path="sw_mush.db"):
    db = Database(db_path)
    await db.connect()
    await db.initialize()

    print("+============================================+")
    print("|    Building Galaxy v3 -- Full World          |")
    print("+============================================+")

    # -- Zones --
    print("\n  Creating zones...")
    zones = {}
    # Mos Eisley zones
    zones["mos_eisley"] = await db.create_zone(
        "Mos Eisley", properties=json.dumps({"environment": "desert_urban",
                                              "lighting": "bright", "gravity": "standard",
                                              "security": "secured"}))
    zones["spaceport"] = await db.create_zone(
        "Spaceport District", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 3, "environment": "industrial",
                                "security": "contested"}))
    zones["cantina"] = await db.create_zone(
        "Chalmun's Cantina", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "lighting": "dim", "environment": "cantina",
                                "security": "contested"}))
    zones["streets"] = await db.create_zone(
        "Streets & Markets", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "street",
                                "security": "secured"}))
    zones["government"] = await db.create_zone(
        "Government Quarter", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 1, "environment": "official",
                                "security": "secured"}))
    zones["jabba"] = await db.create_zone(
        "Jabba's Townhouse", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "lighting": "dim", "environment": "palatial",
                                "security": "contested"}))
    zones["shops"] = await db.create_zone(
        "Commercial District", parent_id=zones["mos_eisley"],
        properties=json.dumps({"cover_max": 2, "environment": "commercial",
                                "security": "secured"}))

    # Nar Shaddaa zones
    zones["ns_docks"] = await db.create_zone(
        "Nar Shaddaa Docks",
        properties=json.dumps({"environment": "urban_industrial",
                               "lighting": "dim", "gravity": "standard",
                               "security": "contested"}))
    zones["ns_corellian"] = await db.create_zone(
        "Corellian Sector", parent_id=zones["ns_docks"],
        properties=json.dumps({"cover_max": 2, "environment": "urban_commercial",
                                "security": "contested"}))
    zones["ns_undercity"] = await db.create_zone(
        "Nar Shaddaa Undercity", parent_id=zones["ns_docks"],
        properties=json.dumps({"cover_max": 1, "lighting": "dark", "environment": "urban_slum",
                                "security": "lawless"}))
    zones["ns_upper"] = await db.create_zone(
        "Nar Shaddaa Upper Levels", parent_id=zones["ns_docks"],
        properties=json.dumps({"cover_max": 3, "lighting": "bright", "environment": "palatial",
                                "security": "contested"}))

    # Kessel zones
    zones["kessel_surface"] = await db.create_zone(
        "Kessel Surface",
        properties=json.dumps({"environment": "barren", "lighting": "bright",
                               "gravity": "light", "atmosphere": "thin",
                               "security": "contested"}))
    zones["kessel_garrison"] = await db.create_zone(
        "Kessel Imperial Garrison", parent_id=zones["kessel_surface"],
        properties=json.dumps({"cover_max": 2, "environment": "military",
                                "security": "secured"}))
    zones["kessel_mines"] = await db.create_zone(
        "Kessel Spice Mines", parent_id=zones["kessel_surface"],
        properties=json.dumps({"cover_max": 1, "lighting": "dim", "environment": "underground",
                                "security": "lawless"}))

    # Corellia zones
    zones["coronet_port"] = await db.create_zone(
        "Coronet Starport",
        properties=json.dumps({"environment": "urban_modern",
                               "lighting": "bright", "gravity": "standard",
                               "security": "secured"}))
    zones["coronet_city"] = await db.create_zone(
        "Coronet City", parent_id=zones["coronet_port"],
        properties=json.dumps({"cover_max": 2, "environment": "urban_commercial",
                                "security": "contested"}))
    zones["coronet_gov"] = await db.create_zone(
        "Coronet Government District", parent_id=zones["coronet_port"],
        properties=json.dumps({"cover_max": 2, "environment": "official",
                                "security": "secured"}))

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
    await db.create_exit(spaceport_row_id, 1, "south to Landing Pad")
    await db.create_exit(2, market_id, "north")
    await db.create_exit(market_id, 2, "south to Street")
    await db.create_exit(3, cantina_entrance_id, "east")
    await db.create_exit(cantina_entrance_id, 3, "west")
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
    print(f"  |  Planets:     4 (Tatooine, Nar Shaddaa,|")
    print(f"  |                  Kessel, Corellia)     |")
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
