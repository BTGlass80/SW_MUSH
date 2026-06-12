# SW_MUSH — Engineering Standards & Testing Conventions
## Lessons from Sessions 32-34 Code Review
### Living Document — Last Updated April 16, 2026

---

## 1. Code Review Process — What Worked

### 1.1 Phased Severity Approach

The review organized findings by blast radius, not by file or feature:

| Phase | Category | Example |
|---|---|---|
| **Phase 1** | Will crash at runtime | Missing methods, missing imports, wrong function names |
| **Phase 2** | Silent data loss | Bare `except: pass`, unguarded `json.loads()` |
| **Phase 3** | Architectural debt | Encapsulation leaks, god-object methods, split-brain patterns |
| **Phase 4** | Polish | Missing docstrings, hardcoded ANSI, input length limits |

**Key lesson:** Fix crash-level bugs first. A 500-line god-object is ugly
but functional; a call to a nonexistent method brings down the server.

### 1.2 Mechanical Migrations Over Surgical Patches

The DB proxy migration (444 call sites, 41 files) proved that large
mechanical changes are *safer* than they look when the transformation is
purely syntactic:

```python
# Before (444 occurrences)
rows = await db._db.execute_fetchall("SELECT ...", params)

# After (identical behavior, clean API)
rows = await db.fetchall("SELECT ...", params)
```

**Rules for safe mechanical migration:**
- Every change is the same pattern — no judgment calls per site
- AST-validate every modified file before packaging
- Run `grep` to verify zero remaining instances of the old pattern
- Run full test suite after each batch

### 1.3 God-Object Refactoring — Two Distinct Patterns

Not all large methods are the same. We found two patterns that need
different refactoring strategies:

**Pattern A — Sub-command dispatch (if/elif chains):**
Methods like `FactionCommand.execute()` (507 lines) that dispatch to
15+ sub-commands via `if sub == "list": ... return`. These are trivially
refactored into a dispatch table + `_cmd_*` methods. An automated AST
transformer handled 3 files in minutes.

**Pattern B — Linear flow with side effects:**
Methods like `MoveCommand.execute()` (323 lines) that do one thing but
with many sequential steps (validate, check locks, broadcast departure,
move, broadcast arrival, check hostile NPCs, fire tutorial hooks...).
These need block extraction into named helpers. Identify blocks by:
- Independent try/except wrappers (each is a natural extraction unit)
- Comment headers that label sections
- Post-action hooks that can be batched into `_post_X_hooks()`

**Key lesson for Pattern B:** Don't force a dispatch table where there
isn't one. Extract the 2-3 largest blocks and leave the rest. Getting
from 323 → 165 lines is a win; getting to 50 isn't realistic for linear
flow methods and would just scatter the logic.

---

## 2. Test Failures — Lessons Learned

### 2.1 Never Ignore a Failing Test

Session 34 inherited a "pre-existing" `test_negative_pips` failure that
had been waved through for multiple sessions. When we actually looked:

- The **code** was right (WEG D6 die borrowing: `3D-1` → `2D+2`)
- The **test** had a wrong assertion and a wrong comment
- Nobody had verified which one was correct because it was "pre-existing"

Fixing all 4 "pre-existing" failures took ~20 minutes and revealed:
- A wrong assertion about game mechanics (`test_negative_pips`)
- Stale schema version hardcoding (`test_npc_crew_migration`)
- An incorrect expectation about dismiss vs delete semantics (`test_wage_deduction`)
- A mock that was missing an attribute set to None (`test_parser_infra`)
- A FakeDB that lacked proxy methods after a 444-site migration (`test_plots`)

**Rule: If a test fails, either fix the test or fix the code. Never
skip it. "Pre-existing" is not a status — it's a debt that compounds.**

### 2.2 Test Mocks Must Explicitly Null Optional Attributes

`MagicMock()` returns a new `MagicMock` for any attribute access. If
production code does `getattr(obj, "_some_flag", None)` to check for an
optional attribute, the mock will return a truthy MagicMock instead of
None, causing the code to take an unexpected branch.

```python
# BAD — _input_intercept will be a MagicMock (truthy)
session = MagicMock()

# GOOD — explicitly set optional attributes
session = MagicMock()
session._input_intercept = None
session._char_obj = None
```

**Rule: When creating mocks, explicitly set every `getattr(..., None)`
attribute that production code checks.**

### 2.3 FakeDB Classes Must Track the Real API

The `test_plots.py` FakeDB had `self._db = conn` but no proxy methods.
When session 33 migrated all code from `db._db.execute_fetchall()` to
`db.fetchall()`, the FakeDB broke silently — it only showed up when the
test actually ran.

**Rule: After any API migration, grep test files for the old pattern:**
```bash
grep -rn "_db\._db\.\|_db\.execute_fetchall" tests/
```

Better yet, make test helpers inherit from or wrap the real class:
```python
class FakeDB:
    def __init__(self, conn):
        self._db = conn
    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)
    async def fetchone(self, sql, params=()):
        rows = await self._db.execute_fetchall(sql, params)
        return rows[0] if rows else None
    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)
    async def commit(self):
        await self._db.commit()
    async def execute_commit(self, sql, params=()):
        await self._db.execute(sql, params)
        await self._db.commit()
```

### 2.4 Schema Version Assertions Must Be Dynamic

Hardcoding `assert schema_version == 2` guarantees a future failure.
Always reference the constant:

```python
from db.database import SCHEMA_VERSION
assert rows[0]["v"] == SCHEMA_VERSION
```

---

## 3. Testing Conventions for New Code

### 3.1 What to Test

| System type | Test focus | Example |
|---|---|---|
| Dice / math | Deterministic edge cases | Wild Die explosion, pip overflow, negative pips |
| Engine functions | Input → output with in-memory DB | `create_plot()` → returns plot dict |
| Command execution | Mock session receives expected output | `FactionCommand` → `session.send_line` called |
| DB proxy methods | Round-trip through `:memory:` DB | Insert → fetchall → verify rows |
| HUD helpers | Payload structure from character dict | `_hud_base()` returns correct keys |
| Refactored methods | Behavior unchanged after extraction | Telnet skips, no-char skips, basic payload |

### 3.2 Test Structure

```python
class TestFeatureName:
    """Group related tests in a class."""

    def test_happy_path(self):
        """Test the normal case first."""
        ...

    def test_edge_case(self):
        """Then boundaries and special inputs."""
        ...

    def test_error_handling(self):
        """Then failure modes."""
        ...

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Async tests need the marker."""
        ...
```

### 3.3 FakeSend Pattern for WebSocket Tests

```python
class FakeSend:
    """Captures all messages sent via _send."""
    def __init__(self):
        self.messages = []
    async def __call__(self, data):
        self.messages.append(data)

def make_session(char=None):
    from server.session import Session, Protocol, SessionState
    sender = FakeSend()
    async def noop(): pass
    s = Session(Protocol.WEBSOCKET, sender, noop)
    s.state = SessionState.IN_GAME
    s.character = char or { ... }
    return s, sender
```

This avoids MagicMock pitfalls and gives you direct access to sent
messages for assertion.

### 3.4 AST Validation Before Delivery

Every modified Python file must pass `ast.parse()` before packaging:

```python
import ast
for path in modified_files:
    ast.parse(open(path).read())
```

This catches syntax errors, unclosed brackets, and bad indentation
that would cause import failures at runtime.

### 3.5 Grep Verification After Migrations

After any pattern migration, verify zero remaining instances:

```bash
# After DB proxy migration
grep -rn "db\._db\." --include="*.py" | grep -v "db/database.py" | wc -l
# Expected: 0

# After silent-except sweep
grep -rn "except.*:$" --include="*.py" -A1 | grep "pass$" | wc -l
# Expected: 0 (or only intentional cases)
```

---

## 4. Architectural Invariants (Never Bypass)

These rules exist because violating them has caused real bugs:

1. **All influence changes → `adjust_territory_influence()`**
2. **All guard spawns → `spawn_guard_npc()`**
3. **All org storage → `adjust_org_storage()`**
4. **All contest state → `territory_contests` table** (no in-memory cache)
5. **All out-of-combat dice → `perform_skill_check()`** (never call `roll_d6_pool` directly)
6. **All intrusion rolls → `perform_skill_check()`**
7. **All private room entry → `can_enter_housing_room()`**
8. **Every `except Exception` must include `log.warning`** — no silent passes
9. **Verify `import logging` + `log = logging.getLogger(__name__)` exist** before adding log calls
10. **All external DB access → proxy methods** (`db.fetchall`, `db.execute`, `db.commit`) — never `db._db.*` from outside `database.py`
11. **All test FakeDB classes must implement proxy methods** — not just `self._db = conn`

---

## 5. Delivery Conventions

### 5.1 Zip Structure

```
session_NN_description.zip
├── server/session.py
├── parser/faction_commands.py
├── engine/whatever.py
├── tests/test_new_feature.py
└── patches/  (if surgical patches instead of full files)
```

Zip uses relative paths from project root so `unzip -o` from `SW_MUSH/`
drops files in the right place.

### 5.2 Validation Checklist

Before declaring a delivery ready:

1. Every `.py` file in the zip passes `ast.parse()`
2. `grep` confirms zero instances of any eliminated pattern
3. Full test suite runs — **0 failures, not "only pre-existing failures"**
4. Handoff doc lists every file with line count change
5. Handoff doc includes a testing checklist for manual verification

---

*This document captures engineering lessons from the Sessions 32-34 code
review (99 files modified, 444 call sites migrated, 133 silent exceptions
logged, 8 god-objects refactored, 4 test failures fixed, 27 new tests
added). Update it as new patterns emerge.*
