# Faction Reputation System — Design Document v1

**SW_MUSH · Per-Character Faction Reputation**
**April 14, 2026 · Opus Session 27**

---

## 1. Problem Statement

The faction reputation system is half-built with critical gaps:

1. **Three of four `adjust_rep()` callers are broken.** `parser/bounty_commands.py`, `parser/mission_commands.py`, and `parser/smuggling_commands.py` all call `ctx.db.adjust_rep()` — a method that doesn't exist on the Database class. The real function is `engine.organizations.adjust_rep(char, faction_code, db, action_key)`. These calls silently fail inside `try/except` blocks, meaning bounty completions, mission completions, and smuggling deliveries **never award faction rep** despite the code's clear intent.

2. **Profession chain completion awards zero faction rep.** `_grant_chain_reward()` in `engine/tutorial_v2.py` only awards credits. The 6 profession chains (Smuggler's Run, Hunter's Mark, Artisan's Forge, Rebel Cell, Imperial Service, Underworld) have no `reward_faction`/`reward_rep` fields on step dicts and no rep award logic. Completing a full chain for the Rebel Alliance should meaningfully boost Rebel standing — it currently does nothing.

3. **No player-facing reputation display.** The only rep visibility is a single `Rep: X/100` line inside `faction status` — which only shows the player's *current* faction. There's no way to see standing with other factions, no way to see how close you are to the next rank, and no way to understand what rep thresholds unlock.

4. **No auto-promotion.** `promote()` exists and correctly checks `min_rep`, but only fires when a faction leader manually promotes someone. There's no auto-promotion check after rep changes. A player who reaches 25 rep with the Empire stays at Recruit rank forever unless a leader promotes them.

5. **Rep has no gameplay consequences beyond rank gating.** No shop discounts, no mission tier unlocks, no NPC dialogue flavor changes, no Director AI narrative integration. Rep is a number that goes up but changes nothing.

6. **Non-member rep is stored but invisible.** `adjust_rep()` correctly stores rep in `attributes.faction_rep{}` for non-members, but nothing reads this. A smuggler who runs 50 jobs for the Hutts but never formally joins has no visible standing.

---

## 2. Design Goals

- **Fix what's broken** — all rep callers routing through `engine.organizations.adjust_rep()` correctly
- **Wire profession chains** — each chain awards rep for the appropriate faction on key steps
- **Make rep visible** — `+reputation` command showing all faction standings with rank thresholds
- **Auto-promote on threshold** — crossing `min_rep` for the next rank triggers automatic promotion
- **Gameplay consequences** — rep tiers unlock shop discounts, mission access, NPC behavior changes
- **Cross-faction awareness** — non-member standings visible and meaningful (hostile faction reps create risk)
- **Web client integration** — reputation panel in sidebar
- **Director AI integration** — faction standing affects NPC dialogue tone and Director event targeting

---

## 3. Rep Sources — Fixed and Expanded

### 3.1 Existing REP_GAINS (Fix Broken Callers)

| Action Key | Delta | Current Status | Fix |
|------------|-------|----------------|-----|
| `complete_faction_mission` | +3 | **BROKEN** — `ctx.db.adjust_rep()` | Route through `engine.organizations.adjust_rep(char, faction_code, db, action_key)` |
| `complete_profession_chain_step` | +5 | **UNHOOKED** — `_grant_chain_reward()` ignores rep | Add `reward_faction` + `reward_rep` to chain step dicts, call `adjust_rep()` in `_grant_chain_reward()` |
| `kill_enemy_faction_npc` | +1 | ✅ Working (combat_commands.py) | No change |
| `complete_bounty` | +2 | **BROKEN** — `ctx.db.adjust_rep()` | Route through `adjust_rep()` |
| `deliver_contraband` | +2 | **BROKEN** — `ctx.db.adjust_rep()` | Route through `adjust_rep()` |
| `crafting_sale` | +1 | **UNHOOKED** — no caller | Wire into vendor droid sale (already has hooks) |
| `faction_event_attendance` | +1 | **UNHOOKED** — no caller | Wire into scene completion when faction members co-present |
| `rule_violation` | -5 | **UNHOOKED** — no caller | Wire into security zone violations (attacking in secured zones) |

### 3.2 New Rep Actions

| Action Key | Delta | Trigger | Notes |
|------------|-------|---------|-------|
| `complete_chain_final` | +15 | Profession chain completion (final step) | Big rep boost for chain finale — distinct from per-step +5 |
| `territory_claim` | +3 | Successful territory claim | Faction members who participate in claiming territory |
| `territory_defense` | +2 | Successful contest defense | Holding territory against challengers |
| `trade_with_faction_vendor` | +1 | Buy from faction-aligned NPC shop | Spending credits at faction shops (e.g. Imperial Garrison shop) |
| `hostile_action` | -5 | Attack same-faction PC/NPC | Friendly fire penalty |
| `defection` | -30 | Leave faction via `faction leave` | Severe rep loss with former faction |
| `cross_faction_kill` | +2 / -3 | Kill enemy-aligned NPC | +2 to own faction, -3 to victim's faction |

### 3.3 Profession Chain Rep Rewards

Each chain awards rep for its aligned faction at key milestones:

| Chain | Faction | Steps | Rep per Step | Final Bonus | Total |
|-------|---------|-------|-------------|-------------|-------|
| Smuggler's Run | `hutt` | Steps 2,3,5,6 (4 steps) | +5 | +15 | +35 |
| Hunter's Mark | `bh_guild` | Steps 2,3,5 (3 steps) | +5 | +15 | +30 |
| Artisan's Forge | Nearest guild | Steps 2,4,6 (3 steps) | +5 | +15 | +30 |
| Rebel Cell | `rebel` | Steps 2,3,5,6 (4 steps) | +5 | +15 | +35 |
| Imperial Service | `empire` | Steps 2,3,5,6 (4 steps) | +5 | +15 | +35 |
| Underworld | `hutt` | Steps 2,4,6 (3 steps) | +5 | +15 | +30 |

Implementation: Add `"reward_faction": "rebel"` and `"reward_rep": 5` (or `15` for finals) to the appropriate step dicts in `engine/tutorial_v2.py`. The `_grant_chain_reward()` function checks for these keys and calls `adjust_rep()`.

---

## 4. Rep Tiers and Gameplay Consequences

### 4.1 Rep Tier Names

| Range | Tier Name | Color | Notes |
|-------|-----------|-------|-------|
| 0–9 | Unknown | `\033[2m` (dim) | Default state for all factions |
| 10–24 | Recognized | `\033[0m` (normal) | Faction NPCs acknowledge you |
| 25–49 | Trusted | `\033[1;33m` (yellow) | Shop discounts, basic mission access |
| 50–74 | Honored | `\033[1;36m` (cyan) | Elite mission access, NPC dialogue deference |
| 75–89 | Revered | `\033[1;32m` (green) | Deep discounts, faction-only content |
| 90–100 | Exalted | `\033[1;35m` (magenta) | Faction hero status, maximum benefits |

### 4.2 Negative Rep (Cross-Faction Hostility)

Non-member faction rep can be negative (range: -100 to +100 for non-members):

| Range | Tier Name | Color | Consequences |
|-------|-----------|-------|-------------|
| -100 to -50 | Hostile | `\033[1;31m` (red) | Faction NPCs attack on sight; faction shop access denied; arrest risk in faction-controlled territory |
| -49 to -25 | Unfriendly | `\033[0;31m` (red dim) | NPC dialogue hostile; shop prices +50%; flagged in faction territory |
| -24 to -1 | Wary | `\033[33m` (dim yellow) | NPC dialogue cautious; no mechanical effect |

### 4.3 Gameplay Consequences by Tier

**Shop Discounts (faction-aligned shops only):**
- Trusted (+25): 5% discount
- Honored (+50): 10% discount
- Revered (+75): 15% discount
- Exalted (+90): 20% discount
- Unfriendly (-25): +50% price increase
- Hostile (-50): Shop access denied

**Mission Access:**
- Trusted (+25): Standard faction missions available on mission board
- Honored (+50): Elite faction missions (higher reward, harder difficulty)
- Revered (+75): Classified faction missions (unique storylines)

**NPC Dialogue Flavor:**
- Injected into `npc_brain.py` persuasion context as `faction_standing` field
- NPCs of the same faction as the player adjust tone: "You've served the Empire well, Lieutenant" vs "I don't know you, spacer"
- Hostile-rep NPCs may refuse to talk or give false information

**Territory Benefits:**
- Trusted (+25): Can use faction armory in claimed rooms (currently gated on membership only)
- Honored (+50): Reduced territory influence costs

**Director AI:**
- Faction standing fed to Director as context: "Player X has Revered standing with the Rebel Alliance"
- Director can target events at high-standing players ("Rebel Intelligence has a mission for their most trusted operative")
- Hostile standings create dramatic tension events ("Imperial agents have taken notice of your rebel sympathies")

---

## 5. Auto-Promotion

### 5.1 Check Trigger

After every `adjust_rep()` call that results in a rep increase, check if the new rep meets the `min_rep` threshold of the next rank. If so, auto-promote.

### 5.2 Implementation

Add `check_auto_promote()` function to `engine/organizations.py`:

```python
async def check_auto_promote(char: dict, faction_code: str, db, session=None) -> bool:
    """Check if character qualifies for promotion based on rep. Returns True if promoted."""
    org = await db.get_organization(faction_code)
    if not org:
        return False
    mem = await db.get_membership(char["id"], org["id"])
    if not mem:
        return False
    
    ranks = await db.get_org_ranks(org["id"])
    current_level = mem["rank_level"]
    next_level = current_level + 1
    next_rank = next((r for r in ranks if r["rank_level"] == next_level), None)
    
    if not next_rank:
        return False  # Already max rank
    
    if mem["rep_score"] < next_rank["min_rep"]:
        return False  # Not enough rep
    
    # Auto-promote
    ok, msg = await promote(char, faction_code, db)
    if ok and session:
        await session.send_line(
            f"\n  \033[1;32m★ RANK UP! ★\033[0m {msg}\n"
        )
        # Web client event
        session.send_json_event("rank_up", {
            "faction": faction_code,
            "new_rank": next_rank["title"],
            "new_level": next_level,
        })
    return ok
```

Call `check_auto_promote()` inside `adjust_rep()` after every rep increase (only for members, not attribute-based non-member rep).

### 5.3 Multi-Rank Jump

If a large rep reward crosses multiple rank thresholds (e.g., profession chain finale +15 jumps past two ranks), `check_auto_promote()` should loop until it fails:

```python
while await check_auto_promote(char, faction_code, db, session):
    pass  # Keep promoting until threshold not met
```

---

## 6. `+reputation` Command

### 6.1 Display

```
==========================================
  FACTION REPUTATION
==========================================
  Galactic Empire      ████████░░  42/100  [Trusted]
    Rank: Corporal (3)  →  Sergeant at 55 rep
  Rebel Alliance       ██░░░░░░░░  -18/100 [Wary]
  Hutt Cartel          ██████████  67/100  [Honored]
  Bounty Hunters' Guild ███░░░░░░░  22/100  [Recognized]
  Independent          ░░░░░░░░░░   0/100  [Unknown]
==========================================
  +reputation <faction>  for detailed breakdown
```

### 6.2 Detailed View (`+reputation empire`)

```
==========================================
  GALACTIC EMPIRE — REPUTATION
==========================================
  Standing:  42/100 [Trusted]
  Rank:      Corporal (3)
  Next Rank: Sergeant at 55 rep (13 away)
------------------------------------------
  RANK THRESHOLDS
    ✓ Recruit      (0)
    ✓ Private      (10)   — e11_blaster_rifle, stormtrooper_armor
    ✓ Corporal     (25)   — improved_armor
    ▸ Sergeant     (40)   ← CURRENT TARGET
    ○ Lieutenant   (60)   — officers_sidearm
    ○ Captain      (75)
    ○ Commander    (90)
------------------------------------------
  RECENT REP CHANGES
    +3  Mission complete: "Imperial Supply Run"       2 hours ago
    +1  NPC kill: Rebel Trooper                       5 hours ago
    +5  Profession chain: Imperial Service Step 3     1 day ago
==========================================
```

### 6.3 Rep History

Store the last 10 rep changes per faction in character attributes JSON under `rep_history`:

```json
{
  "faction_rep": {"empire": 42, "rebel": -18, "hutt": 67},
  "rep_history": {
    "empire": [
      {"delta": 3, "reason": "Mission complete", "ts": 1713100000},
      {"delta": 1, "reason": "NPC kill", "ts": 1713090000}
    ]
  }
}
```

Capped at 10 entries per faction (FIFO). Displayed in `+reputation <faction>` detailed view.

---

## 7. `adjust_rep()` Refactor

### 7.1 Updated Signature

```python
async def adjust_rep(char: dict, faction_code: str, db,
                     action_key: str = None,
                     delta: int = None,
                     reason: str = None,
                     session=None) -> int:
```

**New parameters:**
- `delta` — explicit override (bypasses `REP_GAINS` lookup). Used by profession chain rewards.
- `reason` — human-readable reason for rep history log.
- `session` — if provided, sends rep change notification and triggers auto-promotion check.

If `action_key` is provided, `delta` is looked up from `REP_GAINS`. If `delta` is provided directly, `action_key` is ignored for the delta value but can still be used as the reason string.

### 7.2 Cross-Faction Rep

When a player earns positive rep with a faction, apply a smaller *negative* rep effect to opposing factions:

| Gaining Faction | Losing Factions | Ratio |
|-----------------|-----------------|-------|
| `empire` | `rebel` | -50% of gain |
| `rebel` | `empire` | -50% of gain |
| `hutt` | — | No cross-faction loss |
| `bh_guild` | — | No cross-faction loss |

Example: Complete an Imperial mission (+3 Empire rep) → -1 Rebel rep automatically. This creates meaningful faction choice tension without making cross-faction play impossible.

### 7.3 Non-Member Rep Range

Non-member rep stored in `attributes.faction_rep{}` currently clamps to 0–100. Expand to -100 to +100 for non-members to support hostile standings.

---

## 8. Web Client Integration

### 8.1 HUD Data

Add `reputation` dict to `session.py` HUD update:

```python
"reputation": {
    "empire": {"rep": 42, "tier": "trusted", "rank": "Corporal", "rank_level": 3},
    "rebel": {"rep": -18, "tier": "wary", "rank": None, "rank_level": None},
    "hutt": {"rep": 67, "tier": "honored", "rank": None, "rank_level": None},
    "bh_guild": {"rep": 22, "tier": "recognized", "rank": None, "rank_level": None},
}
```

### 8.2 Sidebar Panel

Compact reputation bars in the HUD sidebar, visible when not in combat/space:

- Faction name + colored tier badge
- Mini progress bar (10-segment)
- Current rank (if member)
- Expand on click for detailed view

### 8.3 Rep Change Toast

On rep change, send JSON event `rep_change`:

```json
{
    "type": "rep_change",
    "faction": "empire",
    "delta": 3,
    "new_rep": 42,
    "tier": "trusted",
    "reason": "Mission complete"
}
```

Render as a subtle inline notification (not a full toast like achievements — rep changes are frequent and shouldn't be intrusive). Slide-in from left, dim colors, auto-dismiss 2.5s.

---

## 9. Director AI Integration

### 9.1 Context Injection

When Director generates events, inject player faction standings for all online players:

```
Active players: Han (Empire: Trusted, Rebel: Unknown, Hutt: Honored),
                Leia (Empire: Hostile, Rebel: Revered, Hutt: Unknown)
```

This lets the Director target events appropriately — "Imperial agents approach Han with a proposition" vs "Rebel command reaches out to Leia for a critical mission."

### 9.2 NPC Dialogue Context

In `npc_brain.py`, extend the `persuasion_context` dict with faction standing:

```python
"faction_standing": {
    "npc_faction": "empire",
    "player_rep": 42,
    "player_tier": "trusted",
    "relationship": "The player is a trusted Imperial Corporal."
}
```

NPCs already receive `persuasion_context` — this adds faction-aware dialogue without changing the prompt structure.

---

## 10. Implementation Drops

### Drop 1 — Fix Broken Callers + `adjust_rep()` Refactor (Core)

**Files:** `engine/organizations.py`, `parser/bounty_commands.py`, `parser/mission_commands.py`, `parser/smuggling_commands.py`

- Refactor `adjust_rep()` with optional `delta`, `reason`, `session` parameters
- Add rep history logging (last 10 per faction in `attributes.rep_history`)
- Add cross-faction rep (Empire ↔ Rebel at -50%)
- Expand non-member range to -100 to +100
- Fix 3 broken callers: replace `ctx.db.adjust_rep(char["id"], ...)` with `await adjust_rep(char, faction_code, ctx.db, action_key, session=ctx.session)`
- Wire `crafting_sale` into vendor droid sale in `engine/vendor_droids.py`
- Wire `rule_violation` into security zone violation in `parser/combat_commands.py`

**Effort:** 3-4 hours

### Drop 2 — Auto-Promotion + `+reputation` Command

**Files:** `engine/organizations.py`, `parser/faction_commands.py` (or new `parser/reputation_commands.py`)

- `check_auto_promote()` with multi-rank loop
- Call from `adjust_rep()` after every member rep increase
- `+reputation` command — all-factions overview with progress bars
- `+reputation <faction>` — detailed view with rank thresholds + recent changes
- Web client JSON event for rank-up notification

**Effort:** 3-4 hours

### Drop 3 — Profession Chain Rep Rewards

**Files:** `engine/tutorial_v2.py`

- Add `reward_faction` and `reward_rep` keys to chain step dicts (see §3.3)
- Update `_grant_chain_reward()` to call `adjust_rep()` when these keys present
- Final steps get `reward_rep: 15` + `complete_chain_final` action key
- Test all 6 chains for correct faction assignment

**Effort:** 2-3 hours

### Drop 4 — Gameplay Consequences

**Files:** `parser/shop_commands.py`, `engine/missions.py`, `ai/npc_brain.py`, `engine/security.py`

- Shop discount/markup based on faction rep tier
- Faction mission tier filtering (Trusted/Honored/Revered unlock tiers)
- NPC dialogue `faction_standing` context injection
- Hostile rep: faction guard NPCs attack, shop access denied

**Effort:** 4-6 hours

### Drop 5 — Web Client Reputation Panel

**Files:** `server/session.py`, `static/client.html`

- Reputation dict in HUD update
- Sidebar panel with compact rep bars
- Rep change inline notification
- Rank-up toast notification

**Effort:** 3-4 hours

### Drop 6 — Director AI Integration

**Files:** `engine/director.py`, `ai/npc_brain.py`

- Online player standings in Director event prompt context
- NPC brain persuasion_context extension with faction_standing
- Director event targeting based on player rep tiers

**Effort:** 2-3 hours

---

## 11. Total Effort

| Drop | Contents | Effort |
|------|----------|--------|
| 1 | Fix callers + adjust_rep refactor | 3-4 hrs |
| 2 | Auto-promote + +reputation command | 3-4 hrs |
| 3 | Profession chain rep rewards | 2-3 hrs |
| 4 | Gameplay consequences | 4-6 hrs |
| 5 | Web client reputation panel | 3-4 hrs |
| 6 | Director AI integration | 2-3 hrs |
| **Total** | | **17-24 hrs** |

---

## 12. Testing

### Integration Tests (extend `tests/`)

- `test_reputation.py`:
  - `adjust_rep()` correctly updates member rep_score
  - `adjust_rep()` correctly updates non-member attributes.faction_rep
  - Cross-faction rep: Empire gain → Rebel loss
  - Auto-promotion fires on threshold crossing
  - Multi-rank jump works correctly
  - Rep history capped at 10 entries
  - Broken callers now route correctly (bounty, mission, smuggling)
  - `+reputation` command output parsing
  - Shop discount applies at correct tier thresholds
  - Hostile rep blocks shop access

### Manual Tests

1. Complete a bounty → verify `bh_guild` rep increases (was silently failing)
2. Complete a mission → verify faction rep increases
3. Complete smuggling run → verify `hutt` rep increases
4. Complete Rebel Cell chain → verify `rebel` rep accumulates across steps
5. Cross 25 rep threshold → verify auto-promotion fires
6. `+reputation` → verify all factions displayed with correct tiers
7. Shop buy with Trusted rep → verify 5% discount applies

---

## 13. Invariants

- All rep changes go through `engine/organizations.adjust_rep()` — no direct DB writes
- Rep history capped at 10 entries per faction (FIFO)
- Auto-promotion only fires for members, never for attribute-based non-member rep
- Cross-faction rep only applies to Empire ↔ Rebel axis (Hutts and BH Guild are neutral)
- Negative rep clamps at -100, positive at +100
- Shop discounts stack additively with Bargain skill check results
- Rep change notifications are subtle inline events, not full toast popups
- `+reputation` works on Telnet (ANSI progress bars) and web client (JSON panel)

---

## 14. What This Unlocks

With a working reputation system:

1. **Profession chains become meaningful** — completing a chain grants real faction advancement, not just credits
2. **Faction choice has consequences** — helping the Empire hurts your Rebel standing and vice versa
3. **NPC interactions gain depth** — dialogue changes based on your standing
4. **Auto-promotion removes admin bottleneck** — players advance through gameplay, not GM intervention
5. **Director AI gains targeting intelligence** — faction-specific events reach the right players
6. **Territory control gains depth** — territory operations build faction standing
7. **Economy gains a reputation sink** — faction discounts reward loyal members

This is the single biggest gameplay hole remaining. Every system that should interact with factions (missions, bounties, smuggling, crafting, chains, territory, Director) currently treats reputation as a no-op.

---

*Design document v1. 6 drops, ~17-24 hours total. Fixes 3 broken callers, unwires 30+ no-op hooks, adds 2 new commands, 1 web panel, and Director integration.*
