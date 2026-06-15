# SW_MUSH Critical Audit — Index and Executive Summary

**Subject:** SW_MUSH stripped codebase upload, plus architecture document v52/v52.3 notes.  
**Date:** 2026-06-14  
**Assumption incorporated:** The local full test suite passes on Brian's machine. I therefore treated test success as a baseline and focused on blind spots, design risk, coupling, exploit surfaces, launch readiness, UI/UX, and whether the game is likely to be fun and legible to players.

## Scope and confidence

This review used the stripped codebase archive and the supplied architecture document. It was not a live multiplayer playtest, not a full security penetration test, and not a performance load test. Documentation, images, and large non-code files were intentionally removed from the uploaded zip, so any content-facing judgments are partly inferred from code/data/docs that remained.

Even with that limitation, the codebase was rich enough to identify several concrete engineering issues, economy/game-design risks, and UI/UX risks worth sending back to Claude.

## Report set

1. **01_Economy_Audit.md** — credits, CP, FP, faction reputation, materials, schematics, contraband, sinks/faucets, dashboards, exploit risks.
2. **02_Gameplay_Design_Audit.md** — fun, coherence, role loops, new-player funnel, content density, social play, system gaps.
3. **03_Senior_Developer_Code_Audit.md** — code quality, bugs, architecture, networking, security, dependencies, tests, maintainability.
4. **04_UI_UX_Audit.md** — web client, telnet/MUSH affordances, onboarding, command discoverability, accessibility, visual hierarchy, player feedback.
5. **05_Claude_Backlog_and_Audit_Prompts.md** — prioritized issue list and ready-to-paste Claude prompts.

## Top findings

### 1. The project is unusually audit-aware for a solo game, but the audit discipline is uneven across value types.

The strongest part of the project is its explicit invariant culture: ledger chokepoint, faucet-with-sink rules, vendor stock/presence gates, skill-key canonicalization, era-guard work, schema versioning, and a large regression suite. This is much stronger than the usual solo-codebase baseline.

The weakness is asymmetry. Credits are heavily audited. CP, FP, DSP, faction reputation, schematic knowledge, resource quality, contraband/legal consequences, and equipment condition are not yet treated with the same macroeconomic visibility.

### 2. The biggest economy/design blocker is still quality-to-combat.

The architecture notes already call out `OBS.quality_and_boosts_not_combat_read`: crafted quality and experiment boosts do not currently affect combat math because combat reads damage/protection from registry keys. That means the most important emotional promise of crafting — “my crafted object is better in play” — can collapse into valuation/flavor only.

This should be treated as a **P1 launch-readiness design problem**, not a minor balance polish issue.

### 3. I found one concrete P0 bug: admin password reset appears to write an incompatible hash.

`parser/mux_commands.py::NewPasswordCommand` hashes the new password with raw SHA-256, while normal authentication uses bcrypt. This likely makes reset accounts unable to authenticate, and may cause bad-hash behavior on login. This should be fixed before any live/admin use of `@newpassword`.

### 4. Tests passing locally matters, but the codebase itself documents the danger of “pinning the bug.”

The architecture document repeatedly describes old tests that pinned broken behavior: untrained skill fallback, armor penalties not applying, infinite grenades, decorative `uses`, stale route coverage. The local suite passing is good news, but it does not close the highest-value blind spots: registry collision, exception-policy, docs drift, value-ledger coverage, UI event wiring, replayable user journeys, and migration rehearsal.

### 5. The game is coherent on paper, but the player-facing question is still: “What should I do now?”

SW_MUSH has enough systems to be compelling: faction rep, crafting, threat bands, contraband, bounties, communal objectives, Director AI, Force/Jedi gates, wilderness, space, cities, and questlines. But depth is not the same as fun. The fun risk is cognitive load and unclear next action. The game needs a stronger daily/first-session action surface: briefings, profession contracts, visible local opportunities, and a “next best action” UI.

### 6. The UI has a strong identity, but it risks becoming a cockpit full of unlabeled levers.

The web client is much more ambitious than a basic MUSH client. It has mode-specific panels, command chips, staged actions, maps, datapad/cockpit styling, and a clean-mode concept. That is the right direction.

The risk is that a new player sees a polished command cockpit without enough intent scaffolding. The UI should answer four questions at all times: Where am I? What can I do here? What am I working toward? What changed because of my last action?

### 7. The largest maintainability risk is monolith gravity.

Several files are very large and high-complexity:

| File | Approx. lines |
|---|---:|
| `parser/space_commands.py` | 6,752 |
| `parser/builtin_commands.py` | 5,757 |
| `db/database.py` | 5,322 |
| `engine/player_cities.py` | 5,044 |
| `engine/housing.py` | 3,862 |
| `parser/combat_commands.py` | 3,464 |
| `engine/wilderness_anomalies.py` | 3,526 |

Large files are not automatically bad, but these are risk concentrators. The next phase should be “extract seams without changing behavior,” not a rewrite.

### 8. Broad `except Exception` use is now a design-policy issue, not a style issue.

I counted roughly 1,858 `except Exception` handlers across app code. Some are intentional fail-open surfaces. That is fine for UI flavor, optional AI calls, and player-friendly noncritical paths. It is dangerous for economy/state/persistence paths, where fail-open can hide partial mutation or ledger divergence.

The fix is not “delete all broad exceptions.” The fix is an exception policy: fail-open only for non-authoritative flavor; fail-closed/log-error for value movement, inventory mutation, combat result mutation, quest completion, migration, and account/security operations.

### 9. There is a privileged HTML seam in the web client.

The client generally escapes text well, but `ev.html` paths assign directly to `innerHTML` in some message rendering cases. If the server ever sends or forwards untrusted `html`, this becomes an XSS seam. If it is intentionally privileged, it should be allowlisted and centrally sanitized. The safer default is to remove `ev.html` support and use structured render types.

### 10. Documentation drift is visible and likely to mislead future Claude sessions.

Examples found:

- `README.md` still describes Python 3.11+ and “107 tests,” while the architecture document and current tree are far beyond that.
- `pytest.ini` comments say timeout was removed because `pytest-timeout` is not in requirements, but `requirements.txt` includes it.
- `Guide_06_Economy.md` still references a daily P2P cap, while the architecture document says that cap was removed and converted to velocity alerts.

This matters because Claude will treat docs as truth unless instructed otherwise.

## Recommended launch-readiness order

### P0 — fix before any broader playtest

1. Fix `@newpassword` to use the same bcrypt path as account creation.
2. Add a regression test for admin password reset → successful authentication.
3. Remove or sanitize the web client's privileged `ev.html` rendering path.
4. Add a registry collision audit with an explicit allowlist for intentional command conflicts.

### P1 — fix before inviting real outside testers

1. Design and implement quality/experiment boosts reaching combat math.
2. Add value-change logging for CP, FP, DSP, faction rep, schematic grants, material faucets, equipment destruction, and contraband confiscation.
3. Reconcile economy docs, README, architecture header/schema counts, and test-count statements.
4. Add migration rehearsal from a pre-v44 save state.
5. Add a first-session/new-player funnel test: create account → create character → complete onboarding → take first meaningful contract → earn/spend value.

### P2 — improve before “soft launch”

1. Add UI telemetry counters to identify confusion and failed commands.
2. Add accessibility/keyboard/screen-reader pass.
3. Split high-risk monolith functions into service seams with behavior-preserving tests.
4. Add economy simulation sweeps for faucets/sinks, reward rates, quality bands, and P2P velocity.
5. Add AI-era leak and prompt-output safety regression tests around every LLM-to-player surface.

## Recommended additional audits beyond the requested four

1. **Onboarding/funnel audit** — first 10 minutes, first hour, first three sessions.
2. **Live-ops/SRE audit** — backups, logs, admin tools, error budgets, restart recovery, migration rehearsal.
3. **AI safety/cost/era-consistency audit** — all LLM output surfaces, spend governor, prompt injection, canon/era guard, failure modes.
4. **Accessibility audit** — keyboard-only, color contrast, screen-reader labels, reduced motion, mobile/small-screen behavior.
5. **Abuse/exploit audit** — alt accounts, P2P laundering, contraband mule loops, reputation farming, command spam, social griefing.
6. **Documentation truth audit** — README, guides, architecture, TODO, handoffs, and Claude prompts all reconciled to one current source of truth.
