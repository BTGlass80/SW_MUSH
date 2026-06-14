---
description: Run the full pre-handback verification fan-out on the current drop's diff (invariant-auditor + code-reviewer + test-runner + smoke-verifier), then adjudicate.
argument-hint: "[optional: extra focus note for the reviewers]"
allowed-tools: Bash(git --no-pager diff:*), Bash(git --no-pager log:*), Bash(git status:*), Task
---

You are running the **pre-handback verification ritual** from CLAUDE.md's "Agent roster
& delegation" — the read-only Sonnet fan-out that must pass before any drop goes back to
Brian. Do NOT implement or fix anything in this command; this is the verification gate.

## Context — the diff under review

Current branch and changed surface:

- Branch / recent commits: !`git --no-pager log --oneline -5`
- Working-tree status: !`git status --short`
- Diff vs main (the drop): !`git --no-pager diff main...HEAD --stat`

Extra focus from the caller (may be empty): $ARGUMENTS

## What to do

Spawn these four verification agents **in parallel, in a single message** (they are
independent, read-only, and must not serialize):

1. **invariant-auditor** — audit the diff against the SW_MUSH standing invariants (era
   cleanness, funnel functions, phantom producers/consumers, faucet/sink pairing,
   `force_sensitive` discipline, YAML additive-safety, CHANGELOG/TODO hygiene).
2. **code-reviewer** — hunt the correctness bugs the suite misses (async/aiosqlite
   misuse, edge cases, state/connection leaks, D6 dice-math, web producer/consumer
   protocol mismatches, error handling).
3. **test-runner** — run targeted pytest for the changed modules and triage failures.
4. **smoke-verifier** — confirm the game still BOOTS and basic commands respond
   in-process (`tests/smoke/ -m smoke`), if the drop touched engine/server/loaders/
   schema/world data.

Pass each agent the changed-file list and the caller's focus note so they scope to this
drop, not the whole tree.

## Then adjudicate

You (the main session) are the adjudicator — the agents report, you decide. After all
four return, produce a single verdict:

- **READY FOR BRIAN** — all four clean (or only accepted-baseline skips), OR
- **N ISSUES — FIX FIRST** — list each blocking finding with its source agent and
  `file:line`, in priority order, and state what to change.

Do not soften a real finding to reach "ready." If an agent flags a phantom
producer/consumer, an unpaired faucet, an era violation, or a boot failure, it blocks.
Remember the no-phantom-claims invariant: verify any "this exists / this is missing"
claim against HEAD before repeating it in your verdict.
