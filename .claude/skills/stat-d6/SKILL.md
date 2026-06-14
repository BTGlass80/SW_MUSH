---
name: stat-d6
description: >-
  WEG R&E D6 statting + content procedure for SW_MUSH. Use whenever you author,
  re-stat, or balance an NPC, creature, droid, vehicle, starship/ship, weapon,
  armor, or item; assign or verify a dice code (ND / ND+P); set a credit reward,
  cost, or skill-check difficulty for a piece of content; or look up a D6 rule,
  stat, or table. Surfaces the provenance / dice-code / funnel-function / era /
  phantom-consumer rules and the WEG40120-lookup procedure so inline D6 work in the
  main session follows the same canon the content-author agent uses for bulk
  authoring. Not for wiring an existing adjust_credits / perform_skill_check call
  site in engine code where no new stat or value is being set.
---

# Statting & content to WEG R&E D6

This is the canon for any D6 number that lands in the game from the **main
session** working inline. For **bulk / parallel** authoring (one zone or catalog
at a time, in isolation), delegate to the **content-author** agent instead — it
carries this same procedure; this skill is its main-context counterpart.

Every rule below is a hard invariant. Verify against HEAD; never assume.

## 1. Provenance → re-stat from scratch

**WEG R&E D6 mechanics only.** WotC/Saga/d20 sources are **lore-only**. Re-stat
every creature/item/NPC to D6 from the sourcebook — never port a non-D6 stat.
Verify each entry's provenance at build time and state it in your report.

## 2. WEG40120 is the mechanics authority — the lookup procedure

`docs/sourcebooks/WEG40120.pdf` (+ its OCR sidecar `WEG40120.txt`) outranks every
extraction, design doc, and CLAUDE.md. Sourcebooks are **gitignored / local-only**
on Brian's box — if they're absent in this tree, say so and cite the rule as
UNVERIFIED rather than inventing a number. To use it:

1. **Find** the rule/dice code/table by grepping the sidecar
   `docs/sourcebooks/WEG40120.txt` (it carries dice tokens like `4D+1`, `3D+2`).
2. **Verify** the dice codes and table values **against the PDF page itself** —
   the sidecar is OCR-grade and mangles pips, columns, and table alignment.
3. **Cite** the value as confirmed against the PDF page/section, not the sidecar.

Dice codes are `ND` or `ND+P` (e.g. `4D+1` = four dice plus one pip). Quicker
in-repo orientation (not a substitute for the PDF): `docs/dev/internals_01_weg-d6-core-mechanics.md`.

## 3. Funnel functions are mandatory

Never move a value directly — always through its funnel:

- **Credits** → `adjust_credits(char_id, delta, "source_tag")`
  — chokepoint at `db/database.py` (`adjust_credits`). Do **not**
  `save_character(credits=...)`.
- **Out-of-combat dice** → `perform_skill_check(...)` — `engine/skill_checks.py`.
- **Territory influence** → `adjust_territory_influence(db, org_code, zone_id, ...)`
  — `engine/territory.py`.

**Faucets and sinks land together.** Any new credit *faucet* (reward, payout,
loot) ships in the **same drop** as its corresponding *sink*. Don't add one
without the other.

## 4. `force_sensitive` is DERIVED — never a save kwarg

`force_sensitive` is reconstructed from the presence of `control` / `sense` /
`alter` keys in the attributes blob. NEVER pass `force_sensitive=` to
`save_character` — its writable-column allowlist (`_CHARACTER_WRITABLE_COLUMNS`
in `db/database.py`) will reject it. Author the Force-skill keys; let the engine
derive the flag. (A content NPC YAML *may* carry a `force_sensitive:` field that
`engine/npc_loader.py` reads into the sheet — that is the loader's input schema,
not a `save_character` column.)

## 5. No phantom data — match a live consumer

Before authoring any data entry, **grep the loader that reads the target file**
and confirm every field you write is one it already consumes. Mirror a sibling
entry's exact shape. Do not invent a field hoping code will read it later.

- NPCs → `engine/npc_loader.py` (produces the
  `(name, room_idx, species, description, sheet, ai_config)` tuple; honors the
  `replaces:` overlay protocol). Copy 2–3 sibling rows from a
  `data/worlds/clone_wars/npcs_*.yaml` file as your template.
- Items / equipment → `engine/items.py` (`ItemInstance`; per-slot equipment via
  `read_equipment` / `equipment_keys` / `write_equipment`).
- Skill keys: author the dialect siblings use (NPC blocks are underscore-form,
  e.g. `melee_combat:`); the engine canonicalizes via `canonical_skill_key()`.

If the content needs a field with **no consumer**, STOP — that's an engine/design
dependency. Report it; don't ship dead data.

## 6. Era cleanness (B3) — Clone Wars ~20 BBY

No `Imperial` / `Empire` / `Rebel` / `TIE` in any player-facing string (comments
and era-mapping keys are exempt). Canonical Clone Wars figures (Kenobi, Skywalker,
Dooku, Grievous, Palpatine, Jabba-by-name, …) NEVER appear as open-world NPCs —
reference factions institutionally ("a Hutt kajidic", "Republic Judicial") and
invent original named characters. Sanctioned do-not-touch surfaces:
`village_trials.py` dark-future-self prophecy; director-axis model codes
`imperial`/`rebel` (zone-tone keys, not org codes).

## 7. Balance sanity

Stat new combat gear against the existing band rubric — don't out-class the curve.
Flag anything that would be best-in-slot for review rather than shipping it.

## 8. Validate before handing back

- Every touched YAML must parse:
  `python -c "import yaml; yaml.safe_load(open(r'<file>', encoding='utf-8'))"`.
- Run the file's validator if one exists:
  - tutorial chains → `python tools/verify_tutorial_chains.py`
  - player guide / help prose → `python tools/guide_lint.py`
  - a new parser command → `python tools/audit_cmd_registry.py` (collisions)
- Add/extend a targeted test for the consumer; run it (`python -m pytest tests/<module> -x`).
- AST-check every touched `.py` (`python -m py_compile <file>`).

Report: files touched, the consumer that reads each field (proving no phantom
data), WEG40120 provenance citations, faucet/sink pairing, and any balance flags.
