# SW_MUSH — Gundark's Fantastic Technology: Personal Gear Extraction
## Version 1.0 — June 2, 2026
## Source: WEG40158 — *Gundark's Fantastic Technology: Personal Gear*, West End Games (114 pages, scanned/OCR'd)
## Purpose: Capture the full WEG D6 gear catalog — every stat block, era-translated — so the scan can be pruned, and hand the crafting/gear-economy lane (G06/G07) plus the combat (G03), espionage (G22), wilderness/encounter (G24), and entertainer (G23) lanes a turnkey, era-safe equipment library.

---

## 0. What this is, and the mandates that govern it

This is a **design reference**, not a transcription. Item descriptions are paraphrased; **stat
blocks are transcribed faithfully** — they are game data and the whole point of the extraction.
This is a WEG (D6) book, so per the roadmap we keep **content *and* stats** as-is. Three things
govern the pass:

- **Era translation (Clone Wars, ~20 BBY).** The *gear and its stats are era-agnostic* (this is
  why the roadmap rated the FT line era-flexible), but the book's entire **framing is New
  Republic era** — it is "Gundark's Gear Datalog," a post-ROTJ black-market catalog narrated by a
  fugitive arms dealer, wrapped in a CorSec memo to a New Republic Security Force interdiction
  officer, and salted with in-character bylines from NR-era smugglers and bounty hunters. **All
  of that framing is stripped or recast.** The blanket rule holds: no Empire / Rebel Alliance /
  Imperial / New Republic / stormtrooper / TIE / X-wing / Death Star / Palpatine / Luke reference
  survives into any seeded string (B3 era-cleanness). Per-item strips are in §8.
- **The wrapper, recast.** Where SW_MUSH wants the in-fiction "illegal catalog" flavor, recast it
  to era: a Clone-Wars-era **Hutt-cartel / Outer-Rim black-market datalog**, contacted by slicing
  a contact frequency onto local HoloNet carriers, with the law-enforcement foil being **CorSec /
  Republic Judicial / planetary security** rather than the Empire's "Division Three." The
  smuggling/anonymity/word-of-mouth tradecraft in the book's intro (background checks, alias
  strings, corrupt port officials, infochants, HoloNet piggybacking) is era-agnostic and is good
  texture for the crime/espionage lanes as-is.
- **Q1 canon-character policy.** Light load — the book invents its own NPCs (Gundark, the bylined
  commenters, the Malkite Ring, Dr. Llalik, Morana Fal). None are canon; recast or drop the
  bylines. The only canon name that appears is **Luke** (in the Force Detector entry, §5/§8) —
  cut entirely. **Bothans, Mon Calamari, Twi'leks, Sullustans, Coynites, Ubese, Rodians** appear
  as gear-origin species and are all era-agnostic; keep.

**A note on the asterisk.** The book marks New-Republic-only items with `*` in the availability
code and states most others "could have been found during the previous years." For ~20 BBY,
asterisked items are handled case-by-case in §1.4 — most survive (a lock breaker is a lock
breaker); a few are genuinely later tech and are recast or cut.

**Organization.** §2 is weapons (the combat/crafting payload). §3 is armor + attachments. §4 is
field/utility gear. §5 is the espionage/security/sensor toolkit. §6 is entertainment/leisure. §7
wires it all into our systems. §8 is the era cheat-sheet. §9 is the prune note. The bulk is in
compact tables (stat blocks preserved); genuinely build-relevant or era-flagged items get a call-out.

---

## 1. Conventions

### 1.1 Stat-block format
WEG personal-gear blocks read: **Model** (maker/designation), **Type**, **Scale** (Character
unless noted), **Skill** (the R&E skill + specialization), **Ammo**, **Cost** (credits; ammo/power
in parens), **Availability**, **Fire Rate**, **Fire Control**, **Range** (short/medium/long, in
meters unless KM noted), **Blast Radius**, **Damage**, and **Game Notes**. These map directly onto
whatever weapon/gear schema the build uses; nothing here needs re-statting.

### 1.2 OCR normalization (important)
The scan rendered D6 dice notation badly — "D" frequently became "0", "1" became "I" or "l". **All
dice values below are normalized to canonical D6** (e.g. scanned `50` → `5D`; `40+ 1` → `4D+1`;
`STR+20` → `STR+2D`; `60+2` → `6D+2`; `120` → `12D`). If a value below looks off against the
sourcebook, the scan is the culprit — trust the normalized form, which follows R&E damage grammar.

### 1.3 Availability codes (era-translated)
`1` common/anywhere · `2` licensed or region-limited · `3` specialized/military/hard-to-find ·
`4` rare/prototype/near-unobtainable · `F` requires a license or fee (book: "Imperial" → recast to
**planetary / Republic / sector** license) · `R` restricted, often illegal to civilians · `X`
contraband, illegal almost everywhere. These pair (e.g. `2,R`; `4,X`). For SW_MUSH these gate
nicely onto market tiers / faction-vendor access and the Security-Zone legality model (§7).

### 1.4 Scale
Almost everything is **Character** scale. Exceptions that must route on a different combat path:
**Espo Grenade Mortar** and **Merr-Sonn PLX-4 missile launcher** are **Speeder** scale (vehicle
combat); the **Finbat anti-armor missile** and **anti-vehicle grenade** are Character-scale but
ignore the scale-comparison reduction against speeder-or-smaller targets (i.e. they hit vehicles
at full damage). Power-armor weapon mounts use **armor weapons** or the named skill, not the
wearer's brawling.

---

## 2. Weapons

> Bulk preserved as tables; stats normalized. "Era" column flags only items needing a strip/recast
> beyond dropping the bylines (full handling in §8). Blank Era = drop bylines, keep as-is.

### 2.1 Melee & thrown (Ch. 1)

| Item | Model / maker | Skill (spec) | Cost | Avail | Difficulty | Damage | Era / notes |
|---|---|---|---|---|---|---|---|
| Coyn'skar | Ekkar Arms | melee combat | 400 | 3 | Moderate (blade) / V.Diff (hook disarm) | STR+2D blade, STR+2 hook | Coynite bladed pole |
| D'skar | Ekkar Arms | melee combat | 150 | 3 | Moderate | STR+1D+1 | Coynite dagger |
| Sat'skar | Ekkar Arms | melee combat | 700 | 3 | Difficult (V.Diff 1-handed) | STR+3D+1 (STR+1D 1-handed) | Coynite sword |
| Dematoil | Bitthrevrian | melee combat: dematoil | n/a | 4,X | Moderate–Difficult | STR+1D…STR+3D (scales w/ wielder) | Morningstar; Body 3D–5D+1 |
| Rantok | (Ka'hren/Unfyr) | melee combat: rantok | n/a | 4 | Difficult | STR+1D+1 (1h), STR+2D+1 (2h) | 2h: -1 difficulty, no parry |
| Neuronic Whip | TholCorp | melee combat: neuronic whip | 700 | 4,X | Easy | STR+1D **or** 5D stun | **Slaver gear** (Hutt cartel); keep illegal |
| Stun Baton | Merr-Sonn | melee combat: stun baton | 300 | R | Easy | STR+2D+2 (STR+1D off) | power pack 3 hr |
| Stun Baton Z2 | Merr-Sonn Z2 | melee combat: stun baton | 400 | R | Easy | STR+1D **or** 5D stun | two-setting |
| Stun Cloak | Koromondain SYT-300 | melee combat | 1,500 | 2 | Moderate (Easy vs attacker) | 5D stun | Ammo 3 (8 total); Diff parry to avoid |
| Stun Gauntlets | Palandrix PPG | brawling | 300 | 2 | Easy | STR+2D | Ammo 10 |
| Contact Stunner | SoroSuub C5-12 Stun Master | melee combat: contact stunner | 575 (cells 15) | 2,R | V.Easy | 4D+2 stun | +2D vs detectors, +1D vs pat-down |
| Taser Staff | Merr-Sonn | melee combat: taser staff | 500 (packs 40) | 4,R | Moderate | 5D **or** 5D stun (STR+1D uncharged) | Body 2D; recast "riot/crowd-control staff" |
| Vibrodagger | LaserHone Talon | melee combat | 50 | 2,R | Easy | STR+2D (max 6D) | silent; recast: drop "Storm Commandos" |
| Vibrorapier | LaserHone Duelist | melee combat | 300 | 2,R | Moderate | STR+3D (max 7D) | silent/ultrasonic; boarding favorite |
| Vibro-saw | Greel Wood Logging | melee weapons | 400 | 1,R | Moderate | STR+2D+1 | **legal tool**; cuts bulkheads |
| Zenji Needles | Mistryl (custom) | thrown weapons: zenji needles | n/a | 4 | — | STR+3D+1 (spec) / STR+1D | can crack battle armor |

### 2.2 Projectile, slugthrower & archaic firearms (Ch. 2)

| Item | Model / maker | Skill | Ammo | Range (s/m/l) | Damage | Cost | Avail | Notes |
|---|---|---|---|---|---|---|---|---|
| Auto-caster | Drolan Plasteel Repeating Crossbow | missile: crossbow | 20 | 3-8/20/35 | 3D | 700 | 1,2 | auto-loads next quarrel |
| Wrist-Caster | Drolan Plasteel QuickShot | missile: wrist launcher | 2 | 1-4/10/20 | 2D+2 | 500 | 3 | forearm crossbow |
| Dart Shooter | (typical) | missile: dart shooter | 30/clip | 2-4/8/10 | varies (2D–6D stun/normal) | 350 | 1,F | spring; evades detectors |
| Duo-Flechette Rifle | Salus DF-D1 | armor weapons | 5 | 3-10/30/60 | 5D | 1,000 | 3,R or X | twin shrapnel cartridges |
| Flechette Launcher | Golon Arms FC1 | missile weapons | 6/canister | 5-25/100/250 | 6D/5D/3D AP; 5D/4D/3D (speeder) AV | 800 (+100 AP/200 AV) | 2,F,R or X | blast 0-1/3/5 |
| Neural Inhibitor | Mennotor DAS-430 | firearms: railgun | 240 | 3-20/50/150 (rifle) | 3D+1 impact + 6D stun (neurotoxin) | 5,000 rifle/4,000 pistol | 4,R or X | tiered revive rules |
| Sevari Flash-Pistol | (custom) | archaic guns: flash-pistol | 1 | 3-10/30/60 | 4D+2 | 50–500 | 3 | misfire on Wild Die 1; blade STR+1D |
| Slugthrower Pistol | Morellian .48 Enforcer | firearms: Enforcer | 4 | 1-25/75/150 | 6D+1 | 6,000+ (b.mkt) | 4,R | recoil ↑diff per extra shot |
| Black Powder Pistol | Yctor Arms | archaic guns: black powder | 1 | 3/10/25 | 3D | 200 | 4 | beats energy scanners |

**Call-out — the "silencer" niche.** The slugthrower pistol, black-powder pistol, dart shooter and
duo-flechette are the catalog's *quiet / sensor-evading* ballistic line. They're the right tools to
gate behind smuggling/espionage vendors and to give CorSec weapon-detectors something to *miss*
(see Sniffer/Autoscan, §5) — a clean mechanical hook for the Security-Zone scan model.

### 2.3 Blasters & energy weapons (Ch. 3)

| Item | Model / maker | Skill (spec) | Ammo | Range (s/m/l) | Damage | Cost | Avail | Era / notes |
|---|---|---|---|---|---|---|---|---|
| Hold-out Blaster | Merr-Sonn B22 | blaster: hold-out | 10 | 3-4/8/12 | 3D | 300 | 2,R or X | recast: drop "Imperial requested it" |
| Quickfire-4 Hold-out | Merr-Sonn | blaster: hold-out | 10 | 3-4/8/12 | 4D | 300 | 2,R or X | as strong as a pistol |
| Micro Blaster | Gee-Tech 12 Defender | blaster | 2 | 1-5/— | 2D+2 | 200–400 | 2,R or X | V.Diff search to find |
| Blaster Pistol | BlasTech DL-22 | blaster: pistol | 100 | 3-10/30/120 | 4D+1 | 500 | 1,F,R,X | common DL-18 successor |
| Stun Blaster Pistol | (COMPNOR) | blaster | 10 | 3-10/30/60 | 2D stun | 300 | 2,F or R | **recast** generic weak stun pistol; drop COMPNOR/Empire |
| Disruptor Pistol | (standard) | blaster: disruptor | 5 | 0-3/5/7 | 6D+2 | 3,000 | 4,X | banned everywhere; outlaw-tech build |
| Heavy Blaster Pistol | BlasTech DL-6H | blaster: heavy pistol | 25 | 3-10/30/120 | 5D | 800 | 1,F,R,X | long range in a heavy frame |
| "Thunderer" Heavy | BlasTech T-6 | blaster: heavy pistol | 25 | 3-7/25/50 | 6D+2 | 750 | 2,R or X | hardest-hitting heavy pistol |
| "Renegade" Heavy | SoroSuub | blaster: heavy pistol | 25 | 3-7/25/50 | 5D+2 | 750 | 2,R or X | popular heavy |
| Heavy Disruptor Pistol | Merr-Sonn MSD-36 | blaster: heavy disruptor | 10 | 0-3/5/7 | 6D | 6,000 | 4,X | banned; outlaw-tech |
| Blaster Carbine | BlasTech StarSlasher | blaster: carbine | 100 | 3-25/50/250 (+5 long) | 5D | 900 | 2,X | scope/sling/bipod(+1D)/bayonet(STR+1D+2) |
| Sniper Rifle | SoroSuub X-45 | blasters: sniper | 25 | 1-25/100/250 | 5D | 750 | 2,R or X | scope → long-range to Moderate |
| Blaster Rifle | SoroSuub "Firelance" | blaster: rifle | 100 | 3-30/100/300 | 5D | 1,200 | 2,R or X | untraceable; "bounty-hunter gun" |
| Predator Rifle | Exotac EXP-7(a) | blaster | 8 | 3-30/80/350 | 7D | 7,000 | 4,X | FC 2D; Mod STR to recontrol recoil; prototype |
| Pulse Rifle | Corondexx VES-700 | blaster: pulse rifle | 15 / ∞ w/gen | 1-10/20/30 | 6D/5D/3D (cone) | 5,000 | 4,X | filaments/20 shots; overload rules |
| Riot Gun | BlasTech 500 | blaster: riot gun | 300 | 3-30/100/300 | 5D+1 | 1,500 | 2,R | constant-fire suppression |
| Energy Rifle "Blast & Smash" | Prax AXM-50 | blaster: rifle **+** missile: micro-grenade | 250 / 30 | 3-25/50/75 & 5-25/100/200 | 5D / 4D-3D-2D | 4,500 | 3,F or R | combo; FC Mod-Perc +1D |
| Blaster Speargun | BlasTech Firearc 49 | blaster rifle | 3 / 50 | spear 3-7/25/50; blast 3-20/30/45 | spear 4D-2D-1D; blast 5D-4D-3D+1 | 300 | 2,R or X | underwater/hunting |
| Deck-Clearing Blaster | BlasTech Firespray DL-87 | blast: deck clearer | 10 | 1/5/10 | 5D | 100 | 2,X | 45° arc; ≤5m no dodge |
| Deck-Sweeper | Merr-Sonn Stunning Blaster | blaster: deck-sweeper | 5 | 3/5/10 | 6D | 500 | 2,X | 45° arc **stun**; police/boarding |
| Military Blaster Rifle | (BlasTech E-11) | blaster: rifle | 100 | 3-30/100/300 | 5D | 1,000 | — | **recast** generic mil. rifle; drop stormtrooper/Espo framing |
| Rifle/Slug Combo | (BlasTech E-11/S) | blaster **+** firearms | 25 / 6 | 3-30/100/300 & 3-30/150/400 | 5D / 4D | 7,000 | X,4 | outlaw aftermarket combo |
| **Archaic energy** (4 items below — collectible/Outer-Rim primitive markets) | | | | | | | | |
| Blast Rifle | Core World Arms BRI-Z | blast-rifle | 50 | 3-15/30/150 | 5D | 1,500 | 4,R or X | +5 diff at long |
| Pulse-wave Blaster | Greff-Timms ATA | pulse-wave: blaster | 50 | 3-8/20/100 | 4D | 600 | 4,X | banned on most worlds |
| Pulse-wave Rifle | Greff-Timms Type A | pulse-wave: rifle | 50 | 3-20/75/150 | 5D | 2,000 | 4,X | — |
| Quick-draw Pulse-wave | Greff-Timms SnapShoot DT3 | pulse-wave: quick-draw | 3 | 2-3/6/10 | 3D | 300 | 4,X | draw+fire, no multi-action penalty; *Old-Republic-issue → era-friendly* |
| **Flame / sonic** (4 items) | | | | | | | | |
| Flame Carbine | Authority | flame-thrower | 10 | 3-4/5/7 | 5D (3D next 5 rds) | 500 | 4,X | — |
| Flame Rifle | Authority | flame-thrower | 25 | 3-5/7/10 | 5D+1 (4D next 10 rds) | 700 | 4,X | — |
| Sound Pistol | SonoMax 75 | blaster: sound pistol | 20 | cone 0-3/10/20 | 6D/5D/4D **or** 5D/4D/3D stun | n/a (restricted) | — | riot/crowd-control |
| Sound Rifle | SonoMax 100 | blaster: sound rifle | 60 | cone 0-5/15/30 | 6D/5D/4D **or** 5D/4D/3D stun | n/a (restricted) | — | riot/crowd-control |

> **Dropped Imperial-Munitions duplicates:** the **KK-5**, **SC-4**, **Imperial Munitions Heavy
> Blaster Pistol**, and **StarAnvil Heavy Blaster Rifle** are off-era-branded clones of existing
> R&E blasters (DL-18 / DL-44 / blaster rifle) and add nothing mechanically. **Do not seed.** The
> one reusable *mechanic* — the SC-4's traceable codes + self-destruct grip — is recast brand-neutral
> as a "tracked corporate-security sidearm" hook in §8.

### 2.4 Launchers & heavy weapons (Ch. 4)

| Item | Model / maker | Skill | Scale | Ammo | Range | Damage | Cost | Avail | Notes |
|---|---|---|---|---|---|---|---|---|---|
| Micro-Grenade Launcher | Locris MGL-1 | missile: micro-grenade | Char | 30 | 5-25/100/200 | 4D/3D/2D (frag) | 2,500 | 3,F | FC Mod-Perc +1D; blast 0-2/4/6 |
| Rocket Launcher | Locris RDP-12 | missile: rocket | Char | 4/20 | 3-30/100/300 | 4D (A) / 5D stun + nerve (B) | 1,500 | 3,F or R | Type-12B: Diff stamina or KO |
| Espo Grenade Mortar | (Espo) | blaster artillery | **Speeder** | 100 | 25-100/500/1KM | by grenade | 3,500 | 2,F,R,X | Crew 1; Body 4D; FC 1D; recast "field mortar" |
| Portable Missile Launcher | Merr-Sonn PLX-4 | missile: Plex | **Speeder** | 4 | 100-500/3/10KM | 6D | 6,000 | R* | drop **"savant" NR-only missile**; keep dumb (200)/GAM (600) rockets |

### 2.5 Grenades (Ch. 5)

| Item | Model / maker | Range | Blast | Damage | Cost | Avail | Notes |
|---|---|---|---|---|---|---|---|
| Anti-Vehicle Grenade | Galentro Armaments | — | — | 7D | 750 | R,X | no scale reduction vs ≤speeder |
| Stun Grenade | Merr-Sonn | 0-8/16/25 | 0-2/20/40 | 6D/5D/3D/2D stun | 450 | 2,R or X | rechargeable/reusable |
| Spore/B Stun Grenade | Czerka | 0-8/16/25 | 0-2/20/40 | 4D/3D/2D stun | 300 | 2,X | Bothan spores; resp.-failure risk (Wild Die 1) |
| T-289 Gas Grenade | Czerka | 0-8/16/25 | 0-2/20/40 | 4D/2D/1D stun | 325 | 2,X | nausea/disorient; useless vs sealed suits |
| Glop Grenade | Merr-Sonn | 3-7/30/60 | 0-1/3/5 | 6D/5D/3D (glop STR; opposed roll) | 275 | 2,R or X | adhesive riot foam; no damage |
| Smoke Grenade | BlasTech Nacht-5 | 3-7/20/40 | smoke 0-3 | — | 25 | 2,R,F,X | concealment / target marker |
| Incendiary Grenade | Greff-Timms 0033X | 3-7/20/40 | 0-2/4/6/10 | 4D/3D/2D/1D | 300 | 1,R | *Old-Republic jump-trooper issue → era-friendly* |
| Electronet Grenade | Golon Arms RGL-80 | 10-250/350/500 | — | 1D–10D variable (stun/normal) | 2,000 (mag) | 2,F | wire-guided net; fired from grenade launcher |

### 2.6 Missiles, mines, explosives & demolitions (Ch. 5)

| Item | Model / maker | Skill | Range/Blast | Damage | Cost | Avail | Notes |
|---|---|---|---|---|---|---|---|
| Anti-Armor Missile | Kessler J8Q-128 "Finbat" | missile weapons | 0-50/250/500 | 12D | 4,000 | R,X | Body 1D; **recast** "anti-walker"→ heavy anti-vehicle; interception rules |
| Surface-to-Air Missile | Golog-Bertum Apex Incisor | missile weapons | 0-50/250/1000 | 7D | 1,000 | 2,X | FC 3D; record-arm homing; flee or 3D exhaust |
| E-Mag Mine | Mesonics | demolitions | — | 7D | 200 | 2,R,X | anti-repulsorlift (≤25m alt); sensor 6D; foot-traffic option |
| Detonite Tape | Merr-Sonn Flex-5 | demolition | 0-0.5m | 3D | 1,500/5m | X | seam/hatch breaching |
| Shaped Charge | Merr-Sonn Pre-Shaped | demolitions | — | 2D/charge (+2D on success) | 200 | 2,R | cheap; stack for effect |
| Shaped Charge (focal) | Mesonics Focalized | demolition | — | 10D | 2,500–3,000 | 2,R or X | reduces target STR by -1D |
| Thermite Gel | Gatrellis Plasticene Cube | demolitions | — | 20D/kg/rd (2D/100g/rd) | 1,000/kg | 2,X | 500 °C; lock/armor breaching; demolitions roll by target |
| **Lowickan Firegems** | (natural) | demolitions: Firegems | 300m radius | 8D | 45,000 ea | X | radioactive (1D/hr unshielded); **detonates in hyperdrive reactor** — see call-out |

**Call-out — Lowickan Firegems are a ready sabotage/smuggling plot device.** A radiation-shielded
gem smuggled past port scanners that detonates the *first time the target ship jumps to hyperspace*
is a turnkey assassination/sabotage hook for the Hutt-cartel and crime/espionage lanes. Strip the
Imperial-Intelligence/Star-Destroyer framing → recast as a **cartel sabotage tool** (the book even
hands you the "Hutt used them to wipe out competitors" angle, which is exactly on-faction for us).
Keep the Kessel/Pa'Lowick geography; it's era-flexible.

---

## 3. Armor

### 3.1 Light & medium body armor / vests (Ch. 6)

| Item | Model / maker | Cost | Avail | Protection (phys / energy) | Coverage / penalty | Notes |
|---|---|---|---|---|---|---|
| Concussion Helmet | Core World Arms CT3 | 375 | 1 | +2 phys (incl crash/fall), 0 energy | head | cheap antique |
| Concussion Vest | Core World Arms CV14-B | 500 | 1 | +1D phys (incl crash/fall), 0 energy | torso | pairs w/ CT3 |
| Koromondain Vest | Mk 45 PDS | 250 | 1 | +1D+2 phys / +2 energy | torso | worn under other armor |
| Link Armor | ProTech SupraLink | 500 | 1 | +1D phys / +2 energy; -1D Dex | full | *"Jedi Knights wore it centuries ago" — era-flavored*; double-suit mod → +1D+2/+1D, -2D Dex |
| Castaan Staad | (Twi'lek) | 750 | 3 | +1D / +1D | torso | thin, flexible |
| Camo Armor | Creshaldyne Scout | 1,500 | 2 | +1D phys / +2 energy | torso/arms/legs | holo camo +1D to spot if motionless |
| Riot Armor | Creshaldyne (mod.) | 500 | 2 | +2D phys / +1D energy | torso+legs | IR motion alarm 30m |
| Blast Vest | Corondexx | 3,000 (cells 25) | 2 | +2 phys / +1D energy | torso | ablative; power-hungry |
| Reflec Body Glove | Syncronics ENVC-370 | 4,000 | 3,X | +1D STR vs blaster at med/long only | full (disposable) | absorbs 5 blasts |
| Smasher | Locris (mod.) | 1,250 | 3 | +1D / +1D | + servo +2D brawl/climb/lift/STR-dmg | melee/brawl build |
| Flex-Armor | Drolan Plasteel TY1 | 2,000 | 3 | +1D / +1D; -1D Dex | full | *Old-Republic/Sith-War design*; reinforce → +2D phys, no energy |
| Coynite Battle Armor | Ekkar Arms | 150 | 3 | +2D / +2D; -1D Dex | full | plant-fibre; off-world fakes are inferior |
| Corellian 611 | — | 5,000 | 3,F | +2D phys / +1D energy; no Dex pen. | head+torso | +1D swim difficulty |
| Corellian HuntSuit | — | 2,900 | 3,R | +2D phys / +1D energy; -1D Dex | full | +1D lift; sensor +1D search 50m |
| Stalker Armor | Salus Corp | 8,000 | 3,R | +2D / +2D; -2D Dex | full | tangier gun 4D stun, duo-flechette 5D, blade STR+2D, sensors +1D |
| Dura-Armor | Core World Arms | 8,000 | 3 | +2D / +2D; -2D Dex & Perc | full | *Old-Republic vehicle-crew armor* |
| Ubese Raider | (stock) | 1,000 | 3 | +2D phys / +1D energy; no Dex pen. | torso+head | Type-II enviro filter; flash-guard visor (nullifies visual stun) |
| Arelik Armor | (stock) | n/a | 4,X | +2D phys / +1D energy; -1D Dex | head/torso/arms | bounty-hunter armor; sensor/IR/filter |
| A3AA Defense Module | Corellian Tech | 8,500 | 4,X | +2D phys / +1D energy; -1D Dex | + dispersal cloud -2D vs blaster (Ammo 3) | **recast**: drop "Imperial scouts / Cracken" framing |
| Gladiator Armor | Min-Dal JX4 prototype | n/a | 4,X | +2D phys / +1D energy; no Dex pen. | head/torso/arms | net gun 5D, vibro-shiv STR+1D, jet pack (100/70, 10 chg) |
| Doubler Suit | Corellidyne (mod.) | 30,000 | 4,X | — (holo decoy) | computer prog/repair to run | projects a lifelike holo double ≤10m |

### 3.2 Powered & space armor (Ch. 6)

| Item | Model / maker | Skill | Cost | Avail | Phys / energy | Speed / Dex | Mounts & notes |
|---|---|---|---|---|---|---|---|
| Nova-Tech Powersuit | — | powersuit op | 1,000 | 2 | +3D / +2D | maneuver 1D, space 1 | blaster cannon FC 1D, 5D; cheap, popular |
| Heavy Radiation Powersuit | Nova-Tech HR-211 | powersuit op | 3,000 | 2 | +2D / +2D; -1D Dex | Move 3 | 1hr rad/heat, 6hr power, 12hr O₂; fusion cutter 5D |
| Vagabond Suit | (custom) | powersuit op | 2,500 | 3 | +2D phys | booster space 1 | scout scanner array (+2D sensors/comms solo); deep-space recon |
| Merr-Sonn Spacesuit | "Superior" Boarding | — | 10,000 | 2,X | +1D phys / +2D energy; -1D Dex | rocket pack space 1 | 25hr atmosphere; full life support |
| Wrokix Spacesuit | Deluxe Boarding | — | 8,500 | 2 | +2D phys / +1D energy; -1D Dex | gyro +1D Dex zero-g | 5hr life support |
| Malgon Armor | X5 (mod.) | powersuit op | n/a | 4,X | +2D / +2D; -2D Dex | — | +1D STR lift; flame projectors 5D ×2; recast: drop "Imperial recall/ISB" |
| Dragon Armor | SoroSuub NLZ5-11 | powersuit op | n/a | 4,X | +3D phys / +2D energy; -2D Dex | Speed 7 | sensors +2D, MFTAS +1D; def. blaster 3D, twin flamers 5D, mini-missile 5D, sealed 2hr O₂ |
| Nemesis Armor | Mili-Corp DZ 17X | powersuit op | n/a | 4,X | +3D phys / +2D energy; -2D Dex | Speed 7 | *Old-Republic corporate-militia armor*; DEMP gun 3D ion, light repeating blaster 6D, MFTAS |
| Juggernaut Armor | Cozzell 510 | powersuit op | n/a | 4,X | +3D / +3D; -3D Dex | Speed 5 | med. repeating blaster 7D, grenade launcher 5D, claws STR+2D |
| Sunder 9 (prototype) | Llalik Designs | powersuit op | n/a | 4,X | +3D phys / +2D energy; -1D+2 Dex | — | blaster cannon 6D, flame proj. 5D, rocket pack (90/50, 12 chg), sonar/IR, aquatic +2D swim |
| Leviathan Armor | Mon Calamari | powersuit op | n/a | 4,X | +3D / +3D; -1D Dex water/-3D land | swim 15 | duo-flechette 5D, mini-torpedo 6D, sonar; **recast** aquatic assault armor (drop anti-Imperial framing) |

### 3.3 Armor attachments (Ch. 6)

| Item | Model / maker | Skill | Cost | Avail | Range | Damage / effect |
|---|---|---|---|---|---|---|
| Antipersonnel Net Gun | Conner APNG3 | missile weapons | 750 | 2,R or X | 3-10/19/25 | 5D stun + 5D electrical; opposed STR to escape |
| Mini-Missile Launcher | SoroSuub Firestorm-1 | missile weapons | 1,500 | 3,R or X | 3-40/120/400 | 5D/4D/3D/2D; blast 0-2/8/12/20 |
| Mini-Torpedo Launcher | Mon Cal Defenses | missile weapons | 1,250 | 3,X | 3-30/120/350 | 6D; aquatic heavy-armor only |
| Wrist Lasers | Koromondain RLW-77 | blaster: wrist laser | 2,000/1,200 | 2,F | 0-2 | 4D; overload (15s) 8D/5D/3D, blast 1-2/4/6 |
| Electric Field | Corellian "Big Shock" | — | 1,600 | 3,X | touch | 3D shock lacing (shock-glove variant 1D, 500cr); powered armor only |
| Motion Sensor Array | Neuro-Saav MacroMotion | — | 40 | 3 | 50m | +1D search vs motion |

---

## 4. Field & utility gear

### 4.1 Conveyances (Ch. 7)

| Item | Model / maker | Skill | Cost | Avail | Move | Notes |
|---|---|---|---|---|---|---|
| Combat Paraglider | Nen-Carvon R-19 (mod.) | repulsorlift op | 1,900 (b.mkt) | 2,X | 90 (260 kmh) | Maneuver 3D; Body 2D; reflec panels +1 diff to detect; night/terrain/directional modes; **recast** covert-insertion glider |
| HHS Thruster Pack | Greshnohr DRPV-78 | rocket pack op | 600 | 2,R | hover 15 | 12 bursts (500m/300m); hover 10 min max |
| Zim Rocket Pack | "ROCKET" | rocket pack op | 750 | 2,3 | 120m h/40m v | 10 charges; *Old-Republic rocket-jumper kit → era-friendly* |

### 4.2 Restraints & capture (Ch. 8) — feeds Bounty Hunter Guild + Hutt cartel

| Item | Model / maker | Skill | Cost | Avail | Strength / effect | Notes |
|---|---|---|---|---|---|---|
| Biodegradable Binders | TaggeCo | — | 75 | 2,R | STR 6D | dissolve in 36 hr |
| Stun Cuffs | BlasTech AR-101 | — | 100 | 2,F | stun = victim's STR if struggling | standard |
| Magnacuffs | Loris MC1-100 | — | 75 | 2,F | STR 6D+2 | fingerprint-locked, no keys |
| Magnaharness | Loris MC1-200 | — | 200 | 2,F | STR 8D | full-body restraint |
| Force Cage | Damorind S-3 | security (assemble) | 7,000 | 3 | STR 7D; shock 1D-7D | 5-min assembly |
| Restraint Capsule | Damorind RPC-12 | security | 10,700 | 3,F | STR 7D; shock 1D-7D | shipboard, low power draw |
| Man Trap | Ubrikkian R-TechApp | — | 8,000 | 3,F | gravity STR 5D-15D (variable) | hidden grav-plate; hide vs Perception |
| Tangier Gun | Salus Tangier Elite I | missile weapons | 900 | 3 | 2D impact + 4D stun | spinning weighted wire |
| Slaver Snare Gun | Thalassian Corodex | missile: snare gun | 1,200 (b.mkt) | 3,F or X | 2D stun; STR 3D +1D/rd | **slaver gear** (keep illegal) |
| Stokhli Spray Sticks | (Stokhli) | blaster: spray stick | 14,000 | R | 6D stun; STR 6D entangle | canon long-range capture weapon |
| Slave Collars + Director | (custom) | — | 10,000 (1+10) | 3,R,X | 2D-5D, kill 8D | **slaver gear**; drop "Empire-endorsed" line |
| ~~Universal Energy Cage~~ | (Imperial) | — | 100,000 | X | STR ≤15D; **blocks Force ≤15D** | **HEAVY recast** — see call-out |

**Call-out — the Force-suppression cage.** The Universal Energy Cage's mechanic (a floating
confinement sphere that *dampens Force powers up to 15D*) is a compelling Jedi-capture plot device,
but its framing is explicitly the **post-Order-66 Jedi Purge** ("Great Purge," "Sovereign
Protectors," Umak Leth) — wholly anachronistic for ~20 BBY. If used at all, **recast as a rare
prototype Force-dampening containment sphere of mysterious / Separatist-experimental origin** (the
kind of thing that would terrify a Padawan), strip every Purge reference, and treat as a one-off
quest artifact rather than a vendor item. Same handling applies to the **Force Detector** (§5).

### 4.3 Tools & misc (Ch. 9)

| Item | Model / maker | Cost | Avail | Notes |
|---|---|---|---|---|
| Fibra-rope | (standard) | 10/25m | 1 | holds 750 kg |
| Spacer's Chest | SoroSuub Wanderer | 200 | 1 | 1m chest; combo-lock (Mod); vacuum-sealed; STR 6D |
| Shipsuit | Ayelic/Krongbing | 200 | 1 | multi-pocket coverall; doubles as vacsuit liner |
| Organic Gill | Mon Calamari | 200 | 3 | breathe underwater (Sullustans allergic) |

### 4.4 Survival equipment (Ch. 10) — feeds wilderness / scout / encounter (G24)

| Item | Model / maker | Skill | Cost | Avail | Notes |
|---|---|---|---|---|---|
| Scout's Survival Pack | (custom) | — | 900–2,000 | 2 | bundle: breath mask, comlink, datapad, fusion grapple, glowrod, hold-out (3D), macrobinoculars, medpac, vaporator, rations, recording rod, shelter, syntherope, thermal flare |
| Animal Excluder | Merr-Sonn | — | 350 | 2,F or R | 3 settings (2D/4D/6D), spheres 10/20/40m; willpower vs setting to approach — *direct wilderness-encounter hook* |
| Anti-Insect Canister | Barkhesh Culture | — | 275 | 3 | covers 3 humans / small camp; 1-mo shelf |
| Automap | SoroSuub "Tracker" GPS | computer prog/repair | 2,000 | 2 | near-impossible to get lost when linked; Mod roll/hr |
| Medkit | BioTech | first aid, medicine | 1,200 (2,200 b.mkt) | 2 | medpac ×10; enables field surgery |
| Med-aid | Jassim QuickMed | — | 250 | 1 | +1D first aid, single use |
| Luma Flares | Salamini Model-3287 | — | 100 | 2 | 300m illumination 3 min; 4D burn ≤20m; blind ≤50m |
| Line Master TLG | (TLG) | missile weapons | 800 | 2,R | 100m cord, holds 200 kg |
| Verti-Go Line Thrower | Susuax | missile weapons | 400 | 2 | 150m cord; ascent motor 6/12 m/s |
| Gyro-Grappler | (standard) | — | 15 | 1 | +1D climbing; throw 120m; *Republic-military issue* |
| Dehydrated Food Pack | (standard) | — | 2 | 1 | one meal |

---

## 5. Espionage, security & sensor toolkit (Ch. 12–16) — feeds Espionage (G22) + Security Zones (G04)

This is the chunk that most directly arms the **espionage and security-zone** lanes. It's a
coherent spy-and-counter-spy kit: detectors on one side, defeat-devices on the other.

### 5.1 Comms, recording & imaging (Ch. 12)

| Item | Model / maker | Skill | Cost | Avail | Effect |
|---|---|---|---|---|---|
| Electronic Blaster Sight | SoroSuub True-Site | blaster | 500 | 2,R | +1D blaster |
| Holorecording Macrobinoculars | Neuro-Saav TT4 | search | 2,000 | 2* | +2D search >100m; records 3hr — *holo-record combo is NR-era; keep plain macrobinoculars, treat the recorder as cutting-edge or cut* |
| Hover-Cam | Data-Link DLI-250 | — | 900 | 2,F | repulsor recorder; follows voice; surveillance build (slice → recon drone) |
| Infra-Goggles | Drolan Plasteel | — | 300 | 2 | -2D darkness penalty; blinded by sudden light (Diff willpower) |
| Snooper Goggles | (night macrobinoculars) | search | 300 | 2,R | +2D search low-light; flash-vulnerable w/o photo-reducers |
| Wide-scan Binocs | Jassim VX3 | — | 100 | 1 | +1D search >20m; no power cell |
| Jammer Pack | M39 ComTech (mod.) | communications | 1,050 | X* | high-gain static, kills comlinks ≤150m; Diff roll to crash a whole network — **recast** generic covert-ops jammer |
| PTP Link | (point-to-point) | — | 150 | 2 | 25km audio; encrypted models 1,000cr; *Old-Republic Core-World relay tech → era-friendly* |

### 5.2 Computer equipment (Ch. 13)

| Item | Model / maker | Skill | Cost | Avail | Effect |
|---|---|---|---|---|---|
| Datapad | (various) | computer prog/repair | 25+ | 1 | the standard portable workstation |
| TerexComm DataSearch 9C | Deluxe | computer prog/repair | 600 | 2 | +1D+2 computer / +2D security for info search |
| TerexComm DataSearch 12C-A | Executive | computer prog/repair | 850 | 2 | +2D computer for info search (faster) |
| UniTech "Patch" | Diverter | computer prog/repair | 5,200 | 2,R (gov) | +1D+2 security; masks a breach (or fakes alarms for diversions) |
| Master Command Unit | Authority | — | 100,000 | 4,X | slave-controls ≤25 systems within 300m; *Corporate-Sector tech, era-flexible*; drop "Gundark" byline |

### 5.3 Security & infiltration devices (Ch. 14)

| Item | Model / maker | Skill | Cost | Avail | Effect |
|---|---|---|---|---|---|
| Fusion Cutter | Borallis PCW-880 | technical | 150 | 1 | 3D; breach airlocks/hulls |
| Portable Plasma Cutter | (hand-held) | melee combat (as weapon) | 150 | 1 | 7D; cuts durasteel; 1 rd/1D body for a 2×1m hole |
| Code Slicer | Ouwani UniSlice | security | 2,000 | 3 | +1D security; 5–8 min; *Old-Republic-era lock-breaker* |
| AccuTronics Encryption Pkg | la.44.87 | computer prog/repair | 500 | 2 | +5 to a data file's difficulty to find/crack |
| Disruption Bubble Generator | Bakuran | — | 150,000 | X | 2m sonic-dead bubble; rare, fragile (STR 1D) |
| Voice Box | BothiCorp Duplicator | security | 5,000 | X | defeats voiceprint locks; comm voice-disguise |
| Shipjacking Kit | (individual) | security | 8,000 / 16,000+ | 4,F or X | +3D security vs a ship's systems |
| Master Coder Chip | (illegal) | security | 340,000 | X | +2D security; overrides computerized security; anti-droid systems detect it |
| Electronic Lock Breaker | Outlaw Tech | security + computer | 25,000 (+1,000/profile) | X* | defeats gene-scan locks — *NR-era device; recast generic high-end breaker* |
| ~~Alliance Comms Encrypter~~ | (ACE) | communications | n/a | 4 | **recast/cut** — generic encrypter, +2D comms |

### 5.4 Scanners & detection (Ch. 15)

| Item | Model / maker | Cost | Avail | Effect |
|---|---|---|---|---|
| BlasTech Sniffer | Weapon Detector | 5,600 | 2,R (gov) | search 5D for hidden energy weapons (portable) |
| CorSec Autoscan | Weapons Detector | 7,200 | 2,R (gov) | search 6D, **stationary** — *CorSec is era-flexible*; the port/checkpoint scanner |
| Search-Scan 4 | BlasTech | 9,800 | 2,R (gov) | +1D sensors; finds compartments, weapons, lifeforms, energy in an area |
| Bioscan | Athakam/RMSA | 13,000 | 3,F | +2D first aid/medicine; covertly detects hidden weapons/devices (3m) |
| Lifeform Scanner | Cryoncorp Lifedetec | 2,800 | 2 | detects/pinpoints lifeforms (500/1.5km) |
| Energy Scanner | Fabritech 9000 | 5,600 | 2 | detects energy emissions (500/1/2) |
| Geological Scanner | Fabritech 7000 | 4,800 | 2 | ore/mineral/geo survey (500/1/2km) — *prospecting hook* |
| Medisensor | BioTech RFX/K | 5,000 | 2 | +2D first aid (linked to medbay) / +1D standalone |
| Medscanner | Cryoncorp Mediscan 21 | 3,000 | 2 | +1D first aid; diagnose by wound level |
| Tech Scanner | DreverCorp Techaide | 2,600 | 2 | +1D repair |
| ~~Force Detector~~ | (Imperial) | n/a | 4,X | tells if a subject is Force-sensitive + has Dark Side Points — **HEAVY recast**, see below |

**Call-out — the Force Detector.** Mechanic (a device that reads whether a subject is
Force-sensitive and dark-side-tainted) is a strong Clone-Wars plot item, but the framing is the
Jedi Purge plus a direct **Luke** reference. **Cut the framing entirely**; if used, recast as a
rare **Separatist / black-market prototype "Force-aura analyzer"** — the kind of contraband that a
Jedi PC would very much want kept off the market. Quest artifact, not a vendor good. (Pairs with
the Force-suppression cage, §4.2, as a matched "anti-Jedi tech" pair for a high-stakes plot.)

### 5.5 Specialty equipment (Ch. 16)

| Item | Model / maker | Skill | Cost | Avail | Effect |
|---|---|---|---|---|---|
| Camo-Netting | Fabritech CN-15 | hide | 3,500 | 2,R | +2D to detect w/ sensors >250m; 15m square (225 m²); >3 nets interfere |
| DimSim | (custom) | — | 5,000 | 4,X | holographic "darkness" mask over the face; 20 min |
| Droid Disabler | Mandroxan EDWX-843 | blaster | 10,000 | 4,X | 6D stun +1D/hit vs droids; KOs a droid |
| Fingerprint Masque | (criminal) | computer prog/repair | 15,000 | 4,X | disguises fingerprints 10–12 hr |
| Retinal Disguiser | (criminal) | medicine | 25,000 | 4,X | defeats retinal scanners |
| Tri-laser Engraver | Opirus KL-543 | forgery | 4,000 / 8,000+ | 3,F or R | currency counterfeiting (energy-hungry → detectable) |
| Myostim Unit | Traxes Couch | — | 30,000 | 3 | +1 STR/12hr (max +1D, 1 week); long-term use → -2 stat penalty / berserk risk |
| **Malkite Poisoner's Kit** | (assassin) | — | 800,000 | 4,X | untraceable h'gartha neurotoxin (contact-kill, only bacta stops it) + 4 sensor-defeating modules — *premier assassin tool; Outer-Rim Malkite Ring is era-flexible* |

---

## 6. Entertainment & leisure (Ch. 11) — feeds Sabacc/Entertainer (G23) + cantina/ship-lounge color

| Item | Model / maker | Skill | Cost | Avail | Notes |
|---|---|---|---|---|---|
| B'shingh | Dakerno Holo Game | alien species, tactics | 500 | 3 | holo war boardgame; niche, intellectual/military |
| Kloo Horn | Gonidor (hand-made) | musical instrument: Kloo horn | 2,000 | 3 | **canon cantina instrument**; tenor lead for jizz/jatz |
| Chidinkalu | Gonidor (hand-made) | musical instrument: chidinkalu | 2,500 | 3 | Bith low-register jatz rhythm; non-portable |
| Synth-Harmonica | Mikar (amplified) | musical instrument: synth-harmonica | 500 | 2 | 10 pre-recorded songs for the non-musical |

The intro to this chapter is itself a usable design note: a good **entertainment locker** is what
keeps a smuggler/pirate crew "loose and ready for trouble" on long hauls — a nice in-fiction
justification for ship-lounge furnishings and for the Entertainer role's value aboard player ships.

---

## 7. Build hooks

**7.1 Crafting (G07) — the primary feed.** Every block above is a craftable-item candidate. The
catalog roughly triples the gear vocabulary beyond the R&E core: it adds whole *families* the core
is thin on — **stun/non-lethal melee** (cloak, gauntlets, baton, taser staff, contact stunner),
**capture weapons** (net gun, tangier, snare, Stokhli, electronet), **archaic/sensor-evading
ballistics** (slugthrower, black-powder, dart shooter, flechette), **flame & sonic**, **disruptors**,
**area/deck weapons**, **demolitions** (tape, shaped charges, thermite gel, mines), **powered armor**
(7 suits), and a deep **spy/security toolkit**. Each carries Cost + Availability, which already
encode a crafting-tier/market-gate hint (1 = trivially craftable/buyable → 4,X = master-tier,
contraband). The follow-on crafting-integration drop (deferred per the session plan) would map each
item to G07 recipe tiers and required skills; this doc is the catalog it draws from.

**7.2 Economy (G06) gating.** The `Availability` code is a ready legality/scarcity axis:
`1`→general vendors, `2/F`→licensed vendors, `3`→specialist/faction vendors, `4/R/X`→black-market
only. This dovetails with the Security-Zone legality model (§7.3) and with bulk-premium pricing
(`volume_premium()`): contraband (X) should carry the steepest black-market markup. The book's own
"a blaster sells for up to five times retail on the black market" line is a fair anchor for X-tier
pricing.

**7.3 Security Zones (G04) / scan model.** This chapter is a self-contained **detection vs.
defeat** system, and it maps onto the security-zone scan exactly:
- **Detectors** (zone-side): BlasTech Sniffer (5D), CorSec Autoscan (6D, the fixed checkpoint
  scanner), Search-Scan 4, Bioscan — these define a zone's "weapon-scan" rating.
- **Defeat devices** (player-side): hide-bonus weapons (contact stunner +2D, micro blaster
  V.Diff-to-find), DimSim/Fingerprint Masque/Retinal Disguiser/Voice Box (identity defeat),
  master coder chip / lock breaker / code slicer (lock defeat), camo-netting (sensor defeat).
A clean opposed-roll loop: smuggler's `hide`/concealment vs. the zone's scanner `search`. The
slugthrower/black-powder "beats energy scanners" line is a built-in counter to energy-only zones.

**7.4 Ground combat (G03).** Weapons §2 drop straight into the combat resolver — same skills, same
damage grammar the engine already consumes. Notable additions worth a combat-flavor pass: **area
weapons** (deck-clearer/sweeper, sound rifle, pulse rifle — 45° arc or cone, with the no-dodge /
-1D dodge band), **two-setting stun weapons** (relevant to the Drop D stun-KO design — these are
the in-world sources of stun damage), and **anti-droid** (droid disabler, DEMP/ion mounts).

**7.5 Espionage (G22).** §5 is effectively a turnkey spy loadout: surveillance (hover-cam, snooper
goggles, bioscan), counter-surveillance (disruption bubble, jammer pack), infiltration (lock
breaker, master coder chip, voice box, shipjacking kit, fingerprint/retinal disguise), and the
**Malkite Poisoner's Kit** as a premier assassination tool. The book's intro tradecraft
(background checks, alias strings, dead-drop contact protocols) is good mission-flavor text.

**7.6 Wilderness / encounters (G24).** §4.4 hands the scout/wilderness lane a ready kit: the
**Animal Excluder** is a direct encounter mechanic (ward off a beast: willpower vs. excluder
setting — pairs perfectly with the Creatures-of-the-Galaxy roster), the **Scout's Survival Pack**
is a single buyable bundle, and the **Geological Scanner** is a prospecting/harvest hook for the
contestable-wilderness resource nodes.

**7.7 Bounty Hunter Guild + Hutt cartel (factions).** §4.2 restraints are the Bounty-Hunter-Guild
signature kit (force cage, magnacuffs, man trap, restraint capsule, tangier/snare/Stokhli capture
weapons). The **slaver gear** (neuronic whip, slave collars, snare gun) is era-appropriate
Hutt-cartel contraband — keep it illegal and faction-gated, not on general vendors.

**7.8 Entertainer (G23).** §6 instruments + the entertainment-locker concept feed the Entertainer
role and cantina/ship-lounge ambience; the **Kloo Horn** is the canon cantina-band touchstone.

---

## 8. Era-translation cheat-sheet

**Blanket rule:** strip every Empire / Rebel Alliance / Imperial / New Republic / NRI / NRSF /
stormtrooper / Espo-as-Imperial / TIE / X-wing / Death Star / Palpatine / Luke / Battle-of-Endor /
Battle-of-Hoth / Battle-of-Yavin reference from any seeded string (B3 era-cleanness). The gear and
its stats are unchanged. The **entire bylined-commentary layer is dropped** (it's the densest
source of off-era references). Notable per-item handling:

| Book framing (NR / Imperial era) | SW_MUSH handling (~20 BBY) |
|---|---|
| The whole "Gundark's Gear Datalog" wrapper; CorSec→NRSF interdiction memo; "Division Three" (D-3); Emperor Palpatine's anti-contraband decree | Recast as a **Clone-Wars Hutt-cartel / Outer-Rim black-market datalog**; the foil is CorSec / Republic Judicial / planetary security. Keep the smuggling/anonymity/HoloNet-contact tradecraft. |
| In-character bylines (Gundark, Lowwel, Dr. Itlar, Capt. Rislar, Gunman, "Credman," etc.) | Drop entirely, or genericize to unsigned "field notes." Several reference the Rebellion/Empire directly. |
| **Universal Energy Cage** — "Great Purge of the Jedi," "Sovereign Protectors," Umak Leth | **Recast** as a rare prototype **Force-dampening containment sphere** (mysterious/Separatist origin); quest artifact, not a vendor item. Keep stats (STR ≤15D, Force-block ≤15D). |
| **Force Detector** — "Emperor's hunter teams," the great purge, **Luke** "resolves to use them for good" | **Cut framing**; recast as a rare **Separatist/black-market "Force-aura analyzer" prototype**. Quest artifact. |
| Imperial-Munitions blasters: **KK-5, SC-4, IM Heavy Pistol, StarAnvil** | **Drop** (off-era brand + DL-18/DL-44/rifle clones). Reusable mechanic: SC-4's traceable codes + self-destruct grip → recast as a **"tracked corporate-security sidearm"** hook. |
| **A3AA Module** "pirated from Rebel General Airen Cracken's field manual"; "Imperial scouts/covert troops" | Drop Cracken/Imperial framing; keep as a rare dispersal-cloud defense module. |
| **Malgon Armor** "Imperial recall / ISB field test" | Drop; "production halted by a corporate recall; stolen suits hit the black market." |
| **Leviathan Armor** "Mon Cal commandos vs. elite Imperial aquatic units, planets sympathetic to the Alliance" | Recast as **aquatic assault armor**; keep Mon Cal craftsmanship, drop the war framing. |
| **Vibrodagger** "favorite of Imperial Storm Commandos"; **E-11 / Espo Riot Gun** stormtrooper/Espo torture framing | Drop; "favorite of pirates, infiltrators, and those who need to operate quietly"; **E-11 → generic military rifle**; "Espo" → **corporate / private security**. |
| **Finbat** "anti-AT-AT/AT-ST walker" | Recast "heavy anti-vehicle missile." |
| **PLX-4** "savant" missile (`*` NR-only; "Empire used at Qat Chrystac") | Drop the savant variant; keep dumb/GAM rockets. |
| **Lowickan Firegems** "Imperial Intelligence mines them; Star Destroyer/Customs quarantine" | Recast as **cartel sabotage contraband** (the book's own "a Hutt used them to wipe out competitors" angle is on-faction). Keep Kessel/Pa'Lowick geography. |
| **Jammer Pack / Lock Breaker / Holorecording Macrobinoculars** marked `*` (NR-only); "Imperial Palace on Coruscant" lock examples | Recast brand/era-neutral; **drop the holo-record combo as borderline NR-tech** (keep plain macrobinoculars). Coruscant itself is fine; drop "Imperial Palace." |
| **Master Command Unit / "Patch" / ACE / DB Generator** Corporate-Sector & Alliance framing | CSA/Bakura are era-flexible — keep as corporate/rare tech; **ACE → generic encrypter** (drop "Alliance"). |
| "Old Republic" / "Sith War" / "Jedi Knights wore link armor" framing (blast rifle, flex-armor, dura-armor, Nemesis, gyro-grappler, incendiary grenade, code slicer, quick-draw pulse-wave, Zim rocket pack, PTP link) | **Keep — these are era-friendly or pre-Republic and read as authentic antiques in our setting.** |
| Back-cover **Tapani Sector** ad; the blank order form | Publisher matter — ignore. |

---

## 9. Prune note

With this extraction in hand, **`WEG40158.pdf` (Gundark's Fantastic Technology: Personal Gear) can
be removed from the project.** The full catalog — every stat block across all 16 chapters,
normalized and era-translated, plus the build-lane mapping (crafting / economy / security-zone /
combat / espionage / wilderness / entertainer / faction kits) and the off-era strip list — is
preserved here. If you later want a specific art plate, the book is re-obtainable; the
build-relevant content you'd actually use is captured above.

**Suggested follow-up (deferred, per the session plan):** a **crafting-integration drop** that
lifts §2–§5 into the gear/crafting data (G07 recipe tiers + required skills) and wires the
`Availability` codes onto G06 market gating and the G04 security-zone scan loop (§7.2–7.3). That's
the deliberate next step that turns this reference into live content — gated behind the standard
HEAD pre-flight on the gear/crafting + economy schemas. Per the roadmap's gear lane, the natural
next *extraction* is **Fantastic Technology: Droids** (droid chassis/programs) and then the
weapons-focused **Guns and Gear** if it proves to be a distinct volume rather than a reprint of
this one.
