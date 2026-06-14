# Developer Internals — Guide_06_Economy.md

Extracted from `data/guides/Guide_06_Economy.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

### 🔧 Developer Internals

**Design doc:** `economy_design_v02-1.md`. Full audit in `economy_audit_v1.md`.

The economy audit identified six structural vulnerabilities, the most critical being that trade goods are a "solved game" (static price multipliers can theoretically generate 120x the design target). The audit recommends dynamic supply pools, Bargain skill gates on bulk purchases, and per-planet inventory limits. These are documented but not yet implemented.

### 🔧 Developer Internals

**File:** `engine/missions.py` (~856 lines):

**`MissionType` enum** (lines 46–62): 14 types including 4 space types (PATROL, ESCORT, INTERCEPT, SURVEY_ZONE).

**`MissionStatus` enum**: AVAILABLE, ACCEPTED, COMPLETE, EXPIRED, FAILED.

**`PAY_RANGES` dict** (lines 109–127): Min/max pay per type. Space missions pay 300–2,500 cr.

**Board management:**
- `BOARD_MIN = 5`, `BOARD_MAX = 8`
- `REFRESH_SECONDS = 1800` (30 minutes)
- `MISSION_TTL = 3600` (1 hour unclaimed)
- `MISSION_ACTIVE_TTL = 7200` (2 hours accepted)
- Board maintains the AVAILABLE pool and replaces completed missions immediately

**Mission generation:** Procedural — picks random type, generates reward within range, assigns destination rooms based on type, creates flavor text. Space missions reference specific zone targets from `_PATROL_ZONES`, `_SURVEY_ZONES`, `_INTERCEPT_ZONES`, `_ESCORT_ROUTES`.

**Completion skill check:** Routes through `skill_checks.py::resolve_mission_completion()` which calls `perform_skill_check()`. Difficulty scales with reward via `mission_difficulty()` (intermediate values 8–21, not the canonical R&E ladder).

**File:** `parser/mission_commands.py` (~600 lines): 5 commands — missions, mission accept, mission info, mission complete, mission abandon.

### 🔧 Developer Internals

**File:** `engine/bounty_board.py` (~554 lines):

**`BountyTier` enum** (lines 53–58): EXTRA through SUPERIOR.

**`TIER_WEIGHTS` dict** (lines 70–76): Extras are 5x more common than Superiors.

**`FUGITIVE_ARCHETYPES`** (lines 79–82): 6 archetype strings that make sense as fugitives.

**Board management:**
- `BOARD_SIZE = 4`, `BOARD_MIN = 2`
- `REFRESH_SECONDS = 2700` (45 minutes)
- `BOUNTY_TTL = 10800` (3 hours unclaimed)
- `CLAIMED_TTL = 14400` (4 hours claimed)

**Target spawning:** NPCs are actually spawned in the world using `engine/npc_generator.py`. They're placed in non-obvious rooms (avoids docking bays). Their stats match the tier difficulty.

**Completion:** Requires the target NPC to be killed or incapacitated. The combat system has a bounty kill hook that triggers when a bounty target is defeated.

**File:** `parser/bounty_commands.py` (~410 lines): 5 commands.

### 🔧 Developer Internals

**File:** `engine/smuggling.py` (~625 lines):

**`CargoTier` IntEnum** (lines 102–106): GREY_MARKET(0), BLACK_MARKET(1), CONTRABAND(2), SPICE(3).

**`ROUTE_TIERS` dict** (lines 72–80): 5 route configurations with tier, destination planet, pay override, and patrol chance.

**`PLANET_PATROL_FREQUENCY` dict** (lines 84–89): Per-planet arrival intercept probability. Corellia = 0.60 (Core World).

**Board management:**
- `BOARD_SIZE = 5`, `BOARD_MIN = 3`
- `REFRESH_SECONDS = 2700` (45 minutes)
- `JOB_TTL = 7200` (2 hours unclaimed)
- `JOB_ACTIVE_TTL = 14400` (4 hours accepted)

**Patrol resolution:** Random check against `TIER_PATROL_CHANCE[tier]`. If triggered, player rolls Con or Sneak vs. `PATROL_DIFFICULTY[tier]`. Failure: cargo confiscated, fine = `FINE_FRACTION (0.50) × reward`.

**File:** `parser/smuggling_commands.py` (~480 lines): 5 commands.

### 🔧 Developer Internals

**From economy audit:** ~50% of designed sinks are not yet wired. Missing: transaction tax (5%), recurring daily docking fees, ammo costs, medical NPC treatment costs, crafting material NPC vendors. The most damaging gap is free crafting materials via the `survey` command (zero input cost, output worth hundreds/thousands).

**What's working well (per audit — don't touch):** Weapon durability/repair cycle, vendor droid listing fees, crew wages, smuggling risk/reward.

### 🔧 Developer Internals

**File:** `engine/skill_checks.py` — `resolve_bargain_check()` (lines 297–428). Both player and NPC roll through `roll_d6_pool()`. NPC bargain dice auto-detected from room NPCs; falls back to 3D generic vendor. Result dict includes `adjusted_price`, `price_modifier_pct`, `margin`, `critical`, `fumble`, and narrative `message`.

## 10. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/missions.py` | ~856 | 14 mission types, board management, generation, completion |
| `engine/bounty_board.py` | ~554 | 5 bounty tiers, target spawning, tracking, collection |
| `engine/smuggling.py` | ~625 | 4 cargo tiers, 5 route tiers, patrol encounters, fines |
| `engine/trading.py` | ~335 | 8 trade goods, planet price tables, cargo hold |
| `engine/skill_checks.py` | ~590 | Bargain, mission completion, repair resolvers |
| `parser/mission_commands.py` | ~600 | 5 mission commands |
| `parser/bounty_commands.py` | ~410 | 5 bounty commands |
| `parser/smuggling_commands.py` | ~480 | 5 smuggling commands |
| `parser/builtin_commands.py` | ~1,872 | sell, repair, credits commands |
| `economy_design_v02-1.md` | — | Economy design document |
| `economy_audit_v1.md` | — | Full economy audit with 6 vulnerability findings |

**Total economy system:** ~3,845 lines of engine code + ~1,490 lines of parser code + ~335 lines of trading = ~5,670 lines dedicated to the credit economy.

---

*End of Guide #6 — Economy*
*Next: Guide #7 — Crafting*

