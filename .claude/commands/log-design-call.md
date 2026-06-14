---
description: Append a correctly-structured entry to TODO.json design_calls_pending_brian — the genuine-design-fork escalation from the drop workflow, with the right schema and a HEAD-verified premise.
argument-hint: "<ID.short_slug> | <the question / fork>"
allowed-tools: Bash(git --no-pager diff:*), Read, Edit
---

You are logging a **genuine design fork** into `TODO.json` →
`design_calls_pending_brian`, per step 5 of the CLAUDE.md drop workflow ("do not guess —
log it and ask"). Use this only for a real fork Brian must decide, not for something with
an obvious default.

## Input

The caller passed: $ARGUMENTS

Parse it as `<ID.short_slug> | <question>` if a `|` is present; otherwise treat the whole
string as the question and propose a dotted `AREA.short_slug` id yourself (match the
existing namespace style: `CRAFT.*`, `ECON.*`, `DIRECTOR.*`, `OBS.*`, etc.).

## The exact schema to append

Each pending entry is an object with these keys, in this order:

```json
{
  "id": "<AREA.short_slug>",
  "raised": "<today's date, YYYY-MM-DD>",
  "priority": "<LOW | MEDIUM | HIGH>",
  "question": "<the fork, stated so Brian can decide without re-deriving context>",
  "recommendation": "<your best call + one-line rationale, WEG-D6/era-grounded>",
  "logged": "<today (drop N, <who-raised-it>)>",
  "status": "pending Brian"
}
```

## What to do

1. Before writing, **verify the premise against HEAD** (no-phantom-claims invariant): if
   the fork references a symbol, field, or behavior, grep the working tree to confirm it
   actually exists / is actually missing. A design call built on a hallucinated premise
   wastes Brian's time. State in the `question` what you confirmed.
2. Read `TODO.json`, locate the `design_calls_pending_brian` array, and **append** the
   new object via a surgical Edit (string-insert before the array's closing `]`) — never
   a JSON round-trip rewrite of the whole file (it would churn unrelated keys and risks
   colliding with concurrent edits).
3. Set `priority` honestly: HIGH only if it blocks a drop or risks live-state migration;
   most forks are LOW/MEDIUM.
4. Write a concrete `recommendation` — Brian relaxed "stop and wait" for unattended work;
   a logged call with a defensible default is more useful than a bare question.
5. Report back the id and one-line summary of what you logged. Do NOT also commit — Brian
   commits TODO.json with the drop, and it may be dirty from a concurrent session.
