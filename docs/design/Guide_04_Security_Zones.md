# SW_MUSH Detailed Systems Guide #4
# Security Zones

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

### Player Rules

Every zone in the game has a security level that determines what kind of combat is allowed there. This creates a meaningful risk gradient — safe market areas for socializing and shopping, contested back alleys where PvP requires consent, and lawless wilderness where anything goes.

The three security tiers:

| Security Level | PvE Combat | PvP Combat | Color | Example Zones |
|----------------|-----------|------------|-------|---------------|
| **Secured** | Blocked entirely | Blocked entirely | Blue | Mos Eisley Core, Imperial Garrison, Coronet Gov't District |
| **Contested** | NPC combat allowed | Requires challenge/accept consent | Yellow | Spaceport District, Cantina, most urban zones |
| **Lawless** | Unrestricted | Unrestricted | Red | Jundland Wastes, Nar Shaddaa Undercity, Spice Mines |

When you enter a room or type `look`, the security level appears as a colored tag next to the room name:

```
Mos Eisley Market [SECURED]
  Rows of stalls line the dusty street...

Back Alley [CONTESTED]
  A narrow passage between buildings...

Jundland Wastes - Canyon Floor [LAWLESS]
  Wind-carved sandstone walls rise on either side...
```

### 🔧 Developer Internals

**File:** `engine/security.py` (~249 lines)

**`SecurityLevel` enum** (lines 34–37): `SECURED`, `CONTESTED`, `LAWLESS` — string values match DB/property values.

**Display:** `security_label(level)` returns ANSI-colored badge: blue `[SECURED]`, yellow `[CONTESTED]`, red `[LAWLESS]`. Integrated into the `look` command output in `parser/builtin_commands.py`.

**Refusal messages:** `security_refuse_msg(level, target_is_npc)` returns thematic Imperial security flavor text when combat is blocked.

---

## 2. Security Resolution: How Level Is Determined

### Player Rules

You don't need to know the resolution chain — you just see the result. But understanding it helps explain why security can change dynamically. The effective security level can shift based on Director AI events, Imperial/criminal faction influence, and player organization territory claims.

### 🔧 Developer Internals

**`get_effective_security(room_id, db, character=None)`** (lines 77–152) — The core async function. Resolution order:

1. **Transient Director override on zone_id** (admin `@security` command) — `_overrides` dict, in-memory only
2. **Director env override by zone environment key** — `_env_overrides` dict (e.g., "spaceport" → LAWLESS during a criminal surge event)
3. **Director live influence thresholds** — Reads zone influence state from the Director and applies `_apply_director_overlay()`:
   - Criminal influence ≥ 80: **downgrade** one tier (Secured→Contested, Contested→Lawless)
   - Imperial influence ≥ 75: **upgrade** one tier (Lawless→Contested, Contested→Secured)
   - Imperial influence ≥ 90: **force SECURED** regardless (martial law)
   - Both rules apply in sequence — a crackdown can partially cancel a criminal surge
4. **Room/zone property** — `db.get_room_property(room_id, "security")` — the builder-set static level
5. **Default** — CONTESTED if no value is set anywhere

After base resolution, if a `character` dict is provided:

6. **Territory claim upgrade** — If the room is claimed by the character's organization and the base level is LAWLESS, upgrade to CONTESTED. Org members are safer on their own turf.

**Key architecture invariant:** Every combat initiation — player `attack`, NPC aggro, space `fire` — routes through `get_effective_security()`. No shortcuts. The function is async because it needs DB access for zone/room properties and territory claims.

**Override storage:** Both `_overrides` (zone_id → level) and `_env_overrides` (environment key → level) are transient in-memory dicts. Cleared on server restart — this is intentional, matching the design principle that Director-driven security shifts are temporary narrative effects.

---

## 3. Combat Gates

### Player Rules

When you try to attack in a secured zone, you see:
```
  Imperial security patrols this area.
  The guards would be on you before you could draw.
```

In a contested zone, PvE works normally but PvP requires the challenge/accept flow (see section 4). In a lawless zone, everything is unrestricted — but you get a one-time warning when you first enter:
```
  *** WARNING: You are entering LAWLESS territory. ***
  *** Players can attack you freely here. ***
```

### 🔧 Developer Internals

**Convenience helpers** (lines 214–233):
- `is_combat_allowed(room_id, db)` → `True` if level ≠ SECURED
- `is_pvp_allowed(room_id, db)` → `True` only if level = LAWLESS

**Integration points:**
- `parser/combat_commands.py` — `AttackCommand.execute()` gates on security level before allowing combat initiation
- `engine/npc_combat_ai.py` — NPC aggro is suppressed in secured zones (NPCs are passive — they talk, sell, and quest but don't attack)
- `parser/space_commands.py` — `FireCommand.execute()` gates on space security
- `parser/builtin_commands.py` — `look` command includes security tag; `move` command shows lawless warning on first entry

---

## 4. PvP Consent System

### Player Rules

In **contested zones**, you must get consent before attacking another player:

```
> challenge Vex
  You challenge Vex to a fight!

  (Vex sees: "Tundra challenges Vex to a fight!
   Type 'accept' to accept or 'decline' to refuse.")

> accept                 (Vex types this)
  Vex accepts the challenge! PvP is active for 10 minutes.
```

Once accepted, both players can attack each other freely for 10 minutes. After the window expires or either player leaves the zone, consent lapses and must be re-established.

In **lawless zones**, no consent is needed — any player can attack any other player at any time.

In **secured zones**, no PvP is possible at all.

### 🔧 Developer Internals

**File:** `parser/combat_commands.py` — PvP tracking (lines 41–47):

```python
_pvp_consent: dict[tuple, float] = {}   # (attacker_id, target_id) → timestamp
_pvp_active: dict[tuple, float] = {}    # accepted pairs (either direction)
_PVP_CHALLENGE_TTL = 600                # 10 minutes
```

Both dicts are transient — challenges and active PvP pairs don't survive restarts. The challenge/accept/decline commands are `ChallengeCommand`, `AcceptCommand`, `DeclineCommand` registered in `combat_commands.py`.

**Commands:**
- `ChallengeCommand` — Creates entry in `_pvp_consent` with timestamp, broadcasts to target
- `AcceptCommand` — Moves pair from `_pvp_consent` to `_pvp_active` (both directions), broadcasts confirmation
- `DeclineCommand` — Removes from `_pvp_consent`, broadcasts refusal

---

## 5. Bounty Hunter Override

### Player Rules

Members of the **Bounty Hunters' Guild** with an active claimed bounty contract can bypass PvP consent requirements in contested zones. Their target is fair game — the bounty *is* the consent.

The target sees:
```
  Vex draws on you! [BOUNTY HUNTER — Contract #4421]
  You've been marked. Defend yourself!
```

This creates meaningful PvP content without griefing — only players who've earned a bounty (through criminal actions tracked by the bounty board system) are targetable, and only by players who've invested in Guild standing.

### 🔧 Developer Internals

Implemented in the `AttackCommand` security check: before refusing a PvP attack in a contested zone, checks whether the attacker has an active bounty contract on the target and has sufficient Guild standing. Bypasses the challenge/accept flow if conditions are met.

---

## 6. Space Security

### Player Rules

Space zones follow a parallel security model:

| Space Zone Type | Effective Security | Rationale |
|-----------------|-------------------|-----------|
| **DOCK** | Secured | Landing approach, port control, customs |
| **ORBIT** | Contested | Orbital space, patrols present but thin |
| **DEEP_SPACE** | Lawless | Open void, no authority |
| **HYPERSPACE_LANE** | Contested | Major shipping routes, some patrol presence |

NPC pirate ambushes happen in deep space (lawless). Imperial patrol encounters happen in orbit (contested). Dock zones are safe harbor.

Ship-vs-ship PvP follows the same rules: unrestricted in deep space, consent-required in orbit/lanes, blocked in dock zones. The `fire` command gets the same security gate as the ground `attack` command.

### 🔧 Developer Internals

Space zone type → security level mapping is applied in `parser/space_commands.py` `FireCommand`. The space zone's `zone_type` field (DOCK, ORBIT, DEEP_SPACE, etc.) maps to the equivalent `SecurityLevel`.

---

## 7. Director AI Dynamic Overlays

### Player Rules

The Director AI can temporarily shift security levels based on story events:

- **Imperial crackdown** — When Imperial influence hits 75+ in a zone, security upgrades one tier. At 90+, the zone goes to martial law (forced SECURED regardless of base level). Stormtroopers flood the streets.
- **Criminal surge** — When criminal influence hits 80+ in a zone, security downgrades one tier. The underworld fills the power vacuum.

These shifts are temporary and revert when the influence changes. They create a dynamic, player-affected world — driving Imperial influence down through Rebel or criminal actions makes zones more dangerous, while supporting the Empire makes zones safer.

You can see the current influence state via the Director's zone reports and world event banners on the web client.

### 🔧 Developer Internals

**`_apply_director_overlay(base, zs)`** (lines 155–184):
```python
# Criminal surge — downgrade one tier
if zs.criminal >= 80:
    SECURED → CONTESTED, CONTESTED → LAWLESS

# Imperial crackdown — upgrade one tier
if zs.imperial >= 75:
    LAWLESS → CONTESTED, CONTESTED → SECURED

# Martial law — extreme dominance
if zs.imperial >= 90:
    result = SECURED  # Force regardless
```

Both rules apply in sequence, so a zone can have criminal ≥ 80 AND imperial ≥ 75 — the crackdown partially counters the surge.

**`set_security_override_by_env(zone_env, level)`** — Called by the Director after faction turns or influence updates. Keyed by zone environment string (e.g., "spaceport", "cantina", "jabba"). Transient in-memory.

---

## 8. Territory Claims and Security Upgrades

### Player Rules

When a player organization claims a room in a **lawless** zone, that room is treated as **contested** for the organization's members. You get PvP consent protection on your own turf — enemies still need to challenge you to fight. Non-members entering your claimed territory get no such protection.

This is the first benefit of the Territory Control system (covered in detail in Guide #11).

### 🔧 Developer Internals

**`_apply_claim_upgrade(base, room_id, character, db)`** (lines 187–209):
- Only applies when `base == LAWLESS` — other levels are unaffected
- Checks `character["faction_id"]` — ignores if "independent" or not set
- Calls `territory.is_room_claimed_by(db, room_id, char_org)` from `engine/territory.py`
- Returns CONTESTED if claim exists, otherwise returns original LAWLESS
- The `character` parameter is passed from the command layer, allowing per-player security evaluation

---

## 9. Lawless Zone Incentives

### Player Rules

Why venture into dangerous lawless territory? Higher risk brings higher rewards:

**Economy:** Rare crafting resources only spawn in lawless zones. The mission board offers higher-paying jobs requiring lawless zone travel. Smuggling routes pass through lawless territory for the biggest payouts. Black market vendors sell restricted gear without markup.

**Progression:** Certain advanced NPC trainers only operate in lawless zones. Ground-based discoveries (ruins, crash sites, hidden caches) only appear in lawless zones. CP tick rate has a +25% bonus while actively in a lawless zone.

**Territory Control (future):** Organizations can claim rooms, install defenses, build vendor stalls and crafting stations, and generate passive income. Other organizations can assault claimed territory — this is the endgame PvP content.

---

## 10. Admin Commands

### Player Rules (Staff Only)

```
@security <zone>              — Show security level for a zone
@security <zone> = <level>    — Set level (secured/contested/lawless)
@security override <room> = none  — Clear override
```

These modify the DB directly and take effect immediately — no restart needed.

### 🔧 Developer Internals

Admin commands modify zone/room properties via DB updates. The security check reads from DB on every `attack` attempt, so changes are instant. Schema migration (v9) added `security TEXT DEFAULT 'contested'` to the zones table and `faction_override TEXT DEFAULT NULL` to the rooms table.

---

## 11. Implementation Status

| Drop | Scope | Status |
|------|-------|--------|
| **1** | Core security engine, combat gates, look tags, NPC aggro gate | ✅ Delivered |
| **2** | PvP consent (challenge/accept/decline) | ✅ Delivered |
| **3** | Space security gates (fire command) | ✅ Delivered |
| **4** | Director AI dynamic overlays (criminal surge, crackdown) | ✅ Delivered |
| **5** | Bounty hunter PvP consent override | ✅ Delivered |
| **6A** | Territory influence earning hooks | ✅ Delivered |
| **6B** | Room claiming + security upgrade for members | ✅ Delivered |
| **6C** | Guard NPC spawning, resource nodes | Planned |
| **6D** | Contest state machine, rival org PvP, hostile takeover | Planned |
| **6E** | Web client territory badge, contest alerts, ASCII map | Planned |

---

## 12. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/security.py` | ~249 | SecurityLevel enum, get_effective_security(), Director overlays, territory claim upgrade, convenience helpers |
| `parser/combat_commands.py` | ~1,954 | Combat gates, PvP consent tracking, challenge/accept/decline commands |
| `parser/space_commands.py` | ~5,184 | Space fire command security gate |
| `parser/builtin_commands.py` | ~1,872 | Look command security tag, lawless zone warning |
| `engine/npc_combat_ai.py` | ~461 | NPC aggro suppression in secured zones |
| `engine/director.py` | ~1,483 | Zone influence state, faction turn processing |
| `engine/territory.py` | ~768 | Territory claims, is_room_claimed_by() |

---

*End of Guide #4 — Security Zones*
*Next: Guide #5 — Space Systems*
