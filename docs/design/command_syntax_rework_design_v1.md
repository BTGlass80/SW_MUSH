# Command-Syntax Rework — Design Proposal v1 (2026-06-16)

> **STATUS: PROPOSAL — pending Brian's review/ratification.** Nothing is built. This is the
> design pass Brian asked be "teed up" for review. Every number below is from a live dump of
> the actual command registry at `origin/main` `d11de2a` (built via the server's real
> `_build_command_registry()`), not a guess. The decisions that need YOUR ruling are in §9.

## 1. Goal & non-goals

**Goal:** make the command surface *legible* — a player (especially a web-first newcomer) should
be able to predict how to type a command. Three sub-goals, from the standing intent
(`memory: command-syntax-rework`):
1. **Normalize prefixes** (`+` / `@` / bare) to a stated rule, instead of the current "both forms
   aliased for almost everything."
2. **Kill the "German-word" run-ons** (`bountyclaim`, `questaccept`, `smugdeliver`) in favor of
   `verb <subcommand>` families.
3. **Add a switch convention** (`/switch`) for list/variant forms, which barely exists today.

**Hard non-goals (constraints):**
- **ZERO breakage.** Every string that works today must keep working. The rework is *additive*:
  it picks a **canonical** form per command and demotes the rest to **aliases** — it does not
  remove aliases at launch.
- **No new top-level system.** This rides the existing `CommandRegistry` (`parser/commands.py`).
- **Must PRECEDE the help/Codex doc rework.** The Sonnet content loop is actively writing the
  help corpus *right now* — see §7 (coordination), this is time-sensitive.

## 2. As-is inventory (live, HEAD `d11de2a`)

- **320 primary commands, 472 aliases** across ~55 `parser/*.py` modules.
- **Prefix split (primary keys):** `bare` 165 · `+` 98 · `@` 57.
- **`@` ≈ elevated, but leaky:** of 57 `@` commands → 34 BUILDER, 19 ADMIN, **4 PLAYER**
  (`@desc`, `@getattr`, `@housing`, `@mail`). And **2 elevated commands are NOT `@`-prefixed**
  (`+cantina` BUILDER, `resolve` BUILDER/ADMIN). So "`@` = staff" is ~93% true with 6 exceptions.
- **`+` vs bare is genuinely inconsistent: 128 stems are reachable under multiple prefix forms**
  (e.g. `armor`/`+armor`, `credits`/`+credits`, `faction`/`+faction`/`@faction`,
  `bounty`/`+bounty`/`@bounty`). Both forms are *already aliased* for most of these — so the
  redundancy is real, but backward-compat is already half-built (good news for migration).
- **Subcommand syntax barely exists** — only 5 space-bearing keys (`buy resources`,
  `combat rolls`, `force door`, `full dodge`, `full parry`).
- **Switch syntax barely exists** — only 3 slash keys (`+event/list`, `+plot/list`,
  `@emit/player`).
- **Run-on offenders (verb+noun smashed, single token):** `bountyclaim`, `bountycollect`,
  `bountytrack`, `buyresources`, `questaccept`, `questabandon`, `questcomplete`, `smugdeliver`,
  `spacerquest`, `transponder`, `outmaneuver`. (Long-but-legitimate single words like
  `investigate`, `+achievements`, `+forcestatus` are fine — not offenders.)

## 3. The problem, concretely

- **Discoverability:** a newcomer can't predict `+who` vs `who`, `+sheet` vs `score`, `+inv` vs
  `inventory`. 128 stems work both ways by luck-of-aliasing, but the *help text and the prompts*
  disagree about which to show, so players learn an inconsistent vocabulary.
- **Help-doc drift:** the help corpus (being written now) documents whatever form the author
  picked; without a canonical policy, the docs enshrine the inconsistency. **This is why the
  rework must precede the doc rework.**
- **Run-ons are unguessable + unlistable:** a player who knows `bounty` can't discover
  `bountyclaim`/`bountycollect`/`bountytrack` by typing `bounty` — they're separate top-level
  tokens with no family relationship.
- **Latent dead-routing (from the T3.21/audit findings):** the registry's `register()` is silent
  last-wins (no collision guard). Any canonicalization that reassigns keys/aliases across 320
  commands WILL trip this if not guarded — so the **collision guard is a prerequisite** (§6).

## 4. Proposed conventions (the "to-be")

### 4.1 Prefix policy (the core decision — see §9 Decision A)
The clean, learnable rule (MUX/MUSH-idiomatic, and what most stems already lean toward):
- **bare = in-world / IC actions:** `look`, `say`, `pose`, `get`, `attack`, movement, `mine`,
  `harvest`, `craft`. Things your *character* does in the fiction.
- **`+` = OOC / meta / system / "show me" commands:** `+who`, `+sheet`, `+finger`, `+channels`,
  `+bounties`, `+finances`. Out-of-character or HUD/queries about the game state.
- **`@` = staff / building / account-admin ONLY:** `@dig`, `@teleport`, `@boot`, `@newpassword`.
  If a player can do it in normal play, it is not `@`.

Under this rule each command has **one canonical form**; **all other current forms stay as
aliases** (zero breakage). For the 128 multi-prefix stems we pick the canonical per the rule and
keep the rest. (Alternative policies — collapse `+` entirely into bare, or keep status-quo — are
Decision A.)

### 4.2 Run-on → subcommand families (Decision B)
Convert verb+noun smashes into `verb <sub>` dispatch, keeping the smashed form as an alias:
- `bounty <claim|collect|track>` (aliases: `bountyclaim`, `bountycollect`, `bountytrack`)
- `quest <accept|abandon|complete>` (aliases: `questaccept`, …)
- `smuggle deliver` (alias `smugdeliver`); `buy resources` already exists as a space-form —
  promote it canonical, keep `buyresources`.
This is a small, well-bounded set (~11 offenders, ~4 families). It needs a tiny **subcommand
dispatcher** helper (parse first token after the verb → route), which `+event`/`+plot` already
hint at.

### 4.3 Switch convention (Decision B, paired)
Standardize `verb/switch` for *variant/listing* forms, generalizing the existing
`+event/list` / `+plot/list`:
- `+<family>/list`, `/info`, `/new` etc. as a uniform pattern, parsed by the same dispatcher.
- Decision point: **subcommands (`bounty claim`) vs switches (`bounty/claim`)** — or both
  (switch as an alias of subcommand). Recommend **space-subcommands as canonical** (more
  discoverable for web newcomers) with `/switch` accepted as an alias for MUX-muscle-memory.

### 4.4 The 6 prefix exceptions to clean up (Decision A follow-through)
- Reclassify the 4 PLAYER `@`-commands: `@desc` → keep `@desc` (building-ish, but it's how players
  set their own desc — **borderline; flag**), `@getattr`/`@housing`/`@mail` → canonical bare/`+`
  forms (`mail`/`+mail`, `housing`/`+housing`), `@`-forms kept as aliases.
- Promote the 2 unprefixed elevated commands to `@`: `+cantina`→`@cantina` (BUILDER),
  `resolve`→`@resolve` (BUILDER/ADMIN), old forms aliased.

## 5. Migration strategy — additive, zero-breakage

1. **Prerequisite: land the registry collision guard first** (the audit's A3 / DEV-3 — a test that
   the 320 keys + 472 aliases are unique, and `register()` logs on overwrite). Canonicalizing keys
   across 320 commands is exactly when silent last-wins bites. *This guard is independently useful
   and should land as its own small drop before any key reassignment.*
2. **Per command, set the canonical key per §4.1; move every other current form into `aliases`.**
   Because most dual forms are *already aliased*, this is mostly relabeling which is "primary,"
   not adding routes — low behavioral risk. A test asserts every pre-rework string still resolves.
3. **Add the subcommand dispatcher + the ~4 run-on families** (§4.2), run-on forms aliased.
4. **Standardize switches** (§4.3) via the same dispatcher.
5. **Prompts/HUD/onboarding surface the canonical form**; help corpus documents the canonical form
   (§7). Aliases remain undocumented-but-working.
6. **Deprecation: none at launch** (Decision C). Optionally, post-launch, emit a one-time
   "tip: the canonical form is X" nudge when an alias is used — *not* a removal.

## 6. Test & safety plan
- Golden "every current string still resolves" test (dump the 320+472 set BEFORE, assert all
  resolve AFTER) — the anti-breakage gate.
- The collision-uniqueness guard (prerequisite, §5.1).
- Per-family subcommand-dispatch tests.
- Single-process gate (this box's xdist caveat). Expect churn in tests that assert a specific
  primary key — those update to the canonical form (the alias still works).

## 7. ⚠ Ordering & live coordination (time-sensitive)
- **The Sonnet content loop is writing the help corpus RIGHT NOW** (9 batches shipped overnight,
  more queued). Those help files are choosing command forms *today*. **If the rework is ratified,
  the help corpus should document the CANONICAL forms** — so either (a) ratify the prefix policy
  soon and point the help loop at it, or (b) accept a small help-doc touch-up pass after the
  rework. Recommend (a): a quick ratification of Decision A lets the in-flight help work converge.
- This rework **must precede the broader Codex/command-reference doc rework** (the standing
  ordering constraint) — the doc rework consumes the canonical vocabulary.
- **Collision risk:** the rework touches ~55 parser files; it must land as a focused branch and
  NOT interleave with other parser edits (the standing "command-syntax-rework collides with
  parser work" note). The two durable loops avoid the command-syntax lane (claimed in
  `OPUS_CLAIM.md`).

## 8. Risks
- **Scope:** 320 commands is a lot of surface; canonicalizing *all* 128 multi-prefix stems is a big
  diff. Mitigation: phase it (Decision D) — do the high-traffic/newcomer-facing commands first
  (`who`, `sheet`, `inv`, `finger`, movement, `bounty`/`quest` families), defer the long tail.
- **Muscle memory:** veteran MUXers expect `+`; newcomers expect bare. The alias-everything policy
  serves both, but the *canonical/documented* choice signals the house style — hence Decision A is
  genuinely a product-voice call, not just mechanics.
- **Registry last-wins** (mitigated by §5.1 guard).

## 9. DECISIONS FOR BRIAN (what I need ruled before building)

- **Decision A — prefix policy / house style.**
  - **A1 (recommended):** bare = IC actions, `+` = OOC/meta/queries, `@` = staff only. (Keeps the
    `+` heritage for HUD/queries; cleans the 6 `@` exceptions.)
  - **A2:** collapse `+` into bare entirely (canonical = bare for everything a player types; `+`
    forms become aliases). Simplest for newcomers; sheds the MUX `+` convention.
  - **A3:** status-quo prefixes, only fix the 6 `@` exceptions + the run-ons. Minimal.
- **Decision B — run-on replacement:** space-subcommands (`bounty claim`) canonical with `/switch`
  as alias [recommended] · switches canonical · subcommands only.
- **Decision C — deprecation:** keep all aliases forever [recommended] · post-launch soft-nudge ·
  eventual sunset.
- **Decision D — scope/phasing:** canonicalize ALL 128 multi-prefix stems in one rework · OR
  phase it (newcomer-facing high-traffic commands first, long tail later) [recommended].
- **Decision E — the `@desc` edge:** `@desc` is how a *player* sets their own description but reads
  as a staff `@` verb. Keep `@desc` (+ add bare `desc`/`describe` alias)? or make `describe`
  canonical?

Once A–E are ruled, the build is: (1) collision guard drop → (2) canonical-relabel + golden
resolve-test → (3) subcommand dispatcher + run-on families → (4) switch standardization → (5)
point the help corpus at the canonical forms. Estimable at ~4–7 focused drops depending on D.
