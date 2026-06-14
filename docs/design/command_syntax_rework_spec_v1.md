# Command Syntax Rework — Approach Spec v1 (2026-06-13)

Dials in the approach for a command-syntax normalization pass BEFORE the help/guide doc
rework (no point documenting a syntax that's about to change). Extends the existing (stalled)
taxonomy in `command_syntax_help_design.md` (April 2026). This spec is the PLAN; the pass is
a later set of drops.

## GOVERNING PRINCIPLE for the bare-vs-`+` line (Brian, 2026-06-13)

The classification rule, ruled by Brian: **embodied IC verbs stay BARE; invoking a game
SYSTEM gets `+`.** Bare = the things that make you feel *in the world*: perceiving (`look`,
`examine`), moving (`move` + compass directions, `enter`/`leave`), handling physical things
in the room (`get`/`drop`), and speaking (`say`/`pose`/`emote`/`page`/`ooc`/`whisper`). `+`
= invoking a system surface that isn't a physical in-room act: `+sheet`, `+faction`, `+craft`,
`+bounty`, `+mission`, and — yes — combat and ship/piloting (you're operating a *system*, even
though it's diegetic). This MUSH-faithful split is the measuring stick for every debatable
row in the catalog: "is the player doing a thing in the room, or opening a game system?"

## The taxonomy (already documented, half-implemented)

Per `command_syntax_help_design.md` and Brian's MUSH model:
- **Social / IC speech = NO prefix:** say, pose, emote, page, ooc, whisper, think, channels.
  These stay bare (muscle memory; they're "talking," not "doing a system thing").
- **Game-system actions = `+` prefix:** the canonical form for anything mechanical.
- **Admin / builder = `@` prefix:** already well-established (62 `@` commands).
- **Variants = `/switch`:** `+sheet/brief`, `+bounty/collect` — a sub-action of a command,
  not a separate command.

**Pre-existing rule (from the doc):** *"The bare-word version ALWAYS remains as an alias."*
That rule was written for a LIVE game (protect player muscle memory).

**BRIAN CORRECTION (2026-06-13): there are NO PLAYERS YET — so DROP the keep-the-bare-alias
constraint.** A re-prefix is a CLEAN RENAME, not an additive alias layer. Consequences:
- No 33-alias backfill (axis 2 mostly evaporates — just rename where a `+` form should be
  canonical; only keep a bare alias where the bare form is genuinely the better name, e.g. a
  social verb).
- The ugly run-ons (axis 3) DISAPPEAR rather than lingering as dead aliases. `collectbounty`
  becomes `+bounty/collect` and `collectbounty` simply stops existing.
- The end state is CLEANER (no alias cruft), but each drop is slightly MORE involved: a rename
  means every INTERNAL reference to the old key must be updated IN THE SAME CHANGE. That's not
  muscle memory — it's code/data coupling:
  · tutorial chains (`command_executed:` steps — 24 total; only 4 bare game-system strings
    actually referenced: `examine`, `scan`, `search`, `meditate` — verified),
  · tests asserting on keys (~1-2),
  · help/`help_text` keyed off command names.
- So the discipline shifts from "always add an alias" to "rename + sweep every internal
  reference in the same drop, guarded by a test that no dangling old-key reference remains."

## What the audit found (HEAD, verified)

320 commands across 68 parser modules:
- **No-prefix: 166** — only 12 are genuinely social; **154 are game-system actions that
  should be `+`.**
- **`+` prefix: 92** — but **33 of these lack a bare-word alias** (a backward-compat gap).
- **`@` prefix: 62** — correct, leave alone.

Migration was STARTED, not finished: e.g. `combat_commands.py:1493 key="attack"` (no prefix)
but `space_commands.py:6388 key="+pilot"` exists alongside `space_commands.py:732 key="pilot"`.
Inconsistent half-state.

## FOUR axes to normalize (not just prefixes)

### Axis 1 — Missing `+` prefix on game-system commands (154)
Combat (27: attack, dodge, parry, aim, flee…), ship/piloting (30: pilot, gunner, fire, scan,
shields, hyperspace…), mission/quest (12), crafting (9), medical (6), bounty (5), +49 others.
Fix: `key = "+attack"`, `aliases = ["attack"]` — canonical `+`, bare stays as alias.

### Axis 2 — `+` commands missing their bare alias (33)
+bounty, +combat, +city, +mission, +faction, +medical, +craft, +ship… have `aliases=[]`.
Fix: add the bare word as an alias so both forms work. **Zero risk, ~2-3 hrs.**

### Axis 3 — "German word" run-on compounds (Brian, 2026-06-13)
Verb+noun smashed into one token: `questcomplete` / `completequest` (both exist!),
`collectbounty` / `bountycollect` (both!), `acceptbounty`, `abandonquest`, `buyresources`,
`damagecontrol`, `takecontrolofthehelm`-style. These are unreadable AND inconsistent (the same
action exists two ways). Fix: collapse each into the parent command + a SWITCH:
- `collectbounty` / `bountycollect` / `+bounty collect` → **`+bounty/collect`**
- `acceptbounty` → **`+bounty/accept`**; `questcomplete`/`completequest` → **`+quest/complete`**
- `buyresources` → **`+buy/resources`** or a `+shop` switch; `damagecontrol` → **`+ship/repair`** switch
Keep each run-on as an alias so nothing breaks.

### Axis 4 — Missed switch opportunities (complex multi-part commands)
Commands taking a positional sub-verb instead of a switch:
- `+city found/claim/tax/banish/…` (17 sub-verbs as positional args)
- `@director status/enable/trigger/…`, `+faction leader/treasury/…`, `+mission board/accept/…`
These already PARSE the sub-verb positionally; the switch form (`+city/found`) is the
consistent surface. **Design call:** positional sub-verbs are arguably fine for discoverability
(`+city` with no args lists them). Recommendation: standardize on switches for VARIANTS of one
output (`+sheet/brief`) but ALLOW positional sub-verbs for genuinely different sub-actions with
their own args (`+city found <name>`) — document the rule rather than force-convert all. This
axis is the most debatable; see open questions.

## Why it's ADDITIVE and non-breaking (the load-bearing mechanism — verified)

The alias system makes a re-prefix a NON-breaking change:
1. Rename `key="attack"` → `key="+attack"`, add `aliases=["attack"]`.
2. Player types `attack` → registry matches via alias → returns the command. Both forms work.
3. **Tutorial/quest chains still match:** the chain hook (`parser/commands.py:378`) passes
   `ctx.command` = the RAW INPUT TOKEN the player typed, and `engine/chain_events.py:262`
   compares against it. So a chain step `command_executed: "attack"` still fires when the
   player types `attack` (the alias), regardless of the canonical key. **Verified.**
4. Help system keys off `registry.get()` which honors aliases — no breakage.
5. Only ~1-2 tests hardcode a bare key as an assertion; trivially updated.

So every axis is "add the canonical form, keep the old form as an alias" — players never lose
muscle memory, chains/quests/tests keep working.

## Risk + feasibility

- **Risk: LOW-MODERATE, fully mitigatable.** The alias path is production-ready and proven.
  The one real watch-item: a re-prefix must ALWAYS add the bare alias (a rename WITHOUT the
  alias would break chains/muscle-memory). Enforce with a test: "every game-system command's
  bare form resolves." For run-on collapses (axis 3), keep the run-on as an alias.
- **Collision with the parallel session — and how coordination ACTUALLY works.** parser/*.py
  is the parallel session's active surface (confirmed: `parser/space_commands.py` is dirty
  RIGHT NOW, which is exactly the Batch-2 ship target). IMPORTANT LIMIT: the two Claude sessions
  CANNOT talk to each other — separate contexts, no shared channel, no lock one respects. The
  ONLY coordinator is Brian (the human running both). So "explicit coordination" does NOT mean
  the sessions negotiate; it means **Brian sequences them, OR the work is structured so it
  doesn't need negotiation.** Three viable models:
  1. **Serialize (cleanest):** Brian pauses the parser-touching parallel work, this pass runs to
     completion on a quiet parser surface, then parallel work resumes. Zero collision.
  2. **File-partition:** assign each session DISJOINT files. The re-prefix pass takes the parser
     files the parallel session is NOT in; the parallel session keeps its files. Since a
     re-prefix is a per-file `key=` rename, it partitions cleanly by file. Needs Brian to declare
     the partition (which files are whose) — that's the coordination, and it's a one-time call.
  3. **Re-prefix LAST, in one quiet window:** do it as the final pre-doc pass after the
     parallel session's parser work (T5-questline) lands, so the surface is quiet by
     construction. This is the lowest-friction option and matches the natural sequencing
     (rework → then doc rework).
  The per-command `key=` line is an isolated one-liner (verified — changing it doesn't touch the
  command's logic), so a rename merges cleanly EXCEPT when both sessions edit the same file's
  same region. Partitioning by file (model 2) or by time (models 1/3) both avoid that.
- **It's the right time relative to docs:** the help/guide rework (`help_guides_rework`) and
  the in-game `help_text` SHOULD document the post-rework syntax. So this pass precedes the
  doc rework — exactly Brian's instinct.

## Recommended batching (each batch = one drop, additive, with a "bare form resolves" test)

1. **Batch 0 — alias backfill (zero risk, do first):** add bare aliases to the 33 `+`
   commands missing them. No key changes, pure addition.
2. **Batch 1 — combat (27):** +attack/+dodge/+parry/… , bare as alias.
3. **Batch 2 — ship/piloting (30):** +pilot/+fire/+scan/+shields/… (finish the started
   migration; reconcile the existing `+pilot`/`pilot` split).
4. **Batch 3 — run-on collapse (axis 3):** the German-word verb+noun tokens → parent + switch,
   run-on kept as alias. De-duplicate the two-forms-same-action cases.
5. **Batch 4 — remaining game-system (mission, craft, medical, bounty, misc).**
6. **Batch 5 — switch normalization (axis 4):** apply the documented switch-vs-sub-verb rule;
   convert true variants to switches.
7. **THEN** the help/guide doc rework documents the final syntax.

## Open questions for Brian (the real forks)

- **Axis 4 scope:** force ALL multi-part commands to switches, or keep positional sub-verbs for
  sub-actions-with-args and use switches only for output variants? (Recommendation: the latter —
  `+city found <name>` reads better than `+city/found <name>`, but `+sheet/brief` is right.)
- **Run-on canonical names (axis 3):** confirm the target for the ugly ones — e.g. is
  `damagecontrol` → `+ship/repair` or its own `+damagecontrol`→`+ship` switch? Per-command call.
- **Sequencing vs. the parallel session:** this touches parser/*.py heavily — schedule when
  that surface is quiet (post-T5-questline), or it collides.
- **Should the bare alias EVER be dropped** (e.g. for an ugly run-on), or kept forever? (Recommend
  keep forever — zero cost, protects muscle memory.)
