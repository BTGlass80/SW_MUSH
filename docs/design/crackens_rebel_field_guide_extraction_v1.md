# SW_MUSH — Cracken's Rebel Field Guide Extraction
## Version 1.0 — April 14, 2026 · Opus Session 24
### Source: WEG40046 (82 pages, scanned — full text readable in context)

---

## Table of Contents

1. Book Identity & Mining Assessment
2. Jury-Rigging System — Design Integration
3. Equipment Catalog — New Craftable Items
4. Prosthetics & Cybernetics — Future System Stub
5. Vehicle Stat Blocks — Data Extraction
6. Weapon Modifications — New Schematics
7. World Lore Entries — 10 New Entries
8. Transponder Codes & BoSS — Space System Enrichment
9. Computer Data Files — Slicing System Seed
10. Implementation Plan

---

## 1. Book Identity & Mining Assessment

| Field | Value |
|-------|-------|
| WEG ID | WEG40046 |
| Title | Cracken's Rebel Field Guide |
| Author | Christopher Kubasik |
| Year | 1991 |
| Pages | 80 (82 with covers) |
| Format | Scanned pages, fully readable in context window |
| Sections | Introduction (jury-rigging, prosthetics, computers), General Cracken bio, Computers, Equipment, Jury-Rigging gadgets, Prosthetics, Vehicles, Weapons |

### Mining Value: **HIGH**

This book is a treasure trove for SW_MUSH. Unlike the narrative-heavy sourcebooks, Cracken's is almost entirely game-statted equipment with clear specifications, costs, availability codes, and skill requirements. The "datapage" format means every item has a structured stat block.

### Key Extraction Targets

| Target | Value for SW_MUSH | Priority |
|--------|-------------------|----------|
| Jury-rigging rules | Maps directly to crafting experimentation system | HIGH |
| 15+ equipment items with full specs | New schematics for crafting | HIGH |
| Transponder code mechanics | Enriches existing space/smuggling systems | HIGH |
| BoSS organization + NPC stat blocks | World lore + NPC templates | MEDIUM |
| Prosthetics/cybernetics rules | Future system (not current priority) | LOW |
| Vehicle stat blocks (5 vehicles) | Data file additions | MEDIUM |
| Blaster mechanics (how blasters work) | World lore flavor | LOW |

---

## 2. Jury-Rigging System — Experimentation Engine Refinement

### 2A. Current State vs. Design Target

The **current `ExperimentCommand`** (line 304 of `parser/crafting_commands.py`) is a flat prototype: it adds +5 difficulty to a fresh craft attempt and +20 quality on success. It consumes materials, produces a new item, and has no axis selection, no tradeoffs, and no per-item experiment tracking. It's essentially "craft but harder and better."

The **design target** from `sourcebook_mining_crafting_exp_design_v1.md` §6 is fundamentally different: you experiment **on an already-crafted item in your inventory**, choosing a stat axis to tune, with tradeoffs on opposing axes, escalating difficulty per attempt, and risk of destroying the item.

Cracken's jury-rigging rules (pp. 2–4) provide the WEG canon foundation for the full design and — critically — fill in parameter gaps the mining design left as TBD.

### 2B. WEG Canon Rules Extracted (pp. 2–4)

**Difficulty ladder:**
- +1D improvement → Moderate (≈15)
- +2D improvement → Difficult (≈20)
- +3D improvement → Very Difficult (≈25)

This maps to our `difficulty_escalation` parameter. The mining design used +3 per prior experiment. Cracken's says the jump is +5 per tier (Moderate→Difficult→VeryDifficult). **Revised recommendation: `difficulty_escalation: 5`** for weapons and components, keeping +3 for consumables/survival gear where the stakes are lower.

**Time constraint:** 1 hour standard, 1 minute if rushed (difficulty +1 level). No way to spend more time to reduce difficulty. In MUSH terms, experimentation should have a **cooldown** — you can't spam experiments. Recommendation: 1 real-time minute between experiments on the same item, matching the "rushed" option. No "take your time for easier roll" path — the difficulty is what it is.

**Retry penalty:** Failed roll → retry always takes the full hour even if you rushed. In MUSH terms: **failed experiment imposes a 5-minute lockout** on that specific item before you can try again. This prevents brute-force retries.

**Breakdown table (per category):**

| Category | Roll 1 (16.7%) | Roll 2 (16.7%) | Roll 3 (16.7%) | Roll 4-6 (50%) |
|----------|----------------|----------------|----------------|----------------|
| Lethal (weapons) | Explodes — damage = jury-rig bonus | Broken, unrepairable | Stops, slam to restart (1 action) | Fine |
| Non-Lethal (equipment) | Broken, unrepairable | Stops, slam to restart | Fine | Fine |
| Vehicles (ship components) | Full power shutdown, emergency landing needed | Bucks — Easy skill roll to maintain control | Fine | Fine |
| No-Dice (special items) | Duration-based degradation (see below) | — | — | — |

**No-Dice items** don't get bonus dice at all. Instead they have a fixed building difficulty and work for a time-limited duration before requiring another skill check. The duration depends on how much the builder beat the difficulty by:
- Below difficulty → Non-Lethal breakdown table, recheck in 1 minute
- Equals difficulty → Works for 15 minutes
- Beats by 1 level → Works for 1 hour
- Beats by 2+ levels → Works for 6 hours

### 2C. Mapping Cracken's to Experimentation Parameters

The mining design's `DEFAULT_EXPERIMENT_PARAMS` needs these refinements based on Cracken's:

**1. Difficulty escalation** — Change from +3 to +5 for weapons and components:

```python
DEFAULT_EXPERIMENT_PARAMS = {
    "weapon": {
        # ...
        "difficulty_escalation": 5,   # was 3 — Cracken's M→D→VD = +5 per tier
    },
    "component": {
        # ...
        "difficulty_escalation": 5,   # was 4
    },
    "consumable": {
        # ...
        "difficulty_escalation": 3,   # keep at 3 — lower stakes
    },
    "survival_gear": {
        # ...
        "difficulty_escalation": 4,   # was 5, soften slightly
    },
}
```

**2. Breakdown categories** — Add a `breakdown_type` field to experiment params that maps to Cracken's four categories. This determines what happens on failure/fumble:

```python
# New field in experiment_params
"breakdown_type": "lethal",    # weapons — fumble can explode
"breakdown_type": "non_lethal", # equipment — fumble breaks it
"breakdown_type": "vehicle",    # ship components — fumble = system shutdown
"breakdown_type": "no_dice",    # special items — duration-limited
```

**3. Fumble consequence granularity** — The mining design had `fumble_risk: "destroy"` as a binary. Cracken's breakdown table shows a **graduated failure**: only 16.7% chance of catastrophic destruction, 16.7% broken-but-recoverable, 16.7% temporary stop, 50% fine. Revised implementation:

```python
async def resolve_experiment_failure(item, breakdown_type, margin):
    """Called when experiment skill check fails."""
    if margin <= -5:  # fumble threshold
        roll = random.randint(1, 6)
        if breakdown_type == "lethal":
            if roll == 1:
                return "destroyed_explosion"  # item gone, 2D stun damage to crafter
            elif roll == 2:
                return "destroyed_clean"       # item gone, no damage
            elif roll == 3:
                return "jammed"                # item loses 25% durability, still usable
            else:
                return "fine"                  # close call, no effect
        elif breakdown_type == "non_lethal":
            if roll <= 1:
                return "destroyed_clean"
            elif roll == 2:
                return "jammed"
            else:
                return "fine"
        elif breakdown_type == "vehicle":
            if roll == 1:
                return "system_shutdown"       # component disabled until repaired
            elif roll == 2:
                return "degraded"              # -1D to component stat until repaired
            else:
                return "fine"
    else:
        # Regular failure (not fumble) — item quality degrades
        return "quality_loss"
```

**4. Use-time breakdown risk** — Cracken's most distinctive mechanic is that jury-rigged items risk failure **every time they're used**, not just during the experiment. The bonus dice are rolled separately, and if any shows a 1, the breakdown table fires.

For MUSH implementation, this means experimentally-enhanced weapons should have a **per-use breakdown chance**. Each experiment adds a breakdown die. If any breakdown die rolls 1 during combat use, the weapon malfunctions.

```python
# In combat.py, after damage roll for experimentally modified weapons:
experiment_count = weapon.get("experiment_count", 0)
if experiment_count > 0:
    breakdown_dice = [random.randint(1, 6) for _ in range(experiment_count)]
    if 1 in breakdown_dice:
        # Roll on breakdown table for this weapon's type
        breakdown_result = resolve_breakdown(weapon)
        # "fine" 50% of the time, "jammed" ~17%, "broken" ~17%, "exploded" ~17%
```

This is the most impactful design refinement from Cracken's. It means experimentation is genuinely risky even after success — your souped-up blaster might blow up in combat. This creates natural demand for replacement weapons (crafting sink) and makes the player choose between reliable stock gear vs. powerful-but-unreliable modded gear. Classic risk/reward.

**Economy impact:** This single mechanic creates a significant item sink. A 3-experiment weapon has ~42% chance of triggering a breakdown check per use (1 - (5/6)³), and each check has a 1-in-6 chance of permanent destruction. Over 20 combat uses, there's roughly a 75% chance the weapon eventually breaks. That's a healthy durability curve — comparable to the existing condition system but with dramatic failure modes instead of gradual degradation.

### 2D. Revised Experiment Flow (incorporating Cracken's)

1. Player crafts an item normally → item has quality score, `experiment_count: 0`, `breakdown_dice: 0`
2. `experiment <item#> <axis>` → choose stat axis to tune
3. System rolls skill check: `schematic.difficulty + 5 + (5 × prior_experiments_on_item)`
4. **Fumble (margin ≤ -5):** Roll on breakdown table per item's `breakdown_type`. 16.7–50% chance of destruction, rest of the time item survives with damage.
5. **Failure (margin < 0):** Item quality degrades by |margin| × 2. Retry locked for 5 minutes.
6. **Success (margin ≥ 0):** Boost chosen axis by `boost_per_margin × margin`. Apply tradeoff to opposing axis. `experiment_count += 1`, `breakdown_dice += 1`.
7. **Critical success (margin ≥ 10):** Double boost. No tradeoff applied. `breakdown_dice += 1` still (the improvement is still jury-rigged, just better).
8. After `max_experiments` (3 for weapons, 2 for components/consumables, 1 for survival gear), no more attempts.
9. **In combat:** After each use of a weapon with `breakdown_dice > 0`, roll that many d6. If any shows 1, roll on the breakdown table. This is the permanent risk of running modded gear.

### 2E. Specific Weapon Modifications from Cracken's

The book provides several specific weapon modifications that should become **named experimentation presets** rather than generic axis names:

| Cracken's Name | Page | Axis Mapping | Boost | Tradeoff |
|---------------|------|-------------|-------|----------|
| Upgraded Galven Pattern | 69 | `damage` | +1D/2D/3D damage | Lethal breakdown risk |
| Blaster Beam Splitter | 66 | `accuracy` | +1D blaster skill | -1D damage |
| Blaster Sight | 67 | `accuracy` | +1D blaster skill | None (Moderate build diff) |
| Blaster Hair Trigger | 70 | `rate_of_fire` | Double shots per pull | -1D per extra shot, breakdown risk |

These validate the axis names in the mining design: `damage` = Galven Pattern, `accuracy` = Beam Splitter/Sight, and suggest a potential fourth axis `rate_of_fire` for a post-launch burst-fire feature.

**Recommendation:** Use Cracken's names as the experiment axis labels for weapons to give them Star Wars flavor:

```python
"weapon": {
    "axes": [
        {"axis": "damage", "label": "Galven Pattern Upgrade",
         "boost_per_margin": 0.5, "tradeoff_axis": "durability", "tradeoff_ratio": 0.3},
        {"axis": "accuracy", "label": "Beam Calibration",
         "boost_per_margin": 0.4, "tradeoff_axis": "damage", "tradeoff_ratio": 0.2},
        {"axis": "durability", "label": "Reinforced Housing",
         "boost_per_margin": 0.6, "tradeoff_axis": None},
    ],
    "max_experiments": 3,
    "difficulty_escalation": 5,
    "breakdown_type": "lethal",
    "fumble_risk": "breakdown_table",
    "failure_risk": "quality_loss",
},
```

### 2F. Vehicle/Ship Component Modifications from Cracken's

The book's vehicle section (pp. 48–58) gives specific modification examples that map to ship component experimentation:

| Cracken's Name | Vehicle Type | Axis | Effect |
|---------------|-------------|------|--------|
| Customizing Airspeeder Control Flaps | Airspeeder | maneuverability | +1D/2D/3D maneuver, Vehicle breakdown |
| Airspeeder Afterburner Power Increase | Airspeeder | speed | +1D/2D/3D speed, Vehicle breakdown |
| Speeder Bike Maneuverability Adjustments | Speeder | maneuverability | +1D/2D/3D maneuver, Vehicle breakdown |
| Enhanced Speeder Bike Power Dispersers | Speeder | speed | +1D/2D/3D speed, Vehicle breakdown |
| Landspeeder Turbothrust Overdrive | Landspeeder | speed | +1D/2D/3D speed, Vehicle breakdown |
| Twin Fopal 888 Repulsorlift Rack | Landspeeder | maneuverability | +1D/2D/3D maneuver, Vehicle breakdown |

These all follow the same pattern: pick speed or maneuverability, get +1D/2D/3D, risk Vehicle-category breakdown. This confirms the component experimentation axis design:

```python
"component": {
    "axes": [
        {"axis": "power", "label": "Power Routing",
         "boost_per_margin": 0.3, "tradeoff_axis": "weight", "tradeoff_ratio": 0.4},
        {"axis": "weight", "label": "Mass Reduction",
         "boost_per_margin": 0.4, "tradeoff_axis": "reliability", "tradeoff_ratio": 0.3},
        {"axis": "reliability", "label": "Stress Testing",
         "boost_per_margin": 0.5, "tradeoff_axis": None},
    ],
    "max_experiments": 2,
    "difficulty_escalation": 5,
    "breakdown_type": "vehicle",
    "fumble_risk": "breakdown_table",
    "failure_risk": "quality_loss",
},
```

### 2G. Implementation Summary for Experimentation Engine

The full `ExperimentCommand` rewrite needs:

**`engine/crafting.py` changes:**
1. Add `DEFAULT_EXPERIMENT_PARAMS` dict (from §2E/2F above, plus consumable/survival defaults from mining design)
2. Add `resolve_experiment(char, item, axis)` → performs skill check, applies boost/tradeoff, updates item JSON
3. Add `resolve_breakdown(item)` → rolls on breakdown table, returns result
4. Add `get_experiment_axes(item)` → returns available axes for item based on schematic's `output_type`
5. Add experiment tracking fields to item JSON: `experiment_count`, `experiment_log`, `breakdown_dice`, `effective_stats`

**`parser/crafting_commands.py` changes:**
1. Rewrite `ExperimentCommand` to operate on inventory items (not fresh crafts)
2. `experiment list <item#>` → show axes, history, remaining attempts
3. `experiment <item#> <axis_name>` → perform experiment
4. `experiment <item#> <axis#>` → shorthand by number

**`engine/combat.py` changes:**
1. After weapon damage roll, check `breakdown_dice > 0`
2. If so, roll breakdown dice and check for 1s
3. On breakdown trigger, call `resolve_breakdown()` and apply result
4. Display dramatic breakdown messages (weapon sparks, misfires, explodes)

**`data/schematics.yaml` changes:**
1. Add `experiment_params` overrides for any schematics that need non-default tuning
2. Most schematics inherit from `DEFAULT_EXPERIMENT_PARAMS` by `output_type`

**No DB schema changes** — all experiment data lives in item JSON within the character's inventory.

---

## 3. Equipment Catalog — New Craftable Items

These items from Cracken's have clear specs and map to existing crafting categories. Each could become a new schematic.

### 3A. BioTech FastFlesh Medpac (p. 16)

| Spec | Value |
|------|-------|
| Type | Advanced Medpac |
| Skill | Medicine |
| Availability | 2 |
| Cost | 500 Credits |
| Effect | Wounded: diff 5, Incapacitated: diff 10, Mortally Wounded: diff 15 |
| Limit | Once per day (standard medpacs unlimited alongside) |

**MUSH Integration:** New schematic `medpac_fastflesh`. Strictly better than standard medpac but with once-per-day limit enforced by a cooldown timestamp on the item. Higher crafting difficulty (18) and component requirements (chemical × 3, organic × 2, min_quality 50). This creates a meaningful crafting goal beyond basic medpacs.

```yaml
- key: medpac_fastflesh
  name: "FastFlesh Medpac"
  skill_required: first_aid
  difficulty: 18
  trainer_npc: Doc Vashar  # medical trainer
  components:
    - type: chemical
      quantity: 3
      min_quality: 50
    - type: organic
      quantity: 2
      min_quality: 45
  output_type: consumable
  output_key: medpac_fastflesh
  base_cost: 500
```

### 3B. Comlink Bug (p. 28)

| Spec | Value |
|------|-------|
| Build Skill | Technology |
| Building Difficulty | Very Easy |
| Jury-Rig Type | No-Dice |
| Effect | Surveillance device. hide/sneak to place, search to find |

**MUSH Integration:** New schematic `comlink_bug`. Usable item — `plant bug` in a room, `sweep` to detect. Feeds into the security/intrusion system already built for housing. Low difficulty, low materials — a Technician profession bread-and-butter item.

```yaml
- key: comlink_bug
  name: "Comlink Bug"
  skill_required: security
  difficulty: 8
  trainer_npc: Kayson  # tech trainer
  components:
    - type: energy
      quantity: 1
      min_quality: 20
    - type: composite
      quantity: 1
      min_quality: 15
  output_type: equipment
  output_key: comlink_bug
  base_cost: 50
```

### 3C. Simple Lock Picker (p. 25)

| Spec | Value |
|------|-------|
| Build Skill | Technology |
| Use Skill | Security |
| Building Difficulty | Per jury-rigging rules |
| Jury-Rig Type | Non-Lethal |
| Effect | +1D, 2D, or 3D to security skill on Very Easy/Easy locks. Triggers alarms on harder locks. |

**MUSH Integration:** Maps to housing intrusion system. Craft a lock picker → use on locked housing doors → security skill check with bonus dice. Already have the intrusion mechanics in `engine/housing.py`. New schematic `lockpick_simple`.

```yaml
- key: lockpick_simple
  name: "Simple Lock Picker"
  skill_required: security
  difficulty: 12
  trainer_npc: Kayson
  components:
    - type: metal
      quantity: 1
      min_quality: 25
    - type: energy
      quantity: 1
      min_quality: 20
  output_type: equipment
  output_key: lockpick_simple
  base_cost: 75
```

### 3D. Lectroticker (p. 26)

| Spec | Value |
|------|-------|
| Build Skill | Technology |
| Use Skill | Security |
| Building Difficulty | Per jury-rigging rules |
| Jury-Rig Type | Non-Lethal |
| Effect | +1D, 2D, or 3D to security on card key locks. A 1 on jury-rig dice sounds alarm. |
| Components | Sense-Plate (pressure sensor), Data Compiler (life form detector) |

**MUSH Integration:** Higher-tier lockpick for card-key locked housing/faction doors. New schematic `lectroticker`.

```yaml
- key: lectroticker
  name: "Lectroticker"
  skill_required: security
  difficulty: 16
  trainer_npc: Kayson
  components:
    - type: composite
      quantity: 2
      min_quality: 40
    - type: energy
      quantity: 1
      min_quality: 35
  output_type: equipment
  output_key: lectroticker
  base_cost: 200
```

### 3E. Personal Tracking Device (p. 22)

Three tiers from Cracken's:

| Model | Range | Info Given | Cost |
|-------|-------|-----------|------|
| MechBlaze Observer | 1 km | Direction + range | 500 cr |
| Astroserver Rover | 3 km | Range, direction, speed | 1,000 cr |
| Rhinsome SureSnoop | 5 km | Exact range, direction, speed | 3,000 cr |

All use Search skill, one difficulty easier when beacon is in range.

**MUSH Integration:** Tracking beacons already exist conceptually in the bounty system. A craftable tracker schematic would give bounty hunters a tool to tag targets. `plant beacon <player>` → tracker shows direction to target in `+track`. Three tiers = three schematics.

```yaml
- key: tracker_basic
  name: "MechBlaze Tracking Observer"
  skill_required: security
  difficulty: 10
  trainer_npc: Kayson
  components:
    - type: energy
      quantity: 1
      min_quality: 25
    - type: composite
      quantity: 1
      min_quality: 20
  output_type: equipment
  output_key: tracker_basic
  base_cost: 500
```

### 3F. Blaster Beam Splitter (p. 66)

| Spec | Value |
|------|-------|
| Build Skill | Technology |
| Use Skill | Blaster |
| Building Difficulty | Very Easy |
| Jury-Rig Type | Lethal |
| Effect | +1D to blaster skill (accuracy), -1D weapon damage |
| Components | Three beam gems, adhesive |

**MUSH Integration:** Weapon attachment schematic. After crafting, `modify <weapon>` to install. Trades damage for accuracy — exactly the kind of tradeoff the experimentation system models.

### 3G. Blaster Sight (p. 67)

| Spec | Value |
|------|-------|
| Build Skill | Technology |
| Use Skill | Blaster |
| Building Difficulty | Moderate |
| Jury-Rig Type | Lethal |
| Effect | +1D to blaster skill |
| Components | Variable Pressure Adjustor (from pocket computer keypad) |

**MUSH Integration:** Pure accuracy boost, no tradeoff. Higher difficulty to build (Moderate = 15). Premium weapon attachment.

### 3H. Blaster Hair Trigger (p. 70)

| Spec | Value |
|------|-------|
| Build Skill | Technology |
| Use Skill | Blaster |
| Building Difficulty | Difficult |
| Jury-Rig Type | Lethal |
| Effect | Two shots per trigger pull (two rolls to hit, -1D per extra shot, four rolls total for two pulls). Each bonus shot's damage dice count for breakdown. |
| Components | Scomp Link (from Comlink) |

**MUSH Integration:** Burst-fire modification. Maps to a "rapid fire" mode toggle. Complex — would need combat.py changes to support multi-shot resolution. **Defer to post-launch.**

### Summary of New Schematics

| Key | Name | Skill | Difficulty | Priority |
|-----|------|-------|-----------|----------|
| `medpac_fastflesh` | FastFlesh Medpac | first_aid | 18 | HIGH |
| `comlink_bug` | Comlink Bug | security | 8 | MEDIUM |
| `lockpick_simple` | Simple Lock Picker | security | 12 | MEDIUM |
| `lectroticker` | Lectroticker | security | 16 | MEDIUM |
| `tracker_basic` | Tracking Observer | security | 10 | MEDIUM |
| `blaster_beam_splitter` | Beam Splitter | blaster_repair | 10 | LOW (needs attachment system) |
| `blaster_sight` | Blaster Sight | blaster_repair | 15 | LOW (needs attachment system) |

Items marked LOW require a weapon attachment/modification subsystem that doesn't exist yet. The HIGH and MEDIUM items work with existing systems.

---

## 4. Prosthetics & Cybernetics — Future System Stub

Cracken's has the most complete prosthetics rules in the WEG line (pp. 4–6, 29–41). This is a future feature, not current priority, but worth documenting the design space.

### 4A. Replacement Prosthetics (p. 30)

Simple replacements that duplicate natural function. No enhancement.

| Part | Cost |
|------|------|
| Hand | 1,000 cr |
| Arm | 2,000 cr |
| Leg | 2,000 cr |
| Eye | 2,750 cr |
| Ear | 2,750 cr |
| Heart | 5,000 cr |
| Lungs | 4,000 cr |

Cyber Points: 1 per replacement.

### 4B. Enhancement Packages (pp. 35–39)

| Package | Type | Attribute | Base Cost/pip | Cyber Points |
|---------|------|-----------|---------------|-------------|
| Neuro-Saav Cardio-Muscular | Enhancement | Strength | 800 cr/pip | 2 |
| 'Geneering RiMPack | Enhancement | Dexterity | 700 cr/pip | 2 |
| SoroSuub Motion Interface | Enhancement | Mechanical | 400 cr/pip | 2 |
| Neuro-Saav Hifold Sensory | Enhancement | Perception | 400 cr/pip | 2 (see cost example p. 6) |
| Neuro-Saav Hi-Sense Eyes | Enhancement | Search only | 100 cr/pip | 2 |

### 4C. Force Interaction (p. 6)

Characters with cyber points must roll a die when calling on the Force. If the roll is ≤ total cyber points, the Force cannot be used. Characters with any cyber points receive **double Dark Side Points** from all sources.

### 4D. MUSH Design Notes (for future)

- Prosthetics would live in a `character.prosthetics` JSON field
- Cyber points tracked as `character.cyber_points` integer
- Force users with prosthetics get the Force-blocking roll integrated into `engine/force_powers.py`
- DSP doubling wired into `engine/cp_engine.py`
- Social stigma modeled through NPC reaction modifiers
- **Not building this now** — it's a deep feature that touches combat, Force, economy, and social systems simultaneously

---

## 5. Vehicle Stat Blocks — Data Extraction

### 5A. Aratech A14 Repulsorlift Disk (p. 43)

| Stat | Value |
|------|-------|
| Type | One-Person Repulsorlift Disk |
| Scale | Speeder |
| Crew | 1 |
| Speed Code | 1D |
| Maneuverability | 1D |
| Body Strength | 1D |
| Flight Ceiling | 25 km |
| Cost | 300 cr |
| Weapons | None |

### 5B. Aratech Screamer Jumper Jet Pack (p. 44)

| Stat | Value |
|------|-------|
| Type | Personal Jet Pack |
| Scale | Character |
| Skill | Dexterity or Mechanical |
| Cost | 250 cr (fuel: 50 cr) |
| Fuel | 10 bursts |
| Range | 100m horizontal, 70m vertical per burst |
| Notes | One round cooldown between bursts. Easy skill roll to use. |

### 5C. Nen-Carvon R-444 Imperial Sky Swooper (p. 45)

| Stat | Value |
|------|-------|
| Type | Repulsor/Para-Wing Glider |
| Scale | Speeder |
| Length | 4 meters |
| Crew | 1 |
| Speed Code | 2D |
| Maneuverability | 4D |
| Body Strength | 1D |
| Weapons | Light Blaster Cannon (FC: 1D, Damage: 2D) |
| Cost | 400 cr |

### 5D. Hydrospeare Corp. Explorer Submergible (p. 46)

| Stat | Value |
|------|-------|
| Type | Undersea Exploration Vehicle |
| Scale | Walker |
| Length | 9.1 meters |
| Crew | 4, Passengers: 2 |
| Cargo | 500 kg |
| Speed Code | 2D |
| Body Strength | 3D |
| Weapons | Heavy Blaster Cannon (FC: 1D, Damage: 5D), Light Blaster Cannon (FC: 1D, Damage: 2D) |

### 5E. Corellian Engineering Corporation Escape Pod (p. 47)

| Stat | Value |
|------|-------|
| Type | Escape Pod |
| Scale | Starfighter |
| Passengers | 6 |
| Cargo | 18 kg |
| Consumables | 1 week (for 6) |
| Hyperdrive | None |
| Sublight Speed | 0D |
| Maneuverability | 0D |
| Hull | 1D |
| Weapons | None |

**MUSH Integration:** The escape pod is relevant for capital ship rules (already designed). The vehicles are exotic — useful as Director AI event flavor or rare vendor inventory, not standard gameplay items.

---

## 6. Weapon Modifications — New Schematics

### 6A. Upgraded Blaster Galven Pattern (p. 69)

| Spec | Value |
|------|-------|
| Components | Blaster, Droid or Datapad |
| Scale | Any |
| Build Skill | Technology |
| Use Skill | Blaster, Heavy Weapons, or Starship Gunnery |
| Building Difficulty | Per jury-rigging rules |
| Damage | +1D, 2D, or 3D upgrade |
| Jury-Rig Type | Lethal |

This is the canonical "upgrade your blaster's damage" modification. Maps directly to the crafting experimentation `power_output` axis.

### 6B. Blaster Bolt Diffusion (p. 71)

| Spec | Value |
|------|-------|
| Function | Creates gas cloud that reduces blaster damage by 1D |
| Components | 1-liter gas canister, coolant, V30 landspeeder mixture filter |
| Range | 1 meter cloud radius |
| Duration | 12 rounds per liter |
| Cost | Coolant: 50 cr/liter, Filter: 25 cr |

**MUSH Integration:** Defensive consumable. Player deploys a diffusion cloud in the room — all blaster attacks in that room deal -1D damage for 12 rounds. Interesting tactical item for territory defense. Could be a schematic.

### 6C. Blaster Power Pack Bomb (p. 77)

| Spec | Value |
|------|-------|
| Components | Several power packs, tape |
| Build Skill | Technology |
| Use Skill | Grenade (thrown) |
| Building Difficulty | Easy |
| Damage | 1D per power pack, falloff by range band |
| Notes | If tech roll fails, explodes in builder's hands. GM secretly rolls timer (1D rounds). |

**MUSH Integration:** Already have the `demolition` skill. This is an improvised explosive — interesting for the experimentation system as a "No-Dice" jury-rig item. **Defer** — explosives need careful balancing and the demolition system isn't a priority.

---

## 7. World Lore Entries — 10 New Entries

These entries feed the Director AI digest and NPC brain context. All avoid duplicating the 52 entries already in `world_lore.py`.

```python
# --- Cracken's Rebel Field Guide (WEG40046) ---

{
    "title": "General Airen Cracken",
    "keywords": "cracken,rebel,general,intelligence,contruum,sabotage",
    "content": "General Airen Cracken is the Rebel Alliance's chief intelligence officer. Born on Contruum, he ran a mechanic's shop before the Empire arrived. When Imperial Command demanded the planet's borium, Cracken organized his employees into a guerrilla force specializing in mechanical sabotage. His saboteurs left calling cards reading 'Cracken's Crew Says Hello.' He eventually joined the Alliance formally and rose to command through field ingenuity rather than military academy training.",
    "category": "character",
    "priority": 5,
},
{
    "title": "Jury-Rigging Equipment",
    "keywords": "jury-rig,modify,improve,breakdown,malfunction,repair,tinker",
    "content": "Field modification of equipment — called jury-rigging — can temporarily boost a device's performance by up to 3D, but the improvement is unreliable. Jury-rigged equipment has a chance of breakdown every time it is used. The more powerful the modification, the greater the risk. Modifications take about an hour, or one minute if rushed at higher difficulty. When jury-rigged equipment fails, weapons may explode, vehicles may lose power, and non-lethal devices simply stop working.",
    "category": "item",
    "priority": 5,
},
{
    "title": "Transponder Codes",
    "keywords": "transponder,code,identity,ship,boss,registration,signal",
    "content": "Every starship has a unique transponder code burned into its sublight engine. The code broadcasts the ship's name, type, owner, and registration data continuously. The code is extremely difficult to alter because it is embedded in the engine itself — tampering can fuse the wiring irreparably. False transponder codes can be added by analyzing the ship's signal and overlaying matching frequencies, but more than three false codes begin to bleed into each other and look suspicious on scanners.",
    "category": "item",
    "priority": 6,
},
{
    "title": "Bureau of Ships and Services (BoSS)",
    "keywords": "boss,bureau,ships,services,registration,transponder,gatherers",
    "content": "The Bureau of Ships and Services is one of the oldest institutions in the galaxy, predating the Empire by millennia. BoSS maintains records on every registered starship via transponder code tracking. The organization is technically independent — BoSS families pass positions by heredity and keep their files in nearly indecipherable internal codes. The Empire tolerates BoSS because it needs the registration system. BoSS field operatives, called Gatherers, collect data across the galaxy and are trained in computer skills, espionage, and sometimes combat.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Cybernetic Enhancements",
    "keywords": "cybernetics,prosthetic,enhancement,cyborg,implant,machine",
    "content": "Cybernetic enhancements are available but deeply stigmatized across the galaxy. The average citizen fears the blurring line between being and machine. People with visible prosthetics face discrimination and curtailment of civil rights. Enhanced beings often hide their modifications. The technology improves physical abilities but reportedly reduces empathy and emotional connection. Force users with cybernetics find it harder to tap the Force and are more vulnerable to the Dark Side.",
    "category": "item",
    "priority": 4,
},
{
    "title": "How Blasters Work",
    "keywords": "blaster,gas,xciter,galven,power pack,tibanna,bolt",
    "content": "Blasters fire by exciting gas in a chamber. The trigger opens the energy converter valve, releasing gas into the XCiter where it is energized by the power pack. The excited gas passes through the Actuating Blaster Module and is focused by the galven pattern in the barrel into a beam of intense energy. The visible light is a byproduct — the energy itself is what causes damage. Different gases produce different power levels and bolt colors. Tibanna gas from Cloud City is among the most powerful but hardest to acquire.",
    "category": "item",
    "priority": 4,
},
{
    "title": "Acquiring Blaster Gas",
    "keywords": "blaster,gas,tibanna,supply,piracy,donation,black market,mining",
    "content": "The Rebel Alliance acquires blaster gas through three channels: donations from sympathetic mining colonies, piracy of Imperial-allied corporate transports, and black market purchases. Cloud City is a reliable source for spin-sealed Tibanna gas, though officially the city only sells 'star drive engine coolant' to avoid Imperial attention. The Empire controls gas distribution by granting munitions monopolies to loyal corporations, making supply a constant challenge for the Alliance.",
    "category": "item",
    "priority": 4,
},
{
    "title": "Imperial Lift-Mines",
    "keywords": "mine,lift-mine,repulsorlift,norsam,blockade,minefield",
    "content": "The Norsam DR-X55 Imperial lift-mine floats above a planet's surface using repulsorlifts, set at specific altitudes to intercept speeders and low-flying vehicles. Top-of-the-line models detect craft up to 100 meters away and adjust altitude to intercept. Imperial policy staggers mines at different heights — low mines against speeder bikes, mid-range against landspeeders, high against airspeeders. Mine fields require a piloting maneuver roll for every mine within 20 meters of the flight path.",
    "category": "item",
    "priority": 4,
},
{
    "title": "Merr-Sonn Defender Ion Mines",
    "keywords": "ion,mine,space,blockade,merr-sonn,defender,cloaking",
    "content": "Merr-Sonn Defender Ion Mines are space-based weapons used to blockade planets. The mines use cloaking revvers and scatter particle beams to remain nearly invisible. When a ship comes within ten kilometers, the mine fires a powerful ion attack that neutralizes the vessel, leaving it adrift until Imperial forces arrive to board. Getting through a Defender blockade requires detecting the mines with an Easy Mechanical roll, then a starship piloting maneuver action opposed by each mine's 6D fire control.",
    "category": "item",
    "priority": 5,
},
{
    "title": "Computer Data Files in the Galaxy",
    "keywords": "computer,data,file,datapad,holistic,HDT,slicing,portable",
    "content": "Computer data files in the Star Wars galaxy use Holistic Data Transfer languages — AI-enhanced shorthand that lets files provide more information than they literally contain by making educated deductions. Files are rated by die codes from 1D to 13D, with higher ratings exponentially more expensive. A 4D file costs 1,000 credits while a 10D file costs 100,000. Pocket datapads store up to 5D of files, portable computers up to 20D, and capital starship computers up to 30D. MicroThrust portable computers can add their power rating as bonus dice to a programmer's skill.",
    "category": "item",
    "priority": 4,
},
```

---

## 8. Transponder Codes & BoSS — Space System Enrichment

This is one of the most actionable sections for SW_MUSH. The transponder code system maps directly to the existing ship identity system and enriches smuggling gameplay.

### 8A. Adding False Transponder Codes (p. 61)

**Canon mechanics:**
- First false code: 3 skill points, 1,500 cr, Easy technology roll
- Second: 6 skill points, 3,000 cr, Moderate technology roll
- Third: 9 skill points, 4,500 cr, Difficult technology roll
- Fourth+: 12 skill points each, 6,000 cr each, Very Difficult technology roll
- More than 3 codes: Anyone scanning with Easy technical roll spots the bleed
- Takes one week per code on a starfighter-scale ship

**MUSH Integration:** This maps to ship modifications. A `+transponder/add` command that:
1. Requires a technology skill check (difficulty escalates per code)
2. Costs credits (escalating)
3. Adds a false identity to the ship's DB record
4. `+transponder/switch <identity>` toggles active transponder
5. NPC scan encounters check against the false identity
6. More than 3 codes → increased detection chance on all scans

This directly enriches the smuggling profession lane.

### 8B. Removing Transponder Codes (p. 62)

**Canon mechanics:**
- Requires a plasma displacer (300 cr, Availability R)
- Blur signal: Moderate technology roll, 4 hours work
- Restore signal: Difficult technology roll, 1 full day
- Ship is still detectable by engines, just unidentifiable at range
- At close range, signal pattern reveals the code was deliberately obscured
- Authorities treat code removal as grounds for arrest

**MUSH Integration:** A separate command `+transponder/mask` that makes the ship appear as "Unknown Vessel" on scans. Higher Imperial alert levels mean more aggressive scanning. Getting caught with a masked transponder → instant wanted status.

### 8C. BoSS NPC Stat Blocks (p. 60)

**BoSS Agent:**
DEX 3D (Blaster 4D+2, Dodge 3D+2), KNO 4D (Alien Races 5D, Cultures 4D+2, Languages 4D+1, Planetary Systems 4D+1, Streetwise 5D), MEC 2D (Beast Riding 3D, Repulsorlift Op 3D+1, Starship Piloting 3D+1), PER 4D (Con 4D+2, Gambling 4D+1, Hide/Sneak 5D, Search 4D+2), STR 3D, TEC 3D (Comp Prog/Repair 4D+1, Demolition 3D+2, Security 4D+2, Starship Repair 5D)

**BoSS Enforcer:**
DEX 4D (Blaster 5D, Brawling Parry 4D+2, Dodge 4D+1, Grenade 4D+1), KNO 2D (Survival 3D+1), MEC 3D (Beast Riding 3D+1, Starship Piloting 3D+1, Starship Gunnery 3D+2), PER 3D (Hide/Sneak 3D+1), STR 4D (Brawling 4D+1, Climbing/Jumping 4D+2, Stamina 5D), TEC 2D (Security 4D, Starship Repair 2D+2)

**BoSS Bureaucrat:**
DEX 2D, KNO 4D (Alien Races 5D, Cultures 5D, Languages 4D+1, Planetary Systems 5D), MEC 2D, PER 4D (Bargain 4D+2, Command 4D+1), STR 2D, TEC 4D (Comp Prog/Repair 5D, Security 5D+1, Starship Repair 5D+2)

**MUSH Integration:** Add to `data/npcs_gg7.yaml` as spawnable NPC templates. BoSS Gatherers could appear as random encounters at starports, creating interesting tension for smugglers with modified transponders.

---

## 9. Computer Data Files — Slicing System Seed

The computer data file system (pp. 5–7) describes a mechanic that maps to a future "slicing" profession lane. Not building now but documenting the design space.

### Core Mechanic
- Files rated 1D–13D, costs scale exponentially
- Computer programming skill to search files
- Files can be combined (both must be within 1D of each other, result is +1D, failure loses 1D from each)
- Portable computers add bonus dice to programming skill
- MicroThrust computer spikes (pp. 13) are single-use hacking programs rated 2D–10D, costing 3,000–15,000 credits

### Future "Slicing" Feature Concept
1. `slice <terminal>` → computer_programming skill check vs terminal difficulty
2. Computer spike items boost the roll
3. Success extracts data (mission intel, faction secrets, credit transfers)
4. Failure triggers security alarm (guard NPC spawn, faction rep penalty)

This would be a **post-launch feature** but the world lore entry (§7) and computer spike item costs are worth seeding into the economy now.

---

## 10. Implementation Plan

### Drop 1: World Lore Expansion (Sonnet — Small, ~30 min)

**Files modified:**
- `engine/world_lore.py` — Add 10 new entries from §7 above to `SEED_ENTRIES`

**Deployment:** Existing `ensure_lore_schema` auto-creates on startup. New entries seeded by title match (skips duplicates).

### Drop 2: New Equipment Schematics (Sonnet — Small, ~1 hour)

**Files modified:**
- `data/schematics.yaml` — Add 5 new schematics: `medpac_fastflesh`, `comlink_bug`, `lockpick_simple`, `lectroticker`, `tracker_basic`

**Dependencies:** None — all use existing `output_type: equipment` or `output_type: consumable`. The `equipment` output type may need a handler if it doesn't exist yet (check `engine/crafting.py`).

### Drop 3: Experimentation Engine Rewrite (Sonnet — Large, ~4-6 hours)

This is the main event. Complete rewrite of the experiment system from flat "+5 difficulty" to the full axis/tradeoff/breakdown design.

**Files modified:**
- `engine/crafting.py` — Add `DEFAULT_EXPERIMENT_PARAMS` dict (§2E/2F), `resolve_experiment()`, `resolve_breakdown()`, `get_experiment_axes()`, experiment item JSON tracking
- `parser/crafting_commands.py` — Rewrite `ExperimentCommand`: operates on inventory items, `experiment list <item#>`, `experiment <item#> <axis>`, axis selection UI, experiment log display
- `engine/combat.py` — Add post-damage breakdown dice check for experimentally modified weapons (§2D step 9). On breakdown trigger, call `resolve_breakdown()`, display dramatic failure messages.
- `data/schematics.yaml` — Add `experiment_params` overrides for any schematics needing non-default tuning (most inherit from `DEFAULT_EXPERIMENT_PARAMS` by `output_type`)

**Files unchanged:**
- `db/database.py` — No schema changes (experiment data lives in item JSON within character inventory)
- `engine/skill_checks.py` — Uses existing `perform_skill_check()`

**Key parameters (from §2C–2E):**
- Weapons: `difficulty_escalation: 5`, `max_experiments: 3`, `breakdown_type: lethal`
- Components: `difficulty_escalation: 5`, `max_experiments: 2`, `breakdown_type: vehicle`
- Consumables: `difficulty_escalation: 3`, `max_experiments: 2`, `breakdown_type: non_lethal`
- Survival gear: `difficulty_escalation: 4`, `max_experiments: 1`, `breakdown_type: non_lethal`
- Weapon axis labels from Cracken's: "Galven Pattern Upgrade", "Beam Calibration", "Reinforced Housing"

### Drop 4: BoSS NPC Templates (Sonnet — Small, ~30 min)

**Files modified:**
- `data/npcs_gg7.yaml` — Add BoSS Agent, BoSS Enforcer, BoSS Bureaucrat templates

### Drop 5: Transponder Code System (Sonnet — Medium, ~3-4 hours)

**Files modified:**
- `engine/starships.py` — `add_false_transponder()`, `switch_transponder()`, `mask_transponder()`, `check_transponder_bleed()`
- `parser/space_commands.py` — `+transponder/add`, `+transponder/switch`, `+transponder/mask` commands
- `db/database.py` — Add `transponder_codes` JSON field to ships table (or use existing ship attributes JSON)

**Dependencies:** None on other drops. This enriches smuggling gameplay immediately.

### Optional Drop 6: General Cracken as NPC (Sonnet — Small, ~30 min)

**Files modified:**
- `data/npcs_gg7.yaml` — Add General Cracken with full stat block from p. 10
- Potentially `build_mos_eisley.py` or a Rebel base builder — place Cracken at a Rebel contact point

### Priority Order

1. **Drop 3** (experimentation engine) — highest impact, completes Competitive Analysis feature #12
2. **Drop 1** (world lore) — immediate, no risk, do alongside Drop 3
3. **Drop 2** (schematics) — immediate, gives crafters more items to experiment on
4. **Drop 5** (transponder codes) — major smuggling enrichment
5. **Drop 4** (BoSS NPCs) — flavor enhancement
6. **Drop 6** (Cracken NPC) — flavor

---

## Appendix A: Items Evaluated and Deferred

| Item | Reason for Deferral |
|------|-------------------|
| Droid Restraining Bolt (p. 17) | No droid PC/companion system |
| Deactivating Restraining Bolt device (p. 18) | Same dependency |
| Imperial Heat Sensor Trip (p. 19) | Would need sensor/alarm system infrastructure |
| BlasTech MoveSense 34 Motion Trip (p. 20) | Same dependency |
| Pressure Plate Trip (p. 21) | Same dependency |
| False Voice Transmitter (p. 23) | Niche, no voice system |
| Holo-Bit Generator (p. 24) | Niche deception device |
| Stormtrooper Channel Scanner (p. 29) | Would need comms interception system |
| All prosthetics (pp. 29–42) | Deep feature — see §4 |
| Animal Restraining Bolt (p. 48) | No beast companion system |
| All vehicle jury-rig mods (pp. 48–58) | Would need ground vehicle system |
| Explosive Slugs (p. 72) | Slugthrower ammo — niche |
| Jawa Ionization Gun (p. 74) | Anti-droid weapon — no droid combat |
| Merr-Sonn Tangle Gun 7 (p. 75) | Non-lethal weapon — interesting but deferred |
| Negative Power Coupler Bomb (p. 78) | Explosives — defer |
| SoroSuub XG Anti-Gravity Field Bombs (p. 79) | Explosives — defer |
| Micronite Explosive Charge (p. 76) | Sabotage device — defer |

---

*End of Cracken's Rebel Field Guide Extraction — Version 1.0*
*Source: WEG40046 (82 pages, scanned)*
*Deliverables: 10 world lore entries, 5 new schematics, 3 BoSS NPC templates, transponder code system design, General Cracken stat block*
*Deferred: prosthetics system, weapon attachment system, explosive devices, sensor/alarm infrastructure, vehicle modifications*
*Next: Implement Drop 1 (world lore) + Drop 2 (schematics) in Sonnet session, then Drop 4 (transponder codes) as a medium feature*
