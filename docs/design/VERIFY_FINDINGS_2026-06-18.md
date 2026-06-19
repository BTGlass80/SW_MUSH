# Concurrency / Tick Verification — Findings & Status (2026-06-18)

Source: an adversarial read-only Workflow probe of the **never-load-tested runtime surfaces**
(read-pool/WAL, throttle/session state, tick/timer systems, WS event routing) — the residual-risk
surfaces the QA method-note flagged (zero concurrency/load testing; tick-driven systems never run).
18 findings, all confirmed-in-code or likely. **7 fixed (the blocker + 5 of 6 high + 2 med/low);
the rest are documented here for follow-up.**

## ✅ FIXED (committed, with regression tests)

| Sev | Finding | Commit |
|---|---|---|
| **BLOCKER** | `wound_recovery_tick` iterated nonexistent `sm.sessions` → free wound recovery never fired | verify-fix 1 |
| HIGH | Hutt-debt collection tick — same `.sessions` bug → collected nothing | verify-fix 1 |
| HIGH | Read-pool poisoning — rejected write left an open txn → stale reads + WAL growth | verify-fix 2 |
| HIGH | Tutorial hint-timer leak — never cancelled on disconnect | verify-fix 3 |
| HIGH | Area-map memo advanced before send → map blank until re-enter | verify-fix 4 |
| HIGH | Combat broadcasts sequential → slow client head-of-line-blocks the round | verify-fix 4 |
| MED | `broadcast_chat` global branch iterated dict keys (ints) → crash on null room | verify-fix 4 |
| LOW | Dead duplicate `case 'pose_event'` in client WS dispatch | verify-fix 4 |
| (LOW×2) | Read-pool: no txn-reset on release + overstated "snapshot" docstrings | folded into verify-fix 2 |

(Also fixed the now-false `hasattr(...,"sessions")` guard in `achievements.py` + the `director.py` site.)

## ⏳ OPEN — for follow-up drops (with evidence + fix-sketch)

### HIGH — needs its own careful drop (scheduler-semantics change)
- **Tick-scheduler uptime counter never fires long-interval ticks on a restart-prone box.**
  `server/game_server.py:478` `self._tick_count=0` (uptime, resets every restart) → `:1830` increment
  → `tick_scheduler.py:98` `(ctx.tick_count - h.offset) % h.interval != 0`. A weekly tick
  (interval≈604800) needs ~7 days of *continuous* uptime to ever satisfy the modulo; a home box that
  reboots never gets there (long-interval economy ticks — payroll, fees — never fire), and a very
  long-uptime box can double-apply. **Fix options:** (a) derive scheduling from wall-clock + a
  per-handler "last-fired window" with a boot-skip guard (robust but changes ALL handlers — must
  re-verify the hot short-interval combat/movement/telemetry ticks); (b) leave the scheduler alone
  and give each long-interval economy tick a DB-anchored idempotency check (`last_payroll_ts` etc. —
  surgical, touches each handler). **Relevant to the home-hosted launch (restarts happen).** Do NOT
  rush — pick (a) or (b) deliberately and gate on the full suite.

### MEDIUM
- **Parser rate-bucket leak / cross-session bleed.** `parser/commands.py:306` `_rate_buckets` keyed on
  `id(session)` (reused address) and never freed. Fix: key on `session.id`, delete in
  `SessionManager.remove` (same pattern as the hint-timer fix).
- **Per-IP throttle empty-key leak.** `server/api.py:152,194` + `server/web_portal.py:51` — the sliding
  window prunes timestamps within a key but never deletes an emptied key → unbounded dict growth across
  distinct IPs. Fix: `del bucket[ip]` when emptied, or a periodic reaper.
- **Same-account double-login TOCTOU.** `server/game_server.py:996-1012` — `find_by_account` is checked
  *before* the bcrypt await and never re-checked, so two concurrent logins can both bind. Fix: re-run
  `find_by_account` after `authenticate` (close+remove the existing in the same sync slice) + a
  `find_by_character` guard at bind.
- **Ship-systems lost-update race.** `tick_handlers_ships.py:43-78` — tick and a concurrent player
  command both do full-`systems`-JSON read-modify-write on the same ship row (last writer wins). Fix:
  a JSON-merge update helper (read inside the await-free critical section, merge changed keys) or an
  optimistic version column.
- **No per-session send buffer bound.** `server/session.py` send path has no outbound queue/limit — a
  slow/non-reading WS client balloons the aiohttp transport buffer unbounded. Fix: bound the outbound
  path (`asyncio.wait_for` on sends with force-close on repeated timeout, or a bounded queue + single
  writer task that drops on overflow).

### LOW
- **Kicked session keeps running its loop.** `server/game_server.py:1004-1005` `existing.close()` only
  sets DISCONNECTING + awaits transport close; it doesn't cancel the kicked session's handler task →
  stale-copy save race. Fix: track + cancel the per-session task on kick.
- **SpaceGrid not rehydrated on boot.** `engine/starships.py:168-218` — transient grid rebuilt empty
  each start; undocked ships are absent from the combat/range grid after a restart until they relaunch.
  Fix: re-add `get_ships_in_space()` (non-hyperspace) ships at startup, mirroring `hyperspace_arrival_tick`.

## Not-bugs (verified clean, for the record)
Per-IP login throttle is correctly per-IP (not global); per-viewer combat_state is correctly
personalized (no private-data leak); the Mail/Achievements producer↔consumer shapes are aligned (that
bug was already fixed); the tick scheduler's per-handler try/except isolation is sound.
