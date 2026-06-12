# Field Kit UI — Audit & Remediation Design Memo v1

**Status:** Design, awaiting approval
**Author:** Opus (audit)
**Target implementer:** Sonnet
**Related designs:** `web_client_ux_overhaul_v1.md`, `sw_d6_mush_architecture_v32.md`, `engineering_standards_v1.md`
**Source material reviewed:** `design_handoff_sw_mush_field_kit/` (Designer drop, Apr 2026)

---

## 1. Context

The second Designer pass on the web client UI ("Field Kit" — amber datapad for ground, cyan cockpit for space) arrived with substantially better mechanical fidelity than the prior round. The new README explicitly rejects the earlier HP-bar / percentage-shield / power-allocation mistakes and cites `engine/character.py`, `engine/starships.py`, and `engine/combat.py` as sources of truth.

Cross-checking every Designer claim against the actual Windows-current code surfaced a set of drifts, mislabels, and scope gaps that would each cause a concrete gameplay or rendering problem if the prototype JSX were ported directly into `static/client.html`. None of the issues invalidate the direction; all are fixable with targeted corrections to the prototype files plus one server-side schema extension.

This memo catalogs the findings, proposes a priority-ordered remediation plan, and specifies the `pose_event` schema extension the PoseLog design implicitly requires.

### 1.1 What was verified, not questioned

The following Designer claims were confirmed against the engine and do not require any change:

- Wound levels are a single enum on `Character`, with `penalty_dice` mapping `{WOUNDED: 1, WOUNDED_TWICE: 2}` and STUNNED penalty coming from `len(stun_timers)` — correct.
- `stun_timers` is a list, separate from `wound_level` — correct.
- Ship hull is a dice-pool string (`"4D"`), 1D = 3 pips via `DicePool.total_pips()` — correct.
- `hull_condition()` returns Pristine / Light Damage / Moderate Damage / Heavy Damage / Critical Damage / Destroyed — correct.
- `ShipInstance` has `shields_up: bool`, `shield_dice_front: int`, `shield_dice_rear: int` — two arcs plus bool, no quadrants, no percentages. Correct.
- `systems_damaged` is a list of strings from `{engines, weapons, shields, hyperdrive, sensors}` — correct.
- Combat phases `INITIATIVE → DECLARATION → RESOLUTION → POSING`, 180-second pose window, auto-pose generation — correct.
- `to_hud_dict(viewer_id)` returns `{active, round, phase, combatants, your_actions, waiting_for, pose_deadline}` — shape matches; the README's method-name reference is wrong (F11).
- Staged-command pattern (click populates input, Enter commits) is the right interaction model.
- Autoscroll + "new events" pill logic is correct, including scrolled-up behavior.

---

## 2. Audit findings summary

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| F1  | **Blocker**  | `combat-hud.jsx:37`, `ground.jsx:26` | Wound ladder arrays inconsistent; neither covers all 7 WoundLevel values |
| F2  | **Blocker**  | `combat-hud.jsx:92`                  | `dodge` button tooltip describes full dodge; mechanical contract break |
| F3  | **Blocker**  | `combat-hud.jsx:226`                 | Posing panel instructs `pose <text>`; actual command is `cpose <text>` |
| F4  | **High**     | README §Commands                     | `fullDefense` listed but doesn't exist in the parser |
| F5  | **High**     | `combat-hud.jsx:91`                  | FIRE button sends `fire <target>`, which is space-only |
| F6  | **High**     | (absent)                             | No ground-combat HUD; `combat-hud.jsx` is cockpit-only |
| F7  | **High**     | server-wide                          | PoseLog row shape assumes structured events; built-in pose/say/whisper commands emit plain text |
| F8  | **Medium**   | `ground.jsx:36`                      | `maxStuns = 3` hardcoded; should derive from character's STR dice |
| F9  | **Medium**   | `ground.jsx:37`                      | `fpMax = 3` renders FP as N/3 bar; FP is uncapped in R&E |
| F10 | **Medium**   | `ground.jsx:117`                     | CharSheet omits Control/Sense/Alter dice for Force-sensitive PCs |
| F11 | **Low**      | README §Combat flow                  | References `get_combat_snapshot()`; actual method is `to_hud_dict(viewer_id)` |
| F12 | **Low**      | `space.jsx:100`                      | Shield bar hardcoded to 3 segments; ships can have 4D+ arcs |
| F13 | **Low**      | `space.jsx:28`                       | Condition-band color lookup uses uppercase keys; engine returns title-case |
| F14 | **Low**      | `combat-hud.jsx:185`                 | Posing progress bar denominator hardcoded to 180; demo uses 90s |
| F15 | **Cosmetic** | `combat-hud.jsx:298`                 | Demo applies character wound terms ("MORTALLY WOUNDED") to ship damage |
| F16 | **Lore**     | `ground.jsx:59`                      | `JEDI·INIT` badge on a Rebel in GCW era; fine for Clone Wars pivot |
| F17 | **Advisory** | `parser/space_commands.py:502`       | `board` command aliased to `gunnery` — surprising, unrelated to Designer scope |

Severity definitions:
- **Blocker**: Corrupts play or silently mis-displays canonical state if shipped.
- **High**: Breaks intended behavior visibly; scope gap that leaves a major path unhandled.
- **Medium**: Incomplete but not wrong; user sees a partially-working control.
- **Low**: Cosmetic or derived-from-static-data; trivial fix.
- **Cosmetic**: Demo-only; does not ship.
- **Lore**: Content concern, not code. Deferred.
- **Advisory**: Existing code smell unrelated to this handoff; noted for future cleanup.

---

## 3. Findings detail

### F1 — Wound ladder inconsistent, neither covers all 7 levels  *(Blocker)*

**What.** `engine/character.py` defines `WoundLevel(IntEnum)` with 7 values (0–6): HEALTHY, STUNNED, WOUNDED, WOUNDED_TWICE, INCAPACITATED, MORTALLY_WOUNDED, DEAD. Two JSX files render this ladder, each differently and each incompletely.

`prototype/combat-hud.jsx:37`:
```js
const wounds = ['HEALTHY', 'STUNNED', 'WOUNDED', 'INCAP', 'MORT WND', 'DEAD'];
```
→ WOUNDED_TWICE is dropped. A character with `wound_level=3` (the canonical -2D state, still acting) renders as "INCAP".

`prototype/ground.jsx:26`:
```js
const WOUND_RUNGS = [
  { v: 0, label: 'HEALTHY',    pen: '' },
  { v: 1, label: 'STUNNED',    pen: '' },
  { v: 2, label: 'WOUNDED',    pen: '-1D' },
  { v: 3, label: 'WOUNDED ×2', pen: '-2D' },
  { v: 4, label: 'INCAP',      pen: '' },
  { v: 5, label: 'MORTALLY',   pen: '' },
];
```
→ DEAD (6) is dropped. A dead character renders with no active rung.

**Why it matters.** The combat HUD mislabels a common mid-combat state; the character sheet silently fails on death. Identity of the same mechanical concept diverges between panels in the same client.

**Fix.** Single canonical array, 7 entries, shared across both components. Extract into `tokens.jsx` and re-export:

```js
// tokens.jsx
const WOUND_RUNGS = [
  { v: 0, label: 'HEALTHY',     pen: '',    sev: 'ok'   },
  { v: 1, label: 'STUNNED',     pen: '',    sev: 'warn' },  // penalty comes from stun_timers
  { v: 2, label: 'WOUNDED',     pen: '-1D', sev: 'warn' },
  { v: 3, label: 'WOUNDED ×2',  pen: '-2D', sev: 'hurt' },
  { v: 4, label: 'INCAP',       pen: '',    sev: 'crit' },  // can_act = false from here
  { v: 5, label: 'MORTAL',      pen: '',    sev: 'crit' },
  { v: 6, label: 'DEAD',        pen: '',    sev: 'dead' },
];
```

CombatantPip uses `WOUND_RUNGS.find(r => r.v === c.wound_level)` with a fallback to `HEALTHY` for malformed input. Ground CharSheet renders all 7 rungs (DEAD lit = grim but unambiguous), or 6 rungs + hide DEAD and show an override banner when `wound_level === 6` — Sonnet's call.

### F2 — DODGE button sends wrong command and describes wrong mechanic  *(Blocker)*

**What.** `combat-hud.jsx:92`:
```js
{ id: 'dodge', label: 'DODGE', cmd: 'dodge',
  desc: 'Full dodge — +2D to be missed, no attack this round' }
```

The parser has two distinct commands:
- `DodgeCommand` (key `"dodge"`): reactive dodge, declared in advance, allows other actions. Skill roll determines difficulty bump.
- `FullDodgeCommand` (key `"fulldodge"`, alias `"fdodge"`, `"full dodge"`): consumes the round, no other actions permitted.

The tooltip describes full dodge. The command sent is reactive dodge. Clicking DODGE:
1. Does not grant the "no attack this round" protection the tooltip promised.
2. Leaves the player free to attack, which they'll expect they can't.
3. Gives a reaction roll whose effect is the rolled total (not a fixed +2D).

The "+2D to be missed" value is also fictional — R&E dodge is a reaction skill roll whose total becomes the new difficulty for incoming attacks.

**Fix.** Split into two buttons with correct tooltips:

```js
{ id: 'dodge',     label: 'DODGE',     cmd: 'dodge',
  desc: 'Reactive dodge — raises difficulty for incoming ranged fire. Can still act.' },
{ id: 'fulldodge', label: 'FULL DODGE', cmd: 'fulldodge',
  desc: 'Spend the round dodging. All incoming ranged fire rolled against your dodge. No other actions.' },
```

Same pattern for `parry` / `fullparry` on the ground HUD (see F6).

### F3 — Posing panel tells players the wrong command  *(Blocker)*

**What.** `combat-hud.jsx:226`:
> "Type your narrative pose into the command input below, prefixed with `pose` (or just `:`)."

In POSING phase, the command for submitting a combat pose is `cpose <text>` (aliased `combatpose`). The plain `pose` / `:` / `emote` command hits `EmoteCommand` in `builtin_commands.py`, which broadcasts to the room as a regular RP pose but does **not** register the text against `combat._pose_state[char_id]`.

**Consequence when a player follows the instruction.** The player types `pose dives behind the crate, fires twice` during POSING. The text broadcasts to the room. Their combat-pose slot remains `"pending"`. After 180 seconds, `_pose_grace_timer` fires and `generate_auto_pose()` writes an auto-generated pose on top. The player's narration is now a decorative side-effect instead of the canonical round log.

**Fix options, in order of preference:**

**(A) Bridge `pose` → `cpose` during POSING phase.** In `EmoteCommand.execute`, detect `combat.phase == CombatPhase.POSING` for the actor, and delegate to `CombatPoseCommand`. This matches user expectation (one `pose` verb, context-sensitive) and also rescues players who type `pose` from muscle memory even without the UI. Downside: magical behavior; the same verb does different things in different contexts.

**(B) Update the panel instruction to say `cpose`.** Literal fix, zero engine change, visible.

**(C) Both.** Panel says `cpose` (explicit for visual readers), but `pose` during POSING also works as a fallback (graceful for muscle-memory typers).

**Recommended: C.** Primary instruction is `cpose`; the bridge is defense in depth.

### F4 — `fullDefense` command doesn't exist  *(High)*

**What.** README §Commands lists `fullDefense` as a combat command. `grep -rn "fullDefense\|full_defense"` across `parser/` returns zero matches. The engine has a validation string referencing "full defense" at `combat.py:619`, but no parser command of that name.

**Why.** R&E doesn't have a "full defense" action — the closest concepts are `fulldodge` and `fullparry`, which are distinct commands for distinct rolls. "Full defense" is a GURPS/d20 term leaking in from another game system.

**Fix.** Remove `fullDefense` from the README. Ensure no button in any HUD sends it.

### F5 — FIRE / ATTACK conflation  *(High)*

**What.** The DeclarationPanel's FIRE button stages `fire <target_id>`. `FireCommand` is in `parser/space_commands.py:2126` — space-combat only. Ground combat uses `AttackCommand` (`combat_commands.py:731`) with invocation `attack <target> [with <skill>] [damage <dice>] [cp N] [stun]`.

**Why.** The prototype has only a cockpit CombatHUD, so in the prototype's context, `fire` is correct. But the README's Commands list presents both under one bullet ("Combat: `fire`, `attack <target>`...") without flagging which applies where. Implementers porting the combat-hud JSX to ground scope would send `fire greedo` and fail.

**Fix.** Separate command glossary in README by combat context. See F6 — the ground HUD needs different buttons anyway.

### F6 — No ground-combat HUD  *(High)*

**What.** `prototype/combat-hud.jsx` contains only cockpit visuals (space blue palette, ship combatant pips, FIRE button). Ground combat — the bulk of the game's expected play (cantina shoot-outs, lightsaber duels, Imperial patrols) — has no action-button scaffolding.

**Why it matters.** Without a ground combat HUD, players in a blaster fight have no buttons; they fall back to raw typing of `attack greedo`, `dodge`, `fulldodge`, `parry`, `fullparry`, `cover`, `aim`, `grenade`, `pass`, `cp N`, `fp`. The web-first policy and the designer's whole "pose log is the hero, chrome is context-aware" principle both require this HUD.

**Fix.** Build a `ground-combat-hud.jsx` module parallel to `combat-hud.jsx`, using the pad amber palette. Action buttons vary by phase:

| Phase       | Ground buttons                                                                |
|-------------|-------------------------------------------------------------------------------|
| DECLARATION | ATTACK, DODGE, FULL DODGE, PARRY, FULL PARRY, AIM, COVER, GRENADE, FLEE, PASS |
| RESOLUTION  | (banner only, no buttons)                                                     |
| POSING      | (same posing panel as space; deadline bar, cpose guidance, PASS)              |

FP toggle and CP spinner appear in DECLARATION in both ground and space. See F9 for FP rendering.

Scope-wise, ground HUD reuses `PhasePill`, `CombatantStrip` (with slightly different styling), `ResolutionBanner`, `PosingPanel` verbatim from the shared combat-hud module. Only the DeclarationPanel is context-specific.

### F7 — PoseLog expects structured events the server doesn't emit  *(High)*

**What.** `pose-log.jsx` renders rows shaped like:
```js
{ t: 'pose',    who: 'Tundra', text: 'draws a blaster' }
{ t: 'pose',    who: 'Mak',    mode: 'says',     text: 'Late again.' }
{ t: 'pose',    who: 'Mak',    mode: 'whispers', to: 'you', text: '…' }
{ t: 'comm-in', who: 'Red-3',  channel: 'ENC',   text: '…' }
```

The server's built-in `EmoteCommand`, `SayCommand`, and `WhisperCommand` all emit via `send_line` / `broadcast_to_room` — a single concatenated text string per recipient:
- `EmoteCommand`: `"Tundra draws a blaster"`
- `SayCommand`: `'Tundra says, "Late again."'`
- `WhisperCommand`: `'Tundra whispers to you, "..."'`

The client has a `classifyAndAppend` function (static/client.html:2963) that regex-parses these text lines back into structured rows. This is the source of the "Room says…" bug from the earlier round — ambient narration like `"Room shudders as the door seals"` gets misclassified as `{who: 'Room', mode: 'says', text: 'as the door seals'}`.

**Meanwhile**, `pose_event` is already a real protocol message in the server, emitted by `engine/boarding.py` and `engine/encounter_boarding.py` for ambient sys-events, and consumed correctly by the client's `handlePoseEvent` handler (static/client.html:4659) with dedup fingerprints.

The asymmetry: **ambient/system narration has migrated to structured `pose_event` emission; canonical PC speech and poses still use plain text.** This is backwards from what a clean web-first architecture wants.

**Fix.** Extend `pose_event` emission coverage to the built-in PC commands. Detailed schema in §4 below. This simultaneously:
- Kills the text classifier's need to guess at pose shape.
- Makes the Field Kit PoseLog directly compatible with the server without a re-classification layer.
- Eliminates the "Room says…" mis-render class of bugs by making the classifier a fallback, not a primary path.

### F8 — Stun counter max hardcoded  *(Medium)*

**What.** `ground.jsx:36`: `const maxStuns = 3;` with comment "cap ≈ STR dice". KO threshold is `len(stun_timers) >= str_dice`, where `str_dice` is the character's current Strength dice count (not pips). So a PC with STR 2D KOs at 2 stuns; STR 4D KOs at 4.

**Fix.** Plumb `strength_dice` through the character HUD payload. Character sheet fetches `char.strength.dice` and passes to stun renderer. If the HUD payload doesn't yet include it, extend that payload — don't approximate client-side.

### F9 — Force Points rendered as a capped bar  *(Medium)*

**What.** `ground.jsx:37`: `const fp = 2, fpMax = 3;` then renders `{fp}/{fpMax}` with `max(fpMax, fp)` dots. Force Points have no cap in R&E — they're a running integer earned through play (~1 per major adventure), spent at 1-per-use to double all dice for a round.

**Why it matters.** Rendering "2 / 3" with remaining empty dots implies a meter that refills toward a maximum — the exact percentage-bar mentality the README otherwise rejects for shields and hull.

**Fix.** Render FP as N filled dots. If N > some visual budget (say, 8), render 8 dots + `+{N-8}` text. No empty dots, no denominator.

Same rule applies if Dark Side Points are ever displayed: an integer with red styling, not a meter.

### F10 — CharSheet missing Control / Sense / Alter  *(Medium)*

**What.** The Character dataclass has three Force skill dice pools (`control`, `sense`, `alter`), each a `DicePool`. These govern Force skill rolls for Force-sensitive PCs. The Field Kit CharSheet renders the six standard attributes but omits these.

**Why it matters.** A Jedi character sheet without C/S/A is structurally incomplete — they can't see what they roll to use Control Pain, Sense Force, or Telekinesis. Especially relevant for the Clone Wars era pivot, where Force-sensitive PCs are a more prominent cohort than in GCW.

**Fix.** Conditional block in `CharSheet`: if `char.force_sensitive === true`, render a "FORCE SKILLS" section after ATTRIBUTES with C/S/A dice in the same `4D+2` format. Suppress entirely for non-sensitive PCs.

### F11 — README method name wrong  *(Low)*

**What.** README says `get_combat_snapshot()`. Actual method is `CombatInstance.to_hud_dict(viewer_id)`.

**Fix.** README text correction only. No code impact — the shape the JSX consumes matches what the method returns.

### F12 — Shield bar hardcoded to 3 segments  *(Low)*

**What.** `space.jsx:100`: `Array.from({ length: 3 })` for shield arc segments. Some ships have 4D or higher shields per arc.

**Fix.** Use `Math.max(shield_dice_front, shield_dice_rear, DEFAULT_SHIELD_SLOTS)` where `DEFAULT_SHIELD_SLOTS = 3` so ships with no shields still render an empty grid of 3. Or bake `total_shield_slots` into the ship HUD payload.

### F13 — Condition-band color-lookup case mismatch  *(Low)*

**What.** `space.jsx:28`:
```js
const condColor = { 'PRISTINE': FK.cockGreen, 'LIGHT DAMAGE': FK.cockGreen, ... }[ship.cond]
```
Engine returns `"Pristine"`, `"Light Damage"`, etc.

**Fix.** Either `.toUpperCase()` before lookup, or use title-case keys in the map. Document which convention the HUD payload uses so this doesn't drift again.

### F14 — Posing bar denominator hardcoded  *(Low)*

**What.** `combat-hud.jsx:185`: `const pct = (remaining / 180) * 100;`

**Fix.** Pass `totalSeconds` as a prop (derive from `pose_deadline` minus the timestamp at POSING entry, or just accept 180 as the canonical window and read it from an engine-exported constant).

### F15 — Demo uses wound terminology for ship damage  *(Cosmetic)*

**What.** `combat-hud.jsx:298`: `'Damage 6D vs. hull 3D — TIE-1 takes MORTALLY WOUNDED damage'`. Ships have hull conditions, not wound levels. Demo-only; not shipped.

**Fix.** Replace with `'Damage 6D vs. hull 3D — TIE-1 takes CRITICAL hull damage'` or similar. Useful as a lint example for future content.

### F16 — `JEDI·INIT` badge on Rebel in GCW era  *(Lore)*

**What.** Designer mock shows a Rebel character with a Jedi Initiate badge. Lore-implausible in GCW (~19 BBY–19 ABY span); perfectly plausible in Clone Wars era (~22–19 BBY).

**Fix.** Deferred to Clone Wars pivot. No action required now.

### F17 — `board` aliased to `gunnery`  *(Advisory)*

**What.** `space_commands.py:502` — `BoardCommand` has `aliases = ["gunnery"]`. Gunnery is a skill, not a boarding verb. Having `gunnery` teleport the player into a ship interior is surprising.

**Fix.** Not Designer's scope. Recommend splitting into a separate future cleanup: either remove the alias or repurpose `gunnery` as a "take the gunnery station" command on an already-boarded ship.

---

## 4. `pose_event` schema — canonical specification

This section defines the server→client event contract. It extends the existing `pose_event` protocol already used for boarding/encounter narration; it does not introduce a new message type.

### 4.1 Wire format

Every structured pose-log event is a `send_json("pose_event", payload)` where `payload` has shape:

```python
{
    "event_type": str,      # see 4.2 for enum
    "who":        str,      # speaker/actor name, "" for ambient system events
    "text":       str,      # the narrative/speech content (server strips ANSI)
    "mode":       str|None, # verb modifier for pose events ("says", "whispers", "poses", …)
    "to":         str|None, # target recipient for directed speech (whispers)
    "channel":    str|None, # channel key for comm events ("ooc", "fcomm", "freq:86.5", …)
    "room_id":    int|None, # optional — aids client-side dedup and scene filtering
    "timestamp":  str,      # ISO-8601 UTC timestamp, server-assigned
}
```

All fields are always present in the JSON, even if `None` — clients should not key off key presence. Unknown fields are ignored by the client (forward-compatible).

### 4.2 `event_type` enum

| Value          | Emitted when                                                                  | Client renders as            |
|----------------|-------------------------------------------------------------------------------|------------------------------|
| `pose`         | `EmoteCommand` / `:` / `em` — actor describes an action                       | pose row (1 line, amber)     |
| `say`          | `SayCommand` / `'` / `"` — actor speaks aloud in room                         | pose row, quoted             |
| `whisper`      | `WhisperCommand` — actor speaks privately to `to`                             | pose row, dim italic         |
| `cpose`        | `CombatPoseCommand` — actor's canonical combat-round narration                | pose row, combat-styled      |
| `comm-in`      | Channel broadcasts (`ooc`, `fcomm`, `freq:*`, comlink)                        | comm row with channel tag    |
| `sys-arrival`  | A character enters/leaves the room (connection, movement, disembark)          | system arrival row           |
| `sys-event`    | Ambient narration (boarding alarms, encounter flavor, space anomalies)        | sys-event row, colored       |
| `sys-ok`       | Engine confirmations (target lock, credits transfer, crafting success)        | sys-ok row, green dim        |
| `desc`         | Room / ship / object description (from `look`)                                | desc block, muted paragraph  |
| `desc-inline`  | Ambient scene prose that follows a sys-arrival                                | desc-inline, dim italic      |
| `room-enter`   | Player arrives in a room (following movement resolution)                      | header bar with zone badge   |

Notes:
- `pose` collapses both the traditional `:draws his blaster` and semipose `;hand shakes`. The `mode` field is `"poses"` for the former and `"semipose"` for the latter (client may style differently, may not).
- `say` sets `mode="says"`. This is redundant but explicit for forward-compat with future localized verbs.
- `whisper` sets `mode="whispers"` and always populates `to`.
- `cpose` is the POSING-phase combat pose, rendered with a combat-distinct border color so the player can see their canonical round log inside the regular feed.
- `comm-in` sets `channel` to the key (`"ooc"`, `"fcomm:rebellion"`, `"freq:86.5"`). The client renders the channel label from the key.
- `sys-arrival` populates `who` with the subject and `text` with the clause (`"enters from the north"`, `"disconnects"`). Client assembles `"<who> <text>"`.

### 4.3 Dedup discipline

The client already dedupes text broadcasts against recent pose_event fingerprints (60-char prefix, 2-second window). Server-side emission discipline:

- Any command that emits `pose_event` **must still** call `broadcast_to_room` for the plain-text line (Telnet compatibility per web-first policy — Telnet remains supported for admin/debug).
- The `pose_event` goes out **first**, then the text broadcast. Ordering matters: the client's fingerprint set needs to be populated before the text arrives for the dedup to fire.
- Fingerprint content is the canonical concatenated line the classifier would produce. For example, for `say`, the server fingerprint matches the text form `'Tundra says, "Hello"'`.

### 4.4 Classifier becomes a fallback, not a primary path

Once all built-in commands emit `pose_event`, the existing `classifyAndAppend` in `static/client.html` demotes from "primary pose classifier" to "safety net for untyped lines" (e.g., ANSI-colored admin narration, TinyMUX-style `@emit`, third-party modules that haven't migrated).

Per web-first policy: we do **not** delete the classifier. We lower its confidence — when it detects an attribution shape ("X says, ...") that's already fingerprinted, it skips rendering; when it detects a shape not fingerprinted, it still renders (but as a generic `sys` row with a debug flag in dev builds).

### 4.5 Migration order for emission sites

Not all callers migrate in one shot. Recommended order, each shippable independently:

1. `SayCommand` → emit `pose_event(event_type="say")` before text broadcast.
2. `WhisperCommand` → emit with `to` populated.
3. `EmoteCommand` → emit with `mode="poses"` or `"semipose"`.
4. `CombatPoseCommand` → emit with `event_type="cpose"`.
5. Movement / `LookCommand` → `sys-arrival`, `room-enter`, `desc` events.
6. Channel broadcasts (`broadcast_ooc`, `broadcast_comlink`, etc.) → `comm-in`.
7. Achievement / scene-log emissions → `sys-ok`.

Each step is a surgical ~5–15 line patch to one command class. Tests: each migration adds one test that asserts both a `pose_event` payload shape and a text broadcast, and that the fingerprint dedup kicks in for a WebSocket session.

---

## 5. Remediation plan

Three drops, in priority order. Each drop is independently shippable and independently testable.

### Drop A — Blocker fixes to the JSX prototype  *(~2–3 hour implementation)*

Scope: F1, F2, F3, F4, F11, F13, F14, F15.

These are corrections to `design_handoff_sw_mush_field_kit/` itself — before any port into `static/client.html` begins. Deliverable: a corrected `design_handoff_sw_mush_field_kit_v2/` drop.

Changes:
- Extract canonical `WOUND_RUNGS` array into `tokens.jsx`, import from both ground and combat-hud.
- Split DODGE into DODGE + FULL DODGE buttons; fix tooltips to match actual R&E mechanics.
- Change posing-panel instruction text from `pose` to `cpose`; note the `:` shortcut is NOT cpose.
- Remove `fullDefense` from README command list; add note distinguishing ground (`attack`) from space (`fire`) commands.
- README: correct `get_combat_snapshot()` → `to_hud_dict(viewer_id)`.
- InstrumentPanel: title-case keys or `.toUpperCase()` normalization.
- PosingPanel: accept `totalSeconds` prop.
- Demo dialog: replace "MORTALLY WOUNDED" for ship with "CRITICAL hull damage".

### Drop B — Server-side `pose_event` emission migration  *(~4–6 hour implementation)*

Scope: F7.

Steps 1–4 from §4.5 (Say / Whisper / Emote / CombatPose), with tests. Steps 5–7 deferred to a second wave if A + B land cleanly.

Per-command pattern: add a pre-broadcast `await s.send_json("pose_event", payload)` for WebSocket sessions in the target room, call `recordPoseEventFingerprint`-equivalent server-side metadata if we want, then proceed with existing text broadcast.

Regression surface: every test that currently asserts on `send_line` text content keeps passing. New tests assert the JSON shape.

**Blocks:** the full Field Kit port (Drop C) should not begin until Drop B lands, or the PoseLog will need a client-side classifier fallback that we'd then tear out.

### Drop C — Field Kit port into `static/client.html`  *(large, separate design)*

Scope: F5, F6, F8, F9, F10, F12, plus the actual Babel → hand-coded-HTML port.

This is a substantial implementation effort that warrants its own design memo after A and B prove out. Not in this memo's scope to detail. Precondition: Drops A and B landed, plus the ground-combat HUD is designed (F6 — I can produce that as a follow-up memo).

---

## 6. Sequencing for Sonnet

Recommended order:

1. **Drop A** — Read `design_handoff_sw_mush_field_kit/README.md` and the five prototype JSX files. Apply the enumerated fixes. Re-zip as `design_handoff_sw_mush_field_kit_v2/`. Sonnet-authored deliverable. No engine code touched.
2. **Drop B** — Read `engine/boarding.py:411` (`_emit_boarding_sys`) as the canonical pattern reference. Apply equivalent emission to `SayCommand`, `WhisperCommand`, `EmoteCommand`, `CombatPoseCommand` — in that order, one per commit. Update `tests/test_core_systems.py` (or new module) to assert both the JSON and the text broadcast. AST-validate, confirm dedup fingerprint matches by inspection.
3. **Decision point** — Brian reviews Drop B on his dev box, runs full pytest suite externally. If green, proceed to Drop C design.
4. **Drop C (design)** — Opus drafts `field_kit_port_design_v1.md` covering ground-combat HUD scope, payload shape for the character HUD (stun max, C/S/A), page-level architecture inside `client.html`, incremental rollout vs. big-bang replacement.
5. **Drop C (implementation)** — Sonnet implements against that design.

## 7. Open questions / decisions needed from Brian

1. **F3 policy choice.** Do we want `pose` during POSING phase to silently delegate to `cpose` (option C from §3)? This is forgiving of muscle memory but adds magic to the parser. The alternative (option B — just fix the UI instruction) is more honest but unforgiving.

2. **F10 surface area.** Should C/S/A always be visible in the CharSheet (grayed out if not Force-sensitive), or conditionally hidden? Visible is more discoverable for new players ("what are those?"); hidden is cleaner for the 90% of PCs who are non-sensitive.

3. **F6 scope boundary.** Ground-combat HUD is big enough to warrant its own memo (I flagged it as precondition to Drop C). Want me to draft that next, or defer to after A + B land?

4. **Drop B test framework.** The WebSocket/session-manager dedup test needs a mock WS session. Is there an existing pattern in `tests/conftest.py` for that, or should Sonnet introduce one?

---

*End of memo.*
