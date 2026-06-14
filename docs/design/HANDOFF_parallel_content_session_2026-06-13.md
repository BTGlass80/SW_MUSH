# HANDOFF — Parallel session (content / defect-hunt lane) — 2026-06-13

> For the CONTINUATION chat of this parallel session. The MAIN session migrated
> separately (Director scope + workflow handoff). Read this, then continue in
> the worktree below. Everything here is verified against HEAD at write time.

## TL;DR

Three parallel-safe drops shipped to `origin/main` this session, each
full-suite-gated. All are the same theme: **a referenced thing with no
producer / a flag cleared from the wrong slot — bugs the confirmatory suite
missed.** Found via two discovery workflows + one adversarial break-it pass,
each finding independently re-verified at HEAD before fixing.

`origin/main` @ **`83a59b8`** at handoff.

| # | Drop | Commit | What |
|---|------|--------|------|
| 1 | wilderness phantom creatures | (in main @ `8e1e593`, integrated by main session from the shared tree) | 4 encounter `npc_template` refs (`dewback`, `tusken_warrior`, `maze_predator`, `underworld_thug`) didn't resolve → encounters fired narrative, spawned nothing. +4 WEG-D6 creatures + a global resolution guard (`tests/test_wilderness_encounter_template_resolution.py`). |
| 2 | chain combat-fallback stranding | `45cee83` | `separatist_agent` step 4 "Talk past Republic Security": fail-the-bluff `combat_won` fallback keyed to `republic_security_officer`, but no NPC carried that `chain_enemy_template` tag → fight path uncompletable. Tagged Daln + new reachability **CLASS 5** (combat_won enemy_template → tagged NPC). |
| 3 | questline graduation re-fire | `83a59b8` | `chain_graduation.py::execute_pending_teleport` success-path `_clear_pending` (line 419) omitted `pending_state_key` → a **questline** graduation's pending flag (in `active_questline`) never cleared → "training complete" flavor + synthetic look re-fired on **every** command until restart. One-line fix + regression test. |

Gate at handoff: **9222 passed**, 1 failed = the documented `republic_soldier`
chain-walkthrough **flake** (confirmed passing solo; it's a parallel-load
flake, not any of these drops), 24 skipped, 5 xfailed, in ~4:24.

## Where to work (git / worktree model)

Per Brian's 2026-06-13 ruling, sessions use **per-session git worktrees** off
`main` and each commits its own drops. See memory `parallel-session-worktrees`.

- **This session's worktree: `C:/SW_MUSH_wild` on branch `opus-parallel`.**
  Resume here. It's at `83a59b8` (== origin/main at handoff), clean except
  untracked `_gate*.log` scratch files (ignore/delete them).
- Other live worktrees (do NOT edit): main session `C:/SW_MUSH_dev@opus-wt`
  and `C:/SW_MUSH_dir@drop/director-economic-nudges`; the legacy shared tree
  `c:\SW_MUSH` (other sessions / strays — don't touch).
- Mechanics (Windows, this harness): Bash cwd resets to `c:\SW_MUSH` each call
  and `cd` alone can prompt — drive the worktree via `git -C C:/SW_MUSH_wild`,
  `cd /c/SW_MUSH_wild && <python/pytest>`, and absolute `C:/SW_MUSH_wild/...`
  edit paths. `git checkout` is denied → stay on `opus-parallel`, commit drops
  sequentially, `git branch -f main <sha>` + `git push origin main` to ff.
- **ff race:** `main` moved 3× while I worked (the integrator session pushes
  often). Before every push: `git fetch origin`, and if `origin/main` !=
  your commit's parent, `git rebase origin/main` first (my 4-file drops never
  conflicted, but CHANGELOG/TODO are the conflict-prone files).

## Gate methodology (IMPORTANT — fixed a real footgun this session)

The full suite **hung at 99%** the first time because (a) no per-test timeout
let a final-shard test stall the whole `-n auto` run, and (b) it was
backgrounded + awaited, so the never-completing task never notified me → I sat
idle ("are you waiting on me?"). Fix, now proven (4:12–4:24 clean):

```
cd /c/SW_MUSH_wild && python -m pytest -n auto --dist loadscope -o addopts="" \
  --maxfail=300 --timeout=120 --timeout-method=thread -q
```

Run it in the **FOREGROUND** with the Bash tool `timeout: 540000` (NOT
backgrounded-and-awaited). Strip `-x` via `-o addopts=""`. The lone expected
red is `test_smoke_chain_walkthrough[republic_soldier]` (solo-passing flake) —
re-run it alone to confirm before treating any red as real. See memory
`threaded-test-methodology` + `xdist-orphan-process-swarm` (TaskStop reaps the
worker tree cleanly; don't blanket-kill python on the shared box).

## Open / deferred (for the continuation)

- **`TD.ENCOUNTER_COUNT_RANGE_IGNORED`** (logged in TODO.json tech_debt, drop 1):
  `creature_library.creature_spawn_count` can't parse a `[lo,hi]` range `count`
  (`int([4,6])` raises → caught → falls back to `pack_count[0]`), so EVERY
  wilderness encounter spawns the pack minimum regardless of its authored range
  (e.g. the six-rider Tusken war party fields 2). The break-it pass
  **independently re-confirmed** this. Fix is a small contained change to that
  pure function (roll `randint(lo,hi)` when count is a 2-list), BUT it raises
  spawn counts galaxy-wide → a conscious **balance decision** for Brian, not a
  drop-in fix. Decide, then ship (parallel-safe: `creature_library.py`).
- **Defect surface status:** the static dangling-reference class is **swept
  clean** — two discovery workflows verified items/loot/schematics/trainers,
  lore/species/dialogue, the safe engine modules, the SPA, and (directly) the
  wilderness terrain/band contracts all resolve. The break-it pass found the
  wilderness-spawn + chain-advance runtime otherwise robust (0 crash / 0
  corruption / 0 leak besides the 2 above).
- **Next-lane candidates** (all parallel-safe, no design call needed): more
  break-it passes on other engine state machines (sabacc / espionage / housing
  / harvest); content depth via the now-guarded seams (band-gated wilderness
  encounters for the thin Coruscant sub-regions; new questlines in `chains.yaml`
  — the quest engine seam is verified additive, see
  `quest_expansion_postlaunch_path_v1.md`). Avoid Session A files (combat,
  items, character, director, missions, security, server/session,
  server/web_portal, ai/claude_provider) and all of `parser/` (Session B).

## Method that worked (repeat it)

Scout/defect-hunt **workflow** (fan-out Explore agents, structured schema,
skeptical triage that discards false positives) → **independently re-verify
each surviving finding at HEAD** (the triage discarded 5 false positives;
2 agents had grep errors) → fix the parallel-safe ones → targeted gate +
full-suite gate → rebase/ff/push → CHANGELOG + TODO + per-drop test in the
same commit.
