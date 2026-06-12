# Security Zones Design Document
## SW_MUSH · April 10, 2026

---

## 1. Overview

Cities should feel safe. The cantina shouldn't be a gank zone. But the Jundland Wastes should feel dangerous, and Nar Shaddaa's undercity should feel *lethal*. This document introduces a three-tier security level system for ground zones that controls who can attack whom and where, inspired by EVE Online's high/low/null security model but adapted for Star Wars and a MUSH-scale playerbase.

The system layers cleanly on top of the existing ground zone architecture (7 zones in Mos Eisley, more as planets are built out) and integrates with the planned Faction Reputation system (economy_design_v02-1.md §8) and the Director AI's zone influence model.

---

## 2. The Three Security Levels

### 2.1 Imperial Authority (Secured)

The Empire keeps order here. Stormtroopers patrol. Blasters stay holstered.

**Rules:**
- `attack` is blocked entirely (player vs player AND player vs NPC)
- NPCs will not initiate combat against players
- Exception: faction-hostile rooms (see §3.2)
- The `attack` command prints a thematic refusal message:
  *"Imperial security is too heavy here. You'd be stunned and detained before you cleared your holster."*

**Thematic feel:** A player walks through the market, buys supplies, talks to NPCs, trains skills, crafts items. They are safe. New players learn the game here without being ganked.

**Narrative exceptions:** Specific scripted NPC encounters (e.g., an Imperial checkpoint search during a Crackdown world event) can still trigger combat in secured zones — but only server-initiated, never player-initiated. These use a flag (`scripted_combat=True`) that bypasses the security gate.

### 2.2 Disputed Ground (Contested)

The Empire's grip loosens. Patrols are thin. Bad things happen in back alleys.

**Rules:**
- Player vs NPC combat is fully enabled (players can `attack` NPCs, NPCs can aggro players)
- Player vs player combat requires mutual consent via a `challenge`/`accept` system (see §5)
- Unconsented `attack` against another player prints:
  *"You can't just open fire here — there are still witnesses. Challenge them to a fight first, or take it somewhere lawless."*

**Thematic feel:** This is where missions play out, where smugglers get jumped by bounty hunter NPCs, where the cantina back hallway gets rough. PvE danger is real. PvP is possible but consensual — two players who want to fight can, but griefing is blocked.

### 2.3 No Law (Lawless)

Nobody's coming to help you. Out here, you're on your own.

**Rules:**
- All combat is unrestricted — player vs NPC, player vs player
- `attack <player>` works immediately with no consent required
- NPCs in lawless zones use more aggressive combat AI profiles
- Death penalties may be harsher (no guaranteed body recovery, loot drop risk — see §7)

**Thematic feel:** The deep desert. Nar Shaddaa's lower levels. Kessel's spice tunnels. High risk, high reward. Players go here for the best resources, the most lucrative missions, and the thrill of genuine danger. Eventually, player organizations claim territory here.

---

## 3. Zone Security Assignments

### 3.1 Per-Planet Defaults

Security level is stored on the ground zone record in the `zones` table (new column: `security TEXT DEFAULT 'contested'`). Each room inherits the security level of its zone.

**Tatooine (Mos Eisley)**

| Zone | Security | Rationale |
|------|----------|-----------|
| market | secured | Commercial heart, heavy foot traffic |
| cantina | secured | Chalmun's has a bouncer; the Empire watches |
| residential | secured | Homes, monastery, hotel |
| civic | secured | Bank, police station, clinic |
| spaceport | secured | Docking bays, transport depot — Imperial customs |
| outskirts | contested | City edges, back alleys, less patrol coverage |
| wastes | lawless | Jundland Wastes, deep desert — no law at all |

Note: The existing 7 zones cover the city well. Future Tatooine expansion (Beggar's Canyon, Jawa territory, moisture farms) would add more contested/lawless zones outside the city walls.

**Nar Shaddaa**

| Zone | Security | Rationale |
|------|----------|-----------|
| landing_pad | secured | The one safe harbor — even smugglers need a port |
| promenade | contested | Upper levels, Hutt-controlled commerce |
| undercity | lawless | Lower levels, no authority, full PvP |
| warrens | lawless | Deep undercity, the worst of the worst |

**Kessel**

| Zone | Security | Rationale |
|------|----------|-----------|
| station | contested | Orbital station, minimal security |
| mines | lawless | Spice mines, convict labor, no rules |
| deep_mines | lawless | Deeper tunnels, rare resources, extreme danger |

**Corellia (Coronet City)**

| Zone | Security | Rationale |
|------|----------|-----------|
| city_center | secured | Core world, CorSec patrols, civilized |
| industrial | secured | Shipyards, CEC facilities, corporate security |
| port_district | contested | Spacer bars, black market fringe |
| old_quarter | contested | Run-down neighborhoods, less patrol coverage |

### 3.2 Faction-Hostile Room Override

Some rooms within a secured zone have a faction restriction. A non-Imperial player walking into the Imperial Garrison is trespassing. The room itself carries a `faction_restriction` tag (already implied by the zone lock system). In these rooms, the security level effectively becomes **contested** or **lawless** for players who don't belong:

- Imperial Garrison interior → lawless for non-Imperials (NPCs will aggro)
- Rebel safehouse (future) → lawless for Imperial-aligned players
- Hutt palace interior → contested for everyone (Hutt guards decide)

This is a room-level override, not a zone-level one. The garrison sits inside the "civic" zone (secured), but its interior rooms have `faction_override: "empire"` which changes the effective security for unauthorized players.

**Implementation:** When computing effective security, check the room's `faction_override` field first. If the player's faction standing with that faction is Hostile or Unfriendly (from economy_design_v02-1.md §8.3), downgrade the effective security level.

---

## 4. Implementation

### 4.1 Schema Change

Add `security` column to the `zones` table:

```sql
ALTER TABLE zones ADD COLUMN security TEXT DEFAULT 'contested';
```

Valid values: `secured`, `contested`, `lawless`. Default is `contested` so any new zone without explicit assignment has moderate danger — safe from griefing but not from NPCs.

Room-level override (optional, for §3.2):

```sql
ALTER TABLE rooms ADD COLUMN faction_override TEXT DEFAULT NULL;
-- NULL = inherit zone security
-- "empire" / "rebel" / "hutt" = faction-restricted room
```

### 4.2 Security Enum

```python
# engine/security.py (new file, small)

from enum import Enum

class SecurityLevel(Enum):
    SECURED = "secured"
    CONTESTED = "contested"
    LAWLESS = "lawless"

async def get_effective_security(room, zone, character, db) -> SecurityLevel:
    """Determine the effective security level for a character in a room."""
    base = SecurityLevel(zone.get("security", "contested"))

    # Check room-level faction override
    faction_override = room.get("faction_override")
    if faction_override and base == SecurityLevel.SECURED:
        # If the character is hostile/unfriendly to the overriding faction,
        # downgrade security
        standing = await _get_faction_standing(character, faction_override, db)
        if standing in ("hostile", "unfriendly"):
            return SecurityLevel.LAWLESS
    return base
```

### 4.3 Combat Gate (the core check)

In `parser/combat_commands.py`, at the top of `AttackCommand.execute()`:

```python
# --- Security zone gate ---
room = await ctx.db.get_room(ctx.character["room_id"])
zone = await ctx.db.get_zone_by_room(room["id"])
security = await get_effective_security(room, zone, ctx.character, ctx.db)

target_is_player = target.get("account_id") is not None  # NPC vs player detection

if security == SecurityLevel.SECURED:
    # Block everything except scripted encounters
    if not ctx.flags.get("scripted_combat"):
        await ctx.session.send_line(
            "  \033[1;33mImperial security is too heavy here. "
            "You'd be stunned and detained before you cleared "
            "your holster.\033[0m"
        )
        return

elif security == SecurityLevel.CONTESTED:
    if target_is_player:
        # Check for active duel/challenge
        if not await _has_pvp_consent(ctx.character, target, ctx.db):
            await ctx.session.send_line(
                "  \033[1;33mYou can't just open fire here — "
                "there are still witnesses. Challenge them first, "
                "or take it somewhere lawless.\033[0m"
            )
            return

# SecurityLevel.LAWLESS — no restrictions, fall through to existing combat code
```

This is approximately 20 lines of gate logic added to the top of one method. The rest of the combat system is untouched.

### 4.4 NPC Aggro Gate

In `engine/npc_combat_ai.py`, wherever NPCs decide to initiate combat, add the same check:

```python
if security == SecurityLevel.SECURED and not scripted:
    return None  # NPC does not aggro in secured zones
```

This prevents random NPC attacks in the market. NPCs in secured zones are passive — they talk, they sell, they give quests, but they don't pull blasters.

### 4.5 `look` Integration

When a player enters a room or types `look`, show the security level as a subtle indicator:

```
Mos Eisley Market [SECURED]
  Rows of stalls line the dusty street...

Back Alley [CONTESTED]
  A narrow passage between buildings...

Jundland Wastes - Canyon Floor [LAWLESS]
  Wind-carved sandstone walls rise on either side...
```

Color coding: SECURED = green, CONTESTED = yellow, LAWLESS = red. This uses existing ANSI formatting.

### 4.6 Web Client Integration

Extend the `hud_update` message with a `security_level` field:

```json
{
  "type": "hud_update",
  "room_name": "Back Alley",
  "security_level": "contested",
  ...
}
```

The web client renders this as a colored badge next to the room name — the same pattern already designed for the Zone Alert Indicator (architecture_section_21_web_client.md, Tier 2).

---

## 5. PvP Consent System (Contested Zones)

### 5.1 Challenge Flow

```
challenge <player>     -- Issue a PvP challenge
accept                 -- Accept the most recent challenge
decline                -- Decline the most recent challenge
```

A challenge is a formal declaration. Both players see it:

```
  Tundra challenges Vex to a fight!
  Type 'accept' to accept or 'decline' to refuse.
```

If accepted, both players are flagged as PvP-consented to each other for **10 minutes** (configurable). During this window, `attack` works normally between them. The flag is stored in a transient in-memory dict (like pending heals), not in the DB — it doesn't need to survive restarts.

After the window expires or either player leaves the zone, the consent lapses. Players can re-challenge.

### 5.2 Bounty Hunter Override

When the Faction Reputation system is live, a player with an active bounty on their head has reduced PvP protection. A bounty hunter with Guild standing ≥ Friendly can attack a bountied player in contested zones without needing a challenge — the bounty *is* the consent. The bountied player sees:

```
  Vex draws on you! [BOUNTY HUNTER — Contract #4421]
  You've been marked. Defend yourself!
```

This creates meaningful PvP content without griefing — only players who've earned a bounty (through criminal actions) are targetable, and only by players who've invested in the Guild.

### 5.3 Flag for PvP (Lawless Zones)

No consent needed. However, players entering a lawless zone for the first time in a session get a one-time warning:

```
  *** WARNING: You are entering LAWLESS territory. ***
  *** Players can attack you freely here.           ***
  *** Type 'understood' to proceed or turn back.    ***
```

After acknowledging once per session, they move freely. This prevents accidental wandering into danger by new players. The flag is session-level (transient).

---

## 6. Director AI Integration

### 6.1 Dynamic Security Shifts

The Director AI can temporarily shift a zone's effective security level based on narrative events. This is an overlay, not a permanent change to the DB:

- **Imperial Crackdown** (world event): Contested zones in affected area temporarily become *secured*. Extra patrols, checkpoints, suppressed aggression. Criminal players are searched.
- **Underworld Takeover**: If Criminal influence ≥ 80 in a zone, it temporarily drops one security tier (secured → contested, contested → lawless). Imperial patrols withdraw.
- **Martial Law**: Extreme event. Even normally lawless zones become contested (Imperial troops sweep the wastes).

These overlays are computed from the `zone_influence` table values that the Director already manages. The `get_effective_security()` function checks for active world events and influence thresholds before returning the final security level.

### 6.2 Implementation

```python
async def get_effective_security(room, zone, character, db) -> SecurityLevel:
    base = SecurityLevel(zone.get("security", "contested"))

    # 1. Check room-level faction override (§3.2)
    # ... (as above)

    # 2. Check Director overlays
    influence = await db.get_zone_influence(zone["id"])
    active_events = await db.get_active_world_events()

    # Underworld surge — downgrade one tier
    if influence.get("criminal", 0) >= 80:
        if base == SecurityLevel.SECURED:
            base = SecurityLevel.CONTESTED
        elif base == SecurityLevel.CONTESTED:
            base = SecurityLevel.LAWLESS

    # Imperial crackdown event — upgrade contested to secured
    for event in active_events:
        if event["type"] == "imperial_crackdown" and zone["name"] in event.get("zones_affected", []):
            if base == SecurityLevel.CONTESTED:
                base = SecurityLevel.SECURED

    return base
```

This means the security map is *alive*. Players who drive Imperial influence down in a zone over weeks of play will see it become more dangerous. Players who help the Empire lock down an area will see it become safer. The Director's narrative events create temporary dramatic shifts.

---

## 7. Lawless Zone Incentives

Players need a reason to go to dangerous areas. Lawless zones offer:

**Economy:**
- Rare crafting resources only spawn in lawless zones (survey checks in the wastes/undercity/mines)
- Mission board offers higher-paying jobs that require travel to lawless zones
- Smuggling routes pass through lawless territory for the biggest payouts
- Black market vendors in lawless zones sell restricted gear at no markup

**Progression:**
- Certain advanced NPC trainers only operate in lawless zones (a grizzled mercenary in the wastes teaches advanced combat techniques, a spice chemist in Kessel teaches exotic schematics)
- Anomaly-equivalent ground discoveries (ruins, crash sites, hidden caches) only appear in lawless zones
- CP bonus modifier: +25% CP tick rate while actively in a lawless zone (risk reward)

**Future — Territory Control (Phase 2):**
- Player organizations can claim rooms in lawless zones
- Claimed rooms can be upgraded: install security (makes it contested for non-members), build vendor stalls, create crafting stations, set up defenses
- Territory generates passive income (resource nodes, NPC traffic tolls)
- Other organizations can assault claimed territory — this is the endgame PvP content

Territory control is a large feature that deserves its own design document. The security zone system is its prerequisite — you need the concept of "lawless space where players make the rules" before you can build claims on top of it.

---

## 8. Space Security Levels

The space zone system already has natural security tiers that should mirror the ground model:

| Space Zone Type | Effective Security | Rationale |
|-----------------|-------------------|-----------|
| DOCK | secured | Landing approach, port control, customs |
| ORBIT | contested | Orbital space, patrols present but thin |
| DEEP_SPACE | lawless | Open void, no authority |
| HYPERSPACE_LANE | contested | Major shipping routes, some patrol presence |

This means NPC pirate ambushes happen in deep space (lawless), Imperial patrol encounters happen in orbit (contested — they hail and scan, but don't open fire without provocation), and dock zones are safe harbor.

Player ship-vs-ship PvP follows the same rules: unrestricted in deep space, consent-required in orbit/lanes, blocked in dock zones. The `fire` command in `parser/space_commands.py` gets the same security gate as the ground `attack` command.

---

## 9. Admin Commands

```
@security <zone>                    -- show security level for a zone
@security <zone> = <level>          -- set security level (secured/contested/lawless)
@security override <room> = <faction>  -- set faction override on a room
@security override <room> = none    -- clear faction override
```

These are builder-level commands. They modify the DB directly. Changes take effect immediately (no restart needed — the security check reads from DB on every `attack` attempt).

---

## 10. Files Modified

| File | Changes |
|------|---------|
| `engine/security.py` | **NEW** — SecurityLevel enum, `get_effective_security()` |
| `parser/combat_commands.py` | Security gate at top of `AttackCommand.execute()` |
| `parser/combat_commands.py` | **NEW** — `ChallengeCommand`, `AcceptCommand`, `DeclineCommand` |
| `engine/npc_combat_ai.py` | NPC aggro gate for secured zones |
| `parser/builtin_commands.py` | `look` output includes security tag |
| `parser/admin_commands.py` | `@security` command |
| `parser/space_commands.py` | Security gate in `FireCommand.execute()` |
| `db/database.py` | `get_zone_by_room()` helper if not already present |
| `build_mos_eisley.py` | Set security levels on existing zones during world build |
| `static/client.html` | Security badge in HUD |

### Schema migration (v9):

```sql
ALTER TABLE zones ADD COLUMN security TEXT DEFAULT 'contested';
ALTER TABLE rooms ADD COLUMN faction_override TEXT DEFAULT NULL;
```

---

## 11. Implementation Plan

**Drop 1: Core Security Gate**
- `engine/security.py` — enum + `get_effective_security()` (basic version, no Director overlay)
- `AttackCommand` gate
- NPC aggro gate
- `build_mos_eisley.py` zone security assignments
- Schema migration
- `look` output tag

**Drop 2: PvP Consent**
- `ChallengeCommand` / `AcceptCommand` / `DeclineCommand`
- Transient consent tracking dict
- Contested zone PvP flow

**Drop 3: Space Security**
- `FireCommand` gate in `parser/space_commands.py`
- Space zone type → security level mapping

**Drop 4: Director Integration**
- World event overlays in `get_effective_security()`
- Zone influence thresholds (criminal surge, Imperial crackdown)
- Web client security badge

**Drop 5: Bounty Hunter Override** (requires Faction Reputation system)
- Bounty-based PvP consent bypass in contested zones
- Guild standing check

**Drop 6+: Territory Control** (future design document)
- Room claiming in lawless zones
- Territory upgrades
- Organization-vs-organization PvP

---

## 12. Architecture Invariants

- **Security checks never skip `get_effective_security()`.** Every combat initiation — player `attack`, NPC aggro, space `fire` — routes through the same function. No shortcuts.
- **Default is contested.** New zones without explicit assignment allow NPC combat but block PvP griefing. This is the safest default for incomplete content.
- **Telnet parity.** The security tag in `look` and the challenge/accept flow work identically on Telnet and WebSocket. The web badge is visual convenience, not gated content.
- **Director overlays are transient.** They modify effective security in real-time but never write to the `zones.security` column. The base security level is always the admin-set value.
- **PvP consent is transient.** Stored in an in-memory dict, keyed by `(char_id_a, char_id_b)` with a timestamp. Lost on restart — intentional. No one should have a stale PvP flag from yesterday.
