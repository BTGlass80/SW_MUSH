# HANDOFF — Drop 1.c: Close the Ledger Wave (2026-06-02)

`+finances` (player ledger view) + `@economy throttle` (admin faucet-tuning
lever) — the two user-facing pieces that **close economy-audit Phase 1
(finding F1, the ledger chokepoint)**. With 1.a→1.b.4 routing every credit
movement through `adjust_credits`, the data is all there; 1.c surfaces it.

> Part of the same-session consolidated drop. Ship
> `SW_MUSH_drops_0b_ledger_3a_3b1_1c_2026-06-02.zip`, which supersedes the
> earlier interim zips and contains 0b + ledger(1.b.4) + 3a + 3b.1 + 1.c.

---

## 1. HEAD audit — the throttle was scaffolded, not wired

The throttle **DB layer already existed at HEAD**, tagged "Drop 1.c":
- `economy_config` KV table (migration v36).
- `Database._faucet_throttle_pct` in-process cache.
- `get_faucet_throttle_pct()` / `set_faucet_throttle_pct()` (clamp, persist,
  cache, fail-open to 100).
- Application inside `adjust_credits` (scale positive deltas).

…but **no command** read or set it, and `get_char_credit_breakdown` carried a
docstring claiming it "powers the player-facing `+finances` command" — which
**did not exist**. Classic infra-complete-but-unwired. 1.c wires both, and
fixes one real correctness bug in the throttle.

---

## 2. What shipped

### `@economy throttle [0-100]` — admin lever (`parser/director_commands.py`)
- `@economy throttle` → show current throttle + plain-English state.
- `@economy throttle <0-100>` → set it (clamped, persisted to `economy_config`,
  cache refreshed). 100 % = no-op; 0 % = faucets fully suppressed (logged as
  zero `credit_log` entries so the suppression is visible on `@economy`).
- Intercepts before the dashboard render so it doesn't fall through to an empty
  board. ADMIN-gated (inherits `EconomyCommand`'s access level).

### Throttle correctness fix (`db/database.py::adjust_credits`)
- **Before:** scaled *all* positive deltas. At <100 % that would also shrink
  **p2p-transfer receipts** (a transfer is zero-sum — the sender already paid
  full) and **refunds** (a refund reverses a prior charge — throttling it
  shortchanges a player on a canceled order).
- **After:** excludes any source containing `p2p_transfer` or `refund`, so only
  genuine new-money faucets are cooled. Sinks (`delta < 0`) and `char_id == 0`
  system entries remain exempt as before. At the default 100 % the whole thing
  is still an exact integer no-op.

### `+finances [hour|day|week]` — player ledger (`parser/finances_commands.py`, new)
- Shows the player's own credit flow over a window: balance, earned (faucets),
  spent (sinks), net, transaction count, and top faucet/sink sources with
  prettified labels. Consumes `get_char_credit_breakdown`. Read-only; fails open
  to an empty summary. PLAYER-gated. Registered in `server/game_server.py`.

---

## 3. Validation (sandbox)

- `py_compile` clean: `db/database.py`, `parser/director_commands.py`,
  `parser/finances_commands.py`, `server/game_server.py`.
- **80 tests passed** across this session's four drop test files **plus the
  `test_drop1a_adjust_credits` ledger regression** — the latter confirms the
  `adjust_credits` edit doesn't regress existing ledger behaviour.
- `tests/test_drop1c_finances_and_throttle.py` (14): the **real**
  `adjust_credits` against in-memory SQLite proving faucet-scaled / sink-exempt
  / transfer-exempt / refund-exempt / system-exempt / full-suppression-logs-zero
  / clamp + persistence, plus both commands.
- Sandbox needed `aiosqlite` + `bcrypt` to exercise the real `Database`. A benign
  aiosqlite teardown ResourceWarning ("event loop is closed") appears under the
  per-test event-loop harness — it's a teardown artifact, not a failure, and is
  clean under your pytest-asyncio config.

### Pending on your Windows box (ground truth)
1. **Full pytest** (~4,854).
2. **In-client smoke:**
   - `+finances` after some earning/spending; try `+finances week`.
   - `@economy throttle 50`, earn a mission/bounty reward → confirm it's halved
     (check `@economy velocity`); confirm a refund (e.g. cancel a bounty) is
     **un**affected. `@economy throttle 100` to restore.

---

## 4. Where the economy work stands

- **Economy-audit Phase 1 (F1 ledger chokepoint): COMPLETE** (1.a → 1.c).
- **Still open:** the deferred whole-game economist pass (`T2.ECON.review`) and
  the Drop 3 sink **depth** — 3b military procurement (faction-gated) and 3b/3c
  (ship customization/paint/modules, vanity, gear insurance, repair backstop,
  catalysts, intel/Hutt/entertainer).

---

## 5. Files in this drop (within the consolidated session zip)
```
db/database.py                                     (adjust_credits throttle excludes transfers/refunds)
parser/director_commands.py                        (@economy throttle subcommand)
parser/finances_commands.py                        (NEW — +finances)
server/game_server.py                              (register +finances)
tests/test_drop1c_finances_and_throttle.py         (NEW — 14 tests)
CHANGELOG.md                                       (1.c entry prepended)
TODO.json                                          (ledger wave marked DONE)
HANDOFF_drop_1c_finances_throttle_2026-06-02.md    (this doc)
```
