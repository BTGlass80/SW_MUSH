# SW_MUSH — Creatures of the Galaxy Extraction
## Version 1.0 — May 31, 2026
## Source: WEG40080 — *Creatures of the Galaxy*, West End Games (1994, 96 pages, scanned/OCR'd)
## Purpose: Distill the build-relevant beast roster so the scan can be pruned, and hand the wilderness/encounter lane (G24) a turnkey, era-safe creature library with D6 stats.

---

## 0. What this is, and the two mandates that govern it

This is a **design reference**, not a transcription. Behavior text is paraphrased and reorganized
for the SW_MUSH wilderness/encounter build (the contestable-wilderness substrate, the Dune Sea
region, the painted areas, the `npc_template` encounter wiring). Stat blocks are transcribed
faithfully — they are game data and the whole point of the extraction. Two project rules apply
throughout:

- **Era translation (Clone Wars, ~20 BBY).** The book is firmly A New Hope / GCW era. The
  *creatures and their stats are era-agnostic* (this is why the roadmap rated COTG era-agnostic),
  but roughly a third of the entries carry GCW framing — the Empire, the Rebellion, X-wings, TIE
  fighters, the ISB / Imperial Intelligence, Imperial governors, Imperial assassin gear. **All of
  it is stripped or recast.** The blanket rule: no Empire/Rebel/Imperial/TIE/X-wing/stormtrooper
  reference survives into any seeded lore string (B3 era-cleanness). Per-creature strips are in §6.
- **Q1 canon-character policy.** Light load here — no canonical Force figures appear. The only
  canon name is **Jabba** (via the worrt), already handled the GG7 way: referenced only as "the
  dominant Hutt cartel," off-screen, with `JABBA'S PALACE` preserved as a pinned *location* name.
  One invented 1990s holostar ("Shantee Ren," in the stohl entry) is non-canon and harmless;
  genericize to "a popular holostar" if you want zero proper nouns.

**Organization.** §2 is the launch-relevant roster, grouped by the six launch worlds' biomes —
these are the beasts worth seeding first. §3 is the handful that drop into *any* terrain. §4 is
the complete remainder (the one-off-planet exotics) as a compact table, so the book is fully
captured and the scan can go. §5 wires it into our systems; §6 is the era cheat-sheet; §7 is the
prune note.

---

## 1. Stat-block convention, scale, and dedup

**Format.** WEG creature blocks are exactly what our encounter `npc_template` and the R&E-core
creature appendix already consume: non-intelligent creatures have only DEX / PER / STR, optional
skills, special abilities, Move, Size, Scale (defaults to Creature), and Orneriness (only if
rideable). Stat lines below read: `DEX · PER · STR · skills · signature attacks · Move · Size`.
"To-hit" uses STR or *brawling*; damage uses STR plus any claw/tooth/etc. modifier.

**Scale matters in two places.** Most entries are Creature (= character) scale. **Miner's Horror
is Starfighter scale** (§2.5) — it fights ships, not people; handle it on the space-combat path,
not the ground path. **Barri's Move is meters-per-round, not Space units** (§2.5) — it's a
Creature-scale drifter that happens to live in vacuum.

**Dedup against R&E core (WEG40120).** The R&E core appendix already ships **ghest** (Rodia swamp
reptile: `DEX 1D · PER 2D · STR 7D · teeth STR+2D · Move 15/8 · 6m`). COTG reprints it with one
extra line (claws STR+1D). **Defer to the core block as canonical; do not double-seed it.** No
other R&E-core beast (bantha, dewback, krayt, tauntaun, rancor, ronto, eopie, mynock, k'lor'slug,
cracian thumper, ukian torbull) appears in COTG, so the rest of this book is purely additive.

---

## 2. Launch-biome roster

### 2.1 Tatooine — Dune Sea & desert

**Worrt** *(Tatooine — canon fauna).* Blind-stupid tongue-ambusher; lunges at anything its own
size or smaller — prey, droids, rocks, whatever crawls past. Common in the wastes and around the
cartel's holdings.
`DEX 1D · PER 0D+2 · STR 1D · brawling/tongue 4D · Tongue 1D · Move 3 · Size 0.5–1.5m`
→ *Use:* low-threat Dune Sea filler; non-hostile that turns nuisance-hostile.

**Glim Worm.** Desert sand-tunneler that tracks prey by vibration at ~40 kph underground and
bursts up beneath it; wraps and rolls victims to its mouth on adhesive scales. Travels in 3–4s.
`DEX 1D · PER 1D · STR 1D · sneak 4D · brawling: grappling 3D, digging 4D · Grapple (opposed brawling vs brawling/STR) · Move 10 / 14 burrow · ≤1m`
→ *Use:* Dune Sea ambient/hazard; an "empty" tile that erupts. Pairs with the burrow-strike beat.

**Hitcher Crab.** Spiked desert crustacean; slow-acting claw venom (merely painful to most
Humanoids if treated), water sacs make it a survival prize, burrows to wait out the heat — easy
to step on unseen.
`DEX 1D · PER 1D+2 · STR 1D · Shell +1D energy/+2D phys · Claws STR+1D · Poison 2D+2 (claws)/1D+2 (shell) · Move 12 · 1.3m`
→ *Use:* desert forager encounter; salvage/water harvest node when buried.

**Magus.** Peaceful desert burrower with armor-tough hide (commercially hunted) and a foul
defensive oil-gland; bolts under the sand from threats.
`DEX 2D+1 · PER 2D+1 · STR 1D+1 · sneak 4D+1 · stamina 5D · Armor +1D+1 · Claws STR+2 · Odors (Very Difficult stamina to close within 3–4m) · Move 9 / 14 in sand · 58cm`
→ *Use:* non-hostile desert wildlife; hide is a harvest good (economy sink, see §5).

**Stalker Lizard.** Low, fast plains constrictor (purple-blue, matches Dune-grass tones in its
native form); sprints the last ~50m and crushes the windpipe. Solitary, one kill at a time.
`DEX 1D · PER 2D · STR 3D · search 3D+2 · sneak 5D · brawling 4D · Constriction STR+2D+2 · Move 13 (normal); "4D" sprint listed (book quirk — treat as a burst run) · ≤3.5m`
→ *Use:* plains/dune ambush predator; a genuine threat to a lone traveler.

*(See §3 for Wrix, Voroos, Shredder Bat — all of which also drop cleanly onto Tatooine.)*

### 2.2 Kamino — ocean

**Selligore.** Gentle 20-meter filter-grazer; harmless by diet but its bulk and habitat-loss
make it dangerous when cornered. A coastal island people herd them cooperatively.
`DEX 1D · PER 2D · STR 4D · swimming 6D · Move 13 (floats) / 4 walking · ≤20m, 4m tall · Orneriness 2D`
→ *Use:* Kamino-ocean megafauna; ambient awe + rideable/mount candidate (§5).

**Onahk.** Curious six-legged amphibian with a telescoping neck (to 2m); air-breather that holds
breath ~5 min, agile on land, constricts with the neck. Pods adopt-follow settlers; tames as a
loyal pet.
`DEX 3D · PER 2D · STR 1D+1 · brawling parry 4D · dodge 3D+2 · search 3D · sneak 4D · brawling 3D+2 · climbing/jumping 3D+1 · swimming 4D+2 · Constricting STR+1D+2 · Claws STR+1D · Move 10 / 14 swim · 1m long, 2.3m tall · Creature`
→ *Use:* coastal Kamino wildlife; tameable companion.

**Chiilak.** Tall six-limbed aquatic bruiser; "known to flatten Wookiees with one swing,"
20-minute breath-hold, swims hundreds of km. Learned to attack hunters.
`DEX 1D · PER 2D · STR 4D+2 · dodge 4D · brawling parry 6D · search 4D · tracking 4D · brawling 5D · climbing/jumping 5D · swimming 6D · Claws STR+1D · Move 9 / 18 swim · ≤2.2m`
→ *Use:* dangerous Kamino-ocean apex; serious melee threat.

**Two-Headed Tortuce.** Slow, intelligent dual-brained coastal amphibian (a Core delicacy, so
heavily harvested); the two heads coordinate attacks.
`DEX 2D+1 · PER 3D+2 · STR 2D+2 · sneak 5D+1 · brawling 3D · swimming 4D · Armor +1D · Dual-brained (two attacks, no penalty) · Heightened smell +1D · Jaws STR+1D · Move 4 / 8 swim · 0.8–1m`
→ *Use:* harmless coastal fauna; delicacy harvest (economy).

**Svaper.** Fast, always-hungry tank-predator; wraps prey and tears with needle teeth, spines
snap off in attackers. *(Also a Nar Shaddaa fixture — see §2.4.)*
`DEX 4D · PER 2D · STR 2D · Bite STR+3D · Spines STR+3D+2 (lodge in skin) · Tough skin +2D (not gills) · Move 20 swim · 2–3m (old captives to 6m)`
→ *Use:* aquatic threat / kept-predator; doubles as urban crime flavor.

**Zuxu.** "Lungfish" that pads ashore at night to raid camps; oil-gland keeps it moist out of
water ~3 hrs; bands up when aquatic food runs short.
`DEX 3D+2 · PER 2D+1 · STR 2D · sneak 3D+1 · swimming 4D · Teeth STR+3D · Move 18 swim / 3 walk · ≤1.1m`
→ *Use:* shoreline night-ambush; a "the water isn't the only danger" beat.

**Tresher.** Coastal-cliff raptor (protected, poached for plumage); acrobatic diver that strikes
from altitude; mates for life and savagely defends territory.
`DEX 3D+2 · PER 4D · STR 5D+2 · dodge 7D · search 6D · Acute vision +2D sight · Bite STR+2 · Talons STR+2 · Tail STR+1D · Diving attack (Move 55, +1D dmg) · Move 6 / 18 fly · 1.8–2.4m tall, 3.5m wingspan`
→ *Use:* Kamino sky/coast predator; high-end threat with a protected-species hook.

**Andoan Mineral-Fish.** Half-meter armored shellfish that eats metal/ore and grows a valuable
alloy shell; schools mark rich mineral deposits.
`DEX 1D · PER 1D · STR 1D · Tail STR+2D · Fins STR+1 · Shell +1D STR-to-resist · Mineral sense · Move 8 · ≤1m`
→ *Use:* harvestable economy fauna; "follow the school to the ore" prospecting hook.

### 2.3 Geonosis — rock, cave, arid

**Arqet.** Patient mountain ambusher; sits rock-still (color-shifts to the rock) until point-blank,
then gores; armor plate shrugs off bolts as it baits attackers closer.
`DEX 3D+2 · PER 3D · STR 3D · sneak 5D · Armor +2D phys/energy · Camouflage (in sneak) · Claws STR+2 · Feigned immobility · Horns STR+2D · Teeth STR+1D · Move 9 / 12 charge · 1.8–2.4m long, 2m tall`
→ *Use:* rocky-terrain ambush predator; the "that boulder moved" beat.

**Draagax.** Pack cave-dweller that turns berserk (and *fast*) after eating a local narcotic
plant; hunts by heat; paralytic bite.
`DEX 4D · PER 3D · STR 4D · dodge 5D · running 6D · sneak 5D · brawling 5D · climbing/jumping 5D · Enhanced speed (berserk → Move 28) · Infrared vision · Poisoned fangs (Moderate stamina or incapacitated) · Move 12 · 1.6–2.0m tall`
→ *Use:* hostile cave/grassland pack; a high-pressure swarm encounter.

**Keejin (Cave Crawler).** Near-blind cave scuttler found on countless worlds (a vacuum
subspecies too); harmless-but-unnerving, flees light; a rare larger variant drops on parties.
`DEX 3D · PER 2D · STR 2D+1 · Camouflage (+2 difficulty to spot) · Clinging (walls/ceilings) · Move 5 · 1–2m`
→ *Use:* cave ambient/atmosphere; optional "large hostile cousin" spawn. Vacuum subspecies → Kuat.

**Preying Makthier.** Crystal-cave flyer that hunts by sonar in total dark; masses 10+ for
attacks; constricts and stings with a paralytic tail.
`DEX 3D+1 · PER 2D+1 · STR 3D+1 · search 4D · sneak 4D+2 · lifting 5D+1 · Sonic motion detection (+1D+2 search) · Constriction (1D/round, −2D DEX) · Paralyzing stinger (2D + 4D stun ×5 rounds) · Move 10 fly · 1.2–2.7m long, 2m wingspan`
→ *Use:* cave hostile pack; pairs with a darkness/no-light tile modifier.

**Thanu.** Heat-immune volcano-dweller that *rolls* on stone "feet"; packs circle prey and grab
with tentacles. (Volcanic rather than strictly Geonosian, but the heat/rock fit is close.)
`DEX 3D · PER 1D+2 · STR 2D · Heat immunity (+1D STR vs blaster; any-temperature surfaces) · Tentacles (STR dmg + entangle) · Teeth STR+2D · Move 4 · 1.1m tall`
→ *Use:* exotic rocky/volcanic hazard; the silicon "stone feet" are a collectible charm (economy).

### 2.4 Nar Shaddaa & Coruscant underworld — urban / station

**Yeomet** *(flagship urban/station vermin).* Lives in stations, ships, and fully built worlds;
digs through almost anything, eats cables and conduits (electrical fires), carries disease;
flees unless cornered. Herds of ≤30 sleep in piles. Exterminators are a respected trade.
`DEX 4D · PER 2D · STR 1D+1 · Teeth STR+2D · Claws STR+1D · Disease transmission (Moderate stamina/STR) · Move 8 · 60cm tall`
→ *Use:* the definitive Nar Shaddaa / Coruscant-underworld / Kuat-station pest; infrastructure
hazard + extermination job-giver. Note the Jenet keep them as pets.

**Borcatu.** Bad-tempered stowaway scavenger; spread galaxy-wide on cargo ships from desert
origins into urban slums; rock-hard digging claws, bites anything that grabs it.
`DEX 3D · PER 2D · STR 1D+2 · Bite STR+2 · Claws STR+1 · Armored hide +2 · Digging · Move 11 · 0.2–0.5m`
→ *Use:* urban/dock pest; dockworkers hate it; cheap nuisance spawn.

**Spor Crawler** *(from "Nar Bo Shalla" — direct Nar Shaddaa adjacency).* Tiny, deadly
assassin's-pet insect; hides in dirt/drawers/under bedding, hives swarm intruders, lethal sting.
Ownership regulated; black-market thrives.
`DEX +2 · PER +2 · STR +2 · Poison 5D (roll every 5 min for 1 hr; Difficult stamina vs pain) · Burrowing · Camouflage (Difficult search) · Move 1 · 8cm`
→ *Use:* assassination/trap flavor; a hidden lethal hazard in seedy interiors.

**Tymp.** Forest forager that evolved an aggressive *urban* subspecies — raids city trash and
grain silos at night, increasingly attacks people.
`DEX 3D · PER 1D · STR 1D+1 · Night vision +2D · Tusks STR+1D · Climbing (+2D under stress) · Move 10 · 0.7m (+0.7m tail)`
→ *Use:* urban-pest spawn with a built-in "the city changed it" story; food-store nuisance.

**Sensor Star.** Five-limbed marsh creature with a near-supernatural sensory array; emits
subsonic "danger" tones — wired as a cheap living alarm system.
`DEX 0D · PER 0D · STR +2 · search 1D+2 · Subsonic communication (detectable to 350m) · Sensitive receptors (broad EM spectrum) · Move 2 · ≤25cm`
→ *Use:* security flavor — a "living sensor net" in a den or stronghold (ties to security-zone /
stronghold content). Rumored to sense "disturbances in the Force" (unconfirmed) — fun flavor.

**Somago.** Ambush "net" creature (relative of the Raen sovra) in several body-forms; the
"helmet" form is sized for Humanoids and chokes head-first. *(Strip Imperial-assassin origin —
recast as "rumored engineered, origin debated.")*
`DEX 4D · PER 2D · STR 3D+1 · Choking attack (+3D/round if it hits the head) · Hooks STR+1D · Move 4 · 50cm`
→ *Use:* interior/urban ambush trap; also a ship-corridor hazard.

*(Svaper, §2.2, belongs here too — "svaper wrestling" in black-market casinos and crimelord
disposal tanks is pure Nar Shaddaa / Hutt color.)*

### 2.5 Kuat — orbital, ships, near-space

**Miner's Horror** *(Starfighter scale — fights ships).* Rare 20m+ vacuum predator that grinds
asteroids (and ships) to dust with saw-teeth; slow, heavily armored, "sniffs out" refined ore —
so it treats a hull as a feast. Like a space slug with intent.
`DEX 3D · PER 1D · STR 4D · brawling 5D · Saw STR+2D · Armor +2D · Move 3 (Space) · 20m+ · Scale: STARFIGHTER`
→ *Use:* Kuat-orbital / wildspace space-combat encounter. Per the book, vs a ship treat *brawling*
as attack, STR(+armor) as hull, DEX as maneuverability. Hunting one yields a refined-ore bonanza.

**Barri.** Enigmatic, possibly-intelligent vacuum drifter; rides debris, secretes rock-dissolving
acid, has an innate astrogation gift and won't damage a ship that carries it.
`DEX 2D · PER 1D · STR 4D · Corrosive spittle 3D/turn · Innate navigation (astrogation 6D) · Move 10 (meters/round, NOT Space units) · ~4m · Creature`
→ *Use:* eerie wildspace/asteroid encounter; a non-hostile oddity with a navigation-aid hook.

**The Raen Sovra** *(technivore — ship/station hazard).* Metal-shelled worm that eats electricity
and metal; infests ships, stations, and building conduits; electrocutes whatever disturbs it.
Spreads like a contagion via docking ships. *(Strip the Imperial-vibrodagger / Imperial-collection
framing; keep the "system quarantined by authorities" beat, generic.)*
`DEX 4D+2 · PER 1D · STR 2D+2 · Electricity sense (+3D PER) · Electrocution 5D+2 (contact) · Space survival · Move 5 · ≤8m × 5cm`
→ *Use:* ties directly to the existing **mynock** ship-pest lore — a Kuat-yard / station / ship
infestation hazard. The companion "Imperial Munitions Vibrodagger" item is off-era; drop it or
recast as a generic black-market prototype.

*(Yeomet, §2.4, also infests stations. Keejin's vacuum subspecies, §2.3, fits airless Kuat
maintenance spaces.)*

---

## 3. Cross-biome drop-in hazards

These work in essentially any terrain — useful as a small "wildcard" set the encounter roller can
pull on multiple worlds.

**Voroos.** Stationary terrain-mimic; disguises as a mossy hill, dune, or snow-mound and tongue-
grabs whatever wanders close. Reported in bog, desert, and frozen waste.
`DEX 4D · PER 2D · STR 4D / 6D / 8D (by size) · Camouflage (Difficult PER to notice) · Tongue STR+1D + grasp (vs brawling parry) · Teeth (½ STR; +3D dmg to pull free) · Move 0 · 1–10m`
→ *Use:* a "the landscape ate me" ambush; the variable STR lets you scale threat per region.

**Shredder Bat.** Eyeless flying blood-drinker that hunts by hearing (detects prey ~15km),
dive-strikes the artery; packs of 20+, sometimes hundreds; spreads to 1,000+ worlds.
`DEX 1D+2 · PER 5D · STR 2D+2 · search: tracking 7D · sneak 6D+2 · brawling 3D+2 · flight 4D · Hearing (15km) · Fangs STR+1D; dive STR+2D+2 · Move 18 fly · ≤1m, 1m wingspan`
→ *Use:* flying-swarm threat anywhere with caves/structures; pairs with night/cave tiles.

**Slimy Nonakara.** Slime-eel that poisons its own pool and migrates overland to the next; larvae
implant in passing animals — a slow, hidden parasite that spreads via travelers.
`DEX 2D+2 · PER 1D+1 · STR 2D · Slime (Easy STR or 1D/round on contact) · Teeth STR+1D · Larval implantation (1-in-6 in an infested pool; drains STR over days) · Move 10 swim / 2 crawl · 20cm–4m`
→ *Use:* any-water hazard + a delayed-consequence parasite hook (a quest seed: "the fatigue
started after the swamp").

**Winged Xendrite.** Pest-control bug gone wrong; pinpoint insect-hunter introduced to "fix"
infestations, then overruns the ecosystem it was meant to protect.
`DEX 3D · PER 4D · STR 1D · Eyesight +2D sight · Move 30 fly / 2 · 40cm, 80cm wingspan`
→ *Use:* harmless individually; a swarm-overpopulation set-piece / ecological-disaster hook.

**Wrix.** Mountain pack-carnivore of folklore; preys on banthas and herd stock, drifts to
settlement fringes for pets; intimidating howl; subspecies up to 3.5m.
`DEX 1D · PER 2D · STR 3D · brawling parry 4D · search 3D · sneak 3D+2 · brawling 5D · climbing/jumping 4D+1 · Claws STR+1D · Howl (intimidation 5D) · Move 13 · ≤2.5m`
→ *Use:* mountain/desert-fringe pack threat (works on Tatooine and Geonosis); livestock-raid hook.

---

## 4. Exotic appendix — full remainder

One-off-planet exotics, lower seeding priority but captured here so the scan can be pruned. Stats
faithful; flavor compressed. All Creature scale unless noted. (Ghest is **omitted** — see §1 dedup.)

| Creature | Origin | Type | DEX / PER / STR | Signature | Move | One-line use |
|---|---|---|---|---|---|---|
| Adar | Omiddelon III | adaptive carnivore (pack) | 2D / 2D / 4D | claws STR+2D, leap STR+3D, flies 5min/hr | 13/15/22 | dive-bombing flying pack predator |
| Altagak | Altora | solitary carnivore | 4D+2 / 3D / 4D | tusk-charge STR+2D, speed burst | 8/28 | savannah sprint-ambusher |
| Attack Stohl | Ichtor 8 | domestic defense pet | 3D / 2D / 2D | bite STR+1D, +3D stun poison, coil | 5 | trained serpent bodyguard / luxury pet |
| Bandara | Devaron | semi-aquatic pest (swarm) | 2D / 1D / +1 | mating song (−1D actions), hunger 1D/round | 1 swarm / 15 | river-sandbar swarm hazard |
| Bergruutfa | Teloc Ol-sen | riding beast | 1D / 1D+2 / 6D | armored head +2D, head-butt, drool slick | 15 | 7m armored war-mount (Orneriness 1D) |
| Bogan's Brown Nafen | tropical worlds | winged rodent (swarm) | 5D / 4D / 1D | cumulative venom, disease vector | 30 fly / 4 | "butterbat" disease swarm |
| Croator | Wyndigal 2 | swamp avian | 2D / 2D / 1D+2 | reflective hood (+2D UV survival) | 15/10 | harmless avian; protective hide |
| Danchaf (Tree Goblin) | Garban | organized predator (pack) | 4D / 4D / 2D+1 | claws STR+1D, +1D+2 tracking, stealth | 8 | cunning arboreal pack hunter |
| Fenner's Rock | various | algae eater | 0D / 3D / +2 | camouflage +2D, screech | 1 | rock-mimic harmless ambient |
| Ganjuko | Fiive sector / Bothan worlds | arctic predator | 1D / 2D / 4D | beak STR+1D, temperature-sensitive | 13 | huge arctic beaked bruiser |
| Gornt | Hethar | meat animal | 1D+2 / 1D / 1D | bite STR+2 | 6 | frontier livestock (food/economy) |
| Graiveh | Ealor | presentient humanoid carnivore | 3D / 3D / 3D+1 | leap STR+3D, eyesight +2D | 12 | near-sentient pack; illegal-zoo flavor |
| Great Oopik | Paramatan | flightless avian-reptile | 1D+1 / 2D / 1D+2 | sonic stun 4D, sonar | 8/10 | sonar tree-ambush avian |
| Helas (Hela) | Enaleh | aeroreal amphibian | 4D+2 / 3D / 1D+1 | repulsorlift sense (2km), teeth | 150 | flying "air-eel" school; drawn to repulsors |
| Herlixx | Kasiol III | swampland omnivore | 3D+2 / 2D / 3D+1 | climbing/swimming | 9/12 | shy harmless swamp omnivore |
| Humbaba | Kashoon | lumbering beast | 2D / 3D / 3D | trunk STR+1D, armor +2D, concealment | 12 | camouflaged omnivore, biome variants (Orneriness 2D) |
| Ibliton | Random 2 | swamp hazard | 4D / 2D / 4D | entangling tentacles, armor +2D | 8 | swamp apex grappler |
| Kalaides (+ Red Miont) | Cols | mineral mollusk / fish | 0D/0D/0D (Miont 1D/2D/1D) | mineral filter / Miont bite STR+2 | 1 / 8 | harvested mollusk (economy); minor fish |
| Lepusa | Freliq | burrowing herbivore | 4D+2 / 4D+1 / 3D | springing, **tool-making** | 6/9/12 | clever burrowing pest (tool-use angle) |
| Ludos | Ganlihk | swampland carnivore | 4D+1 / 3D+2 / 3D+2 | bioluminescence, tentacles | 6/12 | docile glowing pet/companion |
| Nyantolo | Wyndigal 2 | carapaced aquatic mammal | 2D / 2D / 3D | shell concealment, bite STR+3D, song | 5 | swamp shell-ambusher |
| Oskan Blood Eater | (prison worlds) | engineered carnivore | 3D+2 / 2D / 4D | claws STR+3D, frenzy +2D, relentless tracking | 6 | engineered apex predator, origin unknown |
| Qormot | Yeshocq | forest omnivore | 2D+1 / 2D / 2D+1 | quills 3D, restricted vision | 8/14 | single-eyed quilled forager (mating aggro) |
| Quamin | Kidron | flying menace | 4D / 2D / 3D | razor tail STR+1D+2, silent flight | 16 | jungle flock that drains prey |
| Quizzer | Gamorr | scampering beast | 4D / 3D / 1D | climbing +2D | 7/12 | shiny-object thief; comic pest |
| Sanl'jek | Dancreti | communal herbivore (swarm) | 4D / 6D / 1D | communal swarm-rage, heartbeat sense | 12 / 40 frenzy | tiny harmless-until-provoked swarm |
| Skeeg | Vendara | predatory mollusk | 1D+2 / 1D / 2D+1 | stingers+poison, sedating scent | 0.5 | slow perfume-gland ambusher |
| Slar | Port Evokk | leaping hunter | 2D / 2D / 3D | leap 15m vert/40m horiz, razor quills STR+2D | 8/15/40 | erratic-feeding jungle pouncer |
| Sliideptra | Tel IV | arboreal invertebrate carnivore | 1D / 3D / 1D | poison-gas spray 7D (every 50 hrs) | 2 | hanging gas-cloud trap (toxic flesh) |
| Slork | Kidron | scavenger | 1D / 3D / 4D | grubbers STR+1D, stench (nausea), blubber +1D | 3 | reeking corpse-eater; non-aggro |
| Stiltwalker | swamp worlds | amphibious insectivore | 3D / 1D / 1D+1 | eyesight +2D, **Force sense** (chirps near Force users) | 3 | Force-detector flavor critter (§5) |
| Tantla | Ealor | forest scavenger (pack) | 4D+2 / 2D+2 / 2D+2 | grapple tongue, restricted vision | 12 | pelt-prized pack scavenger |
| Tedellian Besiioth | Tedel | high-gravity hunter (guard) | 1D+2 / 2D / 4D+2 | intimidating gaze 7D, visual tracking | 12/18 | guard beast; "stalker" subspecies for forests |
| Telkadis Tree Spider | Telkadis | predatory arachnid | 2D+2 / 2D+1 / 3D+1 | tree-burrow camo (+3D sneak), poison | 12 | tree-trunk ambush arachnid (colony defense) |
| Tentacle Bird of Pelemax | Pelemax | flightless jungle avian (mount) | 3D / 2D / 3D | war cry (stun), water storage (1 month) | 16/10 | caravan mount, esp. desert (Orneriness 2D/3D) |
| Troos Armored Crebik | Troos | arboreal arthropod | 2D / 2D+2 / 3D | falling attack 6D+2, pincers STR+2D | 6 | drops from branches; hammer ambush |
| Yo'uqiol | Ooo-sek | carnivorous mobile plant | 0D / 1D / 1D | poison tendrils 5D, digestive acid, mobile | 2 | ambush plant-trap (perimeter hazard) |

---

## 5. Build hooks

**5.1 Encounter-table wiring (G24 / wilderness).** Every block above slots straight into the
wilderness encounter table format (`npc_template`, `count`, `hostile`, `terrains`, optional
`min_distance_from_edge`, `faction_gate`). Examples, in the existing convention:

```yaml
# Tatooine Dune Sea additions
- id: glim_worm_strike
  weight: 6
  terrains: [dune, rocky_outcrop]
  npc_template: glim_worm
  count: [1, 1]
  hostile: true
  # an "empty" tile that erupts underfoot

- id: worrt_cluster
  weight: 10
  terrains: [rocky_outcrop, vaporator_field]
  npc_template: worrt
  count: [1, 3]
  hostile: false        # nuisance; can turn hostile if poked

- id: wrix_pack
  weight: 5
  terrains: [rocky_outcrop, canyon]
  npc_template: wrix
  count: [3, 5]
  hostile: true
  min_distance_from_edge: 8
```

Count ranges for the swarm/pack creatures (use these so encounters read right): adar 4–36,
shredder bat 20+, spor crawler/sanl'jek/bandara hive 5–50, wrix/draagax/danchaf pack 5–15,
makthier 10+, tantla/graiveh pack 10–12 / 34–40.

**5.2 `world_lore` species entries.** Seed the launch-tier beasts so the Director digest and NPC
brain have context. Same shape as the existing species entries (era-clean strings):

```python
{
  "title": "The Worrt",
  "keywords": "worrt,tatooine,desert,tongue,predator,pest",
  "content": "Worrts are blindly stupid desert ambush predators on Tatooine. Squat and toad-like, "
             "they sit motionless and snap a long tongue at anything their own size or smaller. They "
             "are harmless to a grown Humanoid but a constant nuisance in the wastes and around the "
             "cartel's holdings.",
  "category": "species",
  "zone_scope": "tatooine_outskirts,tatooine_mos_eisley",
  "priority": 4,
},
{
  "title": "Yeomet Vermin",
  "keywords": "yeomet,vermin,station,ship,cable,pest,nar shaddaa,underworld",
  "content": "Yeomets are reptilian vermin that thrive on built worlds, ships, and stations. They "
             "chew through cables and conduits, spread disease, and breed in non-hierarchical herds. "
             "Exterminators who track and clear them are well respected in the lower levels.",
  "category": "species",
  "priority": 4,
},
```

**5.3 Mounts (future beast-riding).** COTG flags four rideables via Orneriness — **Bergruutfa**
(1D, 7m armored war-beast), **Selligore** (2D, aquatic), **Humbaba** (2D, camouflaged), **Tentacle
Bird of Pelemax** (2D native / 3D others, *can go a month without water* → a natural desert mount).
Park these for whenever the beast-riding/mount lane opens; they're the ready stock.

**5.4 Technivores → ship/station pest layer.** **Raen Sovra** and **Somago** join the existing
**mynock** lore as a small "technivore" family — ship and station infestation hazards (power
drain, severed cables, electrocution). Good Kuat-yard and derelict-salvage color.

**5.5 Scale / space.** **Miner's Horror** is the only Starfighter-scale entry — route it through
the space-combat path (attack = brawling, hull = STR+armor, maneuver = DEX), not ground combat.
**Barri** is Creature-scale but lives in vacuum (Move is meters/round) — a non-hostile wildspace
oddity with a navigation-aid hook.

**5.6 Force-sensitive flavor.** **Stiltwalker** literally has a "Force Sense" ability — it chirps
when a Force-user channels nearby (20 stiltwalkers per die of *control*). A cheap, canon-flavored
"the swamp reacts to a Jedi" detail for any Force/Jedi-adjacent content; harmless and Q1-clean.

**5.7 Economy / harvest sinks.** Several beasts are explicitly harvested goods — **Magus** hide,
**Andoan Mineral-Fish** alloy, **Two-Headed Tortuce** (delicacy), **Thanu** stone "feet" (charms),
**Kalaides** (mineral mollusk). Drop-in resource nodes / vendor goods if/when wilderness harvest
goes live; the mineral-fish "school marks the ore" behavior is a free prospecting hook.

---

## 6. Era-translation cheat-sheet

**Blanket rule:** strip every Empire / Rebel Alliance / Imperial / stormtrooper / TIE / X-wing /
ISB / Imperial-Intelligence reference from any seeded string (B3 era-cleanness). The creatures
themselves are unchanged. Notable per-entry strips:

| COTG framing (GCW) | SW_MUSH handling (~20 BBY) |
|---|---|
| Jabba the Hutt (worrt entry) | "the dominant Hutt cartel," off-screen; `JABBA'S PALACE` location name stays pinned |
| Andoan mineral-fish alloy "reinforces the Alliance's X-wing hull"; "the Empire harvests" | "a valuable high-strength alloy"; harvesters / cartel, no faction |
| Gornt on "the Imperial military menu," sold to "the Imperial Navy," "Rebel-sympathetic farmers" | generic frontier ranch livestock; drop Empire/Rebellion |
| Graiveh "Imperial law" / "the Empire breeding docile slave labor" | off-world collectors, illegal zoos; drop Empire |
| Oskan Blood Eater "unauthorized Imperial experiments / Imperial Intelligence Bureau of Operations" | "artificially engineered; origin unknown" |
| Raen Sovra "the Empire collected specimens → Imperial assassin vibrodaggers"; Imperial Munitions Vibrodagger item | drop Imperial framing; keep "technivore" + generic "quarantined by authorities"; vibrodagger → off-era, cut or recast as black-market prototype |
| Sliideptra "the Empire collected for chemical warfare / Imperial spies' self-destruct / serum hidden from the Empire" | recast as cartel/black-market bio-interest; the Ho'Din simply keep their antidote quiet |
| Somago "the Empire created the helmet somago as an assassin's weapon" | "rumored engineered, origin debated" |
| Yo'uqiol "exported by the Imperial governor's munitions companies as land mines / Imperial facilities" | cartel / private security plant them on perimeters |
| Selligore "Voren Na'al / Movie Trilogy Sourcebook / Imperial crackdown on Corsin" | drop the GCW references; keep gentle-giant + generic habitat-loss pressure |
| Chiilak "Imperial Governor Yettaw" | "the local governor" |
| Bergruutfa "several Rebel Alliance bases use them for patrols" | primitive worlds / frontier outposts |
| Shantee Ren (invented holostar, stohl entry) | non-canon, harmless; optionally → "a popular holostar" |

Tagge Holographic Museum framing device (the book's intro conceit) is flavor only — ignore.

---

## 7. Prune note

With this extraction in hand, **`WEG40080.pdf` (Creatures of the Galaxy) can be removed from the
project.** The full roster — every stat block, era-translated, plus the launch-biome mapping,
encounter/lore/mount/economy hooks, and the GCW strip list — is preserved here. If you later want
a specific art plate, the book is re-obtainable; the build-relevant content you'd actually use is
captured above.

**Suggested follow-up (the B2 path):** a single "creature content drop" that lifts the launch-tier
and drop-in blocks into `data/npcs_creatures.yaml` (loader schema), adds the §5.2 `world_lore`
species seeds, and appends the §5.1 encounter-table snippets to the relevant region YAML — gated
behind the standard HEAD pre-flight on the NPC/creature-loader schema and the wilderness encounter
validator (§9 of the wilderness design). Next in the roadmap's encounters/wilderness lane: **GG8
Scouts**.
