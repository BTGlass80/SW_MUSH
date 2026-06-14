# HANDOFF — Era-Cleanness Sweep Inventory (parallel session → main session)

> ## ⚠️ POINT-IN-TIME — captured at commit `254b7e1` (Drop 42). MAY BE SUPERSEDED.
> The session ships multiple drops/day; violations here may already be fixed or shifted by
> drops landed since. **Re-grep each file:line against HEAD before the fix drop.** Head-start,
> not current truth.

> Read-only audit at commit **`254b7e1` (Drop 42)** for `T2.CW.codebase_era_sweep`. The
> apply-this list of every TRUE Imperial/Empire/Rebel/TIE violation in CW production strings,
> with sanctioned exemptions pre-cleared so the fix drop doesn't churn legitimate code.
> Re-verify file:line against HEAD before editing (you move between drops).

## TL;DR — 44 token hits, only 5 are real violations

Swept engine/*.py + parser/*.py (web/guides/help came back clean of new violations; data YAML
was out of this lane's scope — see "remaining" below). Classification:

| Class | Count | Action |
|---|---:|---|
| **VIOLATION** | **5** | fix (4 trivial + 1 needs Brian) |
| sanctioned-exempt | 10 | do not touch (village_trials, lint-era-ok prose) |
| GCW-config | 3 | do not touch (`_REGION_ANCHOR_TEMPLATES['empire']` etc.) |
| comment-or-key | 25 | do not touch (director-axis codes, era-map comments) |
| false-positive | 1 | n/a |

The 39 non-violations are correctly exempt — a naive grep-and-replace would have wrongly
rewritten all of them. **Note:** the `engine/territory.py:785` "Empire's presence" string I
flagged during the guide work is NOT in the violation list — it's keyed under the director-axis
`"empire"` model code; the audit found the *actually-reachable* CW headlines are the director.py
ones below instead. (Worth a second look at whether territory.py:785 is reachable — but the
director.py headlines are the confirmed live path.)

## 🟢 SAFE TO INTEGRATE NOW — 4 trivial string swaps (zero design ambiguity, zero collision)

All in `engine/director.py` zone-state narration (`_generate_local_headline` + the LAX
security-shift notification). Verified present at HEAD. One edit cluster, one drop:

| file:line | token | current | → CW fix |
|---|---|---|---|
| `director.py:1755` | Imperial | `weak Imperial presence` | `weak authority presence` |
| `director.py:1782` | Imperial | `Imperial forces maintain lockdown in …` | `Security forces maintain lockdown in …` |
| `director.py:1786` | Rebel | `Rebel sympathizers grow bolder in …` | `Separatist sympathizers grow bolder in …` |
| `director.py:1788` | Imperial | `Imperial presence wanes in …` | `Authority presence wanes in …` |

Pure string swaps, no signature/behavior change. Add a test asserting `_generate_local_headline()`
+ the LAX shift notification emit no Imperial/Rebel token under `clone_wars` era. **`director.py`
is clean and disjoint from your crafting lane — ship anytime.**

## 🔴 STOP + RECONCILE — `stormtrooper`/`imperial_officer` archetype RESIDUE (DELETE, not gate)

**CORRECTED (Brian, 2026-06-13):** GCW retirement already happened — so `stormtrooper` and
`imperial_officer` are **stranded residue retirement missed, with NO legitimate consumer in a
CW-and-era-agnostic-only game.** The fix is **DELETE the archetypes and their references**, NOT
era-gate them (the original "fold into GCW-retirement / log a design call" framing was wrong —
the retirement decision is already made). Confirmation that this is the project's own intent:
the SPA tests ALREADY assert these tokens must never appear (`tests/spa/test_m3_*.py`:
"No Empire/Imperial/Rebel/TIE/Stormtrooper/Vader") — the web client is guarded; the engine
just never got the same scrub.

**Why retirement missed it:** `bounty_board.py:84-90` miscategorizes them — the comment
`# ── GCW / era-agnostic ──` lumps `stormtrooper`/`imperial_officer` in WITH genuinely
era-agnostic `thug`/`smuggler`/`scout`, so a GCW-tree deletion didn't catch them.

**The residue is WIDER than this audit's engine lane reported — full map (verified HEAD):**

| file:line | what | action |
|---|---|---|
| `engine/npc_generator.py:63-76` | `"stormtrooper"` NPCArchetype def (name="Stormtrooper") | DELETE the archetype |
| `engine/npc_generator.py:77-90` | `"imperial_officer"` NPCArchetype def (name="Imperial Officer") | DELETE the archetype |
| `engine/bounty_board.py:84-90` | both in `FUGITIVE_ARCHETYPES` pool | REMOVE both entries + fix the misleading comment |
| `engine/bounty_board.py:27` | both named in the module docstring | update docstring |
| `engine/npc_combat_ai.py:59,61` | combat-behavior map for both | DELETE both rows |
| `engine/npc_combat_ai.py:84,86` | weapon map for both | DELETE both rows |
| `engine/npc_crew.py:208` | `imperial_officer` in an `archetype_pool` | REMOVE from pool (replace w/ a CW/agnostic archetype) |
| **`engine/territory.py:89`** | **player-facing room-watch flavor: "A stormtrooper in scuffed white armor stands watch…"** | **REWRITE to a CW guard (clone trooper / sector security) — this is a live player-read string the audit's engine lane MISSED** |
| `parser/npc_commands.py:929` | `"stormtrooper"` in an admin `@spawn` list | REMOVE (or leave if admin-only + Brian wants spawnable — confirm) |

**This is a DELETION/SCRUB drop, not a behavior-gate and not a design fork.** No Brian design
call needed on disposition (retirement already decided it) — the only judgment is the
`npc_commands.py:929` admin-spawn line (keep for admin testing, or scrub for full cleanness?).
Add a guard test: no `stormtrooper`/`imperial_officer` archetype key resolves and no
"Stormtrooper"/"Imperial Officer" name is generated in ANY era (they're gone, not gated).

**Note:** `territory.py:89` is the genuinely player-facing one (a room description), arguably
higher-priority than the bounty path — and it confirms the audit's engine lane under-scoped
this residue (it found the bounty path but missed npc_combat_ai, npc_crew, and territory.py).

**BRIAN CALL** (genuine fork): filter-at-pool vs. remap-at-spawn vs. retire imperial_officer/
stormtrooper into the GCW-retirement bucket. Per the `organizations.py` EQUIPMENT_CATALOG
precedent, this likely **folds into GCW-retirement** rather than landing as a one-off. Suggest
logging `design_calls_pending_brian`: *"CW bounty/fugitive board can spawn GCW Imperial
Officer/Stormtrooper NPCs — gate pool by era, remap, or fold into GCW-retirement?"*

## Exemptions confirmed (the fix drop must NOT touch these)

- **village_trials.py** dark-future-self prophecy — sanctioned do-not-touch.
- **director-axis model codes** `imperial`/`rebel` (zone-tone influence keys, not org codes):
  `director.py:218-223` AlertLevel enum comments, `director.py:512/1659/1660/1718/1723` rule
  comments, `security.py:7/24/319/332` — all axis-key references.
- **GCW config tree**: `contest.py:1005-1030 _REGION_ANCHOR_TEMPLATES['empire']/['rebel']`
  (GCW-keyed, only reachable in a GCW contest); `npc_crew.py:206` GCW LocationProfiles.
- **Era-map keys + comments**: `bounty_board.py:159` docstring, `missions.py:1026`,
  `organizations.py:354/670/1197/1198/1320`, `npc_generator.py:184`. The GCW
  `_CRIME_DESCRIPTIONS`/`_POSTING_ORGS` pools (`bounty_board.py:108-127`) ARE era-gated —
  CW players get `_CW_*` pools via `_get_crime_descriptions()`/`_get_posting_orgs()`.
- **lint-era-ok / self-documenting prose**: `dsp_hunter.py:23`, `encounter_patrol.py:34/399/624`,
  `npc_space_traffic.py:1297/409`.

## Remaining (out of this sweep's scope — flag for a follow-up sweep)

- **Data YAML** (`data/worlds/clone_wars/**/*.yaml`) was NOT in this lane (engine/parser only).
  An earlier check found ~11 clone_wars data files with era tokens; a data-YAML sweep should
  run before the fix drop closes the item. The GCW data tree is RETIRED, so any clone_wars/
  data hit is a real candidate (no GCW tree to absorb it).
- **organizations.py EQUIPMENT_CATALOG** Imperial gear — known, folds into GCW-retirement
  (not a standalone fix), per the existing TODO note.

## Collision note

No hard collision. The 5 violations live in `director.py` (Director narration) and
`npc_generator.py`/`bounty_board.py` (NPC spawn) — none are crafting modules or world YAML, so
they're disjoint from your current crafting + world-building lane. **Minor adjacency:**
`npc_generator.py`/`bounty_board.py` are shared NPC-spawn deps; if a world-building drop adds
encounters touching archetype pools, coordinate timing on the fugitive-pool fix so two edits
don't both rewrite `FUGITIVE_ARCHETYPES`. The `director.py` cluster is fully clear to land solo.

## Recommended drop shape
- **Ship now (no fork):** the 4 `director.py` string swaps + test.
- **Ship now (no fork — CORRECTED):** the `stormtrooper`/`imperial_officer` residue DELETION
  (9 sites above). GCW retirement is done, so disposition is already decided — this is cleanup,
  not a design call. Only the `npc_commands.py:929` admin-spawn line is a judgment call
  (keep for admin testing vs. full scrub). Land with a guard test that the two archetype keys
  resolve nowhere and their names generate in no era.
- These two can be ONE "finish-GCW-retirement residue scrub" drop. The only thing that was a
  Brian call (the admin-spawn line) is minor.

*Full 44-hit classified inventory in workflow task `wfej44gjp.output`. NOTE: the audit
originally framed the archetype residue as a "fold-into-GCW-retirement design fork"; Brian
corrected this — retirement already happened, so it's a deletion. The audit's engine lane also
UNDER-SCOPED the residue (missed npc_combat_ai, npc_crew, and the player-facing territory.py:89
room string) — the table above is the corrected, fuller map.*
