# Command Syntax Rework — Catalog Snapshot

> ## ⚠️ POINT-IN-TIME SNAPSHOT — RE-VALIDATE BEFORE USING
> This catalog was captured at **commit `294679b` (Drop 36), 2026-06-13**. The command
> surface is under **active parallel development** — at capture time `parser/space_commands.py`
> and `parser/scene_commands.py` were mid-edit by the other session. Commands have almost
> certainly been **added, removed, or renamed** since.
>
> **Treat this as a head-start, not ground truth.** Before executing any rename drop:
> 1. Re-grep HEAD: `grep -rn 'key = "' parser/*.py` and diff against this catalog.
> 2. Re-confirm the baseline counts below; if they've drifted, new commands exist that
>    aren't catalogued here — catalog them before proceeding.
> 3. Re-verify each `file:line` (line numbers drift with any edit to the file).
>
> The goal of this snapshot is to make the future pass **faster** (the classification +
> rename decisions are pre-thought), not to be authoritative. The taxonomy rules and the
> rename *logic* (in `command_syntax_rework_spec_v1.md`) are durable; the specific
> command LIST is what goes stale.

**Baseline counts at capture (for staleness detection):** no-prefix **170**, `+` **103**,
`@` **63** = **336** total command keys across `parser/*.py`. If a future `grep` shows
different totals, the surface has changed since this snapshot.

Companion to `command_syntax_rework_spec_v1.md` (the durable approach/spec). This file is the
disposable, re-generatable data layer.

---

## Catalog summary (283 commands, 8 domains, captured at Drop 36)

> The full per-command rows live in the workflow result
> (`tasks/w4ssi83tt.output`, 283 rows with file:line). This doc holds the actionable
> summary; regenerate the rows by re-running the catalog workflow against HEAD.

**By classification:**

| Classification | Count | Meaning / action |
|---|---:|---|
| `game-needs-plus` | 125 | bare game-system command → gets `+` |
| `already-correct-plus` | 82 | already `+` — many have a BARE DUPLICATE to delete (see below) |
| `admin-at` | 33 | already `@` — leave alone |
| `social-keep-bare` | 24 | IC verbs — STAY bare (incl. Brian's look/examine/move ruling) |
| `switch-candidate` | 13 | multi-sub-verb command → fold sub-verbs into switches |
| `run-on-collapse` | 6 | "German word" verb+noun token → parent `+`/switch |

**By domain:** SHIP/PILOTING 61, ADMIN/@ 49, builtin 39, faction/city/medical/etc 36,
channels/scene/places/narrative 33, crafting/econ/smuggle/spy 26, COMBAT 22, mission/bounty/quest 17.

## GOVERNING RULING (Brian, 2026-06-13)

**Embodied IC verbs stay BARE; invoking a game SYSTEM gets `+`.** Confirmed bare:
`look`, `examine`, `move` (+ compass directions, `enter`/`leave`), `get`/`drop`, and all
speech (`say`/`pose`/`emote`/`page`/`ooc`/`whisper`/`think`). `+` for sheet/faction/craft/
bounty/mission AND combat AND ship/piloting (operating a system, even diegetically).

## KEY FINDING — ship is HALF-MIGRATED (finish + delete, not add)

`parser/space_commands.py` already has umbrella `+` commands (`+pilot` :6426, `+gunner` :6518,
`+sensors` :6589, `+bridge` :6680, `+ship` :1420) **AND their bare duplicates as SEPARATE
command classes** (`pilot` :732, `gunner` :772, `scan` :1961, `fire` :2324, `close` :2893,
`fleeship` :2964, …). So Batch 2 is mostly **finish the migration: delete the ~24 redundant
bare/separate classes** whose function already exists as an umbrella switch — not add new `+`.
Also a 3-way repair duplication: `+shiprepair` :1160, `+ship/repair` :1462, `damcon` :4296.

## CHAIN COUPLING — the critical execution discipline

Because this is a CLEAN RENAME (no kept aliases), a chain `command_executed:` string that
references a dropped key/alias is now a **HARD break**. Each must be updated IN THE SAME DROP
as the rename. Verified couplings (`data/.../tutorials/chains.yaml`):

| Chain string | Steps (line) | HEAD key | Action |
|---|---|---|---|
| `examine` | 314, 1075, 1246, 1895 (4) | `examine` bare (village_trial:219) | **STAYS BARE** (Brian ruling) → NO update needed ✓ |
| `say` | 289, 733 (2) | social, bare | stays bare → safe ✓ |
| `+factions` | 7 steps | already `+` | safe ✓ |
| `+sheet` | 4 steps | already `+` | safe ✓ |
| `+craft` | 1279 | already `+` (bare `craft` dupe to delete) | chain uses `+craft` → safe ✓ |
| `scan` | 1742 (1) | `scan` bare → `+sensors/scan` | **UPDATE chain string in Batch 2** |
| `search` | 1590, 2047 (2) | ALIAS of `investigate` (espionage:240) | **UPDATE in-drop** — alias drop breaks it |
| `meditate` | 1436 (1) | ALIAS of `+meditate` (:95) | **UPDATE to `+meditate` in-drop** — latent break on alias-strip |
| `give` | 1162 (1) | `give` bare (builtin:4596) | if `give`→`+give`, update in-drop (else stays bare) |

Net: Brian's "examine stays bare" ruling REMOVED the largest chain-coupling risk (4 steps).
Remaining in-drop updates: `scan`, `search`, `meditate` (3 strings) + `give` if re-prefixed.

## FORKS still needing Brian (smaller, post-ruling)

- **`+bridge` umbrella scope:** 14 station verbs (commander/vacate/assist/coordinate/shields/
  damcon/hail/comms/… + engineer/navigator) proposed to collapse into ONE `+bridge`. Confirm
  single parent, OR split `engineer`/`navigator` into their own umbrellas. (`engineer`/`navigator`
  are bare-only today — the `+bridge/engineer` target is a catalog guess.)
- **Duplicate `order` across modules:** `space_commands.py:4955` (NPC combat orders) vs
  `crew_commands.py:408` — same command or two systems? Affects the `+bridge/order` rename.
- **Run-on canonical names (axis 3):** confirm targets for the cross-module run-ons —
  `questcomplete`/`completequest` (narrative:266) → `+quest/complete`?; `collectbounty`/
  `bountycollect` (bounty:326) → `+bounty/collect`?; `buyresources` (crafting:1593) → `+buy`?
- **`give`/`get`/`drop`:** Brian ruled `get`/`drop` bare (IC handling). Confirm `give` also bare
  (it's IC hand-off) — recommendation: yes, bare. Then no chain update for `give`.

## BATCH PLAN (clean-rename; no alias-backfill batch)

Each batch is one additive-style drop with a GUARD test: *no chain `command_executed` string,
help_text key, or test assertion references a dropped key* (a dangling ref is now a hard break).

| Batch | Scope | ~Count | Chain updates in-drop |
|---|---|---:|---|
| **1** | Combat (`combat_commands.py`) → `+attack`/`+dodge`/… | ~22 | none |
| **2** | Ship: finish half-migration, DELETE ~24 bare duplicate classes, add ~7 standalone `+` | ~41 | `scan`→`+sensors/scan` |
| **3** | Run-on collapse + dedupe (in-slice 10 + cross-module questcomplete/collectbounty/buyresources) | ~15 | none |
| **4** | Remaining game-system (mission/craft/medical/bounty/builtin) | ~49 | `search`, `meditate`, (`give`?) |
| **5** | Switch normalization (axis 4): `+city`/`+faction`/`+mission`/`@director` sub-verbs → switches | ~13 | none |

THEN the help/guide doc rework documents the final syntax.

## How to use this (re-read the staleness banner at top first)

1. Re-grep HEAD, diff against the 283-row baseline; catalog any new commands.
2. Pick the batch; re-verify its rows' file:line.
3. Apply the renames + the in-drop chain updates from the coupling table.
4. Add the guard test. Run targeted tests + chain reachability invariant.
