# Developer Internals — Guide_07_Crafting.md

Extracted from `data/guides/Guide_07_Crafting.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

### 🔧 Developer Internals

**File:** `engine/crafting.py` — Resource system (lines 78–244):

**`RESOURCE_TYPES`** (line 26): `{"metal", "chemical", "organic", "energy", "composite", "rare"}`

**Storage:** Resources stored in `character["inventory"]` JSON as a list of `{"type", "quantity", "quality"}` dicts under the `"resources"` key.

**`add_resource(char, rtype, quantity, quality)`** (lines 119–149): Finds an existing stack within `STACK_MERGE_TOLERANCE = 5.0` quality points. If found, merges with weighted average quality. Otherwise creates new stack.

**`remove_resource(char, rtype, quantity, min_quality)`** (lines 152–182): Consumes from best-quality stacks first (sorted descending). Atomic — checks availability before consuming. Prunes empty stacks.

**`check_resources(char, components)`** (lines 185–207): Validates all components available before crafting. Returns `(ok, message)`.

**Zone-to-resource mapping:** `get_survey_resources(zone_name)` (lines 455–463):
- Outdoor keywords (jundland, wastes, outskirts, desert, mesa, plains) → `["metal", "organic"]`
- Default (city/indoor) → `["chemical", "energy"]`

**Quality from survey:** `survey_quality_from_margin(margin, is_outdoor)` (lines 466–483):
- Outdoor: base 60, ceiling 90, +2 per margin point
- City: base 30, ceiling 60, +2 per margin point

### 🔧 Developer Internals

**File:** `data/schematics.yaml` (~397 lines, 20 schematics). Each defines: `key`, `name`, `skill_required`, `difficulty`, `trainer_npc`, `components[]` (type/quantity/min_quality), `output_type` (weapon/consumable/component), `output_key`, `base_cost`. Ship components additionally have `stat_target`, `stat_boost`, `cargo_weight`.

**Loading:** `_load_schematics()` (lines 58–65) — Cached singleton. Loads once on first call. Returns `{key: schematic_dict}`.

**Known schematics storage:** `character["attributes"]["schematics"]` JSON list of schematic keys. `get_known_schematics(char)` / `add_known_schematic(char, key)` helpers.

### 🔧 Developer Internals

**`resolve_craft(char, schematic, skill_check_result, experiment=False)`** (lines 318–428):

The function receives a pre-computed `SkillCheckResult` from `perform_skill_check()` (never rolls dice directly — architecture invariant). Resolution path:

1. **Fumble** → Consume materials, return failure
2. **Partial** (not success but margin ≥ −4) → Consume materials, quality ×0.5, no crafter name
3. **Full failure** (margin < −4) → DON'T consume materials, try again
4. **Success** → Linear quality multiplier (margin 0→1.0, margin 10+→1.3), consume materials, stamp crafter name
5. **Critical** → ×1.5 multiplier (or ×2.0 for experiment critical), consume materials

**`average_component_quality(char, components)`** (lines 216–243): Computes weighted average across best-quality qualifying stacks, matching removal order.

**`quality_to_stats(quality)`** (lines 250–258): Maps quality float to item creation stats via `QUALITY_TIERS` lookup.

### 🔧 Developer Internals

Experimentation uses the same `resolve_craft()` function with `experiment=True`. The only difference is `QUALITY_MULT_EXP_CRIT = 2.0` instead of `QUALITY_MULT_CRIT = 1.5` on critical success. The risk of quality reduction on failure is handled by the calling command, which can apply a negative multiplier.

### 🔧 Developer Internals

**File:** `parser/crafting_commands.py` — `TeachCommand`: Validates both players present, schematic known by teacher, not known by student. Calls `add_known_schematic()` on the student's character.

## 9. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/crafting.py` | ~483 | Resource management, schematic loading, assembly/experiment resolution, quality system, survey helpers |
| `parser/crafting_commands.py` | ~560 | 6 player commands (survey, resources, schematics, craft, experiment, teach) |
| `data/schematics.yaml` | ~397 | 20 schematic definitions (8 weapons, 3 consumables, 7 ship components, 2 countermeasures) |
| `engine/skill_checks.py` | ~590 | perform_skill_check() — all craft rolls route through here |
| `data/weapons.yaml` | ~279 | Output weapon definitions (damage, ranges, costs) |

**Total crafting system:** ~1,043 lines of engine/parser code + ~397 lines of data = ~1,440 lines.

---

*End of Guide #7 — Crafting System*
*Next: Guide #8 — Force Powers*

