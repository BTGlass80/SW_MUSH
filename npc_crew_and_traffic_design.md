# NPC Crew & Space Traffic Design Document
## Star Wars D6 MUSH — v1.0

### Problem

A text-based game with 5-10 concurrent players means most multi-crew ships fly empty and space feels dead. Two systems solve this:

1. **Hireable NPC Crew** — players hire NPCs to fill crew stations so a solo player can fly a YT-1300 with an NPC copilot, gunner, and engineer.
2. **NPC Space Traffic** — AI-controlled ships fly routes, creating encounters (trade, combat, inspections) without requiring other players.

---

## Layer 1: Hireable NPC Crew

### 1.1 Where to Hire

Cantinas and spaceports have a **hiring board** — a pool of available-for-hire NPCs that refreshes periodically. Each location stocks NPCs appropriate to the area (Mos Eisley gets smugglers and mechanics; Imperial sectors get ex-military pilots).

NPCs are generated on demand using the existing `npc_generator.py` with the `pilot`, `smuggler`, `mechanic`, and `scout` archetypes at tiers appropriate to the location.

### 1.2 NPC Crew Roles

| Role | Station | Skill Used | Effect |
|------|---------|------------|--------|
| Pilot | `pilot` | starfighter piloting / space transports | Flies the ship, maneuvers in combat |
| Copilot | `copilot` | space transports | +1D assist to pilot rolls |
| Gunner | `gunner` | starship gunnery | Fires assigned weapon mount |
| Engineer | `engineer` | space transports repair | Can run `damcon` during combat |
| Navigator | `navigator` | astrogation | Plots hyperspace jumps |
| Sensors | `sensors` | sensors | Operates sensors for scan detail |

These map directly to the existing crew station system in `space_commands.py`.

### 1.3 Hiring Flow

```
> hire
  ═══ Available Crew for Hire ═══
  1. Kael Voss      Pilot (Novice)    Starfighter Piloting 5D   150 cr/day
  2. Mira Tann      Mechanic (Average) Space Transport Repair 4D  80 cr/day
  3. Grek Duul      Gunner (Novice)   Starship Gunnery 4D+2     120 cr/day
  
  Type 'hire <name>' to hire. 'roster' to see your crew.

> hire Kael Voss
  Kael Voss joins your crew for 150 credits/day.
  Current balance: 4,850 credits.

> roster
  ═══ Your Crew ═══
  Kael Voss      Pilot (Novice)    UNASSIGNED       150 cr/day
  
  Assign with: assign <name> <station>
  Dismiss with: dismiss <name>

> assign Kael pilot
  Kael Voss takes the pilot seat aboard the Rusty Mynock.
```

### 1.4 Wage System

| Tier | Daily Wage | Rationale |
|------|-----------|-----------|
| Extra | 30 cr/day | Warm body, minimal skill |
| Average | 80 cr/day | Competent, 4D primary skill |
| Novice | 150 cr/day | Good, ~beginning PC level |
| Veteran | 400 cr/day | Expensive but excellent |
| Superior | 1,000 cr/day | Elite, rarely available for hire |

Wages deduct from the player's credits at each game-day tick (configurable, default every 60 real minutes). If funds run out, NPCs give a 1-day warning then leave ("Kael Voss has left your crew — unpaid wages."). This aligns with the economy doc's target of ~300-1,600 cr/hr income, so a novice crew of 2-3 is affordable but meaningful.

### 1.5 NPC Crew in Combat

When combat starts, NPC crew act automatically on their station:

- **NPC Pilot**: Uses their piloting skill for defense rolls and maneuvers. Behavior profile (from `npc_combat_ai.py`) determines whether they close, flee, tail, or evade. Player can override with `order pilot close <target>`.
- **NPC Gunner**: Auto-fires each round at the nearest hostile (or player-designated target via `order gunner fire <target>`). Uses their gunnery skill + weapon fire control.
- **NPC Engineer**: Attempts `damcon` on the most damaged system each round if any system is damaged.
- **NPC Copilot**: Provides +1D assist automatically (already implemented in the copilot station logic).

The `order` command gives players tactical control without requiring them to micro-manage:
```
> order pilot tail Interceptor-3
  Kael Voss acknowledges: "Going for their six!"

> order gunner fire Interceptor-3
  Grek Duul swings the quad laser toward Interceptor-3.
```

### 1.6 Data Model

**New fields on `npcs` table:**
```sql
ALTER TABLE npcs ADD COLUMN hired_by INTEGER REFERENCES characters(id);
ALTER TABLE npcs ADD COLUMN hire_wage INTEGER DEFAULT 0;
ALTER TABLE npcs ADD COLUMN assigned_ship INTEGER REFERENCES ships(id);
ALTER TABLE npcs ADD COLUMN assigned_station TEXT DEFAULT '';  -- pilot/gunner/engineer/etc.
ALTER TABLE npcs ADD COLUMN hired_at TEXT DEFAULT '';
```

**Extended crew JSON on ships table** (backward compatible):
```json
{
  "pilot": 42,
  "copilot": null,
  "gunners": [105],
  "engineer": null,
  "navigator": null,
  "sensors": null,
  "npc_pilot": 7,
  "npc_gunners": [12],
  "npc_engineer": 15
}
```

NPC crew slots are separate from player slots so a player can always bump an NPC out of a station. Existing code that checks `crew["pilot"]` continues to work unchanged.

### 1.7 Hiring Board Refresh

Each cantina/spaceport room gets a `hiring_board` flag. On server tick (or when a player types `hire` and the board is stale), the system generates 3-5 NPCs using `npc_generator.generate_npc()`:

- Tiers weighted by location: backwater cantinas get mostly Extra/Average, major spaceports get Novice/Veteran
- Archetypes weighted toward crew-useful types: pilot, mechanic, smuggler, scout
- Names pulled from a Star Wars name generator (species-appropriate)
- Board refreshes every 4 game-hours (configurable)
- Hired NPCs are removed from the board; unhired NPCs despawn on refresh

### 1.8 Commands Summary

| Command | Description |
|---------|-------------|
| `hire` | Show available NPCs for hire at current location |
| `hire <name>` | Hire an NPC (starts wage clock) |
| `roster` | Show your hired crew and assignments |
| `assign <name> <station>` | Assign NPC to a crew station on your current ship |
| `unassign <name>` | Remove NPC from station (stays hired) |
| `dismiss <name>` | Fire an NPC (stops wages, NPC despawns) |
| `order <station> <action>` | Give tactical order to NPC in combat |

**Total: 7 new commands.**

---

## Layer 2: NPC Space Traffic

### 2.1 Purpose

Make hyperspace lanes and planetary orbits feel populated. When a player scans, they should see freighters, patrols, and occasionally pirates — not empty void.

### 2.2 Traffic Types

| Type | Archetype | Ship | Behavior | Player Interaction |
|------|-----------|------|----------|-------------------|
| **Trader** | merchant | YT-1300, bulk freighter | Neutral, follows route | Hail, trade, ignore |
| **Smuggler** | smuggler | YT-1300, Ghtroc 720 | Evasive, flees if scanned | Hail, report, ignore |
| **Patrol** | imperial_officer | TIE Fighter, Lambda Shuttle | Scans players, may inspect | Submit to inspection or flee |
| **Pirate** | bounty_hunter/thug | Z-95, modified freighter | AGGRESSIVE, attacks at medium range | Fight or flee |
| **Bounty Hunter** | bounty_hunter | Firespray, custom | Targets specific player with bounty | Fight or flee |

### 2.3 Route System

Each planet/sector has a **traffic table** — a weighted list of NPC ship types that can spawn there. Traffic density varies by location:

| Location | Density | Mix |
|----------|---------|-----|
| Coruscant orbit | Heavy (6-10 ships) | 50% patrol, 30% trader, 20% shuttle |
| Mos Eisley space | Medium (3-5 ships) | 30% smuggler, 30% trader, 20% pirate, 20% patrol |
| Kessel Run | Light (1-3 ships) | 50% pirate, 30% smuggler, 20% patrol |
| Deep space | Sparse (0-2 ships) | 60% nothing, 20% pirate, 20% trader |

NPC ships are spawned as lightweight objects — they exist on the SpaceGrid with range/position data but don't need full room interiors. They have:
- A ship template (from `starships.yaml`)
- A generated NPC pilot (from `npc_generator`)
- A behavior profile (AGGRESSIVE for pirates, DEFENSIVE for traders, etc.)
- A route: list of destinations with dwell times

### 2.4 Traffic Lifecycle

```
1. SPAWN: Timer fires → pick traffic type from location table
         → generate NPC pilot + select ship template
         → add to SpaceGrid at Long range from all players in sector

2. LIVE:  NPC ship follows behavior profile:
         - Traders: fly route, ignore players, respond to hail
         - Patrols: scan players at Medium range, demand inspection
         - Pirates: close to attack range, engage AGGRESSIVE
         - Smugglers: flee if scanned, otherwise fly route

3. DESPAWN: NPC ship reaches route destination → remove from grid
           OR: NPC ship destroyed in combat → loot drop + remove
           OR: NPC ship flees to Extreme → remove after 1 round
           OR: No players in sector for 5 min → remove (performance)
```

### 2.5 Interaction Commands

Most interactions use existing commands. New additions:

| Command | Description |
|---------|-------------|
| `hail <ship>` | Open comms with NPC ship (trader: see cargo; patrol: respond to inspection) |
| `inspect` | Submit to Imperial inspection (patrol checks cargo for contraband) |

`scan` already shows all ships on the grid. `fire`, `tail`, `close`, `flee` all work against NPC traffic ships. The NPC combat AI handles the NPC ship's responses.

### 2.6 NPC Ship Combat

NPC ships use the existing combat flow:
- NPC pilot skill used for defense rolls (already supported by `resolve_space_attack`)
- NPC ships fire back using their weapon stats + generated gunnery skill
- Behavior profile determines tactics (close vs flee vs tail)
- Destroyed NPC ships can drop cargo/credits as loot

This hooks into the same `npc_combat_ai.py` behavior system used for ground combat NPCs.

### 2.7 Traffic Manager (Engine Component)

```python
class SpaceTrafficManager:
    """Manages NPC ship spawning, behavior, and despawning."""
    
    def __init__(self, db, space_grid):
        self._db = db
        self._grid = space_grid
        self._active_npc_ships: dict[int, NPCShipState] = {}
        self._traffic_tables: dict[str, list] = TRAFFIC_TABLES
    
    async def tick(self, sector: str):
        """Called each game tick. Spawns/despawns/acts for NPC ships."""
        # 1. Spawn new traffic if below density target
        # 2. Run behavior for each active NPC ship
        # 3. Despawn ships that reached destination or left grid
    
    async def npc_ship_act(self, npc_ship: NPCShipState):
        """One NPC ship takes its turn: maneuver + fire if hostile."""
        # Uses behavior profile to decide action
        # Calls resolve_maneuver / resolve_space_attack
```

### 2.8 Data Model

NPC ships are transient — they don't need persistent database storage. They exist in memory as part of the SpaceTrafficManager. If the server restarts, traffic respawns naturally on the next tick.

```python
@dataclass
class NPCShipState:
    id: int                          # Unique ID for SpaceGrid
    template_key: str                # Ship template from starships.yaml
    name: str                        # "Trader Koss's Freighter"
    npc_pilot: dict                  # Generated NPC stat block
    behavior: str                    # AGGRESSIVE / DEFENSIVE / EVASIVE
    route: list[str]                 # ["tatooine", "corellia"]
    route_idx: int = 0
    hostile: bool = False
    hull_damage: int = 0
    systems: dict = field(default_factory=dict)
```

---

## Implementation Order

### Phase 1: Hireable Crew (est. 4 code drops)

1. **Database migration** — add columns to `npcs` table
2. **engine/npc_crew.py** — hiring board generation, wage tick, NPC crew skill resolution
3. **parser/crew_commands.py** — `hire`, `roster`, `assign`, `unassign`, `dismiss` commands
4. **Combat integration** — NPC crew auto-actions in combat, `order` command

### Phase 2: Space Traffic (est. 4 code drops)

5. **engine/space_traffic.py** — SpaceTrafficManager, traffic tables, spawn/despawn logic
6. **NPC ship behavior loop** — tick-based NPC ship actions (maneuver, fire, flee)
7. **parser/traffic_commands.py** — `hail`, `inspect` commands
8. **Integration** — wire traffic manager into game server tick, connect to SpaceGrid

### Phase 3: Polish

9. **Name generator** — species-appropriate NPC names for hired crew and traffic pilots
10. **Tuning** — wage balance, traffic density, spawn rates based on playtesting

---

## Economy Impact

Per the economy design doc, target player income is 300-1,600 cr/hr:

- A solo player with 1 NPC pilot (150 cr/day) + 1 NPC gunner (120 cr/day) = 270 cr/day ≈ 11 cr/hr. Easily affordable.
- A veteran crew of 3 (pilot + gunner + engineer at novice tier) = 420 cr/day ≈ 18 cr/hr. Still well within margins.
- Veteran-tier crew gets expensive (400/day each) — reserved for wealthy players running high-risk missions.
- Pirate kills from traffic yield 200-1,000 cr in cargo/bounty, providing income for combat-focused players even when no missions are active.

The crew wage system creates a meaningful credit sink without being punishing. It also incentivizes players to do missions (to pay the crew) rather than AFK.

---

## Compatibility Notes

- Crew JSON format is backward compatible — existing `crew["pilot"]` checks work unchanged
- NPC crew use separate `npc_pilot` / `npc_gunners` keys
- All existing space commands work against NPC traffic ships (they're just ships on the SpaceGrid)
- Traffic ships are transient (in-memory only), no database bloat
- The `npc_generator` is used as-is for both hired crew and traffic pilots
- Tailing system (just implemented) works for/against NPC ships
