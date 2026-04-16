# SW_MUSH Detailed Systems Guide #2
# Character Creation

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## How to Read This Guide

**Player Rules** sections explain what you do and see during character creation. **Developer Internals** sections (marked with 🔧) explain the code: data structures, validation logic, file paths, and edge cases.

---

## 1. Overview

Character creation in SW_MUSH follows the WEG D6 Revised & Expanded rules. You choose a species, distribute attribute dice within species-defined ranges, spend skill dice on the skills you want, optionally declare Force sensitivity, write a background, and finalize. The entire process happens through typed commands in a dedicated creation mode.

Two paths are available: a **guided wizard** that walks you through each step with descriptions and prompts, or a **free-form editor** where you can set any field in any order. Both paths produce the same result — a complete character saved to the database.

---

## 2. Species

### Player Rules

Nine playable species are available. Each has different attribute ranges — the minimum and maximum dice you can put into each attribute. All species get the same total dice to distribute (18D for attributes, 7D for skills), but where those dice can go varies dramatically.

| Species | Homeworld | DEX | KNO | MEC | PER | STR | TEC | Move | Special Abilities |
|---------|-----------|-----|-----|-----|-----|-----|-----|------|-------------------|
| **Human** | Various | 2D–4D | 2D–4D | 2D–4D | 2D–4D | 2D–4D | 2D–4D | 10 | None (most versatile) |
| **Bothan** | Bothawui | 1D+1–3D+2 | 2D–4D+1 | 1D–3D | 2D+1–4D+2 | 1D–2D+2 | 1D–3D+1 | 10 | — |
| **Duros** | Duro | 1D–3D+2 | 1D+1–4D | 2D+1–4D+2 | 1D–3D+1 | 1D–3D | 1D+1–4D | 10 | Natural Pilots |
| **Mon Calamari** | Mon Cala | 1D–3D | 1D+1–4D | 1D+1–3D+1 | 1D–3D+1 | 1D–3D | 1D+1–4D+1 | 10 | Amphibious, Moist Environment |
| **Rodian** | Rodia | 1D+1–4D | 1D–3D | 1D–3D+1 | 2D–4D+1 | 1D–3D | 1D–3D+1 | 10 | — |
| **Sullustan** | Sullust | 1D–3D+1 | 1D–3D | 1D+2–4D+1 | 1D–3D+1 | 1D–3D | 1D+1–3D+2 | 10 | Direction Sense, Enhanced Senses |
| **Trandoshan** | Trandosha | 1D–3D | 1D–2D+2 | 1D–2D+2 | 1D–3D | 2D–4D+2 | 1D–2D+2 | 10 | Regeneration, Claws, Vision |
| **Twi'lek** | Ryloth | 1D–3D+2 | 1D–4D | 1D–3D | 2D–4D+2 | 1D–3D | 1D–3D+1 | 10 | Lekku Communication |
| **Wookiee** | Kashyyyk | 1D–3D+2 | 1D–2D+1 | 1D–3D+2 | 1D–2D+1 | 3D–6D | 1D–3D+1 | 11 | Berserker Rage, Climbing Claws |

**Choosing a species matters.** A Wookiee can start with 6D Strength — devastating in brawling — but is capped at 2D+1 Knowledge and Perception. A Bothan excels at Perception (up to 4D+2) but caps at 2D+2 Strength. A Human has no extremes but can put 4D in anything.

**Special abilities** are species-locked traits that can't be learned by other species:

- **Wookiee Berserker Rage:** When wounded or a companion is hurt, gain +2D Strength for brawling damage. Cannot do anything except attack until passing a Moderate Perception check to calm down.
- **Wookiee Climbing Claws:** +2D to climbing checks. Using claws in combat is dishonorable — results in exile from Wookiee society.
- **Trandoshan Regeneration:** Can regrow lost limbs over time.
- **Trandoshan Claws:** Natural weapons that add to brawling damage.
- **Duros Natural Pilots:** Innate aptitude with spacecraft and navigation.
- **Mon Calamari Amphibious:** Can breathe underwater indefinitely.
- **Sullustan Direction Sense:** Almost never get lost, even in unfamiliar environments.
- **Sullustan Enhanced Senses:** Exceptional hearing and vision in low light.
- **Twi'lek Lekku Communication:** Can communicate silently via head-tail movements with other Twi'leks.

To view species details in-game: `info <species>` (e.g., `info wookiee`).

### 🔧 Developer Internals

**File:** `data/species/*.yaml` — Nine YAML files, one per species. Each defines:
```yaml
name: "Wookiee"
description: "..."
homeworld: "Kashyyyk"
attributes:
  dexterity:     { min: "1D", max: "3D+2" }
  # ... all six attributes
attribute_dice: "18D"     # Total to distribute
skill_dice: "7D"          # Total skill dice
special_abilities:
  - name: "Berserker Rage"
    description: "..."
move: 11
story_factors:
  - "Cannot speak Basic..."
```

**File:** `engine/species.py` — Species data model and registry:
- `SpecialAbility` dataclass: `name`, `description`
- `AttributeRange` dataclass: `min_pool: DicePool`, `max_pool: DicePool`
- `Species` dataclass: `name`, `description`, `homeworld`, `attributes: dict[str, AttributeRange]`, `attribute_dice: DicePool`, `skill_dice: DicePool`, `special_abilities: list`, `move: int`, `story_factors: list`
- `Species.validate_attributes(attrs)` — Validates a dict of attribute allocations against species limits. Returns list of error strings (empty = valid). Checks: each attribute within min/max range, total pips equal `attribute_dice.total_pips()`
- `Species.format_display()` — Renders species info for in-game display with word wrapping
- `SpeciesRegistry` — Loads all YAML from a directory, provides `get(name)` (case-insensitive), `list_names()`, `list_all()`
- `_parse_species(data)` — Converts raw YAML dict into `Species` object, parsing DicePools from strings

**Loading:** `SpeciesRegistry.load_directory(path)` is called during server startup. It iterates sorted YAML files, logs each species loaded, and reports the total count.

---

## 3. Attributes

### Player Rules

You have **18D** (54 pips) of attribute dice to distribute among your six attributes. Each attribute must stay within your species' min/max range. Once you've spent all 18D (no more, no less), your attributes are set.

The six attributes and what they govern:

**Dexterity** — Your agility and hand-eye coordination. Governs all combat accuracy (blaster, melee, grenades, lightsaber), dodging, and physical nimbleness. The single most important attribute for combat characters.

**Knowledge** — Your education and worldly awareness. Governs languages, alien species knowledge, streetwise savvy, survival skills, tactics, willpower, and bureaucratic know-how. Essential for social and scholarly characters.

**Mechanical** — Your aptitude with vehicles and instruments. Governs all piloting (space transports, starfighters, capital ships), astrogation, sensors, gunnery, and vehicle operation. The key attribute for pilots and navigators.

**Perception** — Your social awareness and intuition. Governs persuasion, bargain, con, command, search, sneak, hide, gambling, and investigation. The primary attribute for face characters, spies, and leaders.

**Strength** — Your raw physical power and toughness. Governs brawling, lifting, stamina, climbing, and swimming. Also your base damage resistance — when you get shot, you roll Strength (plus armor) to resist damage. Low Strength characters are fragile.

**Technical** — Your mechanical and scientific expertise. Governs all repair skills, first aid, medicine, computer slicing, demolitions, droid programming, and security systems. Essential for engineers and medics.

**Setting attributes in-game:**
```
> set dex 3D+2        (set Dexterity to 3D+2)
> set str 4D          (set Strength to 4D)
> set kno 2D+1        (accepts abbreviations: dex, kno, mec, per, str, tec)
```

Attribute abbreviations work with any unique prefix — `dex`, `d`, `per`, `p`, `str`, `s`, etc. If the prefix is ambiguous (e.g., `s` could be Strength or Sense), you'll get an error asking you to be more specific.

### 🔧 Developer Internals

**File:** `engine/creation.py` — `CreationEngine._cmd_set()` (lines ~213–270):
- Parses attribute name via `_match_attribute()` which matches any unique prefix against `ATTRIBUTE_NAMES` + Force attributes
- Parses the dice value via `DicePool.parse()`
- Validates against species min/max ranges before accepting
- Pushes undo snapshot before applying
- Reports remaining attribute pips via `_status()`

**Attribute tracking:**
- `CreationState.attributes: dict[str, DicePool]` — Current allocation per attribute
- `_attr_pips_spent()` — Sum of `total_pips()` across all allocated attributes
- `_attr_pips_total()` — From `species.attribute_dice.total_pips()` (normally 54 = 18D)
- The status line always shows `Attr: XX pips remaining` so the player knows how much is left

**Validation on `done`:** `_validate()` checks:
1. Name is set (2–30 characters)
2. Species is set
3. Attribute pips fully spent (remaining = 0)
4. Skill pips not overspent (remaining ≥ 0, underspend is allowed)
5. Each attribute within species min/max range

**`_set_minimums()`** — Called when species changes. Sets all six attributes to the species minimum. This ensures you always start from a valid baseline and can only add dice from there.

---

## 4. Skills

### Player Rules

You have **7D** (21 pips) of skill dice to distribute among the game's 75 skills. You can add 1D or 2D (or any pip amount) to any skill. Skills you don't invest in default to the raw attribute — there's no penalty for being "untrained."

**Important:** Skill dice are bonuses *above* the parent attribute. If you put 1D into Blaster and your Dexterity is 3D+1, your effective Blaster is 4D+1. The character sheet shows both the bonus and the total.

You don't have to spend all 7D. Unspent skill pips are lost — they don't convert to anything else.

**Setting skills in-game:**
```
> skill blaster 1D+1      (add 1D+1 bonus to Blaster)
> skill dodge 1D           (add 1D bonus to Dodge)
> skill space transports 2D (multi-word skill names work)
> unskill blaster           (remove Blaster skill bonus)
> list dex                  (browse all Dexterity skills)
> list all                  (browse all 75 skills)
```

Partial skill name matching works — `skill blas 1D` will match Blaster if it's unambiguous.

**Skill dice budget strategy:**

With only 7D, you need to prioritize. The WEG R&E recommends focusing on 4–6 skills that define your character concept rather than spreading thin. A smuggler might put 2D in Space Transports, 1D+1 in Blaster, 1D in Dodge, 1D in Streetwise, 1D in Bargain, and +2 pips in Starship Gunnery. A soldier might go heavier on Blaster (2D), Dodge (1D), Brawling (1D), Grenade (1D), Tactics (1D), and Stamina (1D).

### 🔧 Developer Internals

**File:** `engine/creation.py` — `CreationEngine._cmd_skill()` (lines ~271–310):
- Looks up skill name via `SkillRegistry.get()` with partial matching
- Validates the skill exists and parses the dice bonus
- Pushes undo snapshot
- Adds to `CreationState.skills: dict[str, DicePool]` (key is lowercase skill name)
- Reports remaining skill pips

**`_cmd_unskill()`:** Removes a skill bonus entirely, freeing up those pips.

**`_cmd_list_skills()`:** Lists all skills under an attribute (or all attributes), showing trained skills with their bonus and total, and untrained skills with specialization options.

**Skill pips tracking:**
- `_skill_pips_spent()` = sum of `total_pips()` across all skill bonuses
- `_skill_pips_total()` = `species.skill_dice.total_pips()` (normally 21 = 7D)
- Overspend is blocked at validation time but allowed during editing (the status line shows negative remaining)

---

## 5. Templates

### Player Rules

Don't want to build from scratch? Seven pre-built templates set up reasonable attribute and skill distributions for common character archetypes. You can apply a template and then customize it — change species, adjust attributes, add or remove skills.

| Template | DEX | KNO | MEC | PER | STR | TEC | Key Skills |
|----------|-----|-----|-----|-----|-----|-----|------------|
| **Smuggler** | 3D+1 | 2D+1 | 4D | 3D+1 | 2D+2 | 2D+1 | Blaster +1D+1, Dodge +1D, Space Transports +1D+2, Gunnery +1D, Streetwise +1D, Bargain +1D |
| **Bounty Hunter** | 3D+2 | 2D+1 | 2D+2 | 3D+1 | 3D+1 | 2D+2 | Blaster +2D, Dodge +1D, Brawling +1D, Search +1D, Sneak +1D, Security +1D |
| **Rebel Pilot** | 3D | 2D+2 | 4D+1 | 2D+2 | 2D+2 | 2D+2 | Starfighter Piloting +2D, Gunnery +1D, Astrogation +1D, Sensors +1D, Starfighter Repair +1D, Blaster +1D |
| **Scoundrel** | 3D | 3D | 2D+2 | 4D | 2D+2 | 2D+2 | Con +1D+2, Persuasion +1D, Gambling +1D, Sneak +1D+1, Blaster +1D, Dodge +1D |
| **Technician** | 2D+1 | 3D | 2D+2 | 2D+2 | 2D+2 | 4D+2 | Comp Prog/Repair +1D+2, Space Transport Repair +1D+1, Droid Repair +1D, First Aid +1D, Security +1D, Blaster Repair +1D |
| **Jedi Apprentice** | 3D+1 | 3D | 2D+1 | 3D+2 | 3D | 2D+2 | Lightsaber +1D+2, Dodge +1D, Scholar +1D, Willpower +1D, Sneak +1D, Climbing/Jumping +1D+1 |
| **Soldier** | 3D+2 | 2D+2 | 2D+2 | 2D+2 | 3D+2 | 2D+2 | Blaster +1D+2, Dodge +1D, Brawling +1D, Grenade +1D, Tactics +1D, Stamina +1D+1 |

**Using templates in-game:**
```
> template              (list available templates)
> template smuggler     (apply the Smuggler template)
```

Applying a template sets the species to Human, distributes all 18D of attributes, and spends all 7D of skills. You can then change any of these — switch species (which resets attributes to minimums), adjust individual attributes with `set`, or modify skills with `skill`/`unskill`.

### 🔧 Developer Internals

**File:** `engine/creation.py` — `TEMPLATES` dict (lines 42–101):
- Each template is a dict with `label`, `species`, `attributes` (dict of name → dice string), and `skills` (dict of name → dice bonus string)
- All templates use Human and exactly spend 18D attributes + 7D skills

**`_cmd_template()`:** 
- No args: lists all templates with labels
- With name: looks up template, pushes undo, applies species, attributes, and skills
- Species change triggers `_set_minimums()` then overwrites with template values

---

## 6. Force Sensitivity

### Player Rules

During creation, you choose whether your character is **Force-sensitive**. This is a significant decision with lasting consequences:

**Force-sensitive (Yes):**
- Start with **2 Force Points** instead of 1
- Can learn Force skills (Control, Sense, Alter) and use Force powers
- Must be played as morally upright — the dark side temptation is real, and evil actions earn Dark Side Points that can corrupt your character
- Cannot be as mercenary or morally grey as a non-sensitive character

**Not Force-sensitive (No):**
- Start with **1 Force Point**
- Cannot learn Force skills or use Force powers
- Free to play a morally ambiguous character (smuggler, bounty hunter, etc.)

Per the WEG R&E rules: *"Force-sensitive characters can't be as mercenary as Han Solo is at the beginning of A New Hope. They must be moral, honest and honorable, like Luke Skywalker and Obi-Wan Kenobi, or the dark side will dominate them."*

Force skills (Control, Sense, Alter) cannot be added during initial creation unless they're already on your template. The Jedi Apprentice template is the primary path to starting with Force skills.

### 🔧 Developer Internals

**File:** `engine/creation_wizard.py` — `STEP_FORCE` handler:
- Binary choice: yes/no
- Sets `self._force_sensitive` flag
- In `get_character()`: if force_sensitive, sets `char.force_sensitive = True` and `char.force_points = 2` (R&E rule: Force-sensitive characters start with 2 FP)

**File:** `engine/character.py` — Force attribute fields:
- `force_sensitive: bool = False`
- `control: DicePool`, `sense: DicePool`, `alter: DicePool` — all default to 0D
- `force_points: int = 1` (overridden to 2 for Force-sensitive)
- `dark_side_points: int = 0`

---

## 7. Starting Equipment and Credits

### Player Rules

All characters start with **1,000 credits** and a basic equipment loadout. The WEG R&E rules say to pick "reasonable" starting equipment — the game provides defaults based on common sense for the setting:

- A blaster pistol (500 credits) or other sidearm
- A comlink (100 credits)
- Basic clothing
- Remaining credits for supplies

Specific starting equipment varies by how the character enters play. Credits can be spent at vendors, weapon shops, and other merchants in the game world once you're playing.

### 🔧 Developer Internals

**File:** `engine/character.py` — `Character` defaults:
- `credits: int = 1000` — Default starting credits
- `equipped_weapon: str = ""` — Weapon key from `weapons.yaml`
- `worn_armor: str = ""` — Armor key
- `character_points: int = 5` — Per R&E: all characters start with 5 CP
- `force_points: int = 1` — 1 for non-sensitive, 2 for sensitive (set in wizard)

Equipment is not assigned during the creation wizard — characters receive their starting gear through the tutorial system or by purchasing from in-game vendors.

---

## 8. The Creation Wizard (Guided Mode)

### Player Rules

When you create a character, the wizard walks you through these steps:

1. **Welcome & Path Choice** — Choose between using a template (quick start) or building from scratch
2. **Template Selection** (template path) or **Species Selection** (scratch path) — Pick your template or species with full descriptions
3. **Attributes** (scratch path only) — Distribute 18D across six attributes with real-time remaining count
4. **Skills** — Distribute 7D across skills with descriptions from the WEG rulebook
5. **Force Sensitivity** — Choose Yes or No with an explanation of consequences
6. **Background** — Write free-text character background/backstory
7. **Review & Confirm** — See the complete character sheet and finalize with `done`

At any step, you can:
- Type `back` to go to the previous step
- Type `sheet` to preview your character sheet
- Type `undo` to reverse the last change
- Type `free` to drop into free-form editing mode (all commands available simultaneously)
- Type `guided` to return to the step-by-step wizard from free-form mode
- Type `help` for available commands at any step

### 🔧 Developer Internals

**File:** `engine/creation_wizard.py` — `CreationWizard` class (~940 lines):

**Architecture:** The wizard wraps `CreationEngine` (the free-form editor). All actual data manipulation goes through the engine — the wizard just controls the step flow and provides richer display.

**Step flow:**
```python
SCRATCH_STEPS = [WELCOME, SPECIES, ATTRIBUTES, SKILLS, FORCE, BACKGROUND, REVIEW]
TEMPLATE_STEPS = [WELCOME, TEMPLATE_SELECT, SKILLS, FORCE, BACKGROUND, REVIEW]
```

**Key design decisions:**
- `path` field tracks "template" vs "scratch" — determines which step sequence to follow
- `_go_back()` finds the current step in the active step list and moves to the previous index
- `STEP_FREEFORM` is a special state — all input passes directly to `CreationEngine.process_input()`
- Returning to guided mode from freeform always lands on the REVIEW step (since you could have changed anything)

**Display rendering:** Each step has a dedicated `_render_*()` method that builds ANSI-colored output with box-drawing, descriptions, and current state. The wizard loads `data/skill_descriptions.yaml` (~50K lines) to show WEG rulebook descriptions during the skills step.

**`process_input()` flow:**
1. If in freeform mode, delegate to engine (unless input is "guided")
2. Check global commands: help, sheet, undo, free, back
3. Dispatch to step-specific handler

---

## 9. The Free-Form Editor

### Player Rules

If you prefer full control, the free-form editor gives you all commands simultaneously. This is the underlying engine that the wizard wraps.

**All commands:**

| Command | Purpose | Example |
|---------|---------|---------|
| `name <n>` | Set character name (2–30 chars) | `name Kaelin Voss` |
| `species [name]` | List or set species | `species wookiee` |
| `info <species>` | View species details | `info trandoshan` |
| `template [name]` | List or apply template | `template smuggler` |
| `set <attr> <dice>` | Set attribute dice | `set dex 3D+2` |
| `skill <name> <dice>` | Add skill bonus | `skill blaster 1D+1` |
| `unskill <name>` | Remove skill bonus | `unskill dodge` |
| `list <attr\|all>` | Browse skills by attribute | `list perception` |
| `undo` | Undo last change | `undo` |
| `sheet` / `review` | Show full character sheet | `sheet` |
| `done` | Finalize character | `done` |
| `help` | Show command list | `help` |
| `quit` | Abort creation | `quit` |

The **status line** is always visible at the bottom, showing remaining attribute pips and skill pips:
```
[ Attr: 6 pips remaining | Skills: 12 pips remaining ]
```

### 🔧 Developer Internals

**File:** `engine/creation.py` — `CreationEngine` class (~530 lines):

**Constructor:** Takes `SpeciesRegistry` and `SkillRegistry`. Creates `CreationState` and defaults to Human species.

**`process_input(text)`** — Returns `(display: str, prompt: str, is_done: bool)`:
- Dispatches to handler methods based on first word
- All handlers return the same tuple shape
- `is_done` is True only from `_cmd_done()` after passing validation

**Undo system:** `_push_undo(label)` creates a `_Snapshot` with deep copies of name, species_name, attributes, and skills. Stack capped at 20 entries (FIFO eviction). `_cmd_undo()` pops the latest snapshot and restores state.

**Attribute matching:** `_match_attribute(text)` matches any unique prefix. `"dex"` → `"dexterity"`, `"p"` → `"perception"` (if unambiguous). Also matches Force attributes: `"con"` → `"control"`, `"sen"` → `"sense"`, `"alt"` → `"alter"`.

---

## 10. Character Sheet Display

### Player Rules

The character sheet uses a two-column layout matching the official WEG R&E character sheet format:

```
==============================================================================
  Kaelin Voss  |  Human  |  Smuggler
==============================================================================
  Status: Healthy
  CP: 5  |  FP: 1  |  DSP: 0  |  Credits: 1,000
  Move: 10

  DEXTERITY       3D+1              PERCEPTION      3D+1
    Blaster              4D+2 (+1D+1)  Bargain             4D+1 (+1D)
    Dodge                4D+1 (+1D)    Streetwise          ... (untrained)

  KNOWLEDGE       2D+1              STRENGTH        2D+2
    Streetwise           3D+1 (+1D)    ...

  MECHANICAL      4D                TECHNICAL       2D+1
    Space Transports     5D+2 (+1D+2)  ...
    Starship Gunnery     5D   (+1D)

==============================================================================
```

Left column shows DEX/KNO/MEC, right column shows PER/STR/TEC. Trained skills appear indented under their parent attribute with the total pool and the bonus in parentheses. Untrained skills are hidden unless you use `list all`.

During creation, the sheet also shows species attribute ranges in dim text next to each attribute so you know how much room you have.

### 🔧 Developer Internals

**File:** `engine/sheet_renderer.py` (~543 lines):

**Layout constants:**
- `W = 78` — Total sheet width (fits 80-column terminals)
- `COL = 37` — Column width
- `GUTTER = "  "` — 2-char divider between columns
- `LEFT_ATTRS = ["dexterity", "knowledge", "mechanical"]`
- `RIGHT_ATTRS = ["perception", "strength", "technical"]`

**Key functions:**
- `_build_attr_block()` — Renders one attribute header + its trained skills. Handles both `Character` objects and raw attribute/skill dicts (for creation mode)
- `_attr_header()` — Formats `DEXTERITY          3D+1` with ANSI bold/color
- `_skill_line()` — Formats `  Blaster              5D+1` with cyan/green colors
- `render_creation_sheet()` — Builds the full two-column sheet with attribute ranges, pip budgets, and creation-specific annotations
- `render_status_line()` — The persistent `[Attr: X pips | Skills: Y pips]` footer

**ANSI handling:** `_ansi_len()` strips ANSI escape codes to compute true display width. `_pad()` adds spaces to reach a target visual width (accounting for invisible ANSI codes). This is critical for the two-column alignment to work on terminals.

**File:** `engine/character.py` — `Character.format_sheet()` (line 546) — Simpler single-column sheet for non-creation contexts (post-creation `+sheet` command).

---

## 11. Persistence: How Characters Are Saved

### 🔧 Developer Internals

When the player types `done` and passes validation:

1. `CreationWizard.get_character()` builds a `Character` object from state
2. `Character.to_db_dict()` serializes to a flat dict matching the DB schema:
   - `attributes` → JSON string: `{"dexterity": "3D+1", "knowledge": "2D+1", ...}`
   - `skills` → JSON string: `{"blaster": "1D+1", "dodge": "1D", ...}` (bonus above attribute only)
   - `equipment` → JSON string: `{"weapon": "", "armor": ""}`
   - Scalar fields: `name`, `species`, `template`, `wound_level`, `character_points`, `force_points`, `dark_side_points`, `credits`, `room_id`, `description`
3. The session handler calls `db.create_character()` to INSERT into the `characters` table
4. The character is associated with the player's account via `account_id`
5. The session transitions from creation mode to normal gameplay

**Deserialization:** `Character.from_db_dict(data)` reconstructs from a DB row. Handles both string and pre-parsed JSON for attributes/skills/equipment. `Character.from_npc_sheet(npc_id, sheet)` handles the slightly different NPC format (where skills are also bonus-above-attribute but stored in a `char_sheet_json` field).

---

## 12. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/creation.py` | ~530 | Free-form creation engine, templates, undo system, validation |
| `engine/creation_wizard.py` | ~940 | Guided step-by-step wizard wrapping the creation engine |
| `engine/species.py` | ~212 | Species data model, attribute validation, registry |
| `engine/character.py` | ~588 | Character model, wound system, serialization |
| `engine/sheet_renderer.py` | ~543 | ANSI two-column character sheet display |
| `data/species/*.yaml` | 9 files | Species definitions (attributes, abilities, story factors) |
| `data/skills.yaml` | ~89 | 75 skill definitions with specializations |
| `data/skill_descriptions.yaml` | ~50K | Detailed WEG rulebook skill descriptions |

---

*End of Guide #2 — Character Creation*
*Next: Guide #3 — Ground Combat*
