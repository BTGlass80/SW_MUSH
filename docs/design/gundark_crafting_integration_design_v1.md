# SW_MUSH — Gundark Gear → Crafting Integration: Implementation Plan
## Version 1.0 — June 2, 2026
## Companion to: `gundarks_personal_gear_extraction_v1.md` (the catalog this draws from)
## Scope: Turn the ~180-item WEG40158 catalog into live G07 crafting content (+ G06 economy gating, + G04 security-zone hooks), and expand the crafting system where the catalog's breadth requires it.

---

## 0. Reading this, and one hard precondition

This is an **implementation plan**, not a delivered drop. It defines: the *scope filter* (which of the
~180 items become craftable), the *output-type taxonomy* the catalog forces us to grow into, the
*deterministic rubrics* for deriving crafting difficulty and components (the book ships no crafting
data — it's not a crafting book — so these must be derived, not transcribed), the *gating model*
(trainers, faction/black-market, economy), and a *drop sequence*. It ends with a worked sample
proving the rubric end-to-end, and the decisions I need from you before Drop A.

**Hard precondition — the HEAD pre-flight is Step 0 and is non-negotiable.** This plan is grounded
in `Guide_07_Crafting.md` and `sourcebook_mining_crafting_exp_design_v1.md` (§6). Those are design
docs; they describe the *documented* shape of the crafting system, not verified HEAD state. Per the
project's chronic failure mode (phantom-delivery), **nothing below gets implemented until the live
codebase is audited with symbol-level evidence.** §1 is that audit checklist. Treat every "current
system" claim below as "documented as of Guide #7 — verify."

---

## 1. Step 0 — HEAD pre-flight audit (do this first, every claim verified)

Run against the live tree, capture symbol-level evidence, before any drop. Specifically resolve:

**1.1 Schema of record.** `view data/schematics.yaml` head + one full entry of each output_type.
Confirm the field set: `key, name, skill_required, difficulty, trainer_npc, components[]
(type/quantity/min_quality), output_type, output_key, base_cost`, and the ship extras
`stat_target/stat_boost/cargo_weight`. Confirm whether any field has been added/renamed since Guide #7.

**1.2 The `electronic` resource-type question (blocking).** Guide #7 lists `RESOURCE_TYPES =
{metal, chemical, organic, energy, composite, rare}` (6), but the two countermeasure schematics
consume **`electronic`** ("3 electronic", "4 electronic"). Grep `engine/crafting.py` for
`RESOURCE_TYPES`, `electronic`, and the survey zone-mapping. Three possible findings, each changes
the plan:
- (a) `electronic` is a real 7th type defined elsewhere → adopt it (plan assumes this is the target).
- (b) `electronic` is a silent alias/typo that `add_resource` tolerates → the countermeasure recipes
  are latently broken; **this work fixes it** by formalizing `electronic`.
- (c) `electronic` maps to `energy` by some normalizer → decide whether to keep the alias or split.

**1.3 Did the experimentation engine ship?** The April plan's Drop 2 designed `resolve_experiment()`,
`DEFAULT_EXPERIMENT_PARAMS` (with `weapon/component/consumable/survival_gear` axis blocks), and
per-schematic `experiment_params`. Grep HEAD for `resolve_experiment`, `DEFAULT_EXPERIMENT_PARAMS`,
`experiment_params`, `experiment_count`. **If present**, we extend its category table; **if absent**,
we do NOT block on it — new schematics ship without experiment axes and gain them when/if that engine
lands (the `experiment_params` block is optional in the schema).

**1.4 Output-type enum + stat mapping.** Confirm the accepted `output_type` values and how
`quality_to_stats()` / `resolve_craft()` turn `output_key` + quality into a usable item. Critically:
does the pipeline handle **non-weapon, non-consumable, non-component** outputs today, or does adding
`armor` / `explosive` / `gear` require new mapping branches? (Almost certainly the latter — see §3.)

**1.5 Output item tables.** `data/weapons.yaml` (~279 lines) holds weapon outputs. Find the analogous
tables for consumables, components, and (if they exist) armor/gear/explosives — or confirm they don't
exist yet. Every schematic's `output_key` must resolve to a real item row; a dangling key is the
single most likely silent break.

**1.6 Skill names.** Confirm exactly which `skill_required` strings the crafting path accepts
(`Blaster Repair`, `ST Repair`, `Weapon Repair`, `Comp Prog`, `First Aid`, `Medicine`, and oddly
`Melee Combat` for vibroblades). The new categories need skills for **armor, demolitions/explosives,
and security/electronics** — verify whether `Armor Repair`, `Demolitions`, `Security` are valid R&E
skills already wired into `skill_checks.py`, or whether we reuse existing ones.

**1.7 Trainer binding + NPC seeding.** Confirm `trainer_npc` is bound by **slug, not DB id** (per the
DB-ID-vs-slug discipline), and inventory which trainers actually exist seeded (Kayson, Heist, Venn
Kator, Renna Dox). "Handler NPC seeding" is already a known residual deferred item — this work will
need new trainers, so confirm the seeding path.

**1.8 Era-cleanness gate.** Confirm the B3 era-cleanness static test exists and what it greps, so new
schematic names/descriptions pass it (no Empire/Imperial/stormtrooper/etc. — apply §8 of the
extraction doc).

> **Output of Step 0:** a short "HEAD findings" note that either confirms the assumptions below or
> amends them. The decisions in §9 partly depend on findings 1.2, 1.3, and 1.4.

---

## 2. Scope filter — which of the ~180 items become craftable

**Not all 180 should be schematics.** Three things disqualify an item; everything else is a candidate.

**2.1 Disqualifier — "not a crafted thing."** Vendor/found goods that nobody "crafts" in the SWG
sense: datapads, dehydrated food packs, fibra-rope, spacer's chest, shipsuit, PTP link, scout's
survival pack (it's a *bundle* of other items). → **Vendor/loot items** (already captured in the
extraction doc's catalog); no schematic.

**2.2 Disqualifier — prototype / unique / story-locked.** Items the book itself states are one-off
prototypes or recast to quest artifacts: Predator rifle (3 prototypes), Sunder 9, the recast
Force-suppression cage and Force-aura analyzer, Universal Energy Cage, Master Command Unit,
Disruption Bubble Generator (rare antique). → **Loot/quest artifacts**, not craftable.

**2.3 Disqualifier — dropped on era grounds.** The four Imperial-Munitions blaster clones (KK-5, SC-4,
IM Heavy, StarAnvil) and the "savant" missile — already cut in the extraction doc. Not in scope.

**2.4 Availability code = the master gate for the rest.** Of the survivors, the book's `Availability`
code sorts them into craftability bands. This is the single cleanest signal and it also feeds the
economy/trainer gating (§6):

| Avail | Craftable? | Tier | Trainer / where learned | Min-quality mats |
|---|---|---|---|---|
| `1`, `1,F` | Yes | Common | Open — lawful trainers, taught freely | 25 |
| `2`, `2,F`, `2,R` | Yes | Standard | Licensed/specialist trainers; `R` flags restricted | 40 |
| `3`, `3,F`, `3,R` | Yes | Advanced | Specialist/faction trainers; often gated | 55 |
| `4`, `R,X`, `X` | **Outlaw-tech only** | Master/contraband | Black-market / faction-gated / quest-learned schematics, **never** lawful trainers | 70 |

So the craftable set is roughly **the Avail 1–3 items plus a curated handful of Avail 4/X
"outlaw-tech" schematics** (disruptors, hold-out blasters, slaver gear, the spy-defeat devices) that
the crime/espionage lanes *want* craftable but only via black-market channels. Estimated craftable
total: **~70–90 schematics** (vs. the current 20), which is why this is genuinely a *crafting
expansion*, not just a content dump.

---

## 3. Output-type taxonomy — what the catalog forces us to grow

Current/ designed output_types: **weapon, consumable, component, (survival_gear)**. The catalog adds
whole families that don't fit those. Proposed expanded set (each needs a `quality_to_stats` branch and,
if the experiment engine is live, a `DEFAULT_EXPERIMENT_PARAMS` block):

| output_type | Catalog source (extraction §) | Quality → what it scales | Experiment axes (if engine live) |
|---|---|---|---|
| `weapon` *(existing)* | §2.1–2.4 melee/ranged/energy/heavy | damage dice, max_condition | damage / accuracy / durability |
| `armor` **(new)** | §3.1–3.2 vests & powered suits | protection pips (phys/energy), max_condition, Dex penalty | protection / mobility(↓Dex) / durability |
| `explosive` **(new)** | §2.5–2.6 grenades/mines/demolitions | damage dice, blast radius | yield(damage) / stability(safer) / *no durability* (single-use) |
| `gear` **(new)** | §4.2–4.4, §5 restraints/tools/survival/spy | the device's bonus (search +XD, restraint STR, sensor range) + max_uses | effectiveness / durability |
| `consumable` *(existing)* | medkits/med-aids (§4.4) | potency, yield | potency / yield |
| `component` *(existing)* | — (ship parts unchanged) | stat_boost | stat_boost / weight / reliability |
| `survival_gear` *(designed)* | folds into `gear`, or keep distinct | effectiveness | effectiveness |

**Decision point (see §9):** granularity. I recommend **three new types — `armor`, `explosive`,
`gear`** — and folding the designed `survival_gear` into `gear` (survival items are just gear with an
effectiveness axis). Fewer types = less stat-mapping surface = lower risk. The alternative (a type per
sub-family: `restraint`, `sensor`, `spy_device`, …) is more expressive but multiplies the mapping
branches and test surface for little gameplay gain.

---

## 4. Resource model — formalize `electronic` as the 7th type

The catalog's espionage/security/sensor/comms segment (extraction §5) is large and is *electronics*,
not metal/energy. The codebase **already references `electronic`** in the two countermeasure recipes
(HEAD-audit item 1.2). Recommendation: **formalize `electronic` as the 7th resource type**, which (a)
resolves the latent inconsistency, (b) gives the spy/security gear a coherent primary input, and (c)
keeps the change small (add to `RESOURCE_TYPES`, give it a survey source).

**Survey sourcing for `electronic`:** city/industrial zones (Kuat yards, Coruscant levels, Nar
Shaddaa markets) — mirrors `energy`'s city bias. (Decision in §9 if you'd rather keep 6 and map
electronics → `energy` + `rare`; I think the 7th type is cleaner and the code half-expects it.)

**Resource-mix-by-category rubric** (drives the `components[]` `type` field deterministically):

| Category | Primary | Secondary | Tertiary |
|---|---|---|---|
| Melee / ballistic weapons | metal | composite | (energy if powered) |
| Blasters / energy weapons | metal | energy | composite |
| Armor (non-powered) | composite | metal | — |
| Powered armor | composite | metal + energy | rare |
| Explosives / grenades / demolitions | chemical | rare | (metal casing) |
| Mines / guided ordnance | chemical | electronic | rare |
| Sensors / comms / security / spy gear | electronic | energy | rare |
| Restraints / capture gear | metal | electronic | — |
| Medical consumables | chemical | organic | (rare for advanced) |

---

## 5. Deterministic derivation rubrics (the book has no crafting data)

The point of a rubric is that data generation is **mechanical and auditable**, not eyeballed.

### 5.1 Difficulty
Crafting difficulty is derived, then **anchored against the existing 20 schematics** so new numbers
sit on the same scale (existing anchors: Blaster Pistol 12, Hold-Out 13, Stun Pistol 15, Blaster
Rifle 16, Carbine 17, ship parts 14–20, countermeasures 22–24).

```
difficulty = BASE(by power)  +  AVAIL_MOD  +  COMPLEXITY_MOD
```
- **BASE(by power):** weapons by damage (≤3D→10, 4D→12, 5D→15, 6D→18, 7D+→20); armor by total
  protection pips (1–2→12, 3–4→15, 5–6→18, powered→+2); explosives by damage (≤4D→11, 5–6D→14,
  7D+→17); gear by `base_cost` band (≤500→10, ≤2,500→13, ≤8,000→16, >8,000→19).
- **AVAIL_MOD:** Avail 1→+0, 2→+2, 3→+4, 4/X→+6.
- **COMPLEXITY_MOD:** +2 if the item has integrated sub-systems (powered armor weapon mounts, combo
  weapons, fire-control computers), else +0.
- Clamp to a sane ceiling (~26) so even master/contraband items stay rollable.

### 5.2 Components (quantity + min_quality)
- **`type` set:** from the §4 resource-mix-by-category table.
- **`quantity`:** scales with item size/power — small/holdout 3–4 total units; standard 4–6; rifle/heavy
  6–9; powered armor 10–14. Split across the category's primary/secondary/tertiary roughly 2:1:1.
- **`min_quality`:** from the §2.4 Avail band (1→25, 2→40, 3→55, 4/X→70). This is the lever that makes
  high-tier items *demand* good surveyed materials, which is the existing quality economy's whole point.

### 5.3 base_cost
Use the book's `Cost` directly where given (it's WEG-canon and the April price-validation pass showed
our existing costs already match WEG). For "Not available for sale" items, use the book's black-market
figure if quoted, else derive from tier. Contraband (X) carries the `volume_premium()` / black-market
markup at sale (the book's own "blaster sells for up to 5× retail on the black market" anchors X-tier).

### 5.4 Output stats
`output_key` → a row in the relevant output table (weapons.yaml or new armor/explosive/gear tables),
carrying the **normalized D6 stats straight from the extraction doc** (damage, range, ammo, protection,
blast, effect). Quality tier then modifies these via the per-output-type `quality_to_stats` branch (§3).

---

## 6. Gating — trainers, factions, economy, legality

**6.1 Trainers (NPC).** New categories need teachers. Proposed mapping (new NPCs flagged):

| Category | Trainer | Status |
|---|---|---|
| New blasters/melee/heavy | **Kayson** (Weaponsmith) | existing — extend his taught list |
| Armor (non-powered) | **Armorer** | *new NPC* |
| Powered armor | **Armorer** (advanced) or faction quartermaster | *new / faction* |
| Explosives / demolitions | **outlaw-tech / demolitionist** | *new, faction-gated* |
| Sensors / comms / security / spy gear | **Slicer / Security-tech** | *new* |
| Restraints / capture gear | Bounty Hunter Guild quartermaster | *faction* |
| Survival / utility | **Field outfitter** (or Kayson) | *new / reuse* |
| Medical (medkit) | **Heist** (Clinic) | existing — extend |

Trainer placement ties into the known-deferred "handler NPC seeding" item; sequence the trainer NPCs
into Drop G (§8) and bind schematics by trainer **slug**.

**6.2 Contraband is never taught lawfully.** Avail `X`/`R` schematics (disruptors, slaver gear, lock
breakers, voice box, master coder chip, Malkite kit, neuronic whip, etc.) are **black-market / faction
/ quest-learned only** — guard this with a structural-negative test (§7): *no schematic with a
contraband flag may have a lawful trainer*. This is both flavor and a Security-Zone (G04) interaction:
crafting contraband should be a fringe/faction activity, not a Mos Eisley storefront.

**6.3 Economy (G06).** `Availability` → market tier on the buy side; `base_cost` from the book; X-tier
gets the black-market premium via `volume_premium()`. Crafting a contraband item and selling it is a
fringe-economy sink; this dovetails with the smuggling/contraband sinks already designed.

**6.4 Security Zones (G04).** This is the satisfying cross-system payoff and it needs **no new
mechanic** — the extraction §7.3 detection-vs-defeat loop maps onto the existing scan model: crafted
*detectors* (Sniffer 5D, CorSec Autoscan 6D, Search-Scan 4) raise a zone's scan rating; crafted
*defeat gear* (hide-bonus weapons, masques, lock breakers, camo-netting) feeds the smuggler's opposed
`hide`/concealment roll. Wiring this is a thin pass in Drop F/G, not a system build.

---

## 7. Testing strategy (per-drop, structural-negative)

Per the project test conventions (per-drop files; structural-negative classes that pin completeness):

- **Schema validation** — every new schematic parses; every `output_key` resolves to a real output
  row (the dangling-key guard); every `type` in `components[]` is a valid `RESOURCE_TYPES` member
  (this test is what *proves* the `electronic` fix).
- **Skill validity** — every `skill_required` is a skill `skill_checks.py` accepts.
- **Difficulty-scale sanity** — derived difficulties fall in the anchored band per tier (no Avail-1
  item harder than an Avail-3 item of the same power).
- **`TestContrabandNotLawfullyTaught`** — structural-negative: no contraband-flagged schematic has a
  lawful `trainer_npc`.
- **Era-cleanness** — all new schematic `name`/`description` strings pass the B3 grep (apply §8 of the
  extraction doc; skip the cut/recast items).
- **Round-trip craft smoke** — for a representative item per output_type: seed mats → `craft` →
  assert item produced with quality-scaled stats. Use `room_id_by_slug()` / slug lookups, never
  hardcoded DB ids. Sandbox runs only AST + the changed-module tests; you run the full ~4,854 on the
  Windows box.

---

## 8. Drop sequence (one self-contained drop per session)

Foundation first, then content by category, then gating last. Each drop = HEAD pre-flight → data +
minimal engine → AST/YAML validation → targeted sandbox regression → handoff doc.

| Drop | Title | Touches | Risk |
|---|---|---|---|
| **A** | **Foundation** | `engine/crafting.py` (formalize `electronic` in `RESOURCE_TYPES` + survey source; add `armor`/`explosive`/`gear` to output_type enum + `quality_to_stats` branches; if exp-engine live, add their `DEFAULT_EXPERIMENT_PARAMS` blocks). New empty output tables `data/armor.yaml`, `data/explosives.yaml`, `data/gear.yaml`. **No content.** | Engine-touching → highest care; smallest footprint |
| **B** | **Weapons** | `data/schematics.yaml` + `data/weapons.yaml` — the ~40 craftable weapons (§2). Extend Kayson. | Largest single content set |
| **C** | **Armor** | `data/schematics.yaml` + `data/armor.yaml` — vests → powered suits (§3). | Powered-armor weapon mounts need the COMPLEXITY_MOD path |
| **D** | **Ordnance** | `data/schematics.yaml` + `data/explosives.yaml` — grenades/mines/demolitions (§2.5–2.6). Contraband gating begins. | Single-use output stats; blast handling |
| **E** | **Field & utility gear** | `data/schematics.yaml` + `data/gear.yaml` — restraints/tools/survival (§4). | Bounty/cartel faction gating |
| **F** | **Espionage/security/sensors** | `data/schematics.yaml` + `data/gear.yaml` — the electronic-heavy spy kit (§5) + the G04 scan-loop wiring. | Electronic resource gets exercised; detector/defeat wiring |
| **G** | **Trainers + gating + economy** | Trainer NPC seeding (slug-bound), faction/black-market teaching gating, G06 cost/premium wiring, contraband test. | NPC-seeding path; ties off the loop |

Drops B–F are independent and reorderable; **A must land first** (it's the schema/resource foundation
everything else writes against) and **G last** (it gates the content A–F created).

---

## 9. Decisions needed before Drop A

These shape the foundation drop; I'd like your call (single-letter is fine):

1. **Resource model** — (a) **formalize `electronic` as the 7th resource type** *(recommended; resolves
   the latent countermeasure inconsistency)*, or (b) keep 6 and map electronics → `energy` + `rare`.
2. **Output-type granularity** — (a) **three new types: `armor`, `explosive`, `gear`** (fold
   `survival_gear` into `gear`) *(recommended; minimal mapping surface)*, or (b) finer-grained types
   per sub-family.
3. **Contraband craftability** — (a) **Avail-4/X items are outlaw-tech: craftable only via
   black-market/faction/quest-learned schematics, never lawful trainers** *(recommended)*, or (b)
   contraband is loot/buy-only and **not** craftable at all (smaller scope), or (c) fully craftable
   like everything else (not recommended — erases the fringe/legality flavor).
4. **Craftable breadth** — (a) **curated ~70–90 schematics** (Avail 1–3 + a contraband handful)
   *(recommended)*, or (b) maximalist (every non-prototype item).
5. **Worked-sample sign-off** — review §10 below; if the rubric looks right, Drop A proceeds and the
   per-category content drops mass-apply it.

---

## 10. Worked sample — rubric end-to-end (proof it scales)

Twelve items spanning every new category, derived by the §5 rubrics, era-clean, ready to become
`schematics.yaml` rows once Step 0 confirms the schema. (Stats from the extraction doc; difficulty,
components, min_quality all derived — not from the book.)

```yaml
# ── WEAPONS (output_type: weapon; trainer: kayson) ───────────────────────────
- key: heavy_blaster_pistol_t6
  name: "Heavy Blaster Pistol (Thunderer-pattern)"
  output_type: weapon
  output_key: heavy_blaster_pistol_t6      # → weapons.yaml: 6D+2, 3-7/25/50, ammo 25
  skill_required: Blaster Repair
  difficulty: 20          # BASE 6D→18  + Avail(2,R)→+2  + complexity 0
  trainer_npc: kayson
  base_cost: 750
  components:             # blaster mix: metal / energy / composite
    - {type: metal,     quantity: 3, min_quality: 40}
    - {type: energy,    quantity: 2, min_quality: 40}
    - {type: composite, quantity: 1, min_quality: 40}

- key: vibrorapier_duelist
  name: "Vibrorapier (Duelist-pattern)"
  output_type: weapon
  output_key: vibrorapier_duelist          # → STR+3D (max 7D), silent
  skill_required: Melee Combat              # matches existing vibroblade convention (verify in 1.6)
  difficulty: 17          # BASE 5D-equiv→15 + Avail(2,R)→+2
  trainer_npc: kayson
  base_cost: 300
  components:
    - {type: metal,     quantity: 2, min_quality: 40}
    - {type: composite, quantity: 1, min_quality: 40}

# CONTRABAND weapon — outlaw-tech, NO lawful trainer
- key: disruptor_pistol
  name: "Disruptor Pistol"
  output_type: weapon
  output_key: disruptor_pistol             # → 6D+2, 0-3/5/7, banned
  skill_required: Blaster Repair
  difficulty: 24          # BASE 6D→18 + Avail(4,X)→+6 ; clamp ok
  contraband: true                          # gated; see TestContrabandNotLawfullyTaught
  trainer_npc: null                         # learned black-market/quest only
  base_cost: 3000
  components:
    - {type: metal,  quantity: 2, min_quality: 70}
    - {type: energy, quantity: 2, min_quality: 70}
    - {type: rare,   quantity: 1, min_quality: 70}

# ── ARMOR (output_type: armor; trainer: armorer [new]) ───────────────────────
- key: blast_vest_corondexx
  name: "Blast Vest (ablative)"
  output_type: armor
  output_key: blast_vest_corondexx         # → +1D energy/+2 phys, torso
  skill_required: Armor Repair              # verify exists in 1.6, else reuse
  difficulty: 14          # BASE prot 1-2 pips→12 + Avail(2)→+2
  trainer_npc: armorer
  base_cost: 3000
  components:             # non-powered armor: composite / metal
    - {type: composite, quantity: 3, min_quality: 40}
    - {type: metal,     quantity: 2, min_quality: 40}

- key: powered_armor_nemesis
  name: "Medium Powered Armor (Nemesis-pattern)"
  output_type: armor
  output_key: powered_armor_nemesis        # → +3D phys/+2D energy, mounts
  skill_required: Armor Repair
  difficulty: 26          # BASE powered→18(+2) + Avail(4,X)→+6 + complexity +2 → clamp 26
  contraband: false                          # rare but not illegal; faction quartermaster
  trainer_npc: armorer_advanced
  base_cost: 25000
  components:             # powered: composite / metal+energy / rare
    - {type: composite, quantity: 5, min_quality: 70}
    - {type: metal,     quantity: 4, min_quality: 70}
    - {type: energy,    quantity: 3, min_quality: 70}
    - {type: rare,      quantity: 2, min_quality: 70}

# ── EXPLOSIVES (output_type: explosive; trainer: demolitionist [new, gated]) ─
- key: stun_grenade_merrsonn
  name: "Stun Grenade"
  output_type: explosive
  output_key: stun_grenade_merrsonn        # → 6D/5D/3D/2D stun, blast 0-2/20/40
  skill_required: Demolitions
  difficulty: 16          # BASE 5-6D→14 + Avail(2,R)→+2
  trainer_npc: demolitionist
  base_cost: 450
  components:             # explosive: chemical / rare / metal casing
    - {type: chemical, quantity: 2, min_quality: 40}
    - {type: rare,     quantity: 1, min_quality: 40}
    - {type: metal,    quantity: 1, min_quality: 40}

- key: detonite_tape
  name: "Detonite Tape (Flex-5)"
  output_type: explosive
  output_key: detonite_tape                # → 3D, breaching
  skill_required: Demolitions
  difficulty: 17          # BASE 3D→11 + Avail(X)→+6
  contraband: true
  trainer_npc: null
  base_cost: 1500
  components:
    - {type: chemical, quantity: 3, min_quality: 70}
    - {type: rare,     quantity: 1, min_quality: 70}

# ── GEAR: restraints / sensors / security (output_type: gear) ────────────────
- key: magnacuffs
  name: "Magnacuffs"
  output_type: gear
  output_key: magnacuffs                   # → restraint STR 6D+2, fingerprint-locked
  skill_required: Security
  difficulty: 13          # BASE base_cost ≤500→10 + Avail(2,F)→+2 (+1 complexity lock)
  trainer_npc: bh_quartermaster            # Bounty Hunter Guild
  base_cost: 75
  components:             # restraint: metal / electronic
    - {type: metal,      quantity: 2, min_quality: 40}
    - {type: electronic, quantity: 1, min_quality: 40}

- key: holorecording_macrobinoculars
  name: "Macrobinoculars"
  output_type: gear
  output_key: macrobinoculars              # → +2D search >100m (drop NR-era holo-record combo)
  skill_required: Security                  # or Comp Prog — verify in 1.6
  difficulty: 13          # BASE ≤2500→13 + Avail(2)→0  (kept plain, era-clean)
  trainer_npc: security_tech
  base_cost: 2000
  components:             # sensor/comms: electronic / energy / rare
    - {type: electronic, quantity: 2, min_quality: 40}
    - {type: energy,     quantity: 1, min_quality: 40}

# CONTRABAND gear — defeat device, outlaw-tech
- key: voice_box
  name: "Voice-Pattern Duplicator"
  output_type: gear
  output_key: voice_box                    # → defeats voiceprint locks
  skill_required: Security
  difficulty: 22          # BASE ≤8000→16 + Avail(X)→+6
  contraband: true
  trainer_npc: null
  base_cost: 5000
  components:
    - {type: electronic, quantity: 3, min_quality: 70}
    - {type: rare,       quantity: 2, min_quality: 70}

# ── GEAR: survival (folds survival_gear → gear) ──────────────────────────────
- key: animal_excluder
  name: "Animal Excluder"
  output_type: gear
  output_key: animal_excluder              # → ward beast, willpower vs setting (G24 hook)
  skill_required: Security                  # electronics/field device — verify
  difficulty: 12          # BASE ≤500→10 + Avail(2,F)→+2
  trainer_npc: field_outfitter
  base_cost: 350
  components:
    - {type: electronic, quantity: 1, min_quality: 40}
    - {type: energy,     quantity: 1, min_quality: 40}

# ── CONSUMABLE (existing type; trainer: heist) ───────────────────────────────
- key: medkit_biotech
  name: "Medkit (field-surgery capable)"
  output_type: consumable
  output_key: medkit_biotech               # → medpac ×10, enables field surgery
  skill_required: Medicine
  difficulty: 16          # BASE ≤2500→13 + Avail(2)→0 (+ complexity 2: surgery suite)
  trainer_npc: heist
  base_cost: 1200
  components:             # medical: chemical / organic / rare
    - {type: chemical, quantity: 3, min_quality: 40}
    - {type: organic,  quantity: 2, min_quality: 40}
    - {type: rare,     quantity: 1, min_quality: 40}
```

If §5's rubrics produce sane, scale-consistent rows like these across categories — and the §9
decisions land — Drop A builds the foundation and Drops B–F mass-apply this exact pattern to the
curated set, with Drop G gating it.

---

## 11. What this is NOT doing (explicit non-goals)

- Not touching ship components/countermeasures content (only the `electronic`-type fix grazes them).
- Not building the experimentation engine — if it isn't live (HEAD 1.3), new schematics simply omit
  `experiment_params` and gain axes later.
- Not implementing new G04/G06 *mechanics* — only wiring the catalog onto existing scan/market models.
- Not seeding the trainer NPCs' dialogue/quest trees beyond what teaching requires (Drop G seeds the
  trainers; richer NPC content is a separate lane).
- Not claiming any current crafting-code state as fact — §1 verifies everything first.

---

*End — Gundark Gear → Crafting Integration Implementation Plan v1.0*
*Precondition: §1 HEAD pre-flight. First build: Drop A (foundation), pending §9 decisions.*
