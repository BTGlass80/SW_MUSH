---
description: Draft the end-of-session record — CHANGELOG entry, TODO.json delta, and a fresh HANDOFF doc — from the actual diff, grounded in HEAD. Drafts only; never edits CHANGELOG/TODO directly, never commits.
argument-hint: "[optional: subsystem name for the HANDOFF filename]"
allowed-tools: Bash(git --no-pager diff:*), Bash(git --no-pager log:*), Bash(git status:*), Task
---

You are scaffolding the **end-of-session record** for the current drop. Spawn the
**handoff-writer** agent.

## Context

- Status: !`git status --short`
- Drop diff: !`git --no-pager diff main...HEAD --stat`

Subsystem hint for the HANDOFF filename (or empty — the agent picks): $ARGUMENTS

## What to do

Hand the **handoff-writer** agent the changed surface and the subsystem hint, and have it:

1. Draft the **CHANGELOG entry block** and the **TODO.json design-call delta** as TEXT
   (it must NOT edit those two high-churn shared files directly — a parallel session may
   own uncommitted edits to them).
2. Write **one fresh** `docs/design/HANDOFF_<subsystem>_<date>.md` (confirmed non-existent
   first).
3. Ground every "shipped X" claim in a symbol present in the diff; tag anything
   ungroundable UNVERIFIED.

## After it returns

Review the drafts. If CHANGELOG.md / TODO.json were reported dirty, reconcile against the
concurrent edits before applying the CHANGELOG and TODO text yourself (the agent
deliberately left those two files untouched). Check each UNVERIFIED line against HEAD
before keeping it. Do NOT commit — Brian commits the record with the drop.
