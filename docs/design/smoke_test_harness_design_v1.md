# Smoke Test Harness — Design v1

**Date:** Apr 30, 2026
**Author:** Claude (Opus, parallel session — does NOT touch the active dev branch)
**Status:** Design — awaiting Brian's sign-off on §6 scenario list before implementation
**Scope tag:** `tests/smoke/` (new subtree); also fills the existing
`tests/harness.py` placeholder (Drop 1 of the umbrella sweep left
`_SkipHarness` as a TODO; this design replaces it with a real harness)
**Companion to:** `sw_d6_mush_architecture_v38.md` (delivered as a delta
doc; the active dev session keeps editing v38 directly, this doc folds
in once it's done)

---

## §1. Why this exists

The pytest suite at v38 (1,919 collected, all green) is **regression
coverage**. It asserts that named functions and classes behave as
written, in isolation, with mocked dependencies. It catches "did
someone change `volume_premium()`'s formula" — but it does not catch:

- Wiring bugs (function works in isolation, but the command that calls
  it passes the wrong arg, or the WebSocket handler never routes to it)
- Cross-system state drift (combat HUD says one thing, `combat_state`
  payload says another, because two systems wrote in different orders)
- Client/server protocol drift (server sends `event_type`, JS expects
  `mode`)
- Async race conditions (tests `await` deterministically; live
  sessions don't)
- Real DB schema issues (`execute_fetchone` calls flagged in
  pre-launch issues, missing columns surfacing on first migration)
- "Does anything actually work end-to-end" — which is what Brian
  originally asked for and what gets bypassed every time he logs in
  manually and finds bugs

The phantom-delivered pattern (S51 economy helpers; S57b/S58 umbrella
classes) is the same gap in another guise: a test asserting
`ShopUmbrellaCommand` does X is satisfied by writing
`ShopUmbrellaCommand`, not by connecting it to anything a player can
reach.

This harness exists to fill the gap. It drives a real (or in-process)
server through scripted player sessions and asserts on the wire output
the player would actually see.

## §2. Scope and non-goals

**In scope:**
- A pytest-marked test layer (`@pytest.mark.smoke`) that runs scripted
  player sessions end-to-end
- Both Telnet and WebSocket protocols (parameterized — same scenarios
  run through both)
- Both server-boot modes:
  - **In-process:** harness imports `GameServer`, boots against a
    temp SQLite, drives sessions in-memory via `Session.feed_input`
    and a captured `send_callback`. Fast (single-process, no sockets),
    matches the "boots full game stack against temp SQLite with
    `MockSession`" path that v38 §21B already documents.
  - **Subprocess:** harness `subprocess.Popen`s `python main.py
    --db <tempfile> --telnet-port <free> --web-port <free>`, waits
    for the listening sockets, then drives real Telnet and WebSocket
    clients against them. Slower, but exercises the actual transport
    layer including aiohttp, telnetlib3, and the boot ordering pinned
    by `test_f6a6_boot_ordering.py`.
- Both era flavors (CW + GCW) — parameterized via `@pytest.mark.parametrize`
- Fail-fast and continue-on-error modes (CLI flag controlled)
- Fills the existing `tests/harness.py` skeleton — the ~7 currently
  skipped tests in `test_economy_validation.py` start running for free

**Out of scope (explicitly):**
- Replacing or rewriting any existing unit/integration tests
- Performance benchmarking, load testing
- Browser-driven testing of `static/client.html` JavaScript (that's a
  separate Selenium/Playwright concern and not what Brian asked for)
- Visual regression of the UI
- Testing the Director AI or Mistral-7B output (non-deterministic;
  smoke tests assert on structure, not content)

## §3. Architectural fit

### §3.1 What already exists (and gets reused)

- **`tests/harness.py`** — Drop 1 of the umbrella sweep created this
  with a `_SkipHarness` placeholder and the comment *"If a real
  integration harness is ever introduced, replace `_SkipHarness`
  below with the live one and the runtime tests will start running
  without any further changes to the test file."* This design honors
  that contract.
- **The harness API contract** (discovered by grepping
  `test_economy_validation.py`):
  ```python
  s = await harness.login_as("Name", room_id=2, credits=5000, is_admin=False)
  out = await harness.cmd(s, "+repair Worn DL-44")
  s.character = await harness.get_char(s.character["id"])
  await harness.give_item(s.character["id"], {...})
  credits = await harness.get_credits(s.character["id"])
  rows = await harness.db._db.execute_fetchall(...)  # legacy; will be replaced with proxy
  ```
  Any harness that ships will implement this surface so those ~7
  skipped tests come back online.
- **`GameServer`** has clean `async def start()` / `async def stop()`
  methods with no global state — it accepts a `Config`, builds its own
  `Database`, `SessionManager`, `CommandRegistry`. Multiple instances
  on different ports/DBs in the same process are viable.
- **`Session.feed_input(text)`** is the public API for "user typed
  this." This is what both Telnet and WebSocket handlers call. The
  in-process harness uses it directly; the subprocess harness goes
  through a real socket.
- **`send_callback`** on `Session` is the seam where output goes out.
  In-process harness wraps it to capture per-session.

### §3.2 What the architecture doc says vs. what the code does

While reading the source for this design, found two drift points
worth recording (not blockers, but flagging for a future v38 update):

- **Architecture v38 §3.1** says WebSocket runs on port 4001.
  Reality: WebSocket runs on the same port as HTTP (default 8080) at
  `/ws`. There's a comment in `server/web_client.py:13` confirming
  the separate websockets-library server on 4001 was removed. The
  architecture doc has drifted; the harness will use 8080 and an
  override in tests, matching the actual code.
- **The `Config` dataclass** has `web_client_port` (HTTP+WS shared)
  and `websocket_port` (legacy, unused). The smoke harness ignores
  `websocket_port`.

These are noted in the design but the dev session can address them
whenever; not blockers for the harness.

### §3.3 How it slots into the existing test layout

```
tests/
├── conftest.py              (existing — re-exports harness fixture; minor edit)
├── harness.py               (existing — _SkipHarness REPLACED with real one)
├── test_economy_validation.py  (~7 tests un-skip automatically)
├── ...                      (1,919 existing tests, untouched)
└── smoke/                   (NEW subtree)
    ├── __init__.py
    ├── conftest.py          (smoke-specific fixtures: server, client_factory)
    ├── client_telnet.py     (lightweight Telnet driver)
    ├── client_ws.py         (lightweight WebSocket driver)
    ├── boot_inproc.py       (in-process GameServer fixture)
    ├── boot_subproc.py      (subprocess fixture)
    ├── scenarios/
    │   ├── __init__.py
    │   ├── login.py         (scenario data — NOT pytest tests; just data)
    │   ├── ground_combat.py
    │   ├── ...
    └── test_smoke_*.py      (pytest entry points; one per scenario group)
```

## §4. Pytest marker and run discipline

The smoke harness is **opt-in via marker** and **excluded from the
default suite run**. Reason: it requires either GameServer boot
(slow) or a subprocess (slower); leaving it on by default would push
the dev-box pytest run from ~30 seconds to several minutes, which
would erode the team's discipline of running tests before each drop.

### §4.1 Configuration changes

`pytest.ini` gets two markers added:

```ini
markers =
    smoke: end-to-end smoke scenarios (real GameServer; opt-in)
    smoke_slow: smoke scenarios that boot a subprocess (very opt-in)
```

And the default `addopts` get `-m "not smoke and not smoke_slow"`
appended — preserves "run all tests, get green in 30 seconds" as
the default.

### §4.2 Run modes

| Mode | Command | What runs |
|---|---|---|
| Default (today) | `pytest` | All 1,919 unit/integration tests; smoke skipped |
| Smoke (in-process) | `pytest -m smoke` | All scenarios via in-process GameServer |
| Smoke (subprocess) | `pytest -m "smoke or smoke_slow"` | All scenarios + subprocess parameterization |
| Single scenario | `pytest tests/smoke/test_smoke_login.py -m smoke` | One file's scenarios |
| Fail-fast | `pytest -m smoke -x` | Stop on first failure |
| Continue-on-fail | `pytest -m smoke --continue-on-collection-errors` | Standard pytest; report all |

### §4.3 Brian's recommended cadence

- **Before each drop:** `pytest` (the regular fast suite) — same as today
- **Before merging a multi-drop sequence to a known stable point:**
  `pytest -m smoke` (in-process; should take under 30 seconds for
  the full scenario set)
- **Before flipping the public-launch switch:** `pytest -m "smoke or
  smoke_slow"` (the full subprocess parameterization; takes longer
  but exercises the actual transports including telnetlib3 and
  aiohttp)
- **After hitting a "I logged in and it crashed" moment:** add a
  scenario that reproduces the bug, watch it fail, fix the bug,
  watch it pass. Now it's covered for next time.

## §5. Harness API design

### §5.1 The `harness` fixture (replaces `_SkipHarness`)

`tests/harness.py::harness` becomes (high-level shape; full code in
the implementation drop):

```python
@pytest.fixture
async def harness(request):
    """Live integration harness backed by an in-process GameServer.

    Honors the pre-existing API contract from test_economy_validation.py:
    login_as, cmd, get_char, get_credits, give_item, db.
    """
    h = await _LiveHarness.boot(era=request.config.getoption("--smoke-era", "gcw"))
    yield h
    await h.shutdown()
```

`_LiveHarness` exposes:

```python
class _LiveHarness:
    db: Database  # the real Database instance bound to the temp SQLite
    server: GameServer

    async def login_as(self, name: str, *, room_id: int = 1,
                       credits: int = 0, is_admin: bool = False,
                       species: str = "Human", template: str | None = None,
                       protocol: Protocol = Protocol.WEBSOCKET) -> _ClientSession: ...

    async def cmd(self, s: _ClientSession, text: str,
                  *, timeout: float = 2.0) -> str:
        """Feed input, drain output until quiet, return concatenated text."""

    async def get_char(self, char_id: int) -> dict: ...
    async def get_credits(self, char_id: int) -> int: ...
    async def give_item(self, char_id: int, item: dict) -> None: ...
    async def shutdown(self) -> None: ...
```

`_ClientSession` is the harness's per-test client handle. It wraps:
- For in-process: a real `Session` object whose `send_callback` is
  redirected into a captured-output buffer
- For subprocess: a real Telnet or WebSocket connection to the
  subprocess server, with output drained into a buffer

The same API surface works for both. Tests don't know which they're
running against unless they explicitly opt in via parametrization.

### §5.2 Output-draining model

Every `cmd()` call:
1. Sends the input
2. Waits up to `timeout` seconds for output
3. Returns when output stream goes quiet for `quiet_window` seconds
   (default 0.1s)
4. Returns the full concatenated text output (ANSI-stripped via
   `harness.strip_ansi`)

For WebSocket sessions, `cmd()` separately captures any typed JSON
payloads (`hud_update`, `combat_state`, `space_state`, `pose_event`,
`combat_resolution_event`) into `s.json_events` so scenario code can
assert on them:

```python
async def test_combat_engages_combat_state(harness):
    s = await harness.login_as("Combatant", room_id=2)
    await harness.cmd(s, "attack training_dummy")
    assert any(e["type"] == "combat_state" and e["active"]
               for e in s.json_events)
```

### §5.3 Scenario structure

Scenarios are **plain async functions**, not pytest tests:

```python
# tests/smoke/scenarios/login.py
async def login_basic(h):
    """Boot, create account, log in, see the room. Smoke level 0."""
    s = await h.login_as("Smoker01", room_id=2)
    out = await h.cmd(s, "look")
    assert_output_contains(out, "Mos Eisley")  # or era-appropriate room
    return s  # caller can chain
```

Pytest entry points wrap them:

```python
# tests/smoke/test_smoke_login.py
import pytest
from tests.smoke.scenarios.login import login_basic

@pytest.mark.smoke
@pytest.mark.parametrize("era", ["gcw", "clone_wars"])
@pytest.mark.parametrize("protocol", ["telnet", "websocket"])
async def test_login_basic(era, protocol, harness_factory):
    h = await harness_factory(era=era, default_protocol=protocol)
    await login_basic(h)
```

The split lets scenarios be **composable** (one scenario calls
another) and **reusable** between in-process and subprocess fixtures.

### §5.4 Era-aware assertions

Scenarios that work across both eras assert on era-aware content via
the same data the server reads:

```python
def expected_starting_room_name(era: str) -> str:
    if era == "gcw":
        return "Cantina"  # or whatever the GCW spawn is
    elif era == "clone_wars":
        return "Republic Outpost"  # CW spawn
    raise ValueError(era)
```

This catches the F.5b.3.b drift class — if the era flag flips
silently and players spawn into the wrong era's content, the
scenario's `assert_output_contains(out, expected_starting_room_name(era))`
fails immediately.

## §6. Initial scenario set (v1 deliverable)

Per Brian's steer ("a little deeper, especially space; assume I
haven't been testing right since day 1"), the v1 set is broad —
every major player surface gets at least one scenario. Surface
sizing was checked against the actual codebase: **276 BaseCommand
subclasses across 22 parser modules**, with `parser/space_commands.py`
alone at 6,356 lines / **55 classes** — bigger than combat (21) and
crafting (8) combined. Space gets a dedicated multi-scenario
sub-suite to match.

Scenarios are organized by domain. Each is small (5–25 lines); some
share setup via class fixtures.

### §6.1 Foundation (always runs first; everything else depends on these)

| # | Scenario | What it exercises |
|---|---|---|
| F1 | **Connect + login + look** | Boot, DB init, account auth, room load, `send_line` round-trip |
| F2 | **Account creation flow** | `create <user> <pass>`, validation (min lengths), uniqueness |
| F3 | **Chargen (Telnet wizard)** | `_run_character_creation` end-to-end: species pick, attribute alloc, skill alloc, save. **WebSocket chargen is bypassed in tests via direct DB seed** — see §6.10. |
| F4 | **Reconnect after logout** | Quit, reconnect, character state preserved (room, inventory, credits) |
| F5 | **Multi-character (`+char/switch`)** | Create alt, switch to alt, switch back; `SessionState.CHAR_SWITCH` path |

### §6.2 Movement and exploration

| # | Scenario | What it exercises |
|---|---|---|
| M1 | **Walk all exits in spawn room** | `MoveCommand` for every direction, `look` after each |
| M2 | **Path through 5 rooms and back** | Exit resolution stability, room cache correctness |
| M3 | **Locked door + picklock** | `PicklockCommand`, security gating, failure paths |
| M4 | **Forced door** | `ForceDoorCommand` |
| M5 | **Inventory + equip + remove** | `InventoryCommand`, `EquipCommand`, `WearCommand`, `RemoveArmorCommand` |
| M6 | **Look at NPC, look at object** | Object resolution, description display |

### §6.3 Communication

| # | Scenario | What it exercises |
|---|---|---|
| C1 | **say / pose / emote in room** | Local broadcast, ANSI handling |
| C2 | **whisper to other PC** | Targeted send |
| C3 | **page / OOC** | Cross-room messaging |
| C4 | **Channels: tune, untune, speak, freqs** | `TuneCommand`, `ComlinkCommand`, channel dispatcher |
| C5 | **Faction comlink** | `FcommCommand`, faction-scoped channels |
| C6 | **Mail send/read/respond** | `MailCommand`, persistence, `RespondCommand` |
| C7 | **News list/read** | `NewsCommand` |

### §6.4 Combat (ground)

| # | Scenario | What it exercises |
|---|---|---|
| G1 | **Attack training dummy** | `attack`, dice roll plumbing, hit/miss output |
| G2 | **Combat HUD activation** | `combat_state` JSON sent on engage; verifies `event_type` / `who` schema |
| G3 | **Wound ladder progression** | Take damage, observe wound rung change in HUD payload |
| G4 | **Stun mechanics** | Stun damage, stun cap, recovery |
| G5 | **Dodge declaration** | `dodge`, declaration panel, theatre stays "ground" |
| G6 | **Cover** | `cover`, modifier application |
| G7 | **Flee combat** | `flee`, theatre clears, HUD returns to neutral |
| G8 | **Death + respawn** | Reach Mortally Wounded, `respawn`, character preserved |

### §6.5 Space — **expanded sub-suite per Brian's steer**

55 commands; this is the largest single surface in the game. Below
is a deliberately deeper coverage plan. Era-gated on CW until ships
land for that era — see §9.2.

| # | Scenario | What it exercises |
|---|---|---|
| **Boarding & crew** |
| S1 | **Board own ship + look bridge** | `board`, bridge room load, ship state hydration |
| S2 | **Sit at pilot station** | `pilot`, station seat, station-specific HUD |
| S3 | **All crew stations cycled** | `pilot`/`gunner`/`copilot`/`engineer`/`navigator`/`commander`/`sensors`, then `vacate` |
| S4 | **Multi-PC crew** (one ship, two PCs in different stations) | Crew coordination, broadcast scope |
| S5 | **Disembark to room** | `disembark`, character moved out, ship state preserved |
| **Launch & flight** |
| S6 | **Launch from docked state** | `launch`, ship leaves dock, `space_state` becomes active |
| S7 | **Land at destination** | `land`, dock complete, `space_state` clears |
| S8 | **Course set + sublight transit** | `course`, sublight tick, arrival event |
| S9 | **Hyperspace jump + arrival** | `hyperspace`, hyperspace_arrival_tick, arrival event |
| S10 | **Power management** | `power`, capacitor allocation, status output |
| **Sensors & engagement** |
| S11 | **Scan + deep scan** | `scan`, `+deepscan`, target list output |
| S12 | **Lock on + fire** | `lockon`, `fire`, damage resolution, target hull condition coloring (the F-finding fix) |
| S13 | **Shields manage** | `shields`, arc state, payload to client |
| S14 | **Take fire + damage condition** | NPC ship fires; condition string in HUD updates |
| **Maneuvers** |
| S15 | **Evade / jink / barrel-roll / loop / slip** | The 5 maneuver commands; modifier application |
| S16 | **Outmaneuver + tail** | `outmaneuver`, `tail`, tactical state |
| S17 | **Close range / flee ship** | `close`, `flee`, range tier transitions |
| **Repair & resource** |
| S18 | **Damcon (in-flight repair)** | `damcon`, hull/shield restore on tick |
| S19 | **Ship repair (docked)** | `+srepair`, credits charged, hull restored |
| S20 | **Ship buy + ownership** | `+buy <ship>`, credit deduction, ownership row |
| **Comms & traffic** |
| S21 | **Hail another ship** | `hail`, comm channel open |
| S22 | **Comms broadcast** | `comms`, broadcast scope |
| S23 | **NPC space traffic visible on scan** | Verifies `npc_space_traffic_tick` is producing scannable contacts |
| **Boarding** |
| S24 | **Tractor beam + boarding** | `lockon` tractor, board NPC ship, encounter trigger |
| S25 | **Resist tractor** | `+resisttractor` opposed roll |
| **Salvage & market** |
| S26 | **Salvage destroyed ship** | `salvage`, loot drop |
| S27 | **Market list + buy/sell** | `market`, commodity flow, credit math |
| **Bridge & ownership admin** |
| S28 | **Rename ship** | `+shipname` |
| S29 | **Set bounty** | `+setbounty` |
| S30 | **Transponder toggle** | `transponder` |

### §6.6 Combat (the WEG-specific stuff)

| # | Scenario | What it exercises |
|---|---|---|
| W1 | **Skill check via `+roll`** | `RollCommand`, dice expression parsing, Wild Die |
| W2 | **Opposed check** | `OpposedCommand` |
| W3 | **Force power use** | `+force <power>`, Force Point spend, `PowersCommand` listing |
| W4 | **Force status** | `+forcestatus`, dark side point display |

### §6.7 Economy and progression

| # | Scenario | What it exercises |
|---|---|---|
| E1 | **Shop browse + buy** | `+shop`, `+browse`, credit deduction |
| E2 | **Sell to vendor** | `sell`, vendor purchase price |
| E3 | **Repair worn item** | `+repair`, condition restore |
| E4 | **Player-to-player trade** | `trade`, two-PC handshake |
| E5 | **CP status + train skill** | `+cp`, `+train`, advancement gate |
| E6 | **Kudos + scene bonus** | `+kudos`, `+scenebonus` |
| E7 | **Survey resource node + craft schematic** | `survey`, `+resources`, `+schematics`, `+craft` |
| E8 | **Experiment (crafting)** | `+experiment`, success/fail paths |

### §6.8 Missions, bounties, faction, scenes

| # | Scenario | What it exercises |
|---|---|---|
| Q1 | **Mission accept / active / abandon / complete** | Full mission lifecycle |
| Q2 | **Bounty list / claim / track / collect** | `+bounties`, claim flow |
| Q3 | **Faction list / info / join / leave** | `+faction list`, `+faction info`, `+faction join` |
| Q4 | **Faction reputation gate** | Gated content access (this is where era-aware faction codes have bitten before) |
| Q5 | **Scene start + scene list** | `+scene`, `+scenes` |
| Q6 | **Plot list + plot detail** | `+plots`, `+plot <id>` |
| Q7 | **Encounter trigger + investigate** | Random encounter, `+investigate` |

### §6.9 Housing, medical, social, MUX builtins

| # | Scenario | What it exercises |
|---|---|---|
| H1 | **Housing list (tier3)** — directly relevant to F.5b.3.b/c dev session | `housing tier3`, lot listing with correct room IDs |
| H2 | **Housing claim → enter → set home** | Full claim flow, `SetHomeCommand`, room privacy |
| H3 | **Medical: heal accept** | `+heal`, `+heal/accept`, heal tick |
| H4 | **Sabacc** | `+sabacc`, hand resolution |
| H5 | **Entertainer station_act** | `+stationact` |
| H6 | **Help system** | `help`, `help combat`, `help bogus_topic` |
| H7 | **Sheet (full)** — `score` and `+sheet` | Attribute, skill, advantage display; era-aware data |
| H8 | **Who / Where / Finger** | `who`, `where`, `+finger`; presence |
| H9 | **MUX builtins** — `@name`, `@desc`, `@pemit`, `@wall`  | Admin/builder commands |
| H10 | **Tutorial entry** | `+training`, FDts intro chain |

### §6.10 Implementation gotchas captured during scoping

1. **WebSocket chargen can't be driven via plain `cmd()`.** The
   `_run_web_chargen` flow sends `chargen_start` JSON and waits for
   `__chargen_done__`. The harness `login_as` will short-circuit
   chargen by **directly seeding a character row in the DB** (using
   the same DB methods chargen ultimately uses), then dropping the
   session straight into `SessionState.IN_GAME`. Telnet chargen is
   text-driven and IS exercised by scenario F3 explicitly.
2. **Rate limiter** — `Session` has a 30-burst, 5/sec refill token
   bucket. Smoke scenarios that fire many commands rapidly need to
   either `await asyncio.sleep(0.2)` between commands OR the harness
   exposes a `disable_rate_limit=True` flag. Proposal: harness
   disables rate limiting for in-process tests and respects it for
   subprocess (since real players hit the real limit).
3. **`SessionState.CHAR_SWITCH`** has its own loop in `handle_new_session` —
   F5 needs to drive that path explicitly.
4. **Tick scheduler runs in the in-process harness**. That's mostly
   good (catches tick-driven bugs) but means scenarios cannot assume
   the world stays static. Long-running scenarios (>10s of test
   wall-clock) need to either tolerate ambient ticks or stub the
   scheduler.
5. **Auto-build runs on first boot.** First scenario in a temp DB
   pays the auto-build cost. Class-scoped fixtures (Brian's pick)
   amortize this cost across a class's scenarios. Roughly a 1-2
   second boot per class.

### §6.11 Scenario count and runtime estimate

- **Foundation:** 5
- **Movement:** 6
- **Communication:** 7
- **Ground combat:** 8
- **Space:** 30
- **WEG-specific:** 4
- **Economy/progression:** 8
- **Missions/bounties/faction/scenes:** 7
- **Housing/medical/social/MUX:** 10

**Total: 85 scenarios.** With 2 eras × 2 protocols, the parameterized
expansion is theoretically 340, but many gate out — CW space (~30
scenarios) skips until CW ships land; Telnet+WebSocket symmetry
means many era-irrelevant scenarios still parameterize 2x on
protocol; admin commands skip the chargen/login parameterization.
Realistic run count: **~150-200 actual test cases.**

Target wall-time:
- In-process, GCW only, single protocol: **~30-45 seconds**
- In-process, full parameterization: **~2-3 minutes**
- Subprocess full parameterization: **~5-8 minutes**

This is in line with "run before flipping the public-launch switch"
not "run before every drop." Brian's recommended cadence in §4.3
stands.

## §7. Parallelism with the active dev session

This work touches **only**:

- `tests/harness.py` — replaces `_SkipHarness` (current code is a
  placeholder explicitly marked for replacement)
- `tests/conftest.py` — possibly extended for new fixtures; existing
  re-export preserved
- `tests/smoke/` — entirely new subtree, no overlap with anything
- `pytest.ini` — adds two markers and updates default `addopts`
- A delta doc (`smoke_test_harness_design_v1.md` — this file, plus
  whatever I produce alongside the code drop)

It does **not** touch:
- Any `engine/`, `parser/`, `server/`, `static/`, `data/` files
- `sw_d6_mush_architecture_v38.md` (delta doc instead, folded later)
- Any existing test file (un-skipping the 7 in `test_economy_validation.py`
  is automatic via fixture replacement; their source isn't edited)

The active dev session is currently in `engine/world_loader.py`,
`engine/housing_lots_provider.py`, and `data/worlds/gcw/` for
F.5b.3.b/c. Zero overlap.

## §8. Drop plan

Six drops, each independently shippable. The first three deliver
the foundation and the highest-value scenarios; drops 4-6 fill out
the long tail. Brian can pause after any drop and the harness still
provides real value at that scope.

### §8.1 Drop SH1 — Foundation infrastructure

- `tests/harness.py` rewritten with real `_LiveHarness` (in-process,
  WebSocket, GCW only)
- `tests/smoke/` subtree created with `boot_inproc.py`, `client_ws.py`,
  per-class fixture
- `pytest.ini` markers added; default `addopts` updated to exclude
  smoke
- §6.1 Foundation scenarios (F1-F5)
- The 7 currently-skipped tests in `test_economy_validation.py`
  un-skip; either pass or get diagnosed as real bugs (this is the
  first dividend — those tests have been silently inert)
- Handoff doc

**Acceptance:** `pytest -m smoke` passes; F1-F5 all green; the
previously-skipped economy tests either pass or have tickets opened
for the real bugs they expose.

### §8.2 Drop SH2 — Movement, communication, ground combat, MUX builtins

- §6.2 Movement (M1-M6)
- §6.3 Communication (C1-C7)
- §6.4 Ground combat (G1-G8)
- §6.9 H6-H9 (help, sheet, who, MUX builtins)

**Acceptance:** scenarios SH1+SH2 green in-process. ~26 scenarios
on top of the 5 foundation ones.

### §8.3 Drop SH3 — Telnet driver + protocol parameterization

- `client_telnet.py` driver added
- Subprocess fixture (`@pytest.mark.smoke_slow`)
- Era parameterization wired in (GCW + CW where applicable)
- Existing scenarios (F1-F5, M1-M6, C1-C7, G1-G8, H6-H9) become
  parameterized over `[telnet, websocket]`
- Telnet-specific F3 (text-wizard chargen) added

**Acceptance:** `pytest -m "smoke or smoke_slow"` passes the full
parameterized expansion of everything shipped through SH2.

### §8.4 Drop SH4 — Space sub-suite (the big one)

- §6.5 Space (S1-S30) — 30 scenarios
- Boarding/crew, launch/flight, sensors/engagement, maneuvers,
  repair/resource, comms/traffic, salvage, market, ship admin
- CW gating per Brian's §9.2 answer: CW skips until CW ships land.
  This drop's tests assert the CW skip is correct (i.e., raises
  `pytest.skip("CW has 0 seeded ships per F.1d")` rather than
  silently skipping)

**Acceptance:** 30 GCW space scenarios green. Each scenario produces
useful output even when it fails (i.e., asserts on specific JSON
event keys, not just "didn't crash").

### §8.5 Drop SH5 — WEG dice/Force, economy/progression, missions/factions

- §6.6 WEG-specific (W1-W4)
- §6.7 Economy/progression (E1-E8)
- §6.8 Missions/bounties/faction/scenes (Q1-Q7)

**Acceptance:** 19 more scenarios green; cross-era for the ones
that apply.

### §8.6 Drop SH6 — Housing, social, medical, tutorial; CI integration notes

- §6.9 H1-H5, H10 (housing, sabacc, medical, entertainer, tutorial)
- README in `tests/smoke/` documenting how to add new scenarios
  (since others — including future Claudes — will need to extend
  this)
- A short addition to `engineering_standards_v1.md` describing the
  marker discipline ("smoke is opt-in; if you ship a feature, ship
  a smoke scenario for it")
- Architecture v38 delta describing the smoke harness (folded into
  v38 by whichever session lands last; same delta-rollup pattern
  Brian's been using)
- Document the architectural drift points from §3.2 (WS port,
  unused `websocket_port` config field)

**Acceptance:** Full 85-scenario set green where applicable; CW
gating clean; documentation for future maintainers complete.

### §8.7 Total effort estimate

| Drop | Scenarios added | Cumulative | Estimated session count |
|---|---|---|---|
| SH1 | 5 (foundation) + 7 un-skipped | 12 | 1 (Sonnet implementation) |
| SH2 | 26 | 38 | 1-2 |
| SH3 | (parameterization, no new scenarios) | 38 (~76 with params) | 1 |
| SH4 | 30 (space) | 68 | 2 |
| SH5 | 19 | 87 | 1-2 |
| SH6 | 6 + docs | 93 | 1 |

Total: 7-9 implementation sessions. Independent of Brian's other
priorities; fits naturally as a background track that ships drops
between higher-priority dev work.

## §9. Brian's answers (resolved) and remaining open questions

### §9.1 Resolved during this design pass

- **Scenario priority** → "deeper, especially space, beef up other
  areas, don't only focus on recent development; OK if test suite
  is large." → §6 expanded from 10 to 85 scenarios; space expanded
  to its own 30-scenario sub-suite; coverage is now broad across all
  major surfaces, not just recent dev.
- **Per-class temp DB strategy** → confirmed.
- **In-process default for `pytest -m smoke`, subprocess opted into
  via `-m smoke_slow`** → confirmed.
- **CW ship gating** → "I didn't realize CW has zero ships. If
  there's no drop coming for that, I'll make sure there is." → §6.5
  CW space scenarios SKIP with a clear `pytest.skip()` reason
  citing F.1d's 0-ship log; once CW ships land, the skip
  auto-resolves and the scenarios start running. The skip itself
  is a useful signal — it tells Brian "you have CW ships to
  build."

### §9.2 Remaining open questions for Brian

1. **Test character vs. fresh chargen for non-F3 scenarios.** F3
   (Telnet text-wizard chargen) explicitly drives chargen. Every
   other scenario calls `harness.login_as("Name", ...)` which the
   harness short-circuits via direct DB seed. Question: should
   `login_as` use the existing `data/worlds/<era>/test_character.yaml`
   (post-F.1c), or should it build a minimal character from scratch?
   v1 proposal: **use `test_character.yaml` as the basis, override
   per-call params (name, room_id, credits) on top.** This means
   `test_character.yaml` becomes load-bearing for the test suite
   and changes to it need a smoke-suite re-run. Worth it for the
   shared baseline.

2. **Rate limiter handling for in-process tests.** v1 proposal:
   **disabled by default for in-process; enabled for subprocess.**
   Reason: smoke scenarios fire many commands rapidly to keep test
   wall-time down. Real players hit the limit, so subprocess catches
   the wire-level reality. Confirm?

3. **Scenarios that need multiple PCs in the same room** (S4 multi-PC
   crew, C2 whisper, E4 P2P trade). v1 proposal: **`harness.login_as`
   can be called multiple times in the same scenario; each call gets
   a separate `_ClientSession` against the same `GameServer`.** The
   harness manages session uniqueness internally. Confirm?

4. **Tick-driven scenarios (S8 sublight transit, S9 hyperspace
   arrival, S18 damcon).** These take real wall-clock time on
   normal tick cadence (1s base). v1 proposal: **expose
   `harness.advance_ticks(n)` that calls the scheduled tick
   handlers directly** instead of waiting for wall-clock time.
   Skips actual `asyncio.sleep` and accelerates the test. The
   handlers are already separated cleanly in
   `server/tick_handlers_*.py`. Confirm this approach is acceptable
   (it's slightly different from "real player time" but catches
   functional bugs at much lower wall-cost)?

5. **"Did this fail because of a bug or because the scenario is
   wrong?" — failure triage.** Smoke tests are notoriously hard
   to debug. v1 proposal: **on failure, dump (a) the full session
   transcript, (b) all JSON events received, (c) relevant DB rows
   (character, room, ship if applicable) into a `tests/smoke/_failures/`
   directory.** That gives Brian everything he'd need to repro
   manually. Confirm this debug surface is wanted, or is it
   overkill?

---

*— Smoke harness design v1, parallel to dev session F.5b.3.b/c work,
Apr 30 2026.*
