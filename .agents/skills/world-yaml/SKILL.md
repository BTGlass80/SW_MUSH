---
name: world-yaml
description: >-
  Safe-editing procedure for SW_MUSH world / map data. Use whenever you edit any
  file under data/worlds/ — planet exit graphs, map room placement, NPC/zone/quest
  YAML, era.yaml — especially any file carrying map_x/map_y room coordinates
  (planets, maps, wilderness). Covers the additive-only invariant, comment-preserving
  string-replacement technique, the pinned-coordinate golden-snapshot guard, and
  which validator to run after. Edit this way the first time so you don't trip the
  additive hook or the snapshot guard.
paths:
  - "data/worlds/**/*.yaml"
---

# Editing world / map YAML safely

World YAML is navigation- and snapshot-critical. The PreToolUse
`world_yaml_additive_guard.py` hook will **hard-block** (exit 2) any edit that
net-deletes lines from any YAML under `data/worlds/` (the whole world tree —
widened 2026-06-12 from just planets+maps to include quests, wilderness,
jedi_village, tutorials). This skill is how you edit correctly so the hook never
has to fire and the golden-snapshot guard stays green.

## Hard rules

1. **Purely additive — zero deleted lines.** Add entries; do not remove or
   restructure existing ones. A net-negative line delta on a guarded file is
   blocked at the tool layer.

2. **Comment-preserving string replacement only — NEVER a yaml round-trip.**
   Do not `yaml.safe_load(...)` then `yaml.dump(...)`: that strips comments,
   reorders keys, and reflows the file, which trips the golden-snapshot guard and
   produces a massive phantom diff. Edit via a surgical string `Edit` that inserts
   or appends, preserving surrounding comments, key order, and formatting.

3. **Don't move pinned coordinates.** Exterior surface rooms are pinned by a
   coordinate golden-snapshot guard. Never change an existing room's `x`/`y`.
   Compass-word (`exits[].forward` / `exits[].reverse`) must agree with map x/y
   geometry — "go north" moves the marker *up*. If you add exits/rooms, keep them
   geometry-consistent.

4. **Match a live consumer (no phantom data).** Every field you add must be one a
   loader already reads — e.g. NPCs via `engine/npc_loader.py`, the `era.yaml`
   `content_refs` lists, tutorial chains via the chains schema. Mirror a sibling
   entry's exact shape; don't invent fields. (See the **stat-d6** skill for the
   full content/consumer + WEG-D6 statting procedure.)

5. **Replacement overlays** use the `replaces:` protocol — follow the existing
   pattern when an era-keyed entry supersedes a GCW one.

## Validate after editing

- Parse: `python -c "import yaml; yaml.safe_load(open(r'<file>', encoding='utf-8'))"`.
- Map / exit-graph edits → `python tools/check_map_cardinals.py` (verifies every
  edge's forward AND reverse compass word against map x/y; `--derive` proposes
  geometry-consistent words, collision-aware — review, don't blind-apply).
- Tutorial chains → `python tools/verify_tutorial_chains.py`.
- Run the file's golden-snapshot / build test targeted if one exists.

For **bulk** world authoring across several zones, delegate to the
**content-author** agent (one agent per disjoint file set) rather than editing
many files inline.
