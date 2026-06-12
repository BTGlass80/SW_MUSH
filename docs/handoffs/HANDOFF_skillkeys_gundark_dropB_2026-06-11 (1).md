# HANDOFF — Skill-key unification → Gundark Drop B (weapons band)
## Session 2026-06-11 · Drops 1–2 · Rollup: `SW_MUSH_drops1-2_rollup_2026-06-11.zip` (11 files)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then `run_all_tests.bat`.

**Decisions in from Brian this session:** (a)=**b** — Kayson teaches the full lawful Avail 1–3 set;
q55 components + difficulty gate Avail-3; Drop G adds R/X enforcement only. (b)=**a** — `demolitions`
(already a registered Technical skill) is ordnance's skill_required; **Drop D is unblocked.** Both
recorded in TODO `design_calls_resolved_recent` (`CRAFT.avail_cutoff_and_demolitions`).

---

## 1. Drop 1 — Skill-key resolution unification (P0-class, found in Drop B pre-flight)

**Reproduced live before claiming:** a PC with Blaster Repair 3D + Technical 3D crafting a blaster
rolled **2D raw Perception**. Two key dialects, zero translation: space-form (registry, chargen,
train, MISSION_SKILL_MAP, combat literals) vs underscore-form (every schematic `skill_required`;
46× `melee_combat:` / 43× `first_aid:` NPC yaml blocks). Cross-dialect lookups resolved untrained
AND `_skill_to_attr` fell to its `"perception"` default. Consequences at HEAD: crafter training has
never counted; technical-mission rolls ignored Space Transport Repair training (plural/singular
drift); **every melee_combat-keyed NPC attacked and parried at raw attribute.**

**Fix:** `engine.character.canonical_skill_key()` (underscores→spaces + sanctioned aliases:
`computer_prog`, plural-transport, `pickpocket`) routed through BOTH resolution surfaces —
`SkillRegistry.get`, `Character.get_skill_pool` (+ miss-path canonical scan for NPC dicts),
`advance_skill`, `perform_skill_check` ingress, `_get_skill_pool`, `_skill_to_attr` (+ sanctioned
`craft lightsaber`→technical), and the `train` write-site (no split-key dicts now that the registry
accepts both forms). 22 tests in `tests/test_skill_key_resolution.py`, including the
**whole-catalog gate**: every `skill_required` must resolve to a registered skill or the sanctioned
set — this is what makes rubric mass-application safe from Drop B onward.

**⚑ WINDOWS WATCH ITEM — deliberate behavior change.** Melee/multi-word-skill NPC pools correctly
JUMP; craft and mission rolls now include training. Any suite test pinning the old untrained rolls
was pinning the bug and will flip — expect candidates in combat-balance and mission-outcome pins.
Sandbox combat/skill batches (test_combat_mechanics, test_skill_checks_unit,
test_drop_h_combat_npcs) are green, but the 7,700-test Windows run is the real gate.

## 2. Drop 2 — Gundark Drop B: lawful Avail 1–3 weapons band

14 schematics + 14 weapons.yaml rows, §5 rubric mass-applied, difficulties **recomputed in-test**:

| Band | Items |
|---|---|
| Avail 1 (q25) | vibro-saw · DL-22 pistol (4D+1) · DL-6H heavy (5D at standard-pistol range) |
| Avail 2 (q40) | Talon vibrodagger · stun gauntlets (brawling) · contact stunner (**stun_only**) · auto-caster (missile weapons) · B22 hold-out · X-45 sniper · Firelance rifle · BT-500 riot gun |
| Avail 3 (q55) | Sat'skar (STR+3D+1) · Coyn'skar · Sevari flash-pistol (firearms; first `chemical`-component weapon) |

All Kayson-bound per (a)=b. New use-skills `missile weapons`/`firearms` are registered and
combat-routed (pinned). Drop A gap fixed in passing: vibrorapier was missing its book melee
`difficulty: moderate` (the loader key combat consumes). `weapon_type: firearms` added to the
vocabulary — scars already had a keyed branch.

**Deliberately absent (mandate, deferred not forgotten):** dart-shooter payloads + wrist-caster →
Drop F (conceal/scan loop) · flechette/micro-grenade/rocket blast handling → Drop D · deck-arc and
combo weapons · Quickfire-4/Renegade curated out (4a near-duplicates).

Tests: `tests/test_craft_p2_gundark_drop_b.py` (14).

## 3. Verification state

- **Sandbox:** 273 targeted green — craft core 121 (P0 35 · P2A 18 · P2B 14 · crafting_state 8 ·
  untangle 15 · stragglers 9 · skill-keys 22) + syn6c 40 · TODO/CHANGELOG hygiene 9 · skill-check
  units + combat batches 103. AST on all touched modules; YAML on both data files; rollup
  round-trip verified from a clean tree.
- **Windows:** drops 1–2 NOT yet validated — next `run_all_tests.bat` is the gate. Watch: the
  drop-1 behavior change above; `test_skill_key_resolution` (22); `test_craft_p2_gundark_drop_b`
  (14); plus the still-pending drops 7–8 browser walk from last session (crafting panel
  end-to-end, `stim me with medpac`).

## 4. The market-segmentation thought (logged: `CRAFT.market_segmentation`, pending your letter)

Your instinct maps cleanly onto availability tiers, and most of the machinery already points this
way (crafted quality scaling, npc_refuses_buyback, player shops needing inventory worth selling).
**Recommendation (a):** Avail-1 = vendor-stocked at book cost AND craftable — the new-player floor
and a credit sink; **Avail-2/3 = not routinely vendor-stocked** — craft/loot/player-shop supply, so
crafters ARE the lawful supply chain; Avail-4/X = the Drop G black-market loop. One caveat before
applying: audit existing shop stock for Avail-2+ items already live (e.g. `heavy_blaster_pistol`)
and decide grandfather-vs-withdraw explicitly — no silent inventory rips. **Nothing in Drops C–F is
blocked on this** (they're craft-side only; vendor placement is separate data in Lane C/Drop G).
Letters: a = adopt as above · b = full overlap instead · c = discuss.

## 5. Queue

1. **Brian:** suite run (watch items above) + the outstanding crafting-panel browser walk.
2. **`CRAFT.market_segmentation`** letter.
3. **Gundark Drops C–F** (now C–F: B shipped, D unblocked): C armor + armorer trainer · D ordnance
   (`demolitions`) · E field gear (restraints stay HOOK-gated out) · F espionage kit (force
   detector stays HOOK-gated out). Drop G last.
4. `WEBIFY.commissary_vendor_mode` (can jump ahead) · `CRAFT.HOOK.restraints` /
   `CRAFT.HOOK.force_detector` design passes · then Lane C remainder + Lane F, Kamino, Drop-5
   farming controls.

## 6. Session learnings

- **Pre-flight grep catches what handoffs can't.** The dialect split survived eight prior drops of
  green suites because untrained fallback never crashes — it just quietly rolls the wrong dice.
  Symbol-level verification before mass-applying a convention (here: `skill_required` form) is the
  difference between 14 new schematics that work and 14 more that don't.
- **A "pinning the bug" class exists:** when fixing silent-fallback bugs, expect downstream tests
  that encoded the broken numbers. Flag the flip direction in the handoff so suite triage is
  five minutes, not an afternoon.
- **Loader-key archaeology:** weapons.yaml melee difficulty loads from `difficulty:` (not
  `melee_difficulty:`) — and Drop A's vibrorapier silently lacked it. When a dataclass field and
  its yaml key differ, check every prior row.
