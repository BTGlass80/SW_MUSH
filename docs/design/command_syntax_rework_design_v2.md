# Command-Syntax Rework — Ratified Plan v2 (2026-06-16)

> **STATUS: RATIFIED by Brian 2026-06-16.** Supersedes the open decisions in
> `command_syntax_rework_design_v1.md` (v1 keeps the live inventory + problem analysis).
> Build may proceed (lane claimed in `OPUS_CLAIM.md`; loops avoid it).

## Brian's rulings (the decisions from v1 §9)
- **A → A1.** `bare` = in-world/IC actions; `+` = OOC/meta/query/HUD commands; `@` = staff /
  building / account-admin only. This matches MUSH/MUX idiom (`@`-commands are the
  programming/admin verbs; bare verbs are world interaction — verified against the TinyMUX/PennMUSH
  command docs).
- **B → switches are PRIMARY.** Command families use the MUSH `command/switch` form as the
  **canonical** syntax: `bounty/claim`, `quest/accept`, `event/list`. (This is *the* MUSH idiom —
  `@dig/teleport`, `get/quiet` — so it captures the feel Brian wants.) Switch names may be
  abbreviated to a unique prefix, per MUSH convention.
- **C → CLEAN. No backward-compat aliases.** Nobody is playing yet, so there is no muscle memory
  to preserve. We pick ONE canonical form per command and **delete the redundant forms** (the 128
  multi-prefix duplicates, the run-on smashes). Keep an alias ONLY where it is a genuine, intended
  ergonomic shorthand (e.g. a single-letter `l`→`look` if MUSH-standard) — not as legacy cruft.
  The default posture is *clean*, not *alias-everything*.
- **D → do them ALL** (all 128 multi-prefix stems + the ~11 run-ons + the 6 `@`-exceptions).
  Phasing is allowed where it sequences sensibly, but the end state is the whole surface
  normalized.
- **E → `@desc` stays** (`@desc` is MUSH-compliant for a player setting their own description; same
  for `@mail`). These are the sanctioned player-`@` exceptions.
- **North star: MUSH/MUX feel.** Model the conventions on real MUSH (TinyMUX/PennMUSH): bare IC
  verbs, `@`-admin/building, `command/switch` switches, `=` to separate a two-argument command's
  sides, `cmd lhs = rhs` shape. Reference: [TinyMUX Switch](https://wiki.tinymux.org/index.php/Switch),
  [TinyMUX COMMANDS](https://wiki.tinymux.org/index.php/COMMANDS),
  [PennMUSH conceptual models](https://community.pennmush.org/book/export/html/21).

## Target conventions (the canon)
1. **Prefix policy (A1):**
   - **bare** — IC/world verbs: `look`, `say`, `pose`, `get`, `drop`, movement, `attack`, `mine`,
     `harvest`, `craft`, `board`, `eat`.
   - **`+`** — OOC/meta/query/HUD: `+who`, `+sheet`, `+finger`, `+channels`, `+bounties`,
     `+finances`, `+roll`. "Show me / system / out-of-character."
   - **`@`** — staff/building/account: `@dig`, `@teleport`, `@boot`, `@newpassword`, `@desc`*,
     `@mail`* (*sanctioned player-`@`). Enforced: every `@` command is BUILDER/ADMIN **except** the
     `{@desc, @mail}` allowlist; no elevated command is bare/`+`.
   - Each command has exactly ONE canonical form; the others are **removed** (C).
2. **Switch families (B):** verb + `/switch`, parsed by a shared dispatcher.
   - `bounty/claim|collect|track`, `quest/accept|abandon|complete`, `smuggle/deliver`,
     `event/list|new|join`, `plot/list|...`, etc. (replaces `bountyclaim`, `questaccept`,
     `smugdeliver`, …, which are DELETED).
   - Switch abbreviation to unique prefix (MUSH standard) handled by the dispatcher.
3. **Two-arg shape:** `cmd lhs = rhs` where a command takes two operands (MUSH idiom). Adopt for
   NEW commands + the switch families now; **retrofitting `=` onto every existing command's parser
   is OUT OF SCOPE for this rework** (large, behavioral, error-prone) — tracked as a separate
   follow-up. This rework = prefix policy + switches + run-on elimination + clean removal.

## Enforcement guard (Brian's "make future commands follow our updates")
A CI invariant (`tests/test_command_convention_invariant.py`) that builds the full live registry
and FAILS on any violation — so a future command can't drift:
1. **Prefix↔access (A1):** every `@`-key has access ≥ BUILDER except the `{@desc,@mail}` allowlist;
   no PLAYER/ANYONE command uses `@`; no BUILDER/ADMIN command is bare/`+`. *(The
   `@`↔access half already shipped as `tests/test_t321_admin_command_access_invariant.py` in the
   T3.21 admin-access-gap drop `9ca0692` — extend/compose with it, don't duplicate.)*
2. **Registry uniqueness / collision guard (audit A3, still open):** every primary key and every
   alias resolves to exactly one command; `register()` `log.warning`s on overwrite (kills the
   silent last-wins class that bites during canonicalization). This is the **prerequisite** for the
   canonicalization phases.
3. **Run-on regression blocklist:** the deleted smashes (`bountyclaim`, `questaccept`,
   `smugdeliver`, `buyresources`, `questabandon`, `questcomplete`, `bountycollect`, `bountytrack`,
   `spacerquest`) must NOT reappear as keys/aliases; new family verbs must use `/switch`.
4. **Switch-family integrity:** each declared family's switches dispatch + the bare family verb
   gives usage.

## Phased build plan (D — all of it, sequenced)
- **Drop 0 (FOUNDATION — this is the get-going drop):** the enforcement guard (#1–#3 above) +
  `register()` overwrite-warning + the switch-dispatcher helper. Lands FIRST so every later phase is
  guarded against silent collisions. (No command renames yet → low risk, pure safety net + the
  guardrail Brian asked for.)
- **Drop 1 — prefix canonicalization, newcomer-facing high-traffic first:** `who/+who`,
  `sheet/score/+sheet`, `inv/+inv`, `finger/+finger`, movement, `+roll/+check`. Pick the A1
  canonical, DELETE the rest, update prompts/onboarding to the canonical form.
- **Drop 2 — run-on → switch families:** convert the ~11 smashes to `verb/switch` via the
  dispatcher; delete the smashed keys.
- **Drops 3–4 — the long tail:** the remaining ~110 multi-prefix stems, canonicalized per A1 +
  deleted-redundant, in module-grouped batches.
- **Drop 5 — the 6 `@`-exceptions:** `@getattr/@housing` → bare/`+` canonical (delete `@`-form);
  `+cantina`/`resolve` → `@cantina`/`@resolve`; `@desc`/`@mail` kept.
- **Throughout:** the help/guide corpus documents the CANONICAL forms (coordinate with the guide
  pass — see below). After this lands, the broader Codex/command-reference doc rework consumes the
  canonical vocabulary.

## Safety / test plan
- The enforcement guard (Drop 0) is the standing gate.
- Because we are DELETING forms (not aliasing), the "golden every-old-string-resolves" test from v1
  is REPLACED by: a per-phase test that the canonical form resolves + the deleted forms are GONE +
  the convention invariant stays green. Update the ~dozens of tests that assert a now-deleted
  primary key to the canonical form (expected churn; `-o addopts=` single-process gate).
- One focused branch; do NOT interleave with other parser edits (loops avoid the lane).

## Drop 0 finding (2026-06-16, from the register()-collision instrumentation)
Instrumenting `register()` to record overwrites surfaced **135 silent alias/key collisions** at HEAD
(far more than the audit's 3) — concentrated in the space/combat families (`+combat`, `+bridge`,
`+pilot`, `+gunner`, `+ship*`, `+bounty`, `+mission`, `+quest`, `+smuggle`) where verb commands
re-declare aliases that another command already owns, plus `+ship*` aliases that shadow primary
keys. Also 9 run-on offenders and 2 mis-prefixed elevated commands (`+cantina`, `resolve`).
**Drop 0 implementation notes:** (a) record collisions in `registry._collisions` (silent) for the
test; emit ONE **summary** `log.warning` at end-of-build (`N collisions`), NOT 135 per-line (boot
spam / may trip clean-log smoke). (b) freeze the baseline (`tests/data/command_convention_baseline.json`,
generated) and assert the live registry introduces nothing beyond it; **the baseline only shrinks** as
Drops 1-5 canonicalize, → zero. (c) the `@`↔access half is already covered by
`tests/test_t321_admin_command_access_invariant.py` — compose, don't duplicate. Switches already
parse into `ctx.switches` (event/plot use it) — no new dispatcher needed.

## Coordination
- Lane CLAIMED in `OPUS_CLAIM.md`. Drop 0 built by Brian's interactive Opus session; Drops 1–5
  handed to the Opus loop (fresh context per phase) once Drop 0 lands.
- The Sonnet loop must NOT touch command keys; the guide/help pass it does should target canonical
  forms once Drop 1+ land (sequencing note in OPUS_CLAIM).
