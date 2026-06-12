# SW_MUSH — Field Kit Design Implementation Decomposition v2

**Version:** 2.0
**Generated:** April 25, 2026 (supersedes v1 of April 24, 2026)
**Source materials:** `field_kit_audit_and_remediation_v1.md` + `SW_MUSH_UIUX_3.zip / drop_v2/` (Field Kit Prototype v2) + `field_kit_open_questions_v1_1.md` (D1–D5 resolutions)
**Architecture target:** v33 §16F (Priority A1)
**Status:** 🟦 In flight — implementation decomposed into **6 drops** (5 + Drop B′), ~29–41 hours total

**Changes from v1 (per `field_kit_open_questions_v1_1.md`):**
- F7 (StanceChip) removed from scope — not a WEG D6 R&E mechanic
- Drop B split into Drop B (NPC/Director/system narration) + Drop B′ (player command narration)
- `pose_event` deduplication key formally specified as `speaker_id:timestamp_ms:text_hash[:8]`, 250ms client window
- Drop D server-side prerequisite added: `combat_state.theatre` field

---

## 1. Purpose of this document

The Field Kit Prototype v2 package is a working React/JSX prototype demonstrating 13 specific UI/UX fixes for the SW_MUSH web client (originally 14; F7 removed per WEG fidelity — see `field_kit_open_questions_v1_1.md` §D1). **The prototype is not the deliverable.** The deliverable is integration of those fixes into the live `static/client.html`.

This document decomposes that integration into 6 sequential drops with concrete integration points, file deltas, and acceptance criteria for each. It is the spec the development queue works from.

---

## 2. The Prototype Package

```
drop_v2/
├── Field Kit Prototype v2.html      (402 lines — wrapper, mode toggle, demo apps)
└── prototype/
    ├── tokens.jsx                   (178 lines — tokens, hooks, shared primitives)
    ├── pose-log.jsx                 (218 lines — unified pose log)
    ├── combat-hud.jsx               (341 lines — phase-aware space combat HUD)
    ├── ground-combat-hud.jsx        (266 lines — amber-themed ground combat HUD)
    ├── ground.jsx                   (506 lines — interactive datapad)
    └── space.jsx                    (496 lines — interactive cockpit)
```

**Three demonstration modes** (toggle in HTML wrapper):
- **GROUND** — Datapad UI with amber palette (`padShell` token family)
- **GROUND · COMBAT** — Combat HUD overlaid on datapad
- **SPACE · COCKPIT** — Cockpit UI with cyan palette (`cockMetal` token family)

**The 13 findings resolved:**

| # | Finding | Prototype evidence |
|---|---|---|
| F1 | Wound ladder needed all 7 levels | `tokens.jsx:29` `WOUND_RUNGS` array |
| F2 | DODGE / FULL DODGE split | `combat-hud.jsx:11` (declaration panel two buttons) |
| F3 | Posing panel command was wrong | `combat-hud.jsx:13` (instructs `cpose`) |
| F4 | Removed nonexistent `fullDefense` | (negative finding — not in prototype) |
| F5 | FP dots overflowed when fp > fpMax | `ground.jsx:5` (FP clamp) |
| F6 | Ground combat HUD didn't exist | `ground-combat-hud.jsx` (whole new file) |
| F8 | Stun cap was hardcoded 3 | `tokens.jsx:55` `stunCap(strengthDice)` |
| F9 | Shield slots hardcoded 3 | `space.jsx:5` (shieldForeMax/AftMax) |
| F10 | Wound ladder penalty text misaligned | `ground.jsx:10` (right-aligned) |
| F11 | Target condition rendered without color | `space.jsx:7` (`conditionColor()`) |
| F13 | Conditions SHOUT-CASE while engine returns title-case | `tokens.jsx:62` `CONDITION_COLORS` |
| F14 | Pose window timer hardcoded | `combat-hud.jsx:14` (180s default) |
| F15 | Ship UI implied "wound levels" | `space.jsx:9` (cleanup) |

**F7 removed from scope.** Per `field_kit_open_questions_v1_1.md` §D1: per-round "stance" (cautious/standard/all-out) is not a WEG D6 R&E mechanic. The 8-button declaration panel (`attack`/`dodge`/`fulldodge`/`parry`/`cover`/`move`/`aim`/`pass`) already provides stance-equivalent expression through WEG's per-action declaration model. Shipping a UI-only StanceChip would either be inert or require house-rule modifiers — both depart from R&E without justification.

---

## 3. Drop A — Tokens & Shared Primitives

**Effort:** 2–3 hours
**Blocks:** Drops B, B′, C, D, E (everything depends on this)

### Scope

Port the `tokens.jsx` design tokens and shared helpers into `static/client.html` as CSS custom properties + a global `FK` JavaScript object. This is the foundation; all subsequent drops depend on it.

### Integration approach

`static/client.html` already has CSS variables and inline `<style>` blocks. Add a new dedicated section (suggest: between line 100 and line 150 in the existing CSS) that defines:

```css
:root {
  /* Datapad / ground palette */
  --pad-shell: #2a2220;
  --pad-shell-dark: #1a1412;
  --pad-bezel: #1e1815;
  --pad-screen: #14200e;
  --pad-screen-dim: #0b1408;
  --pad-amber: #ffc857;
  --pad-amber-bright: #ffe3a0;
  --pad-amber-dim: #8a6220;
  --pad-green: #7ce068;
  --pad-red: #ff6e4a;
  --pad-text: #d9b472;
  --pad-text-dim: #7a5e2e;

  /* Cockpit / space palette */
  --cock-metal: #2e3540;
  --cock-metal-dark: #1a2028;
  --cock-metal-light: #3e4855;
  --cock-screen: #04141a;
  --cock-screen-dim: #02090d;
  --cock-cyan: #6ee8ff;
  --cock-cyan-dim: #2e7080;
  --cock-amber: #ffa640;
  --cock-red: #ff5a4a;
  --cock-green: #7ce068;
  --cock-text: #bfd8e4;
  --cock-text-dim: #5a7584;
}
```

In a JavaScript section, add the helpers as a global `FK` object (the prototype already does this with `Object.assign(window, {...})`):

```javascript
const WOUND_RUNGS = [
  { v: 0, label: 'HEALTHY',     pen: '',    sev: 'ok'   },
  { v: 1, label: 'STUNNED',     pen: '',    sev: 'warn' },
  { v: 2, label: 'WOUNDED',     pen: '-1D', sev: 'warn' },
  { v: 3, label: 'WOUNDED ×2',  pen: '-2D', sev: 'hurt' },
  { v: 4, label: 'INCAP',       pen: '',    sev: 'crit' },
  { v: 5, label: 'MORTAL',      pen: '',    sev: 'crit' },
  { v: 6, label: 'DEAD',        pen: '',    sev: 'dead' },
];

function woundRung(level) { ... }
function woundColor(sev, theme = 'pad') { ... }
function stunCap(strengthDice) { ... }
const CONDITION_COLORS = { 'Pristine': ..., 'Light Damage': ..., ... };
function conditionColor(cond) { ... }
```

Copy verbatim from `tokens.jsx`. The `FK` object can stay as a JavaScript constant (no need for CSS doubling for these).

### Acceptance criteria

- ✅ All CSS custom properties from `tokens.jsx` exist in `client.html` `:root` block
- ✅ `WOUND_RUNGS` array exists in client JS scope, exposing all 7 entries
- ✅ `woundRung(level)`, `woundColor(sev, theme)`, `stunCap(strengthDice)`, `conditionColor(cond)` are callable in client JS
- ✅ Existing UI render unchanged (this drop adds primitives; subsequent drops use them)
- ✅ Browser console: `WOUND_RUNGS.length === 7`, `woundRung(3).label === 'WOUNDED ×2'`, `stunCap(4) === 4`, `conditionColor('Light Damage')` returns the expected token

---

## 4. Drop B — Pose Log Migration (server-side `pose_event`, NPC/Director/System paths)

**Effort:** 6–8 hours
**Blocks:** Drops C, D
**Absorbs:** Original `field_kit_audit_and_remediation_v1.md` Drop B (NPC/Director/system narration scope only — player commands are Drop B′)

### Scope

Migrate **NPC, Director, and system** narration emit paths to use the typed `pose_event` JSON message instead of plain text that hits the client's `classifyAndAppend` regex. This fixes the "Room says..." mis-render bug that's currently visible across ambient narration, hazard messages, NPC dialogue, and Director events.

Player commands (`say`, `pose`/`:`, `whisper`, `mutter`) are **deferred to Drop B′** (separate session, scheduled after Drop B lands). Player-issued narration is already attributed correctly today; migrating it is consistency work, not bug-fix work.

### Current state

- ✅ Already emitting typed `pose_event`: `engine/boarding.py` (lines 146, 254, 257, 412, 423), `engine/encounter_boarding.py` (lines 327–340, 602–611)
- ✅ Client consumer: `static/client.html` `handlePoseEvent` at line 4659; suppression logic at 2973, 4694
- ❌ All other narration paths still emit text-only:
  - `engine/director.py` ambient narration
  - `engine/hazards.py` hazard tick messages
  - Room broadcast messages (`engine/world.py`-equivalent paths)
  - NPC dialogue ambients (`ai/npc_brain.py` chat surface)
  - `engine/encounter_*.py` non-boarding encounters
  - `engine/combat.py` combat narration outside the existing posing panel

### Integration approach

1. **Define the canonical schema** — `engine/pose_events.py` (new file) exporting:

   ```python
   import hashlib, time

   def make_dedup_key(speaker_id: int | None, text: str, timestamp_ms: int) -> str:
       """Composite dedup key. Cheap to compute, no server-side state needed.

       Handles the actual dedup case (room broadcast + speaker self-echo
       arriving within milliseconds) without false positives on rapid-fire
       identical poses.
       """
       speaker_part = str(speaker_id) if speaker_id is not None else "system"
       text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
       return f"{speaker_part}:{timestamp_ms}:{text_hash}"

   def make_pose_event(
       speaker: str,           # NPC or PC name
       text: str,              # the narration text
       *,
       speaker_id: int | None = None,
       mode: str = 'pose',     # 'pose' | 'says' | 'whispers' | 'cpose' | 'ambient' | 'system'
       to: str | None = None,  # for whispers
       timestamp_ms: int | None = None,
       deduplication_key: str | None = None,
   ) -> dict:
       """If timestamp_ms is None, uses int(time.time() * 1000).
       If deduplication_key is None, computes composite from
       speaker_id, timestamp_ms, sha1(text)[:8]."""
       if timestamp_ms is None:
           timestamp_ms = int(time.time() * 1000)
       if deduplication_key is None:
           deduplication_key = make_dedup_key(speaker_id, text, timestamp_ms)
       return {
           "speaker": speaker,
           "speaker_id": speaker_id,
           "text": text,
           "mode": mode,
           "to": to,
           "timestamp_ms": timestamp_ms,
           "deduplication_key": deduplication_key,
       }
   ```

2. **Migrate each emit site** — replace `await ctx.session.send_line(text)` with `await ctx.session.send_json({"kind": "pose_event", **make_pose_event(...)})` for narration content (NOT for system messages, prompts, command echoes — those stay as `send_line`).

3. **Client-side dedupe discipline** — when the same `deduplication_key` arrives twice within **250ms**, suppress the second event. The prototype's `pose-log.jsx` already implements this pattern; port the logic to `client.html`'s existing `handlePoseEvent`. Outside the 250ms window, treat as a legitimate distinct event (so a player saying "hmm." three times across 800ms still renders three rows).

4. **Backward compat** — the existing `classifyAndAppend` regex stays as fallback for any path not yet migrated. Keep it during the migration; remove or deprecate only when all paths (including Drop B′ player commands) are typed.

### Migration checklist

- [ ] `engine/director.py` — ambient narration paths
- [ ] `engine/hazards.py` — hazard messages
- [ ] Room broadcast paths in `engine/`
- [ ] `ai/npc_brain.py` — NPC dialogue
- [ ] `engine/encounter_pirate.py`, `engine/encounter_anomaly.py`, `engine/encounter_patrol.py`, `engine/encounter_hunter.py`, `engine/encounter_texture.py` — non-boarding encounter narration
- [ ] `engine/combat.py` — combat narration outside the existing posing panel

**Drop B′ — Player Command Narration Migration** (separate session, scheduled after Drop B lands; ~3–4 hrs):
- [ ] `say` / `sayit` commands
- [ ] `pose` / `:` shorthand
- [ ] `whisper`
- [ ] `mutter`

Drop B′ is consistency work, not bug-fix work. Player-issued narration is already attributed correctly today; migrating is so the entire narration pipeline goes through one typed code path.

### Acceptance criteria

- ✅ `grep -rn "send_line.*\\\"says\\\"\\|send_line.*pose" engine/` returns zero remaining hits in narration paths (system/echo paths are fine)
- ✅ Director ambient events render as typed `pose_event` rows in client, not as terminal text
- ✅ Hazard tick messages render with proper attribution (no "Room says..." artifact)
- ✅ NPC dialogue ambients no longer trip the `classifyAndAppend` regex
- ✅ At least 1 regression test per migrated emit path verifies the typed JSON structure
- ✅ Client suppresses duplicate `pose_event` arrivals within 250ms of the same `deduplication_key`

---

## 5. Drop C — Ground UX (Datapad)

**Effort:** 4–5 hours *(was 5–7 in v1; F7 removal saves ~1–2 hrs)*
**Blocks:** Drop D (combat HUD inherits ground patterns)
**Reference component:** `ground.jsx`

### Scope

Apply the prototype's datapad UI patterns to the existing ground HUD in `client.html`:

- **F1** Rebuild wound-ladder render to use `WOUND_RUNGS` (all 7 entries)
- **F5** FP dots clamp at `fpMax` (no overflow)
- **F8** Stun cap uses `stunCap(character.strength.dice)` instead of hardcoded 3
- **F10** Wound ladder penalty column right-aligned with consistent width

**F7 removed from scope** per `field_kit_open_questions_v1_1.md` §D1. Stance is not a WEG mechanic; the action declaration system in Drop D already provides stance-equivalent expression.

### Integration approach

1. Locate the current wound-ladder render in `client.html` — likely in `_hud_*` rendering or a `renderWoundLadder()` function. Replace the manual `<div>` chain with a loop over `WOUND_RUNGS`.
2. Locate the FP-dots render — it currently has no clamp logic. Add `Math.min(fp, fpMax)` to the rendered count.
3. Locate the stun cap render — replace hardcoded `3` with `stunCap(character.strength?.dice ?? 3)`.
4. Apply right-alignment via existing CSS classes or new `text-align: right` rule on the penalty column.

### Acceptance criteria

- ✅ Wound ladder always renders 7 rungs (test: artificially set `wound_level: 5`, verify MORTAL row visible)
- ✅ FP dots never exceed `fpMax` (test: set `fp: 10, fpMax: 5`, verify only 5 lit dots)
- ✅ Stun cap derives from `strength.dice` (test: set `strength.dice: 5`, verify 5 stun slots render)
- ✅ Wound ladder penalty column right-aligned (visual; manual confirm)
- ✅ No StanceChip / stance-mode UI present (F7 removed per WEG fidelity)
- ✅ At least 1 integration test per F-finding

---

## 6. Drop D — Combat HUD (Both Modes)

**Effort:** 8–12 hours
**Reference components:** `combat-hud.jsx`, `ground-combat-hud.jsx`

### Scope

Build the phase-aware combat HUD for both space and ground modes:

- **F2** DODGE and FULL DODGE as separate buttons with R&E-correct tooltips
- **F3** PosingPanel instructs `cpose <text>`, notes `:` shorthand bridges to it
- **F4** No `fullDefense` button (it was never a real parser command)
- **F6** Ground combat HUD as a parallel of space combat HUD with amber palette
- **F11** Target condition rendered with color via `conditionColor()`
- **F13** Condition lookups use title-case keys
- **F14** PosingPanel timer defaults to 180s (configurable via prop)

### Integration approach

The prototype implements two complete combat HUDs (space cyan, ground amber) sharing engine logic. Port pattern:

1. **Phase pill** — Renders combat round + phase (initiative/declaration/resolution/posing/ended). Already partially implemented in client; align rendering to prototype.
2. **Declaration panel** — Two variants:
   - Space: `attack`, `dodge`, `fulldodge`, `cover`, `move`, `aim`, `pass`
   - Ground: same 7 + `parry` (melee). Both need the DODGE/FULL DODGE distinction enforced.
3. **Combatant pip list** — Uses `woundRung()` for wound state, `theme='cockpit'` for space and `theme='pad'` for ground.
4. **Posing panel** — Activated when phase enters `posing`. Instructs `cpose <text>`. Auto-stages the input field with `cpose ` prefix. Timer countdown: client computes `seconds_remaining` from server's `pose_deadline` (ISO-8601 UTC string) on each tick, defaulting render to 180s when `pose_deadline` is absent.
5. **Range chip** — Ground only. Cycles point-blank / short / medium / long.

### Server-side dependencies

- `combat_state` payload includes `pose_deadline` ✅ confirmed at `engine/combat.py:560` (ISO-8601 UTC string, not seconds-remaining; client computes countdown locally each tick).
- `combat_state.theatre` field is **NEW for v33** — must be added to `engine/combat.py:CombatInstance.to_hud_dict()` at line 471 before client integration. Set `'ground'` for parser/combat_commands paths, `'space'` for parser/space_commands resolution paths. ~30 minutes server change (15 min implementation + 15 min test).
- `cpose <text>` parser command exists ✅ confirmed at `parser/combat_commands.py`.
- `fulldodge` parser command exists ✅ confirmed at `parser/combat_commands.py`.

### Acceptance criteria

- ✅ DODGE and FULL DODGE are separate buttons, each with distinct tooltip text matching R&E
- ✅ Posing panel timer displays seconds remaining, counts down, defaults to 180s when `pose_deadline` absent
- ✅ No "fullDefense" string anywhere in `client.html` (`grep "fullDefense" static/client.html` returns 0)
- ✅ Ground combat HUD activates when `combat_state.theatre === 'ground'`
- ✅ `combat_state.theatre` field present in both ground and space combat fixtures. Tests verify `theatre == 'ground'` for ground-room combats and `theatre == 'space'` for ship-vs-ship combats.
- ✅ Target row renders condition in correct color via `conditionColor()`
- ✅ Title-case condition keys: setting condition to `"Light Damage"` colors green, `"Critical Damage"` colors red
- ✅ At least 1 integration test per F-finding (F2, F3, F4, F6, F11, F13, F14)

---

## 7. Drop E — Space Cockpit

**Effort:** 6–10 hours
**Reference component:** `space.jsx`

### Scope

Apply the cockpit UI pattern to the existing space HUD:

- **F9** Shield slots render true `shield_dice_front` / `shield_dice_rear` from `ShipInstance`, not hardcoded 3
- **F11, F13** Target condition with color (overlap with Drop D — implement once, share)
- **F15** Remove all references to ship "wound levels" (ships use conditions, not wound levels)

### Integration approach

1. **Shield arc** — Locate the current shield render. The data is already in `space_state` payload as `shield_dice_front` / `shield_dice_rear`. Replace any hardcoded slot count (`3` or similar) with the live value.
2. **Target row** — Pulls from `space_state.target` (or equivalent). Apply `conditionColor()` to the rendered condition string.
3. **Audit `client.html`** for any reference to ship wound levels:
   ```
   grep -nE "ship.*wound|wound.*ship|ship_wound_level" static/client.html
   ```
   Replace with condition-based language. The prototype's `space.jsx:9` is the reference for what to do (entire concept of ship wounds is removed; only `condition` exists).

### Acceptance criteria

- ✅ Shield arc renders correct slot count (test: ship with `shield_dice_front: 5`, verify 5 slots; ship with `shield_dice_front: 1`, verify 1 slot)
- ✅ Target condition renders with color matching `CONDITION_COLORS` lookup
- ✅ `grep -nE "ship.*wound|wound.*ship" static/client.html` returns 0 hits
- ✅ At least 1 integration test per F-finding (F9, F15)

---

## 8. Cross-Drop Engineering Notes

### 8.1 Test discipline

Every drop adds tests under `tests/test_field_kit_integration.py` (new file) or extends existing UI integration tests. Each F-finding gets at least one test that proves the specific change is in place. The acceptance signal for Priority A1 complete is: 13 tests, 1 per F-finding, all green.

### 8.2 Migration order rationale

A → B before C/D because the pose-log migration is a server-side change that affects all narration; doing it after the ground/combat work would mean re-doing the integration touch points. C before D because the combat HUD inherits the ground HUD's wound-ladder and stance patterns. E is last because cockpit is the most independent surface. B′ runs after Drop B but otherwise independent of C/D/E ordering.

### 8.3 Backward compatibility

During Drop B migration, the existing `classifyAndAppend` regex stays in place as fallback. Old text-only narration paths still render; they just look like terminal text instead of typed pose-events. As migration progresses, more rows render through the typed path. Only when 100% of narration is typed (i.e., Drop B′ complete too) should `classifyAndAppend` be deprecated.

### 8.4 No JSX in production

The prototype is JSX (Babel-compiled in-browser). The live `static/client.html` is plain JavaScript. Port patterns, not JSX syntax. Use `document.createElement` / template literals / existing render functions in `client.html` rather than introducing a Babel build step.

### 8.5 CSS variable namespace

The prototype's tokens use `padShell`, `cockMetal`, etc. as JS constants. In CSS, prefix all custom properties with `--pad-` or `--cock-` to avoid collisions with existing CSS variables. The prototype's `conditionColor()` returns hex; in `client.html`, the equivalent helper can return the CSS var string directly (`var(--cock-amber)`) for consistency.

### 8.6 WEG fidelity invariant

UI features must correspond to a WEG D6 R&E mechanic or a documented house rule with explicit reasoning. The prototype's `StanceChip` (F7) was removed from scope because per-round stance is not a WEG mechanic and the action declaration system already provides stance-equivalent expression. This invariant applies to all future Field Kit additions. See `field_kit_open_questions_v1_1.md` §D1 for the full rationale.

### 8.7 What's NOT in scope for Priority A1

- Mobile responsive overhaul (Priority E in v33 §19)
- Onboarding overlay (Priority E in v33 §19, Priority 6 of `web_ux_competitive_analysis.md`)
- Notification center expansion (Priority K in v33 §19)
- Field Kit prototype's debug injector or sample-event generator — those are dev tools, not production UI
- F7 StanceChip — removed per WEG fidelity (D1)

These remain on their respective roadmap priorities (or are explicitly out of scope).

---

## 9. Acceptance Signal — Priority A1 Complete

Priority A1 in v33 §19 marks ✅ DELIVERED when:

1. ✅ All 13 F-findings have a confirmed code change in `static/client.html` traceable to the prototype's resolution pattern
2. ✅ `pose_event` is emitted from all narration paths covered by Drop B (boarding ✅, plus Director ambient, room broadcasts, hazard messages, NPC dialogue ambients, non-boarding encounters, combat narration outside posing)
3. ✅ `tests/test_field_kit_integration.py` exists with at least 1 test per F-finding, traceable through symbol-grep
4. ✅ `grep "fullDefense" static/client.html` returns 0
5. ✅ `grep -nE "ship.*wound|wound.*ship" static/client.html` returns 0
6. ✅ `grep -E "StanceChip|stance.*chip|stance_chip" static/client.html` returns 0 (F7 removed per WEG fidelity)
7. ✅ Wound ladder renders all 7 levels (manually confirmed via test character at each level)
8. ✅ Ground combat HUD activates appropriately when `combat_state.theatre === 'ground'`
9. ✅ Posing panel countdown timer functional, defaults to 180s when `pose_deadline` absent
10. ✅ `combat_state.theatre` field present and asserted in tests for both ground and space combat instances
11. ✅ Updated `userMemories` to reflect Field Kit Design fully implemented
12. ✅ v33 §16F status updated to ✅ DELIVERED, §25 row updated

Drop B′ (player command narration migration) ships separately and is **not gating** for Priority A1 closure. When B′ lands:

- ✅ Player `say`, `pose`/`:`, `whisper`, `mutter` all emit typed `pose_event`
- ✅ `classifyAndAppend` fallback regex can be deprecated (or kept indefinitely as defense in depth)

---

## 10. Drop Sequencing Recommendation

For the development queue:

1. **Drop A first.** Smallest, mechanical, fastest. Land it, verify the helpers work in browser console, move on. Apply v1.1 doc edits during this drop.
2. **Drop B second.** Largest single drop. Touches multiple engine files. Land it as its own session because it has the most regression risk.
3. **Drops C, D, E in any order after A and B.** They're parallel (different surface areas). C is easier than D; D is the most code; E is in between.
4. **Drop B′ after B lands.** Independent of C/D/E. Schedule when convenient. Player-command narration is already correctly attributed today, so deferring is safe.

Estimated calendar time at 1 drop per session: **6 sessions** (A, B, C, D, E, B′). At 2 drops per session for the smaller ones: **3–4 sessions**. The longest single session is Drop D (combat HUD) at ~8–12 hours.

**Total effort revised:** ~29–41 hours (was ~28–40 in v1; F7 removal saves ~1–2 hrs in Drop C, Drop B′ adds ~3–4 hrs).

---

## 11. Open Questions Resolution Summary

All five open questions from v1 have been resolved per `field_kit_open_questions_v1_1.md`:

| # | Question | Resolution | Effect on this doc |
|---|---|---|---|
| **D1** | Should F7 (StanceChip) ship? | **REMOVE** — not WEG | Edit A applied (Drop C scope reduced) |
| **D2** | Add `combat_state.theatre` field? | **ADD** | Edit B applied (Drop D server-side prereq) |
| **D3** | Drop B scope — player commands too? | **Split B / B′** | Edit E applied (Drop B′ added) |
| **D4** | Stance modifier values | **MOOT** (D1 removed F7) | n/a |
| **D5** | `pose_event` deduplication key | **Composite** `speaker_id:timestamp_ms:hash` | Edit F applied (signature + helper) |

If a 6th unresolved question surfaces during implementation, surface it back to Brian / the design Opus chat for a decision rather than guessing.

---

*End of Field Kit Design Implementation Decomposition — Version 2.0*
