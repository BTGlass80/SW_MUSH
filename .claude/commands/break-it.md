---
description: Adversarial exploratory test pass — drive the live parser with malformed/out-of-order/boundary inputs to discover breakage the confirmatory suite never checks. Report-only; finds defect hypotheses, never auto-fixes.
argument-hint: "[optional: command / loop / subsystem to focus the sweep on]"
allowed-tools: Bash(git --no-pager diff:*), Bash(git status:*), Task
---

You are launching an **adversarial exploratory test sweep** — envelope expansion, not
conformance. The 8,700-test suite only fails on cases a human already imagined; this
pass goes looking for the departure nobody predicted (the Drop-24-class bug: a real
player walking a real flow into a state no test pre-seeded).

## Scope

Changed surface to target: !`git --no-pager diff main...HEAD --stat`

Caller's focus (a specific command/loop/subsystem, or empty for "the changed surface"):
$ARGUMENTS

## What to do

Spawn the **break-it-tester** agent. Hand it:

- the changed-file list above (so it scopes to what this drop touched), and
- the caller's focus note if present.

Instruct it to drive the live parser through the in-process `tests/harness.py` seam
(`login_as` → `cmd`) with adversarial inputs — malformed args, out-of-order sequences,
impossible targets, interrupted multi-step flows — and to report ONLY genuine breakage
(crash / state corruption / internal-error leak to the player / silent should-have-acted
swallow), ranked by confidence. Clean rejection of bad input is the system working and
is NOT a finding.

## After it returns

Relay its findings to the caller as ranked defect **hypotheses**, preserving the agent's
prioritization: ordered by SEVERITY (blockers first) with EFFORT-to-verify as the
tiebreaker, each carrying its copy-paste **HUMAN WALKTHROUGH** (the literal steps Brian
types/clicks to confirm it himself) plus the developer repro. Lead with the agent's
"FASTEST CRITICAL CHECK" banner if it flagged a BLOCKER that's seconds-to-verify — that's
the highest-value line for a human-in-the-loop. Do NOT auto-fix anything and do NOT write
a passing test that codifies the observed behavior — a finding is a hypothesis for human
triage, and a green test over a bug protects the bug.
