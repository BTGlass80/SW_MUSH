# Combat Posing & Narrative System — Design Document
## SW_MUSH · April 9, 2026

Extends `combat_ux_overhaul_design.md` (v1, April 8). That document covers paced
broadcast, ANSI hierarchy, consolidated initiative/NPC declarations, web panel, and
verb variety. This document covers the systems that sit on top of that foundation:
private briefings, the posing window, idle protection, auto-pose generation, and
cinematic output assembly.

---

## Context: Where This Fits in the Round

The existing combat engine handles steps 1–3. This document defines steps 4–6.

```
  ┌─────────────────────────────────────────────────────┐
  │  1. INITIATIVE          (existing)                   │
  │  2. DECLARATION         (existing)                   │
  │  3. RESOLUTION          (existing — batch resolve)   │
  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
  │  4. PRIVATE BRIEFINGS   THIS DOC                     │
  │  5. POSING WINDOW       THIS DOC                     │
  │  6. ACTION LOG FLUSH    THIS DOC                     │
  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
  │  7. NEXT ROUND          Loop to step 1               │
  └─────────────────────────────────────────────────────┘
```

---

## 1. Private Briefings

After `combat.resolve_round()` completes, the engine sends each player a **per-session**
summary of their outcomes. This is private — only the player sees it, not the room.

### 1.1 Briefing format

```
======================================================================
                     ROUND 2 : PRIVATE BRIEFING
======================================================================

▸ YOUR ACTIONS:
  1. Dodge → SUCCESS (Rolled 15 vs incoming 12)
  2. Attack Stormtrooper → HIT! (Rolled 14 vs Diff 10)
     Result: Inflicted 1 Wound.

▸ INCOMING ACTIONS:
  - Scout fired at you → MISSED (Defeated by your Dodge 15)

----------------------------------------------------------------------
[COMBAT] Write your pose covering your dodge and your attack.
[COMBAT] Type 'pass' to use an auto-generated pose. (3:00 remaining)
======================================================================
```

For multi-action rounds (see Section 4), all declared actions and their outcomes appear
in a single block. The player uses this to write one cohesive narrative paragraph.

NPC briefings are not displayed. NPCs auto-generate poses via the FLAVOR_MATRIX
(Section 5).

### 1.2 Implementation

New method `CombatInstance.build_private_briefing(char_id)` that reads the round's
resolution results and formats a per-character summary. Called from
`_try_auto_resolve()` after `resolve_round()`, delivered via
`session_mgr.send_to_character()`.

The briefing pulls from data already computed by the resolution step — action outcomes,
roll values, damage results, wound changes. No new calculations needed, just formatting.

---

## 2. Grace Timer

An async background task that prevents idle players from deadlocking combat. Spawned
immediately after Private Briefings are delivered.

### 2.1 Timer sequence

| Elapsed | Action |
|---------|--------|
| 0:00 | Briefings sent, posing window opens |
| 1:30 | Nudge: `[COMBAT] Still waiting for poses from: Tundra, Scout.` |
| 3:00 | Timeout: auto-`pass` all remaining `pending` combatants |

The 3-minute default is generous for a MUSH. If playtesting shows most poses come in
under 60 seconds, tighten to 2 minutes. The nudge fires at the halfway mark.

### 2.2 Early completion

If all combatants reach `ready` or `passed` status before the timer expires, the timer
task is cancelled immediately and the Action Log flushes without waiting.

### 2.3 Implementation

```python
async def _pose_grace_timer(combat, session_mgr, room_id,
                            timeout=180, nudge_at=90):
    """Background task: nudge idle posers, auto-pass on timeout."""
    try:
        await asyncio.sleep(nudge_at)
        pending = combat.get_pending_posers()
        if pending:
            names = ", ".join(p.name for p in pending)
            await session_mgr.broadcast_to_room(
                room_id,
                f"[COMBAT] Still waiting for narrative poses from: {names}."
            )
        await asyncio.sleep(timeout - nudge_at)
        # Force-pass anyone still pending
        for char_id in combat.get_pending_poser_ids():
            combat.set_pose_status(char_id, "passed")
            auto_pose = combat.generate_auto_pose(char_id)
            combat.set_pose_text(char_id, auto_pose)
        # Trigger the Action Log flush
        await _flush_action_log(combat, session_mgr, room_id)
    except asyncio.CancelledError:
        pass  # All poses came in early; normal exit
```

The timer handle is stored on the `CombatInstance` so it can be cancelled when the last
poser submits.

### 2.4 Telnet vs. web

Telnet gets the nudge ping at the halfway mark — a simple text line, no cursor
manipulation, no client-specific ANSI tricks.

The web client's `combat_state` JSON includes `pose_deadline` (ISO timestamp) so the
sidebar can render a live countdown timer. This is purely additive; the telnet nudge
is the baseline.

---

## 3. The `pass` Command & Pose Status Tracking

### 3.1 The `pass` command

Allows a player to skip writing a custom pose. The engine substitutes an auto-generated
narrative using the FLAVOR_MATRIX (Section 5).

Player types: `pass`
Engine response (to player only):
```
[COMBAT] You pass. The engine will narrate your actions this round.
```

`pass` sets `pose_status` to `"passed"` and calls `combat.generate_auto_pose(char_id)`
to fill the pose slot. If all combatants are now non-pending, cancel the grace timer
and flush.

### 3.2 Pose status tracking

Each combatant in `CombatInstance` tracks their posing state per round:

```python
self._pose_state = {
    char_id: {
        "status": "pending",   # "pending" | "ready" | "passed"
        "text": None,           # str — custom pose or auto-generated
        "initiative": 14,       # int — for sorting the Action Log
    }
}
```

State transitions:
- Player types a narrative pose → `"ready"`, `text` = their custom text
- Player types `pass` → `"passed"`, `text` = auto-generated
- Grace timer expires → engine forces `"passed"` for all remaining `"pending"`

The timer timeout is mechanically identical to the engine forcing `pass` on the
player's behalf. This makes the state machine self-cleaning — there is no fourth state,
no edge case where someone is stuck between pending and passed.

---

## 4. Multi-Action Poses

When a player declares multiple actions in a round (e.g., dodge + shoot + shoot, taking
the -1D per additional action penalty per WEG D6 RAW), they write **one single combined
pose** covering all their actions.

### 4.1 Rationale

- **No micro-poses.** Splitting into separate entries ("Tundra dodges." ... "Tundra
  shoots.") is exhausting for the player and reads robotically.
- **Cinematic time.** WEG D6 rounds represent ~5 seconds. A dodge-and-shoot is a single
  fluid motion, not two disjoint events.
- **The briefing enables it.** The Private Briefing lists all action outcomes, giving
  the player the full picture to write one cohesive paragraph.

### 4.2 Initiative anchoring

A player's single combined pose is placed in the Action Log at their **primary
initiative roll** position. Even if their second action "happens" a split second later
in the fiction, keeping the narrative block at one position preserves readability.

### 4.3 NPC multi-actions

NPCs with multiple actions are handled by the FLAVOR_MATRIX, which strings compound
actions into a single sentence:

```
[Stormtrooper] The trooper shouts a warning to his squad, then snaps off
a quick shot at Tundra, missing wide.
```

---

## 5. FLAVOR_MATRIX (Auto-Pose Generation)

A lightweight data structure that assembles auto-generated poses from three modular
components. Used for NPC poses every round and for player `pass` auto-poses.

### 5.1 The three components

- **Approach** (verb): Based on the equipped weapon type.
- **Connection** (margin text): Based on the integer result of (Roll − Difficulty).
- **Result** (wound status): Based on the final damage/wound calculation.

### 5.2 Data structure

```python
import random

FLAVOR_MATRIX = {
    # ── Approach verbs: keyed by weapon type ──
    "approach": {
        "blaster": [
            "fires a quick shot at",
            "squeezes the trigger, blasting at",
            "levels their weapon and shoots at",
            "snaps off a shot at",
        ],
        "lightsaber": [
            "lunges forward, swinging at",
            "brings the blade down in a heavy strike against",
            "slashes horizontally at",
            "drives the humming blade toward",
        ],
        "melee": [
            "swings at",
            "slashes at",
            "thrusts at",
            "jabs at",
        ],
        "brawling": [
            "throws a punch at",
            "swings a fist at",
            "charges at",
            "lunges at",
        ],
    },

    # ── Margin ranges: (min, max) inclusive ──
    "margin_ranges": {
        "miss_wild":     (-99, -6),
        "miss_close":    (-5, -1),
        "hit_glancing":  (0, 4),
        "hit_solid":     (5, 9),
        "hit_critical":  (10, 99),
    },

    # ── Connection text: keyed by margin bucket ──
    "connection": {
        "miss_wild": [
            "but the shot goes completely wide.",
            "missing by a mile.",
            "but the attack sails past harmlessly.",
        ],
        "miss_close": [
            "but the attack is barely deflected.",
            "scoring the surface but doing no real harm.",
            "the strike narrowly missing its mark.",
        ],
        "hit_glancing": [
            "landing a glancing blow.",
            "clipping them just enough to stagger.",
            "catching them with a grazing strike.",
        ],
        "hit_solid": [
            "connecting dead center!",
            "landing a heavy, punishing strike!",
            "slamming into them with force!",
        ],
        "hit_critical": [
            "with devastating precision!",
            "finding a critical weak point!",
            "striking with brutal accuracy!",
        ],
    },

    # ── Dodge verbs ──
    "dodge": [
        "ducks behind cover as",
        "throws themselves sideways as",
        "drops into a roll as",
        "pivots sharply as",
    ],
}
```

### 5.3 Assembly function

```python
def generate_auto_pose(char_name, weapon_type, target_name, margin,
                       wound_result, rng_seed=None):
    """Assemble a flavor pose from the FLAVOR_MATRIX components."""
    rng = random.Random(rng_seed)

    approach = rng.choice(FLAVOR_MATRIX["approach"].get(weapon_type, ["attacks"]))

    # Determine margin bucket
    bucket = "miss_wild"
    for key, (lo, hi) in FLAVOR_MATRIX["margin_ranges"].items():
        if lo <= margin <= hi:
            bucket = key
            break

    connection = rng.choice(FLAVOR_MATRIX["connection"][bucket])

    pose = f"{char_name} {approach} {target_name}, {connection}"

    if wound_result and wound_result != "No Damage":
        pose += f" {target_name} is {wound_result}!"

    return pose
```

**Seeding:** Use `round_number * 1000 + combatant_id` as the RNG seed for
reproducibility. Same round + same combatant always produces the same pose, which
matters for reconnection and log replay.

### 5.4 Wound escalation flavor

When a wound pushes past a threshold, append a narrative beat:

```python
WOUND_FLAVOR = {
    "Stunned":          ["staggers, shaking it off.", "flinches from the impact."],
    "Wounded":          ["grimaces in pain.", "stumbles, clutching the wound."],
    "Wounded Twice":    ["staggers, struggling to stay upright.",
                         "drops to one knee, badly hurt."],
    "Incapacitated":    ["crumples to the ground.", "collapses, unable to continue."],
    "Mortally Wounded": ["falls, life slipping away.",
                         "hits the ground hard, barely breathing."],
}
```

### 5.5 NPC flavor profiles (Deferred)

A potential future extension: add a `flavor_profile` key to NPC data dicts that selects
from profile-specific verb pools (e.g., "military" for Stormtroopers, "brute" for
Wookiees, "street" for thugs).

**This is deferred to post-playtest.** At launch, all NPCs use the single shared
FLAVOR_MATRIX. Profile-specific pools require maintaining multiple parallel verb
dictionaries and the payoff is only visible in fights with diverse NPC types. Ship the
core loop first, then evaluate whether players notice or care.

---

## 6. Action Log Flush

After all poses are collected (or the grace timer forces them), the engine assembles the
final room-wide broadcast.

### 6.1 Sort order

All poses are sorted by initiative value, highest to lowest. This produces a strictly
chronological cinematic sequence — like a well-edited movie, not a turn log.

### 6.2 Output format

```
─── ROUND 2 : ACTION LOG ──────────────────────────────────────────────
  (Init 14) [Unnamed Scout] The Scout drops to one knee, firing wildly
            at Tundra — the bolt scorches the wall behind him.
  (Init 5)  [Stormtrooper] Stumbling backward, the trooper blindly
            squeezes the trigger, the shot going wide.
  (Init 2)  [Tundra] Grunting as the bolt grazes flesh, Tundra steps
            forward and drives the blade through the trooper's guard.
────────────────────────────────────────────────────────────────────────
```

### 6.3 Pacing

Same 0.4–0.8s delay between combatant blocks as the staggered broadcast in the
existing design doc (Phase 1.1). The Action Log is delivered as a paced stream, not
a dump.

### 6.4 Implementation

`_flush_action_log()` reads `self._pose_state`, sorts entries by `initiative`
descending, formats each with the `(Init N)` prefix and character tag, then calls
`_broadcast_events_paced()` with inter-combatant delays.

---

## 7. Reaction Stances (Full Dodge) — Ruling

**Pre-declaration only. No interrupt mechanic.**

WEG D6 RAW supports reaction skills (aborting a planned action to make a full dodge
after seeing incoming fire). Implementing a true mid-resolution interrupt in a
simultaneous-resolve MUSH would require breaking out of batch resolution into a
real-time reaction window, adding round-trip latency for each potential reactor, and
introducing massive complexity for marginal gameplay benefit.

Instead, full dodge is treated as a **declared action at round start**. A player who
declares `dodge` or `full dodge` at declaration time gets their full Dodge dice pool
applied against all incoming attacks for that round. This is mechanically equivalent
to the WEG RAW reaction and fits cleanly into the batch-resolve model.

The Private Briefing confirms dodge outcomes:

```
▸ YOUR ACTIONS:
  1. Full Dodge → Applied against all incoming attacks

▸ INCOMING ACTIONS:
  - Stormtrooper fired at you → MISSED (Your Dodge 18 vs their 12)
  - Scout fired at you → HIT! (Their 20 vs your Dodge 18)
     You take: Stunned
```

---

## 8. Web Client Extensions

The existing design doc (Phase 2) spec's `to_hud_dict()` and `combat_state` JSON
broadcast. The posing system adds these fields:

- `phase: "posing"` — new phase value (alongside initiative/declaration/resolution)
- `pose_deadline` — ISO timestamp for the sidebar countdown timer
- `pose_status` per combatant — `"pending"` / `"ready"` / `"passed"`

The sidebar gains a pose countdown timer and per-combatant status indicators (waiting /
submitted / passed). The `pass` button joins the existing quick-action row.

---

## Implementation Order

| Drop | Scope | Depends On | Files | Effort |
|------|-------|------------|-------|--------|
| **A** | Private Briefings (Sec 1) | Existing Drop 3 (ANSI hierarchy) | `engine/combat.py`, `parser/combat_commands.py` | Medium |
| **B** | FLAVOR_MATRIX + auto-pose (Sec 5) | None | `engine/combat_flavor.py` (new) | Small-Medium |
| **C** | Grace Timer + Pass + pose tracking (Sec 2–3) | Drop A, Drop B | `parser/combat_commands.py`, `engine/combat.py` | Medium |
| **D** | Action Log flush (Sec 6) | Drop C | `parser/combat_commands.py` | Medium |
| **E** | Web client pose extensions (Sec 8) | Drop D, existing Drop 8 | `engine/combat.py`, `static/client.html` | Small |

Drop B (FLAVOR_MATRIX) has zero dependencies and can be built anytime. Drop A needs the
ANSI formatting from the existing doc's Drop 3 since briefings use the same wound color
scheme. Drops C and D are the critical path — they wire the posing loop together.

---

## Files Touched

- `engine/combat.py` — `build_private_briefing()`, `_pose_state`, pose status methods
- `engine/combat_flavor.py` — **NEW:** FLAVOR_MATRIX, `generate_auto_pose()`, WOUND_FLAVOR
- `parser/combat_commands.py` — `_pose_grace_timer()`, `pass` handler, `_flush_action_log()`
- `engine/combat.py` / `static/client.html` — `to_hud_dict()` extensions (Drop E)

---

*End of document.*
*Opus session, April 9, 2026.*
