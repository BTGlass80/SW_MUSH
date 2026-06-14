# HANDOFF — T3.21 Security + Optimization Audit (pre-launch fix-list)

> ## ⚠️ SECURITY TIMESLICE — captured at commit `d0c2353`. RE-AUDIT BEFORE TRUSTING.
> This is a **point-in-time security snapshot**, and a stale security verdict is worse than
> none. Before acting on this at build time:
> - **Every "OK / already-defended" verdict is PROVISIONAL.** A defense present today (bcrypt,
>   the SQL allowlist, the LLM output clamps, the Claude budget breaker) can be refactored away
>   between now and the build. Re-confirm each before relying on it.
> - **`server/web_portal.py` findings were captured WHILE THE SESSION WAS EDITING THAT FILE**
>   (it was dirty during the audit). All three launch-blockers live there — re-verify them
>   first; they're the most likely to have already shifted.
> - **Treat the blocker/fix list as a RE-CHECK CHECKLIST, not a certified state.** At build
>   time, confirm each gap still exists AND sweep for NEW gaps the intervening drops introduced.
> The value is a head-start on *where to look*, not a guarantee of *what is true*.

## TL;DR — solid foundation, no catastrophic class, a narrow band of real exposure

Defensive review of authz/session, injection/input, secrets/DoS, perf/scale. Severity tally:
**4 OK · 17 LOW · 18 MEDIUM · 8 HIGH · 3 LAUNCH-BLOCKER.** Verdict: **the genuinely
catastrophic classes are ABSENT** — no SQL injection, no RCE, no auth bypass, no
plaintext/secret exposure, no player-drainable Claude budget. The build is targeted, not a
rewrite.

## ✅ What's already good (so the fix is narrow — re-confirm at build time)

- **No SQL injection.** Every dynamic query traced is parameterized or built from a **hardcoded
  column allowlist** (`web_portal.py` handle_characters/handle_scenes append only `col = ?`
  skeletons, values bound). *The audit's two initial "SQLi" flags it then verified SAFE* —
  maintainability hazards, not vulns. The `save_character` writable-column allowlist
  (`db/database.py:1811-1822`) raises on any non-allowlisted column.
- **bcrypt** password hashing (gensalt + constant-time checkpw, no plaintext logging,
  5-fail/5-min per-account lockout). OWASP-clean.
- **The $20 Claude budget is NOT player-drainable** — the only Claude caller is the tick-gated
  Director faction turn (no player command triggers it); player AI is local Ollama behind a
  per-char rate limiter. The breaker circuit-breaks at 90% with graceful fallback.
- **Funnel discipline intact** (adjust_credits / perform_skill_check / adjust_territory_influence)
  — money/dice/territory mutation centralized, no per-endpoint faucet sprawl.

## 🔴 LAUNCH-BLOCKERS (3 — all small, localized, all in `web_portal.py` + one in `commands.py`)

1. **IDOR / player-privacy leak — `web_portal.py:553-677` (handle_character).** Verified at HEAD:
   `profile["online"]` (line ~650), `achievement_count`, and `scene_count` are returned for ANY
   `char_id` with **zero ownership check** (only credits/skills/attributes are gated). An
   unauthenticated client can enumerate sequential char_ids and build a **live who's-online /
   who's-active map of every player** — a real-player stalking/targeting vector, and the one
   finding that genuinely lets one player derive data about another. *Fix:* move online/
   achievement_count/scene_count into the owner/admin branch; 404 on inactive/nonexistent so IDs
   can't be probed. No schema change. (Also fix the `m.character_id`→`m.char_id` typo at ~610 in
   the same function.)
2. **No IP rate-limit on portal login — `web_portal.py:1224-1261` (handle_login).** Calls
   `db.authenticate` with no per-IP throttle. The 5-fail/5-min lockout is PER-ACCOUNT, so
   credential stuffing across many accounts is unbounded. *Fix:* reuse the `api.py`
   `_get_client_ip`/`_check_rate_limit` pattern, return 429 before authenticate. (Also add a
   throttle to the Telnet `connect`/`create` pre-auth commands.)
3. **Admin authority is a never-revalidated snapshot — `parser/commands.py:82-98` (check_access).**
   `is_admin` is read from `session.account` set at login, never re-checked — a revoked admin
   keeps power until disconnect, and there's NO audit trail of who ran which @-command. *Fix:*
   re-validate `is_admin` against the DB on each ADMIN check (or short-TTL refresh) + add a
   DB-backed `admin_audit` table written at the @-command dispatch seam.

## 🟡 HIGH (fix in the hardening pass, not strictly launch-blocking)

- **Session token secret non-persistent** — `api.py:39` (`os.urandom(32)` at import): every
  restart invalidates all tokens, forcing mass re-auth. Availability/UX, not forgery. *Fix:*
  persist to a gitignored 0600 config file, load-or-create on boot.
- **X-Forwarded-For trusted blindly** — `api.py:91-97`: an attacker can spoof the leading IP to
  defeat the rate limiter (undercuts blockers 2). *Fix:* peername-only on direct-connect; honor
  XFF only from a known proxy IP behind a reverse proxy.
- **Director LLM output not sanitized before player display** — `director.py:1086` headline →
  `director_log` → `/api/portal/news`: truncated but not stripped of metacharacters (no RCE, a
  display-integrity issue). *Fix:* a `sanitize_for_display` before the log write.

## ⚡ PERF risks (bite at N concurrent players, not at 1)

- **Single shared aiosqlite connection serializes ALL queries** — `db/database.py:1449,1458`.
  One connection on one worker thread; WAL+busy_timeout help write contention but add no read
  parallelism. **The dominant scale ceiling** — at tens of active players + the 1Hz tick loop,
  interactive latency climbs. *Launch mitigation:* keep per-request query counts low (fix the
  N+1 below); *medium-term:* a small read-only connection pool for SELECT-heavy portal endpoints.
- **N+1 in the character directory** — `web_portal.py:506-520`: per page, 1 list query + up to
  20 full-row `get_character` SELECTs (just to read faction from the attributes blob), each
  serialized behind the single connection. *Fix:* SELECT attributes in the page query, parse
  faction inline.
- **No index on `characters(account_id)`** — a frequent lookup column. *Fix:* one-line
  `CREATE INDEX idx_characters_account` migration.

## Recommended split (answers the readiness review's "pre-pass?" question)

**YES — pull the 3 blockers FORWARD into a lightweight security pre-pass, don't wait for the
dead-last full review.** They're small, well-localized, depend on no design forks, and the IDOR
is a real-player privacy break that shouldn't be live for even a soft launch. Doing them now
de-risks the final review (fewer blocker-class findings when schedule slack is least).
- **Pre-pass NOW:** the 3 blockers + the `idx_characters_account` migration (ships free with the
  IDOR/login work).
- **Full review (dead-last):** the HIGH items (token persistence, XFF, LLM sanitize), the N+1,
  the connection-pool, and the LOW/MEDIUM tail.

## 🔴 Collision note (LIVE)

All three blocker-fixes land in `server/web_portal.py`, which is **dirty in the session right
now** (the audit was captured while it was being edited). The admin-revalidation + audit table
touch `parser/commands.py` + `db/database.py` (schema + migration), and `db/database.py` is also
hot. Concrete risks: (a) two concurrent edits to `web_portal.py` will conflict — do the security
edits as their own commits on top; (b) the `admin_audit` + `idx_characters_account` migrations
must **reserve the next SCHEMA_VERSION** before any in-flight migration work, or the numbers
collide; (c) the typo fix + IDOR edit are in the same function — one pass. **Land the pre-pass as
a dedicated branch and rebase the hot feature work onto it, not interleaved.**

*Full ~47-finding audit in workflow task `wzhe73me6.output`. Re-run the audit against HEAD before
the build — this is a timeslice.*
