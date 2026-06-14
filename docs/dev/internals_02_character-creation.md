# Developer Internals — Guide_02_Character_Creation.md

Extracted from `data/guides/Guide_02_Character_Creation.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

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

### 🔧 Developer Internals

**File:** `engine/creation.py` — `TEMPLATES` dict (lines 42–101):
- Each template is a dict with `label`, `species`, `attributes` (dict of name → dice string), and `skills` (dict of name → dice bonus string)
- All templates use Human and exactly spend 18D attributes + 7D skills

**`_cmd_template()`:** 
- No args: lists all templates with labels
- With name: looks up template, pushes undo, applies species, attributes, and skills
- Species change triggers `_set_minimums()` then overwrites with template values

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

### 🔧 Developer Internals

**File:** `engine/character.py` — `Character` defaults:
- `credits: int = 1000` — Default starting credits
- `equipped_weapon: str = ""` — Weapon key from `weapons.yaml`
- `worn_armor: str = ""` — Armor key
- `character_points: int = 5` — Per R&E: all characters start with 5 CP
- `force_points: int = 1` — 1 for non-sensitive, 2 for sensitive (set in wizard)

Equipment is not assigned during the creation wizard — characters receive their starting gear through the tutorial system or by purchasing from in-game vendors.

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

### 🔧 Developer Internals

**File:** `engine/creation.py` — `CreationEngine` class (~530 lines):

**Constructor:** Takes `SpeciesRegistry` and `SkillRegistry`. Creates `CreationState` and defaults to Human species.

**`process_input(text)`** — Returns `(display: str, prompt: str, is_done: bool)`:
- Dispatches to handler methods based on first word
- All handlers return the same tuple shape
- `is_done` is True only from `_cmd_done()` after passing validation

**Undo system:** `_push_undo(label)` creates a `_Snapshot` with deep copies of name, species_name, attributes, and skills. Stack capped at 20 entries (FIFO eviction). `_cmd_undo()` pops the latest snapshot and restores state.

**Attribute matching:** `_match_attribute(text)` matches any unique prefix. `"dex"` → `"dexterity"`, `"p"` → `"perception"` (if unambiguous). Also matches Force attributes: `"con"` → `"control"`, `"sen"` → `"sense"`, `"alt"` → `"alter"`.

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

