# SW_MUSH — Combat Mechanics Display Design (v1.1)

**Version:** 1.1
**Generated:** April 27, 2026
**Anchor commit:** `9723a70` ("next2", Apr 26 2026)
**Status:** ✅ READY TO IMPLEMENT — folds in Claude Design's `SW_MUSH UI_UX.html` review modifications
**Supersedes:** `combat_mechanics_display_design_v1.md` (kept in project knowledge for review-trail traceability)
**Roadmap slot:** Drop D′, Priority A1 (Field Kit). When this lands, A1 closes ✅ (alongside Drop B′, which is implementation-complete in working directory).
**Effort estimate:** ~14 hours (revised down from v1's ~17 because per-die explosion chain data already exists in `engine/dice.py` and doesn't need new plumbing).

---

## 1. One-paragraph summary

Combat resolution in `engine/combat.py` already computes every die roll, every modifier, every Wild Die explosion chain, every soak total, and every difficulty delta — but only emits a two-line ANSI text rendering for the pose log. Drop D′ adds a structured **`combat_resolution_event`** WebSocket message carrying the full mechanics breakdown, rendered by the web client as a collapsible inspector panel attached to each combat outcome row. Telnet output is unchanged; the existing two-line story+mechanics narrative continues unmodified for telnet sessions.

---

## 2. Provenance & changes from v1

This is v1.1. What changed since v1:

| # | Source | Change |
|---|---|---|
| 1 | Claude Design Q2 modification | Added per-die `source` tag (one-field flat enum, not a nested grouping) so FP-doubled and weapon dice render as visually distinct groups without bloating the wire payload. |
| 2 | Claude Design schema-gap finding | Added `stun_unconscious: bool` and `stun_duration_dice` / `stun_duration_unit` fields to `wound_outcome` so the "more serious than stunned → unconscious for 2D" routing at `engine/combat.py:1186` can be expressed end-to-end (the v1 `wound_outcome` shape couldn't carry it). |
| 3 | Claude Design Q4 modification | Telnet `/verbose` toggle removed entirely — not deferred-as-future-candidate, not stubbed. If admin debug needs richer telnet data, that's a separate `@combat/debug` admin command, not a player-facing toggle. Telnet stays at the two-line output forever. |
| 4 | Effort revision | Estimate down from ~17 hrs to ~14 hrs. Reason: `RollResult.wild_die.rolls: list[int]` and `WildDieResult.exploded: bool` already exist (`engine/dice.py:97-106`). The "wire per-die explosion chain through the dice engine" line item collapses from ~1.5 hrs to <30 min — the data was already there in v1, just not reflected in v1's effort table. |
| 5 | Q1, Q3, Q5, Q6 | Confirmed without modification. Q6 wording nudge ("relax" → "refine") was applied to architecture v37 §33.1 separately. |

**v1 sections preserved verbatim:** §1 (summary), §3 (web-first context), §11 (visibility rules), §12 (effort breakdown structure). v1.1 reorganizes around the schema modifications; no v1 design intent is dropped except the deferred-`/verbose` line item.

---

## 3. Why this exists

### 3.1 The original constraint

Pre-v37, combat output was a two-line ANSI rendering optimized for telnet:

```
  ▸ Tundra blasts Yenn with blaster — HIT — Wounded!
    (Roll: 17 vs 11 · Damage 14 vs Soak 8 → Wounded)
```

This is good telnet UX. Anything more verbose was rejected as spammy text — and on a 80×24 terminal that's correct.

### 3.2 What the §33 web-first directive changes

Per architecture v37 §33 (formalized in v37, was v36 §31), new features may be designed for the web client first; telnet compatibility is no longer a hard constraint requiring text-only fidelity. The web client can render information the telnet rendering cannot — collapsible inspectors, color groupings, hover tooltips — without violating the §18.16 invariant that mechanic resolution remain identical on both transports. The math is the same; the *display* of the math can be richer on the web.

### 3.3 What "the data is already there" means

`engine/combat.py` already computes:
- Per-die values for the attacker's pool (`attack_roll.normal_dice`, `attack_roll.wild_die.rolls`)
- Wild Die explosion chain (when `attack_roll.wild_die.exploded == True`, `rolls` is the full chain `[6, 5, 2]` etc.)
- Complication state (`attack_roll.complication`, `attack_roll.removed_die`)
- Defender pool with the same structure for opposed rolls
- Damage roll structure
- Soak total + breakdown (armor, strength, character-point soak with individual rolls)
- Force Point doubling state (`actor.force_point_active`)
- Final wound outcome (margin, wound name, stun routing)
- Difficulty number / opposed total

The two-line text rendering throws ~80% of this away. v1's design is "stop discarding it." v1.1 keeps that intent and tightens the wire-format details around three points where the v1 schema was either ambiguous or wrong.

---

## 4. Schema — `combat_resolution_event`

**Top-level message type:** `combat_resolution_event` (Q1 confirmed: new top-level WebSocket type, **not** an extension of `pose_event`). Reason: pose events represent in-room narration that's potentially seen by everyone; combat resolution events have role-aware visibility rules (§5) and a different payload shape that doesn't share fields with `pose_event`. Forcing them into one message type would mean `pose_event` consumers have to type-discriminate inside the handler, which is the wrong factoring.

**Wire shape (TypeScript-style for clarity):**

```typescript
interface CombatResolutionEvent {
  // ─── Discriminator ───
  msg_type: "combat_resolution_event";
  schema_version: 1;        // bump on breaking change

  // ─── Event identity ───
  event_id: string;         // UUID4, stable for client-side dedup
  timestamp_ms: number;     // wall-clock ms epoch
  round_num: number;        // 0 for non-combat-round events
  combat_id: number | null; // FK to combat_states.id, null if ad-hoc

  // ─── Actor / target ───
  actor: {
    id: number;            // character_id or npc_id
    name: string;
    kind: "pc" | "npc";
    is_force_point_active: boolean;
  };
  target: {
    id: number | null;     // null for AoE / environmental
    name: string;
    kind: "pc" | "npc" | "object" | "environment";
  } | null;

  // ─── Action descriptor ───
  action: {
    skill: string;          // e.g. "blaster", "brawling", "lightsaber"
    weapon_name: string | null;  // null for unarmed
    range_band: "close" | "short" | "medium" | "long" | null;
    stun_mode: boolean;     // weapon set-to-stun for this exchange
    is_opposed: boolean;    // melee vs dodge → true; ranged vs static → false
  };

  // ─── Attacker roll (THE big one — Q2 mod here) ───
  attacker_pool: DicePoolRoll;

  // ─── Defender roll (only present when is_opposed=true) ───
  defender_pool: DicePoolRoll | null;

  // ─── Difficulty (only when is_opposed=false) ───
  difficulty: {
    number: number;        // e.g. 11 for "Moderate"
    label: string;         // e.g. "Moderate"
    breakdown: Array<{ name: string; mod: number }>;
                           // [{name:"range", mod:5}, {name:"cover", mod:3}, ...]
  } | null;

  // ─── Damage roll (only on hit) ───
  damage_pool: DicePoolRoll | null;

  // ─── Soak (only on hit) ───
  soak: {
    total: number;
    components: Array<{
      source: "strength" | "armor" | "cp_soak" | "shield";
      label: string;       // human-readable, e.g. "Armor (Padded Vest)"
      value: number;       // contribution to total
      rolls: number[] | null;  // null if it's a flat value (armor)
    }>;
  } | null;

  // ─── Outcome resolution ───
  hit: boolean;
  margin: number;          // attack_total − difficulty (or − defender_total)
  damage_margin: number;   // damage_total − soak_total (when hit)
  wound_outcome: WoundOutcome;
}

interface DicePoolRoll {
  pool_text: string;        // "5D+2"
  pool_dice: number;        // 5
  pool_pips: number;        // 2
  total: number;            // final summed total

  // Per-die breakdown (Q2 modification — see §4.1)
  dice: Array<{
    value: number;          // face value (or chain-final for explosions)
    is_wild: boolean;
    exploded: boolean;      // true if Wild Die exploded
    explosion_chain: number[] | null;  // [6, 5, 2] etc. — only when exploded
    source: "skill" | "weapon" | "modifier" | "fp_double";  // Q2 mod
    dropped: boolean;       // true if removed by complication
  }>;

  pips_added: number;       // flat additive (matches pool_pips, but explicit)

  // Wild-die status (mirrors RollResult.complication / .exploded for convenience)
  complication: boolean;
  exploded: boolean;
  removed_die_value: number | null;   // RollResult.removed_die

  // Optional overlay for character-point spending
  cp_spent: number;         // 0 if none
  cp_rolls: number[];       // empty if cp_spent==0
  cp_bonus: number;         // total contribution from CP dice
}

interface WoundOutcome {
  // The four mutually-exclusive paths the engine routes to
  outcome_type: "no_damage" | "wound" | "stun" | "stun_unconscious" | "incapacitated";

  // Display label — what the existing two-line text shows in the wound slot
  display_name: string;     // "Wounded", "Stunned", "Stunned — Unconscious!", etc.

  // Wound-track delta (when outcome_type ∈ {wound, incapacitated})
  wound_level_before: string | null;  // "Healthy", "Stunned", ...
  wound_level_after: string | null;
  wound_level_delta: number;          // positive = worsened

  // Stun routing details (THE schema gap fix — see §4.2)
  // Populated when outcome_type ∈ {stun, stun_unconscious}
  stun_only: boolean;       // true when stun damage applied as wound, no KO
  stun_unconscious: boolean;            // true ONLY when KO routing fired
  stun_duration_dice: string | null;    // "2D" — null if not unconscious
  stun_duration_unit: "rounds" | "minutes" | null;  // see §11 open question

  // Drama text the engine already produces (kept available for clients
  // that want to render it inline rather than as separate pose_event)
  drama_text: string | null;
}
```

### 4.1 Q2 modification — per-die `source` tag (in detail)

The original v1 design had `dice: Array<{value, is_wild, exploded_to, mishap}>` — a flat list with no provenance. Claude Design's prototype demonstrated that without source tagging, the inspector can't visually group dice that came from different parts of the pool, which is the most common UX question players ask ("which dice were the weapon damage?").

The v1.1 schema adds a single `source` enum field per die object. Four values:

| value | meaning | example |
|---|---|---|
| `"skill"` | Came from the actor's skill rating | `attacker.combat_skills["blaster"] == DicePool(4, 0)` → 4 dice of source="skill" |
| `"weapon"` | Came from the weapon's bonus dice | weapon.bonus_dice == DicePool(2, 0) → 2 dice of source="weapon" (only relevant for damage_pool) |
| `"modifier"` | Came from a situational modifier roll-add (rare; most modifiers are flat pip adjustments) | tactical bonus, terrain bonus, etc. |
| `"fp_double"` | Came from Force Point doubling | When `actor.force_point_active`, the attacker's pre-bonus pool is rolled twice; the duplicate dice carry `source="fp_double"` |

**Why a single string field, not a nested grouping?** Wire size and parser simplicity. Grouped representation (`{skill: [...], weapon: [...], fp_double: [...]}`) makes the per-die explosion chain awkward to express (does the chain belong to the group or to the individual die?), and the client renderer ends up having to flatten anyway for ordered display. The flat `dice` array with a `source` field gives the renderer everything it needs to group visually (`groupBy(dice, 'source')`) without imposing a rigid structure on the wire format.

**Implementation note for the engine side:** The current `RollResult.normal_dice: list[int]` doesn't carry source provenance — the dice engine just sums them. The provenance is composed at the call site in `engine/combat.py` where the pool is built. The proposed approach (Drop D′ §6) is to construct the per-die `source` list at *emission* time inside combat.py, not to thread provenance through `RollResult`. This avoids touching the dice engine API and keeps the change localized.

### 4.2 Stun-mode schema gap (in detail)

The v1 `wound_outcome` shape had:
```
stun_only: bool     // true = damage applied as a stun-track wound
```

This couldn't represent the third possible routing in `engine/combat.py:1186`:

```python
# v22 audit #11: stun damage routing per R&E p83
# "Weapons set for stun roll damage normally, but treat any result
#  more serious than 'stunned' as 'unconscious for 2D minutes.'"
stun_knocked_out = False
if action.stun_mode and damage_margin > 3:
    # Margin > 3 would normally be wounded or worse;
    # stun caps it at "unconscious for 2D minutes"
    stun_knocked_out = True
    target.apply_wound(1)  # Apply a stun (margin 1 = stunned)
    wound_text = "Stunned — Unconscious!"
elif damage_margin > 0:
    wound = target.apply_wound(damage_margin)
    wound_text = wound.display_name
else:
    wound_text = "No Damage"
```

There are **three** stun-mode outcomes the engine actually emits:
1. `stun_mode==True` and `damage_margin <= 0` → no damage (handled by the falsy `damage_margin` branch)
2. `stun_mode==True` and `0 < damage_margin <= 3` → applied as stun-track wound (the v1 `stun_only:true` case)
3. `stun_mode==True` and `damage_margin > 3` → "Stunned — Unconscious!" knockout (the missing case)

v1.1 expresses all three by promoting the resolution to an `outcome_type` enum:

```typescript
outcome_type: "no_damage" | "wound" | "stun" | "stun_unconscious" | "incapacitated"
```

Plus the pair `stun_unconscious: bool` and `stun_duration_dice: "2D"` in the wound_outcome (only populated when `outcome_type == "stun_unconscious"`). This lets the inspector render the stun-knockout case correctly: "Stunned — Unconscious for 2D minutes" with the duration roll inline if/when the engine starts emitting the duration roll itself.

**Note on stun duration:** The engine currently emits the descriptive label "Stunned — Unconscious!" but does **not** roll the 2D duration or apply a timed unconscious state. That is a pre-existing engine gap, not something Drop D′ fixes; the schema reserves the `stun_duration_dice` field so when the engine does start rolling the duration, the wire format already accommodates it. See §11 for the WEG-fidelity question on rounds-vs-minutes that should be settled before that engine work happens.

---

## 5. Visibility rules (Q3 confirmed)

| Viewer | Default state |
|---|---|
| Actor (the one rolling) | Inspector **expanded** by default |
| Target (the one being rolled at) | Inspector **expanded** by default |
| Bystander (anyone else in the room) | Inspector **collapsed** by default |

Rationale: actor and target both have a stake in understanding what just happened. Bystanders get the two-line story+mechanics row but don't get the inspector pre-opened — they can click to expand if they want detail. This keeps the pose log scannable in busy combat rooms with multiple PCs.

The visibility decision is made **client-side** by comparing `event.actor.id` and `event.target.id` against the local session's `character.id`. The wire payload is identical for all viewers; only the default UI state differs.

**Server-side privacy:** The full `combat_resolution_event` is broadcast to everyone in the room (just like the existing two-line text). Rationale: the existing telnet text already shows both rolls and totals to bystanders, so suppressing them in the structured event would be a net *reduction* in visible information. There is no asymmetric-information layer in WEG D6 combat to preserve; the system is open-information by design.

---

## 6. Engine emission point

Single emission site: `engine/combat.py` resolve loop, immediately after the existing two-line narrative is composed (currently around line 1218 where `narrative = story_line + "\n" + mech_line` is built).

```python
# After narrative composition, before broadcasting:
from engine.combat_events import build_combat_resolution_event
combat_event = build_combat_resolution_event(
    actor=actor, target=target, action=action,
    attack_roll=attack_roll, defender_roll=defender_roll,
    damage_roll=damage_roll, soak_total=soak_total, soak_components=soak_components,
    wound_text=wound_text, wound_level_before=wound_level_before,
    wound_level_after=target.wound_level.name,
    stun_knocked_out=stun_knocked_out,
    round_num=self.round_num, combat_id=self.combat_id,
)
await session_mgr.broadcast_json_to_room(
    room.id, "combat_resolution_event", combat_event,
)
# Existing two-line text broadcast continues unchanged for telnet:
await session_mgr.broadcast_to_room(room.id, narrative)
```

The new builder lives in a new module `engine/combat_events.py` (≈250-350 lines) following the same factory pattern as `engine/pose_events.py`. Keeping it out of `combat.py` itself preserves the resolve loop's readability and gives Drop D′ a clean unit-test surface separate from the combat resolver.

**Per-die source list construction:** `build_combat_resolution_event` is the only place that needs to know that the first N dice of `attack_roll.normal_dice` came from skill, the next M from FP doubling, etc. The combat resolver already constructs the pool by composition (skill + weapon-bonus + FP-double, with explicit knowledge of each component's size), so the source list is a straightforward zip operation at this layer. No changes required to `engine/dice.py`.

---

## 7. Client rendering

### 7.1 Dispatch

Add a new case to the WebSocket message router at `static/client.html:6162` (alongside the existing `pose_event` case):

```javascript
case 'combat_resolution_event':
  handleCombatResolutionEvent(msg);
  return;
```

### 7.2 Handler (`handleCombatResolutionEvent`)

Renders a new pose-log row of type `combat-result`. The row contains:

1. **Header line** — same content as the existing two-line story line: `Tundra blasts Yenn with blaster — HIT — Wounded!`
2. **Mechanics line** — same content as the existing dim mechanics line: `(Roll: 17 vs 11 · Damage 14 vs Soak 8 → Wounded)`
3. **Inspector toggle** — chevron button. Default state per §5 visibility rules.
4. **Inspector body** (collapsible) — the structured breakdown:
   - Attacker pool, dice grouped by `source`, Wild Die highlighted, explosion chain shown inline (`W: 6→5→2 = 13`)
   - Defender pool (if opposed) or difficulty breakdown (if static target)
   - Damage pool (if hit), dice grouped by source
   - Soak components, each with rolls if rolled, flat value if armor
   - Wound outcome, with stun routing detail when applicable
   - CP spent (if any) on either side, with rolls

### 7.3 Pose-log integration

The new `combat-result` row type registers with the existing pose-log infrastructure (`appendEvent`). It does **not** go through `classifyAndAppend`'s regex fallback — it's a typed event, just like `pose_event`. This means it does not need to be defended against the legacy say/whisper regex misfires that motivated Drop B.

**Backward compat:** If the server emits the existing two-line narrative *and* the new `combat_resolution_event`, the client will receive both. The client suppresses the redundant two-line narrative when a `combat_resolution_event` for the same `event_id` arrived in the prior 250ms window (same dedup pattern as Drop B's `pose_event` dedup). This means:
- Telnet sessions get the existing two-line text (unchanged behavior)
- WebSocket sessions get the structured event and suppress the duplicate narrative

The dedup logic lives client-side. The engine emits both unconditionally; the client decides what to render based on transport.

---

## 8. Telnet behavior (Q4 mod: defer `/verbose` entirely)

**Telnet sessions get the existing two-line narrative. Period.**

v1 left a future-candidate `+combat/verbose on` toggle in scope-but-deferred state. v1.1 removes that line item. Reasons:

1. **Two clients to maintain is already the cost of the web-first directive.** Adding a third "telnet-but-verbose" rendering path multiplies the maintenance surface for a feature whose core motivation (web-first richer display) doesn't apply to telnet.
2. **The telnet two-line format is a deliberate UX choice**, not a limitation. Even with infinite vertical space, a telnet pose log full of mechanics breakdowns would be unreadable — the two-line story+mechanics format is what telnet players actually want.
3. **Admin debug needs are a different problem.** If an admin wants the full mechanics breakdown for debugging a combat, that's an `@combat/debug` command (admin-only, on-demand, dumps last N events for a combat_id). Not a player-facing toggle. Out of scope for Drop D′.

If a future drop wants to add an admin debug command, that's its own design ticket. Drop D′ does not stub it, gate for it, or reserve schema fields for it.

---

## 9. The four payload archetypes

Per Claude Design's prototype (`SW_MUSH UI_UX.html`), the inspector is exercised against four canonical archetypes. v1.1 adds a fifth (melee opposed) per architecture v37 §34.5 action item 3:

| # | Archetype | Why it's interesting |
|---|---|---|
| 1 | Ranged hit with Wild Die explosion | Tests the per-die explosion chain rendering and the per-die source grouping for skill+weapon+modifier dice |
| 2 | Ranged miss | Tests the `hit:false` short-circuit (no damage_pool, no soak, no wound_outcome details) |
| 3 | Melee mishap (Wild Die complication) | Tests `complication:true`, `removed_die_value`, the dropped-die styling, and the static-difficulty branch |
| 4 | Space combat with Force Point | Tests the `fp_double` per-die source group rendering and the `is_force_point_active:true` actor decoration |
| 5 (v1.1 addition) | Melee opposed | Tests the `is_opposed:true` branch with both `attacker_pool` and `defender_pool` populated, and the margin computation against `defender_pool.total` rather than a static `difficulty.number` |

The acceptance criteria require at least one regression test per archetype; the test fixture data lives in `tests/fixtures/combat_resolution_events/`.

---

## 10. Implementation work breakdown (~14 hours)

| # | Task | Hours | Files |
|---|---|---|---|
| 1 | New module `engine/combat_events.py` with `build_combat_resolution_event()` factory | 3.5 | engine/combat_events.py (new, ~300 lines) |
| 2 | Engine emission wiring in `engine/combat.py` resolve loop (single call after narrative composition) | 1.5 | engine/combat.py |
| 3 | Per-die source list construction (zip skill+weapon+modifier+fp_double pool components) | 1.0 | engine/combat_events.py |
| 4 | Soak component breakdown (extract strength/armor/cp_soak/shield contributions) | 1.0 | engine/combat_events.py + engine/combat.py refactor of soak total to track components |
| 5 | Stun-mode schema population (5-way `outcome_type` enum routing) | 0.5 | engine/combat_events.py |
| 6 | WebSocket dispatch case in client | 0.25 | static/client.html (~6162) |
| 7 | `handleCombatResolutionEvent` + inspector panel HTML/CSS | 4.0 | static/client.html (new ~600-line block) |
| 8 | Per-die source visual grouping (skill/weapon/fp_double color tokens, hover labels) | 1.5 | static/client.html + tokens reference |
| 9 | Bystander-collapsed default visibility logic | 0.25 | static/client.html (handleCombatResolutionEvent) |
| 10 | Tests: 5 archetype fixtures + 5 schema-validation tests + visibility-rule tests | 1.5 | tests/test_field_kit_drop_d_prime.py (new) |
| | **Total** | **~14 hrs** | |

The estimate is conservative on the client-side rendering (item 7) and aggressive on the engine factory (items 1, 3, 4) because the dice engine's existing structure carries most of the heavy lifting.

---

## 11. Open WEG-fidelity question — stun duration units

This question must be settled before the engine starts populating `stun_duration_dice` and `stun_duration_unit`. **It does not block Drop D′ implementation** because v1.1 reserves the schema fields without requiring engine population — the inspector will simply omit the duration line if the fields are null.

The contradiction:

- `engine/combat.py:1183` comment quotes R&E p83 as: *"treat any result more serious than 'stunned' as 'unconscious for 2D **minutes**.'"*
- Architecture v37 §34.4 footnote claims: *"R&E specifies **rounds**."*
- The two cannot both be right, and the engine currently doesn't roll the duration at all (just emits the label "Stunned — Unconscious!").

**Resolution path** (separate ticket, not Drop D′ scope):
1. Re-verify R&E p83 wording against a clean copy of the rulebook.
2. Update the engine comment if needed.
3. Add the actual 2D roll + timed-unconscious state in a separate engine drop (one of the open D Phase 3 items — see architecture v37 §19.4 row "D Phase 3").
4. The schema's `stun_duration_unit: "rounds" | "minutes" | null` accommodates either resolution.

---

## 12. Acceptance criteria

Drop D′ is ✅ DELIVERED when all 14 items below pass. Items 1–9 are functional; 10–14 are quality-gate.

- [ ] **AC1** — `engine/combat_events.py` module exists with `build_combat_resolution_event()` returning a dict matching the v1.1 schema in §4.
- [ ] **AC2** — `engine/combat.py` resolve loop calls `build_combat_resolution_event()` and broadcasts via `session_mgr.broadcast_json_to_room(..., "combat_resolution_event", ...)` immediately after the existing two-line narrative is composed.
- [ ] **AC3** — Telnet output for combat is **byte-identical** to pre-Drop-D′ output (the existing two-line story+mechanics narrative, no new lines, no new ANSI).
- [ ] **AC4** — Web client dispatches `combat_resolution_event` messages to `handleCombatResolutionEvent` at `static/client.html:6162` (or the post-Drop-B′ equivalent line).
- [ ] **AC5** — Inspector panel renders for all 5 archetypes (§9) with attacker pool, defender pool / difficulty, damage pool (if hit), soak components, wound outcome, and any CP spending.
- [ ] **AC6** — Per-die source grouping renders skill / weapon / modifier / fp_double dice with visually distinct treatment (color or border).
- [ ] **AC7** — Wild Die explosion chain renders inline as `W: 6→5→2 = 13` for the exploded case; as `W: 1!` for the complication case; as `W: 4` for the normal case.
- [ ] **AC8** — Stun-mode KO routing (`outcome_type == "stun_unconscious"`) renders "Stunned — Unconscious!" plus a placeholder for the future 2D duration roll (which will populate when the separate engine drop adds it; v1.1 schema reserves the field but the engine emits null).
- [ ] **AC9** — Visibility rule: actor and target see the inspector pre-expanded; bystanders see it collapsed. Verified by spawning a bystander session in the same room and inspecting the rendered DOM.
- [ ] **AC10** — Web client suppresses the redundant two-line narrative when a `combat_resolution_event` for the same `event_id` arrives within the prior 250ms window.
- [ ] **AC11** — At least one regression test per archetype (5 total) verifying the wire payload structure against a fixture.
- [ ] **AC12** — Schema-validation tests verifying that all required fields are populated for each `outcome_type` branch (e.g., `damage_pool` is non-null when `hit:true`, `defender_pool` is non-null when `is_opposed:true`, `stun_unconscious` is true only when `outcome_type == "stun_unconscious"`).
- [ ] **AC13** — `+combat/verbose` is **not** added to telnet command parser. Search `parser/` for `verbose` returns no new matches added by Drop D′.
- [ ] **AC14** — `engine/dice.py` is **not modified**. The per-die source provenance is composed at the combat-events factory layer, not threaded through the dice engine.

---

## 13. References

| Source | Used for |
|---|---|
| `combat_mechanics_display_design_v1.md` (project knowledge — superseded; preserved for review trail) | The v1 baseline this revises |
| `SW_MUSH UI_UX.html` (project knowledge) | Claude Design's review package — verdict, Q1–Q6 answer cards, prototype, schema convergence |
| `field_kit_design_decomposition_v2.md` §10 | A1 closure criteria (B′ + D′ both land) |
| `field_kit_open_questions_v1_1.md` §D5 | Dedup-key pattern reused for the 250ms suppression window |
| `sw_d6_mush_architecture_v37_consolidated.md` §34 | Drop D′ summary, Claude Design review outcome, action items |
| `sw_d6_mush_architecture_v37_consolidated.md` §33 | Web-first directive context |
| `sw_d6_mush_architecture_v37_consolidated.md` §18.16 | Dual-Interface invariant (mechanic resolution identical on both transports) |
| `engine/dice.py:96-118` | `WildDieResult` and `RollResult` shapes |
| `engine/combat.py:1186` | Stun-mode routing (the source of the schema-gap finding) |
| `engine/pose_events.py` | Factory pattern to mirror in `engine/combat_events.py` |
| `static/client.html:6162` | Dispatch site for the new message type |
| WEG D6 R&E p83 (sourcebook) | Stun damage rules — pending units verification (§11) |

---

## 14. What's next after this design lands

1. Brian / Claude reviews v1.1 (this document). Approve, request edits, or push back on a specific schema decision.
2. Once approved: Drop D′ implementation queues. Per architecture v37 §19.7, this is the next engine-lane item after Drop B′ (which is already implementation-complete in the working directory and just needs to be committed).
3. When Drop D′ ships ✅, **Priority A1 closes** — the longest-running engine-lane priority since v32 is done.
4. Engine lane then opens up for F.0 (world data loader integration), the single highest-leverage unblocker for the entire Clone Wars era pivot.

---

**End of v1.1.**
