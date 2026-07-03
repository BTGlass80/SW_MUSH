---
name: lane-partition
description: >-
  Partition a known backlog into conflict-minimized parallel lanes BEFORE you fan
  work out. Use at a decomposition point: authoring a Workflow that fans over many
  tasks, spinning up parallel sessions / git worktrees, or dividing a backlog
  between agents or sessions so their edits do not collide. Given a work-list (open
  TODO items or a supplied list) it predicts each task's file-touch set (from cited
  symbols + a git-history proxy), builds a file-contention graph, and emits N lanes
  whose edits are disjoint (each with an owner), the always-shared-file protocol for
  the high-churn bookkeeping files, cross-lane hazards, and — when overlap is high or
  the backlog is small — a plain "serialize instead" verdict. NOT for a single linear
  task, and NOT a standing task-discovery agent: it runs once, at a planning fork.
---

# Lane partition — carve a backlog into conflict-free parallel lanes

Parallelism is bounded by **file contention + dependencies**, not by the number of
tasks. This skill turns a backlog into lanes whose edits do not collide, so parallel
workflows / sessions spend their speedup on work instead of merge churn — or worse, a
hard conflict on `TODO.json` / `CHANGELOG.md`. Run it once at a decomposition point.
The honest output is often "serialize" — say so.

## The one principle

Two tasks may run in parallel **iff** their file-touch sets are disjoint (minus the
always-shared bookkeeping files, handled by the protocol below) **and** neither
consumes the other's output. Everything else is bookkeeping.

## Procedure

1. **Gather the work-list.** Open `TODO.json` items (`tier_1_active` still ACTIVE,
   `tier_2_queued`, `design_calls_pending_brian`, OPEN `tech_debt`) or the supplied
   list. Each candidate is `{id, one-line intent}`.
2. **Predict each task's FILE-TOUCH SET — conservatively; over-predict.** A missed
   file is a surprise conflict. Sources, cheapest first:
   - Files/symbols the task's own description cites → grep those symbols to their
     files.
   - **Git-history proxy:** for the task's subsystem, `git log --name-only` over
     recent commits (or grep the CHANGELOG entry of the last drop in that area) →
     the file set those drops touched. Past drops in a subsystem are the best
     predictor of the next one's footprint.
   - Record a confidence for each set (high = cited files; low = inferred).
3. **Set aside the always-shared files** — `CHANGELOG.md` and `TODO.json`. They are
   NOT lane discriminators: every lane writes them. Handle via the protocol, never by
   trying to keep lanes off them.
4. **Build the contention graph.** Edge A—B iff their non-shared file sets intersect.
5. **Add dependency edges.** If X produces a seam/symbol that Y consumes, Y must land
   after X — sequence them (same lane, ordered), do not parallelize across that
   boundary.
6. **Partition (greedy graph-coloring).** The FEWEST lanes that break real contention;
   balance load; give each lane an owner. Do **not** over-shard — a lane per task is a
   coordination tax, not a speedup.
7. **Emit the plan.** Per lane: its tasks (ordered) + the union of files it OWNS + an
   owner label. Plus (a) HAZARDS — any file ≥2 lanes want: single-owner it, split the
   task, or serialize just that file; (b) the shared-file protocol; (c) a SERIALIZE
   verdict where parallelism is not worth it.

## Shared-file protocol (the highest-leverage rule)

`CHANGELOG.md` + `TODO.json` are unavoidable cross-lane writes. These rules keep them
from hard-conflicting:

- **CHANGELOG.md** — prepend newest-first; on conflict, **union** (keep both entry
  blocks, drop the three `<<<<<<< / ======= / >>>>>>>` markers). Never reflow an
  existing entry.
- **TODO.json** — edit by **surgical string-splice** (prepend into the target array;
  move an item pending→resolved by removing its object span + inserting the resolved
  one). **NEVER a full `json.load` → `json.dump` rewrite** — it reformats the whole
  file, which is both a guaranteed whole-file merge conflict and the object/scalar
  union-corruption trap. `json.loads()` to validate after every edit.
- A **scalar** field both lanes changed (e.g. `last_updated_note`) is a duplicate-key
  conflict — **pick one** on merge, do not union.
- If churn is high, name ONE owner for `TODO.json` bookkeeping and have the other
  lanes hand it deltas instead of editing it directly.

## When to SERIALIZE (say it plainly, without apology)

- Small backlog — coordination cost exceeds the speedup.
- The tasks share a **hot file that cannot be split** (e.g. `parser/space_commands.py`,
  `static/client.html`) — one lane owns it; the others wait.
- A dense dependency chain — it is sequential by nature.
- A lane's file set cannot be predicted with confidence — do not parallelize blind.

## Multi-session use (git worktrees)

The same partition is your session-lane map. Give each session a file-set it OWNS; a
task whose predicted files cross two owners is a coordination point — assign it to one
owner or split it **before** both sessions touch it. This is the pre-flight that
prevents the "two agents auto-resolve a hard conflict in each other's lane" failure.

## Output + execution

Return: (1) the lane table, (2) the hazards, (3) the shared-file protocol reminder,
(4) confidence/uncertainty notes and any SERIALIZE verdict. Then execute — the
Workflow tool's `parallel`/`pipeline` for in-process fan-out (this skill decided WHAT
goes in them), or per-session worktrees for multi-session lanes.

## Honesty rules

- Over-predict file sets; report what you could not predict.
- Prefer fewer lanes; conclude "serialize" when that is the right answer.
- Never call two tasks conflict-free without a file-set basis for it.
