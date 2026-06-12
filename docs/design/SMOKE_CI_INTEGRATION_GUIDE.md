# Smoke Suite — CI Integration Guide

**Status:** Final design-track artifact (SH7 closeout)
**Suite size:** 97 scenarios, ~140 seconds wall-time
**Maintenance load:** Add a class for any new player-facing surface

---

## TL;DR

Run smoke on every PR that touches engine, parser, server, static,
or data files. Don't run it on doc-only or test-only PRs. The
suite is fast enough (~2 min) for blocking checks; it catches the
real bugs that unit tests miss because they touch only one layer.

To run it: `pytest -m smoke`. To skip it: `pytest` (default
`addopts` excludes the `smoke` marker).

---

## §1. What the suite covers

97 end-to-end scenarios across 21 test classes:

| Domain | Class | Scenarios |
|---|---|---|
| Login / chargen / accounts | TestFoundation | 5 |
| Movement / look / inventory | TestMovement | 6 |
| Say / pose / whisper / page / OOC | TestCommunication | 8 |
| Ground combat | TestGroundCombat | 3 |
| Help / sheet / where | TestBuiltins | 4 |
| Telnet protocol parity | TestTelnetProtocol + TestTelnetChargen | 6 |
| Clone Wars era | TestCloneWarsEra | 5 |
| Space — boarding | TestSpaceBoarding | 5 |
| Space — flight | TestSpaceFlight | 5 |
| Space — engagement | TestSpaceEngagement | 3 |
| Space — maneuvers + admin | TestSpaceManeuversAdmin | 5 |
| Space — hyperspace + repair | TestSpaceHyperspaceAndRepair | 4 |
| Space — combat gating | TestSpaceCombatGating | 5 |
| Space — SH7 long tail | TestSpaceSH7 | 8 |
| WEG dice / Force | TestWEGForce | 4 |
| Economy / progression | TestEconomyProgression | 6 |
| Missions / factions | TestMissionsFactions | 6 |
| Housing | TestHousing | 3 |
| Cantina activities | TestCantinaActivities | 2 |
| Medical | TestMedical | 2 |
| Tutorial | TestTutorial | 2 |

Each class is independent — a failure in one doesn't cascade. The
class-scoped harness gives you per-domain isolation so you can run
just the affected slice if a fix is local.

---

## §2. GitHub Actions wiring

A minimal `.github/workflows/smoke.yml`:

```yaml
name: smoke

on:
  pull_request:
    paths:
      - 'engine/**'
      - 'parser/**'
      - 'server/**'
      - 'static/**'
      - 'data/**'
      - 'tests/harness.py'
      - 'tests/smoke/**'
      - 'requirements*.txt'
      - 'pytest.ini'
  push:
    branches: [main, dev]

jobs:
  smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-asyncio
      - name: Run smoke suite
        run: pytest -m smoke -v --tb=short
        timeout-minutes: 4
```

Notes:
- `paths` filter avoids running smoke on README-only PRs
- `timeout-minutes: 5` provides headroom over the ~2.5-minute
  expected wall-time
- The `tb=short` keeps failure output usable in the PR check
  rather than the full traceback (full traceback is in the log if
  you click through)

---

## §3. Local developer workflow

### Pre-commit (optional)

For a developer who's editing engine/parser code:

```
$ pytest -m smoke -x --tb=line
```

Stops on first failure. ~2 minutes.

### Just the affected slice

If your edit is in `parser/space_commands.py`:

```
$ pytest -m smoke -v tests/smoke/test_smoke_space_*.py
```

That subset (~50 scenarios) runs in ~80 seconds.

If your edit is in `parser/builtin_commands.py`:

```
$ pytest -m smoke -v tests/smoke/test_smoke_communication.py \
                     tests/smoke/test_smoke_movement.py \
                     tests/smoke/test_smoke_builtins.py
```

### Failure debug bundles

When a smoke test fails, the conftest's `_dump_on_failure` hook
writes a debug bundle to `tests/smoke/_failures/<scenario_name>/`
containing:
- The failing session's text and JSON event transcripts
- Key DB rows for the affected character/ship/room
- The pytest assertion message

Inspect that bundle before re-running with `-v --tb=long` to skip
the guessing phase.

---

## §4. Maintenance: when to add a scenario

### Add a class when

- A new player-facing subsystem ships (e.g. crafting v2, capital
  ships, force lightning)
- A new player-facing command surface gains 3+ commands
- A pre-existing class's domain doubles in size

### Add a scenario when

- A real bug ships to production despite the smoke suite — the
  scenario that would have caught it is the regression guard
- A user-reported bug touches a surface the suite doesn't exercise

### Don't add a scenario when

- Coverage is the goal — smoke is for END-TO-END behavior, not
  branch coverage. Use unit tests for that.
- The behavior under test is undeterministic (RNG, real-time
  network) without a way to seed/control it
- The scenario takes >5 seconds to run — break it up or move to
  the (still-unused) `smoke_slow` marker

---

## §5. Class structure

Each class follows the same pattern:

```python
@pytest.mark.smoke
class TestThing:
    """One sentence describing the domain."""
    # Optional: smoke_era = "clone_wars" to override default GCW
    
    async def test_t1_short_what_it_asserts(self, harness):
        await thing_module.t1_short_what_it_asserts(harness)
```

Scenario logic lives in `tests/smoke/scenarios/<domain>.py`,
imported by the test module. This keeps test files thin (just
class + entry points) and scenarios reusable.

The `harness` fixture is class-scoped: each class boots its own
GameServer + temp SQLite. Different classes get different harnesses
so cross-class ordering doesn't matter.

---

## §6. The harness contract (what scenarios get)

```python
# Login a fresh test PC
s = await harness.login_as("MyTest", room_id=1, credits=1000,
                            protocol="websocket")  # or "telnet"

# Run a command (returns the text output)
out = await harness.cmd(s, "look")

# Inspect the typed-event stream (JSON envelopes on WebSocket)
events = s.json_events  # list[dict]

# Refresh character row from DB
s.character = await harness.get_char(s.character["id"])

# Direct DB access for setup / inspection
rows = await harness.db.fetchall("SELECT ... FROM ...", params)

# Tick advancement (SH7+; for tick-driven progression)
await harness.advance_ticks(5)

# Two-ship combat fixture (SH7+)
ctx = await harness.setup_two_ship_combat("Att", "Def")
```

The harness deliberately does NOT abstract:
- The command parser (use real text input)
- Database calls (scenarios may pre-stage state, but they go
  through the real DB layer)
- Session machinery (real `Session` objects with the same protocol
  enum production uses)

This means scenarios validate the same code paths a real player
hits — which is the whole point of end-to-end smoke testing.

---

## §7. Known limitations

1. **In-process only.** The harness boots a real `GameServer` but
   skips `start()` to avoid binding sockets. Subprocess flavor (real
   telnetlib3 stack, real WebSocket server) was deliberately
   deferred — adds a lot of complexity for incremental coverage
   above what unit tests already provide for the wire layer.

2. **Single-process tick driver.** `advance_ticks(n)` runs the same
   tick scheduler production uses, but in-process synchronously.
   Race conditions that only manifest under real concurrent ticks
   aren't catchable here.

3. **Class-scoped DB.** All tests in a class share one DB. If a
   scenario forgets to clean up after itself (leaves a ship in
   space, a character mid-quest, etc.), later scenarios in the
   same class can be affected. SH4-A's `_claim_ship(scenario_id)`
   pattern is one fix; per-scenario teardown is another. Use
   whichever fits your scenario.

4. **GCW only for many scenarios.** Anything that needs ships,
   space combat, or ship-data references gates GCW-only because
   the Clone Wars era currently has 0 seeded ships. When CW ships
   land, add a sister class with `smoke_era = "clone_wars"`.

---

## §8. Outstanding bugs the smoke harness has flagged

As of SH7 closeout — items 1-5 are fixed in the dev-branch
consolidated handoff, items 6-9 are open design questions:

1. ~~`crew.gunners` schema drift~~ — fixed
2. ~~`SCHEMA_VERSION` drift~~ — fixed
3. ~~`build_tutorial.build_all()` ignores `db_path`~~ — fixed
4. ~~`db.create_character()` ignores `credits`~~ — fixed
5. ~~`HousingCommand` import-scope bug~~ — fixed
6. `+ooc` (room-local) vs `ooc` (global) channel collision — design call
7. `page` aliased to `whisper` (same-room only) — design call
8. `whisper` requires `=` separator — UX call
9. Survey cooldown soft warning — needs investigation

Plus one data-side finding: room #3 ("Chalmun's Cantina") has
`zone_id = NULL` while sub-rooms #16-18 are correctly tagged with
zone 3. Players in the canonical cantina can't sabacc/perform.

---

## §9. Files inventory

```
tests/
├── harness.py                              # _LiveHarness, fixtures, helpers
├── conftest.py                             # smoke_era CLI, failure-dump hook
├── pytest.ini                              # smoke + smoke_slow markers
└── smoke/
    ├── __init__.py
    ├── scenarios/                          # scenario logic, reusable
    │   ├── __init__.py
    │   ├── foundation.py                   # F1-F5
    │   ├── foundation_telnet.py            # F3 (Telnet wizard)
    │   ├── movement.py                     # M1-M6
    │   ├── communication.py                # C1-C8
    │   ├── ground_combat.py                # G1-G3
    │   ├── builtins.py                     # H6-H8
    │   ├── telnet_protocol.py              # T1-T5
    │   ├── era_clone_wars.py               # CW1-CW5
    │   ├── space_boarding.py               # S1-S5
    │   ├── space_flight.py                 # S6-S10
    │   ├── space_engagement.py             # S11-S13
    │   ├── space_maneuvers_admin.py        # S15, S21-S23, S28
    │   ├── space_hyperspace_repair.py      # S9, S9b, S18, S19
    │   ├── space_combat_gating.py          # S14, S14b, S25, S30, S30b
    │   ├── space_sh7.py                    # S8, S16, S17, S20, S24, S26, S27, S29
    │   ├── weg_force.py                    # W1-W4
    │   ├── economy_progression.py          # E1-E6
    │   ├── missions_factions.py            # Q1-Q6
    │   └── social_housing_medical_tutorial.py  # H1-H9
    └── test_smoke_*.py                     # pytest entry points (one per domain)
```

That's 19 scenario modules + 21 test modules covering 97 scenarios.

---

*— SH-track complete, May 1 2026.*
