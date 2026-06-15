# SW_MUSH Claude Backlog and Audit Prompts

This file turns the audit into actionable Claude work packages. The recurring instruction should be: **verify first, write a failing test or audit table first, then patch.** Do not let Claude jump straight into implementation on broad systems.

## Priority backlog

### P0 — immediate correctness/security

| ID | Issue | Why it matters | First deliverable |
|---|---|---|---|
| P0-1 | `@newpassword` uses SHA-256 while auth expects bcrypt | Admin reset can break login/security | Failing reset-auth test, then fix. |
| P0-2 | Privileged `ev.html` render seam | Future XSS risk | Map all `innerHTML` paths, remove/sanitize. |
| P0-3 | Command collision allowlist | Prevent silent alias/key overwrite | Registry audit + allowlist test. |

### P1 — launch readiness

| ID | Issue | Why it matters | First deliverable |
|---|---|---|---|
| P1-1 | Crafted quality/boosts not read by combat | Crafting economy payoff risk | Bounded quality→combat design doc + tests. |
| P1-2 | Non-credit value ledger missing | CP/FP/rep/DSP/material economy invisible | Mutation map + value_log design. |
| P1-3 | Exception policy absent | Fail-open may hide state bugs | Broad-exception classification table. |
| P1-4 | Session cache before DB mutation | Local/DB divergence risk | Authoritative mutation audit. |
| P1-5 | Stale docs | Claude can reintroduce old truths | Docs truth map and patch. |
| P1-6 | First-session funnel unproven | Fun/retention risk | Playtest script + automated journey smoke. |
| P1-7 | Migration rehearsal | Pre-existing saves can break silently | Old-save-to-current migration test. |
| P1-8 | Economy simulation absent | Macro instability risk | Baseline sim report before tuning. |

### P2 — soft-launch polish

| ID | Issue | Why it matters | First deliverable |
|---|---|---|---|
| P2-1 | UI lacks persistent next action | Players may feel lost | Next Best Action panel using existing data. |
| P2-2 | Command discoverability | Web users do not know MUSH syntax | Command palette design + MVP. |
| P2-3 | Accessibility | Broader usability and quality | Keyboard/screen-reader audit. |
| P2-4 | Monolith concentration | Future regression risk | Extract one service seam at a time. |
| P2-5 | Live-ops runbook | Real testers need recovery tools | Backup/log/restart/admin checklist. |

## Ready-to-paste Claude prompts

### 1. Password reset P0

> Verify `parser/mux_commands.py::NewPasswordCommand` against account creation and login. It appears to store SHA-256 while `authenticate` expects bcrypt. First write a failing regression test: create account, reset password as admin, authenticate with new password, verify old password fails, verify stored hash is bcrypt. Then fix the command using the same bcrypt hashing path as account creation. Also align password minimum length policy and ensure bad stored hashes fail cleanly instead of crashing login.

### 2. Client HTML/XSS P0

> Audit `static/client.html` and SPA modules for every `innerHTML` assignment, especially paths using `ev.html`. Build a table: file, function, source of data, trusted/untrusted, current escaping, recommended fix. Then patch user-originated message paths so say/pose/page/channel/whisper/NPC dialogue cannot inject HTML. Prefer structured renderers over raw HTML. Add jsdom regression tests.

### 3. Command registry collision P0

> Audit every command key and alias registered in SW_MUSH. Identify duplicate keys, duplicate aliases, and partial-match ambiguities. Classify each as intentional, legacy, umbrella/smart-dispatch, or accidental. Add a test that fails on any new collision not present in an explicit allowlist with a reason. Do not remove intentional collisions without a design note.

### 4. Quality-to-combat P1

> Design a bounded quality-to-combat system for crafted weapons, armor, powered armor, consumables, and tools. Constraints: WEG D6 readability, no runaway power creep, registry base stats remain canonical, high-quality crafted gear must feel valuable in combat, low-quality gear must remain usable, and combat messages must explain modifiers. Produce design tables and caps before coding. Then implement with tests for weapons, armor, consumables, and no bonus-stacking exploit.

### 5. Non-credit value ledger P1

> Audit every write site for CP, FP, DSP, faction reputation, schematic knowledge, crafting materials, item quality, item condition, contraband status, legal infractions, and item destruction/confiscation. Create a mutation map with file/function/source tag/atomicity/session-cache behavior. Then design a minimal value_log or domain-specific ledgers. Add tests proving major value changes are logged with before/after/source metadata.

### 6. Exception policy P1

> Count and classify all broad `except Exception` handlers. Categorize each as optional flavor fail-open, AI fail-open, command parse fail-clean, or authoritative mutation fail-closed. High-risk zones: credits, CP, FP, rep, inventory, combat, quests, migration, auth, admin. Produce a patch plan and add an AST/lint-style test preventing new broad exceptions in protected mutation zones unless allowlisted.

### 7. Authoritative mutation P1

> Audit value and inventory mutations where session/local character dictionaries are changed before the authoritative DB/service call. Look for credits, CP, FP, rep, inventory, item condition, quest completion, wound state, and contraband. Produce a table of risky paths. Refactor the highest-risk ones so service/DB returns canonical state first, then session cache updates from that result.

### 8. Economy simulation P1

> Build an offline economy simulation harness. Profiles: casual mission runner, bounty hunter, crafter, gatherer, smuggler, space trader, Jedi/Force path, social/RP low-combat player, optimizer/alt abuser. Simulate 1, 7, 30, and 90 days. Report credits/hour, CP/hour, faction rep/hour, material quality stockpiles, item creation/destruction/confiscation, P2P velocity, and time to first meaningful upgrades. Do not tune values until the baseline report is produced.

### 9. Documentation truth audit P1

> Audit README, guide docs, architecture docs, TODO, changelog, and handoffs for stale claims about schema version, test count, Python version, P2P cap, economy targets, launch priorities, open/closed design calls, and current module counts. Produce a precedence policy for docs. Patch stale docs so future Claude sessions do not reintroduce old assumptions.

### 10. First-session funnel P1

> Design a first-session funnel audit. Trace account creation, character creation, first room, first movement, first NPC interaction, first objective, first reward, first spend, and first self-directed goal. Use no new content unless necessary. Identify every point where the player may not know what to do next. Propose UI/help/briefing changes and add an automated smoke journey where possible.

### 11. UI Next Best Action P2

> Implement a minimal Next Best Action panel in the web client using existing data only: tutorial state, questline state, local NPC/vendor/trainer/jobs, faction state, threat band, communal objective, and character role. Show 1–3 actions with reason, risk, reward type, and a stage-command button. Add tests for empty state, tutorial state, vendor/trainer nearby, active communal objective, and no unsafe auto-send.

### 12. Command palette P2

> Design a command palette for the web client. It should search command names, aliases, usage strings, local contextual actions, and examples. It must support keyboard navigation, placeholder filling, staging, and danger labels. Add jsdom tests for search, selection, staging, and escape/close.

### 13. Accessibility P2

> Audit the web client for keyboard-only operation, focus indicators, modal focus traps, aria labels, color-only states, text scaling, reduced motion, and small-screen behavior. Prioritize login, character select, command input, movement, inventory, map, modal close, and staged command send. Implement the smallest fixes and add tests where feasible.

### 14. Monolith seam extraction P2

> Pick one high-risk monolith function or file and extract a behavior-preserving service seam. Do not rewrite. Start with tests around current behavior, create a service/result object, move logic behind the service, and keep the command output unchanged. Candidate areas: vendor buy/sell, combat equipment wear, space state builder, credit/value movement, inventory mutation.

### 15. Live-ops readiness P2

> Produce a live-ops readiness checklist for a small private multiplayer test: backup/restore, log rotation, crash recovery, admin commands, stuck-character recovery, password reset, migration rehearsal, economy dashboard, abuse reports, account lockout, server restart, and rollback plan. Then audit code/docs for gaps.

## How to ask Claude to work safely

Use this wrapper before each prompt:

> Work in verify-first mode. Do not make broad changes. First identify the exact files/functions involved and produce an audit table. Then write or identify a failing test for the highest-risk behavior. Only then patch the smallest surface needed. After patching, list tests run and any behavior deliberately changed. If you find stale docs or conflicting architecture notes, stop and report the conflict instead of guessing.
