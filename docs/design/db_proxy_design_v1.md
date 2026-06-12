# SW_MUSH: Database Proxy Methods — Design Doc v1

**Date:** April 16, 2026
**Author:** Claude (Opus, Session 33)
**Status:** Design complete → ready for Sonnet implementation
**Scope:** Eliminate all 444 raw `db._db.*` accesses across 40 files by
adding proxy methods to the `Database` class. Phase 3 C1 from the session
32 code review.

---

## 1. Problem Statement

The `Database` class in `db/database.py` wraps `aiosqlite.Connection` but
provides no generic query methods. Engine and parser code must reach
through to the raw connection via `db._db`:

```python
# Current pattern (444 occurrences)
rows = await db._db.execute_fetchall("SELECT * FROM foo WHERE id = ?", (1,))
await db._db.execute("UPDATE foo SET bar = ? WHERE id = ?", (val, 1))
await db._db.commit()
```

This creates:
- **Commit-safety risk**: every write caller must remember `db._db.commit()`
  after their last `execute`. Forgetting it means data writes sit in
  uncommitted state until the next unrelated caller commits — or until
  the connection closes, rolling them back silently.
- **Encapsulation breach**: 40 files depend on `_db` being an aiosqlite
  Connection with specific methods. If we ever swap the backend (e.g., to
  PostgreSQL), every call site breaks.
- **Inconsistency**: half the codebase uses the wrapper's named methods
  (`db.get_room()`, `db.save_character()`), the other half uses raw SQL
  through `db._db`.

## 2. Design

### 2.1 New Methods on `Database`

Add three proxy methods after `close()`:

```python
async def fetchall(self, sql: str, params: tuple = ()) -> list:
    """Execute SQL and return all rows as a list of Row objects."""
    return await self._db.execute_fetchall(sql, params)

async def fetchone(self, sql: str, params: tuple = ()):
    """Execute SQL and return the first row, or None."""
    rows = await self._db.execute_fetchall(sql, params)
    return rows[0] if rows else None

async def execute(self, sql: str, params: tuple = ()):
    """Execute a write statement (INSERT/UPDATE/DELETE). Does NOT auto-commit."""
    return await self._db.execute(sql, params)

async def commit(self):
    """Commit the current transaction."""
    await self._db.commit()

async def executescript(self, sql: str):
    """Execute a multi-statement SQL script."""
    await self._db.executescript(sql)
```

### 2.2 Why NOT auto-commit

The codebase has ~50 multi-statement write batches like:

```python
await db._db.execute("UPDATE ships SET ...", ...)
await db._db.execute("INSERT INTO ship_log ...", ...)
await db._db.commit()  # one commit for both
```

Auto-commit on every `execute()` would turn these into separate
transactions, hurting performance (2× fsync overhead) and breaking
atomicity. Keeping explicit `commit()` is the safer migration path.

### 2.3 Migration Pattern

For each file, the transformation is mechanical:

```python
# Before
rows = await db._db.execute_fetchall("SELECT ...", params)
await db._db.execute("INSERT ...", params)
await db._db.commit()

# After
rows = await db.fetchall("SELECT ...", params)
await db.execute("INSERT ...", params)
await db.commit()
```

The `self._db._db` pattern (in web_portal.py and a few others where `self._db`
is the Database instance) becomes:

```python
# Before
rows = await self._db._db.execute_fetchall("SELECT ...", params)

# After
rows = await self._db.fetchall("SELECT ...", params)
```

### 2.4 Internal usage (database.py itself)

The 100+ methods inside `database.py` also access `self._db` directly.
These do NOT need migration — they're inside the class, using the private
attribute is correct encapsulation. Only external callers need the proxy.

## 3. Scope

### 3.1 Call-site inventory

| Method | External Calls | Pattern |
|---|---|---|
| `_db.execute_fetchall` | 200 | `rows = await db._db.execute_fetchall(sql, params)` → `rows = await db.fetchall(sql, params)` |
| `_db.execute` | 139 | `await db._db.execute(sql, params)` → `await db.execute(sql, params)` |
| `_db.commit` | 104 | `await db._db.commit()` → `await db.commit()` |
| `_db.executescript` | 1 | `await db._db.executescript(sql)` → `await db.executescript(sql)` |
| **Total** | **444** | |

### 3.2 Files by access count (top 20)

| File | Accesses |
|---|---|
| `engine/housing.py` | 112 |
| `engine/territory.py` | 52 |
| `build_tutorial.py` | 33 |
| `engine/scenes.py` | 32 |
| `engine/plots.py` | 23 |
| `parser/mail_commands.py` | 20 |
| `engine/party.py` | 19 |
| `engine/events.py` | 19 |
| `engine/director.py` | 16 |
| `engine/world_lore.py` | 12 |
| `parser/building_tier2.py` | 10 |
| `parser/housing_commands.py` | 8 |
| `engine/room_states.py` | 8 |
| `parser/faction_leader_commands.py` | 7 |
| `build_mos_eisley.py` | 7 |
| `parser/mux_commands.py` | 6 |
| `engine/spacer_quest.py` | 6 |
| `parser/scene_commands.py` | 5 |
| `engine/achievements.py` | 5 |
| `server/session.py` | 4 |

Plus 20 more files with 1-4 accesses each.

## 4. Implementation Plan

### Drop 1: Database proxy methods + tests

**Scope:** Add the 5 proxy methods to `db/database.py`. Write a test file
`tests/test_db_proxy.py` that verifies each method against a `:memory:` DB.
No call-site migration yet.

**Deliverable:** `db/database.py` (modified), `tests/test_db_proxy.py` (new).

### Drop 2: Small files (1-6 accesses, ~20 files)

Migrate all files with ≤6 `_db` accesses. These are quick, low-risk, and
get the long tail out of the way. Estimated 20 files, ~80 call sites.

Files: `server/session.py`, `server/api.py`, `server/game_server.py`,
`parser/shop_commands.py`, `parser/scene_commands.py`,
`parser/tutorial_commands.py`, `parser/channel_commands.py`,
`parser/narrative_commands.py`, `parser/director_commands.py`,
`parser/plot_commands.py`, `parser/combat_commands.py`,
`parser/builtin_commands.py`, `parser/mux_commands.py`,
`engine/achievements.py`, `engine/spacer_quest.py`, `engine/debt.py`,
`engine/idle_queue.py`, `engine/npc_crew.py`, `engine/smuggling.py`,
`engine/room_states.py`, `engine/vendor_droids.py`,
`engine/organizations.py`, `engine/hazards.py`, `engine/narrative.py`,
`engine/world_lore.py`, `ai/npc_brain.py`.

### Drop 3: Medium files (7-20 accesses, ~7 files)

`parser/mail_commands.py` (20), `parser/housing_commands.py` (8),
`parser/building_tier2.py` (10), `parser/faction_leader_commands.py` (7),
`engine/events.py` (19), `engine/party.py` (19),
`engine/director.py` (16).

### Drop 4: Large files (20+ accesses, ~5 files)

`engine/housing.py` (112), `engine/territory.py` (52),
`engine/scenes.py` (32), `engine/plots.py` (23).

### Drop 5: Build scripts

`build_tutorial.py` (33), `build_mos_eisley.py` (7). These can use the
build script's own db instance — same proxy pattern applies.

### Drop 6: web_portal.py cleanup

`server/web_portal.py` already has the `_fetchone` helper from Session 33
Phase 1 that routes through `self._db._db.execute_fetchall`. After the
proxy is in place, refactor the helper to use `self._db.fetchone` and
migrate the remaining `self._db._db.execute_fetchall` calls to
`self._db.fetchall`.

### Validation per drop

Each drop:
1. AST-validate every modified file.
2. `grep -rn "db\._db\." --include="*.py" | grep -v "db/database.py"` →
   count should decrease by the expected amount.
3. Run `python3 -m pytest tests/` to confirm no regressions.

### Final validation

When all drops are applied:
- `grep -rn "db\._db\." --include="*.py" | grep -v "db/database.py\|tests/"` → **zero** results (excluding database.py internal usage and test files).
- Full test suite passes.
- Server boots and responds to basic commands.

## 5. Risk Assessment

**Low risk.** Every change is a pure rename of a method call path — the
SQL strings and parameter tuples are identical. No behavioral changes.
No schema changes. The proxy methods are thin wrappers that delegate to
the same underlying aiosqlite methods.

The main risk is **merge conflicts** if new code is written between drops
that introduces fresh `_db._db` accesses. Mitigation: process all drops
in a single focused session.

## 6. Future Benefits

Once all external callers use the proxy:
- **`_db` becomes truly private.** New code has no reason to touch it.
- **Auto-commit option.** A future `db.execute_and_commit()` method can
  bundle the commit for single-write cases, reducing boilerplate.
- **Transaction context manager.** `async with db.transaction(): ...`
  can batch multiple writes with a single commit at the end.
- **Backend swap.** The `Database` class becomes a genuine abstraction
  layer. Swapping SQLite for PostgreSQL requires only changing the
  internals of the 5 proxy methods.

---

*Design doc for Phase 3 C1. Estimates: Drop 1 (~30 min), Drops 2-5 (~3-4
hours total), Drop 6 (~30 min). Can be spread across 1-2 Sonnet sessions.
All drops are cumulative and can be validated independently.*
