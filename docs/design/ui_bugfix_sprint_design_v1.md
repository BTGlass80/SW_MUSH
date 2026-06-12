# Bug-Fix Sprint Design — Tier 1 #3 (UI design-drop fixes)

**SW_MUSH — Star Wars D6 Revised & Expanded · Clone Wars era (~20 BBY)**
**BTGlass80 — May 26 2026**
**Status:** Design + drop scope. Ready for engineering Claude execution.
**Architecture-of-record:** `sw_d6_mush_architecture_v50.md` (Tier 1 #3 — bug-fix sprint, opened in v49 §3.2).
**Source review:** `design_review_may24_v1.md` (the 24-item issue catalog).
**Vision doc context:** `web_client_vision_and_protocol_v1_3.md` (latest UI design).
**Companion handoffs:** `HANDOFF_MAY25_SYN10.md` (last engine drop), `HANDOFF_MAY24_DESIGN_LOCK_v2.md` (design lock pattern).

---

## 0. What this drop is

The May 24 design review catalogued 24 issues in the v2 + v3 Claude Design drops (`SW_MUSH_UIUX_24May26.zip`). Brian chose **Path B** with a mandatory pre-implementation checkpoint: engineering Claude applies fixes to the existing v3 JSX *before* any production port to `static/client.html` begins. Brian reviews the fixed JSX, then the production port proceeds.

This document scopes that bug-fix sprint as a self-contained drop.

### What this drop is NOT

- **Not** the production port to `static/client.html`. That's the next drop after this one.
- **Not** a redesign. The visual language, layout, asset library, renderer architecture, holocron content, holonet content, sheet structure, and combat-theater pose-stream layout are all **preserved**. We're fixing 24 specific issues without re-litigating the design.
- **Not** an engine change. Zero Python files touched. JSX-only.
- **Not** an inline-Sector-Map fix in `ground.jsx` (M1). The review explicitly defers that to the renderer integration drop in Phase 3. Mentioned for completeness; not included.

### Position in the lane

- **Tier 1 #3** — UI bug-fix sprint (this drop).
- **Tier 1 #4** — production port v3-fixed → `static/client.html` (the next drop after Brian signs off on this one).
- **Tier 1 #5+** — Phase 1 protocol-substrate drops (1.1–1.5 from vision §9), then Phase 2 panel build-out.

---

## 1. Issue catalog — what gets fixed and what doesn't

Pulled directly from `design_review_may24_v1.md`. Status legend:

- ✅ **In scope** — fixed in this drop.
- ⏸ **Deferred** — explicitly out of scope; noted with the drop it lands in.
- 🚫 **Wontfix** — design call to leave as-is, with rationale.

### Blockers (B1–B4)

| ID  | Issue | Status | Lands in |
|-----|-------|--------|----------|
| B1  | `pass` button missing in `map_v3/combat-theater.jsx` PosingBody + DeclarationBody | ✅ | This drop |
| B2  | Invented `stance` mechanic in `drop_v2/prototype/ground.jsx` | ✅ | This drop |
| B3  | Era contamination — 12 hits across v2 + v3 | ✅ | This drop |
| B4  | Wound-ladder rung count mismatch in `map_v3/sheet-v2.jsx` | ✅ | This drop |

### High-severity (H1–H6)

| ID  | Issue | Status | Lands in |
|-----|-------|--------|----------|
| H1  | MAP label `−1D MAP if 2nd` ambiguous in `combat-theater.jsx:104,107` | ✅ | This drop |
| H2  | AIM labeled "free · +1D next" — wrong; AIM IS the action | ✅ | This drop |
| H3  | Cover treated as binary; R&E has graded cover | 🚫 | Wontfix — engine is binary today; revisit if engine grades cover later |
| H4  | No Force panel in any sheet | ⏸ | Deferred — Phase 2 Drop 2.1 (HUD/sheet) per vision §6.13 |
| H5  | FP rendered as `2/3` with hard `fp_max=3` in `ground.jsx:37` | ✅ | This drop |
| H6  | Damage thresholds and stun-vs-wound conflation | ✅ | This drop |

H3 wontfix rationale: the engine's current cover model is binary (in/out). Graded cover would require an engine change beyond this drop's scope. The audit doc didn't flag it as broken — only as a design opportunity. Defer to the engine's call. The button stays "already in cover" → disabled.

H4 deferral rationale: the Force panel is a §6.13 spec in v1.3 vision. Adding it requires layout space and a sheet redesign that doesn't belong in a bug-fix sprint. Drop 2.1 (HUD) or a dedicated 2.x sheet drop handles it.

### Medium-severity (M1–M5)

| ID  | Issue | Status | Lands in |
|-----|-------|--------|----------|
| M1  | Inline `SectorMap` in `drop_v2/prototype/ground.jsx:191-239` | ⏸ | Deferred — Phase 3 Drop 3.7/renderer integration |
| M2  | Pose-log `room-enter` row too heavy in `drop_v2/prototype/pose-log.jsx:92-106` | ✅ | This drop |
| M3  | Hardcoded comms tabs don't match dynamic engine channel set | ⏸ | Deferred — Phase 2 Drop 2.5 (tabbed comms) |
| M4  | Initiative ladder shows bare numbers without "Perception" label | ✅ | This drop |
| M5  | "1 stun applied" outcome ambiguous in `combat-theater.jsx:31` | ✅ | This drop |

M1 is the largest deferred item; per the review, the field-kit mini-map should call into the same renderer the full map uses, which is Phase 3 work. The `SectorMap` is left as-is for this drop; a small TODO comment is added pointing to the deferred work.

M3 is deferred because the engine doesn't yet emit a dynamic channel-subscription message (per vision §5.7, `chat_message` is "Designed" not "Shipped"); fixing the tabs depends on that protocol work landing first.

### Low-severity / cosmetic (L1–L5)

| ID  | Issue | Status | Lands in |
|-----|-------|--------|----------|
| L1  | Wuher tagged `hostile` in `map_v3/data-mos-eisley.jsx:105` | ✅ | This drop |
| L2  | "Garrison" civic building label in CW era | ✅ | This drop |
| L3  | `KILLED` vs `DEAD` vs "Mortal" label inconsistency | ✅ | This drop |
| L4  | "Cargo lifter" cover doesn't match Docking Bay 94 description | ✅ | This drop |
| L5  | Two demo characters (Tundra Vex / Tey Voss); standardize on Tey Voss | ✅ | This drop |

All five low-severity items are quick text-data edits with no structural impact. Fold into this drop.

---

### Scope tally

- **✅ In scope:** 18 of 24 (B1-B4, H1, H2, H5, H6, M2, M4, M5, L1-L5).
- **⏸ Deferred to later drops:** 5 of 24 (H4, M1, M3 — plus 2 sub-items inside H6 that are post-launch polish).
- **🚫 Wontfix:** 1 of 24 (H3).

---

## 2. Pre-flight audit findings

Per the standing pre-flight discipline (architecture v50 §5.9, §6.2), this section captures what's verified at HEAD before code starts.

### 2.1 Files verified to exist with cited issues

Every issue location cited in `design_review_may24_v1.md` was grep-verified against the unzipped JSX in `SW_MUSH_UIUX_24May26.zip`. All cited line numbers are accurate as of HEAD; no phantom-issue findings.

Confirmed hit locations (samples):

- `drop_v2/prototype/ground.jsx:24` — "Imperial stripped two ships last cycle" — CONFIRMED
- `drop_v2/prototype/ground.jsx:40` — `tags = ['REBEL', 'JEDI·INIT']` — CONFIRMED
- `drop_v2/prototype/ground.jsx:159-189` — `StanceChip` component — CONFIRMED (lines 159–189 contain it)
- `drop_v2/prototype/ground.jsx:317,322,449-454,498` — `stance` plumbing — CONFIRMED (state hook, parser regex, panel render, hint text)
- `drop_v2/prototype/space.jsx:15,17-19,21-24,217,219,252` — TIE/X-wing references — CONFIRMED
- `drop_v2/prototype/combat-hud.jsx:246-247,266,279,296,298-299,303-304,315,330` — TIE-1/TIE-2 demo — CONFIRMED
- `drop_v2/prototype/tokens.jsx:161,168,171` — Imperial patrol pose + TIE comm — CONFIRMED (3 additional hits not in the original B3 table; fold in)
- `map_v3/sheet-v2.jsx:26` — 5-label wound ladder — CONFIRMED (line 26 has `labels: ['Stunned', 'Wounded', 'Wounded Twice', 'Incapacitated', 'Mortal']`)
- `map_v3/sheet-v2.jsx:113` — "Sealed Imperial Dispatch" — CONFIRMED
- `map_v3/sheet-v2.jsx:978` — Tag chip list with 'Empire' — needs re-verification (file is 1121 lines; line numbers shift if upstream edits land)
- `map_v3/holocron.jsx:96` — ISB quote — CONFIRMED
- `map_v3/holonet.jsx:74` — "Imperial Patrol" anomaly — CONFIRMED
- `map_v3/assembled-client.jsx:550` — "Sealed Imperial Disp." — CONFIRMED
- `map_v3/assets-landmarks.jsx:232,256` — Imperial comments — CONFIRMED
- `map_v3/combat-theater.jsx:104,107` — MAP labels — CONFIRMED
- `map_v3/combat-theater.jsx:105` — AIM "free" — CONFIRMED
- `map_v3/combat-theater.jsx:102-111` — `availableNextDeclaration` list with no `pass` entry — CONFIRMED
- `drop_v2/combat-hud.jsx:104` and `drop_v2/ground-combat-hud.jsx:20` — `pass` button IS present — CONFIRMED (these are the reference implementations to mirror in map_v3)

### 2.2 New finds beyond the original review

- **`drop_v2/prototype/tokens.jsx:161,168,171`** — three additional Imperial/TIE references in the tokens demo-event source. Not in the original B3 table. Fold into B3 fixes.
- **`map_v3/composition-engine.jsx:56`** — substring "TIER" in a UI label (`TIER {tier}`) which is a *false positive* for the era-contamination grep (it's the renderer tier system, not TIE fighters). Verified manually — leave unchanged.
- **`map_v3/map-navigator.jsx:17-89`** — `TIER_DEFS` constant — also false-positive matches for "TIE" substring. Leave unchanged.

### 2.3 Phantom-pattern check

Per architecture v50 §6.2, the phantom-pattern catalog is alert for these anti-patterns. None observed at HEAD for this drop:

- **No vacuous-assertion phantoms** — every fix has a concrete test (see §6).
- **No loud-substitution phantoms** — every era replacement is explicit, not a silent rename.
- **No byte-grep-pinned-but-not-runtime-pinned phantoms** — JSX changes are visible at runtime via SPA render.
- **No inverted-narrative phantoms** — design review and this drop's fix narrative agree.
- **No rendering-layer phantoms** — JSX changes are inspectable in the React render tree, not buried in CSS z-index.

---

## 3. Fix-by-fix specifications

Each subsection covers: target file, exact change, rationale, and acceptance criteria.

### 3.1 B1 — `pass` button in map_v3/combat-theater.jsx

**Files touched:** `map_v3/combat-theater.jsx`.

**Change 1 — DeclarationBody (around line 102-111).** Add a `pass` entry to `availableNextDeclaration` after `flee`:

```jsx
availableNextDeclaration: [
  { id: 'attack', label: 'ATTACK',     icon: '✤', enabled: true,  cost: '−0D' },
  { id: 'dodge',  label: 'DODGE',      icon: '⚝', enabled: true,  cost: '−1D MAP if 2nd' },  // H1 will retouch
  { id: 'aim',    label: 'AIM',        icon: '⦿', enabled: true,  cost: '1 action · +1D next round' },  // H2 will retouch
  { id: 'cover',  label: 'COVER',      icon: '◥', enabled: false, cost: 'already in cover' },
  { id: 'move',   label: 'MOVE',       icon: '→', enabled: true,  cost: '−1D MAP if 2nd' },  // H1 will retouch
  { id: 'reload', label: 'RELOAD',     icon: '↻', enabled: false, cost: 'mag at 49/50' },
  { id: 'fp',     label: 'SPEND FP',   icon: '✮', enabled: true,  cost: '×2 ALL DICE' },
  { id: 'flee',   label: 'FLEE',       icon: '⤥', enabled: true,  cost: 'end combat' },
  { id: 'pass',   label: 'PASS',       icon: '·', enabled: true,  cost: 'hold action' },  // B1
],
```

**Change 2 — PosingBody (around line 1024-1068).** Add a prominent "ACCEPT AUTO-POSE" button next to the cpose input, labeled clearly and styled with equal visual weight to the cpose submit. Wire it to send `pass` as the command. Visible whenever the auto-pose text is rendered.

The button label is "▸ ACCEPT AUTO-POSE" per the review's recommendation. Tooltip: "Sends `pass` — uses the engine-generated default pose above."

**Keyboard shortcut:** `Ctrl+P` (per the review's "perhaps `Ctrl+P`" suggestion). Wire via a `useEffect` keydown handler scoped to the posing phase.

**Acceptance criteria:**
- Declaration phase shows 9 action buttons including a `PASS` chip with equal visual treatment to the others.
- Posing phase shows the auto-pose preview and an "ACCEPT AUTO-POSE" button beside the cpose input.
- Clicking the button sends `pass` to the command rail.
- `Ctrl+P` triggers the same action during posing phase only.
- Tests assert both buttons render and both wire to `pass` (see §6).

**Engineering note:** B1 fix doesn't touch `drop_v2/combat-hud.jsx:104` or `drop_v2/ground-combat-hud.jsx:20` — those already have `pass` as a proper button (lines 104 / 20). Preserve. M2's pose-log row is a sibling fix in `pose-log.jsx`; don't conflate.

---

### 3.2 B2 — Remove StanceChip from `drop_v2/prototype/ground.jsx`

**Files touched:** `drop_v2/prototype/ground.jsx`.

**Changes:**

1. **Remove the `StanceChip` component definition** (lines 159–189).
2. **Remove the `useState` hook** at line 317: `const [stance, setStance] = React.useState('standard');`.
3. **Remove the command interception** at lines 322–325 (the `if (/^stance\s+(cautious|standard|all-out)$/i.test(text))` block).
4. **Remove the panel render** at lines 449–454 (the `{/* F7 — stance chip sits above the hardware strip */}` block).
5. **Remove the `stance cautious` from the command hint text** at line 498. Replace with one of the canonical commands (e.g. `dodge` or `aim`).
6. **Remove the comment block** at lines 6–7 referencing the F7 wiring.

**Acceptance criteria:**
- `grep -nE "stance|StanceChip|Cautious|All-Out" drop_v2/prototype/ground.jsx` returns zero hits.
- Sandbox test loads `ground.jsx` and asserts no `StanceChip` is rendered.
- The text command hint no longer mentions stance.

**Rationale:** `stance` is not a WEG R&E mechanic and not a parser command. Per vision §3.15, this is a NEVER-invent. Preventing regression is a top concern: the F.0 acceptance criterion #6 (per `field_kit_design_decomposition_v2.md` §9) was specifically `grep -E "StanceChip|stance.*chip|stance_chip" static/client.html` returns 0. We extend that discipline to the prototype JSX so future drops can't reintroduce it.

---

### 3.3 B3 — Era contamination (12 hits + 3 new finds)

**Files touched:** 7 files across v2 + v3.

This is the largest single sub-task by file count. Substitutions are mechanical but era-aware — each replacement is chosen to feel natural in CW.

#### Heavy contamination — v2 drop

**`drop_v2/prototype/ground.jsx`:**

| Line | From | To |
|---|---|---|
| 24 | `'Imperial stripped two ships last cycle. Whatever you\'re carrying, get it off-planet before dusk.'` | `'Republic patrols swept two ships last cycle. Whatever you\'re carrying, get it off-planet before dusk.'` |
| 40 | `tags = ['REBEL', 'JEDI·INIT']` | `tags = ['REPUBLIC', 'PADAWAN']` |

**`drop_v2/prototype/space.jsx`:**

| Line | From | To |
|---|---|---|
| 15 | `'Two TIE/ln flights hold station at 12K, engines cool.'` | `'Two Vulture-droid flights hold station at 12K, sublights idle.'` |
| 17 | `{ n: 'Red-3', d: 'X-wing · wingmate · Light Damage' }` | `{ n: 'Red-3', d: 'ARC-170 · wingmate · Light Damage' }` |
| 18-19 | `'TIE-1'`, `'TIE-2'` callsigns and descriptions | `'VULT-1'`, `'VULT-2'` with appropriate range descriptions |
| 21 | `'Two TIEs on intercept.'` | `'Two Vultures on intercept.'` |
| 22 | `'angling the nose toward TIE-1.'` | `'angling the nose toward VULT-1.'` |
| 24 | `'TIE-2 breaking formation, closing fast'` | `'VULT-2 breaking formation, closing fast'` |
| 217 | `>TIE-1 ◉ LOCKED</text>` | `>VULT-1 ◉ LOCKED</text>` |
| 219 | `>TIE-2</text>` | `>VULT-2</text>` |
| 252 | `id: 'TIE-1', class: 'TIE/ln Fighter · Imperial'` | `id: 'VULT-1', class: 'Vulture-class droid starfighter · CIS'` |

**`drop_v2/prototype/combat-hud.jsx`:** (the all-TIE space combat demo)

Every `TIE-1` / `TIE-2` → `VULT-1` / `VULT-2`. Every `'TIE'` → `'Vulture'` in narrative text. Specifically:

- Line 246: `name: 'TIE-1'` → `name: 'VULT-1'`
- Line 247: `name: 'TIE-2'` → `name: 'VULT-2'`
- Line 266: initiative readout — `'TIE-1'`/`'TIE-2'` → `'VULT-1'`/`'VULT-2'`
- Line 279: action summary — `'FIRE at TIE-2'` → `'FIRE at VULT-2'`
- Lines 296, 298, 299: dice + outcome readouts — all `'TIE-1'` → `'VULT-1'`
- Lines 303, 304: enemy fire + ally pose — `'TIE-2'` → `'VULT-2'`
- Line 315: `'You fired on TIE-1...'` → `'You fired on VULT-1...'`
- Line 330: pose text — `'as the TIE blooms'` → `'as the Vulture blooms'`

**`drop_v2/prototype/tokens.jsx`:** (NEW — not in original B3 table)

- Line 161: `'Imperial patrol is three blocks out. Move.'` → `'Republic patrol is three blocks out. Move.'`
- Line 168: `'Two TIEs on intercept. You\'ve got ninety seconds.'` → `'Two Vultures on intercept. You\'ve got ninety seconds.'`
- Line 171: `'banks hard to port, cannons strobing — two hits splash the lead TIE.'` → `'banks hard to port, cannons strobing — two hits splash the lead Vulture.'`

#### Residual contamination — v3 drop

**`map_v3/holocron.jsx`:**

- Line 96: `'— Sergeant Vex, Imperial Security Bureau (retro briefing)'` → `'— Captain Vex, Senate Bureau of Intelligence (field briefing)'`

(The Senate Bureau of Intelligence — SBI — is the canonical CW-era intelligence service per `clone_wars_era_design_v3.md` §A2.)

**`map_v3/holonet.jsx`:**

- Line 74: `{ kind: 'anomaly', tier: 2, name: 'Imperial Patrol', loc: 'Jundland', status: 'ACTIVE', color: 'red' }` → `{ kind: 'anomaly', tier: 2, name: 'Republic Patrol', loc: 'Jundland', status: 'ACTIVE', color: 'red' }`

(Republic patrol is CW-era authentic — clone troopers in Phase 1 armor, LAAT/i gunships.)

**`map_v3/sheet-v2.jsx`:**

- Line 113: `title: 'Sealed Imperial Dispatch'` → `title: 'Sealed Senate Dispatch'`
- Line 122 (personality text): `'Hates the Empire — though it doesn\'t exist yet, the seeds are there.'` → `'Distrusts Senate elites and Trade Federation profiteers in equal measure.'`
- Line ~978 (Empire tag in chip list — re-grep at execution time since file edits may shift the line): remove `'Empire'` from the list. The CW-correct list per the review is `Republic, CIS/Separatists, Jedi Order, Hutt Cartel, Bounty Hunters Guild, Black Sun, Mandalorian Clans`.

**`map_v3/assembled-client.jsx`:**

- Line 550: `'Sealed Imperial Disp.'` → `'Sealed Senate Disp.'` (mirror the sheet rename)

**`map_v3/assets-landmarks.jsx`:**

- Line 232 comment: `// Imperial-style civic with banner and rectangular footprint.` → `// Civic / Republic-government style with banner and rectangular footprint.`
- Line 256 comment: `{/* Imperial-era banner — kept neutral here, Clone Wars era */}` → `{/* Civic banner — Clone Wars era */}`

#### Acceptance criteria (B3)

- `grep -inE "\b(Empire|Imperial|Rebel|Rebellion|Stormtrooper|TIE|X-wing|Vader|Death Star|ISB|Imperial Security Bureau|stormtroop)\b" drop_v2/ map_v3/` returns ONLY false positives (TIER, tier, etc.). Each false positive is documented in a sandbox-test allowlist (mirroring the GCW_AUDIT_REPORT pattern).
- New canonical CW tags appear in `ground.jsx:40`: `'REPUBLIC'`, `'PADAWAN'`.
- New CIS callsigns (`VULT-1`, `VULT-2`) appear consistently across all `space.jsx`, `combat-hud.jsx`, `tokens.jsx` demo sites.
- Sandbox test loads each modified file and asserts presence of the new strings + absence of the era-contaminated ones.

#### Non-issues to leave alone (per the review)

- Greedo, Wuher, DL-44 heavy blaster, YT-1300, Kessel/Kessel Run — all CW-era plausible. Leave.
- Lando Calrissian reference in `sheet-data.jsx:126` notes — review flagged this as OT-coded familiarity but a Brian call. Default: **leave**, document as a possible polish item.

---

### 3.4 B4 — Wound ladder canonicalization

**Files touched:** `map_v3/sheet-v2.jsx`.

**Change:** `map_v3/sheet-v2.jsx:26` currently has:

```js
wounds: { tier: 1, max: 5, labels: ['Stunned', 'Wounded', 'Wounded Twice', 'Incapacitated', 'Mortal'] },
```

Replace with the canonical 7-rung set from `drop_v2/prototype/tokens.jsx`:

```js
wounds: {
  tier: 1,
  max: 6,  // 0=HEALTHY (no marker), 1-6 are render tiers
  labels: ['HEALTHY', 'STUNNED', 'WOUNDED', 'WOUNDED ×2', 'INCAPACITATED', 'MORTALLY WOUNDED', 'DEAD'],
},
```

Better: instead of duplicating the labels here, **import `WOUND_RUNGS` from `drop_v2/prototype/tokens.jsx`** (or a shared `tokens.jsx` to be created in `map_v3/` if cross-directory imports aren't supported in this prototype harness).

If cross-directory import isn't possible in the prototype, copy the canonical `WOUND_RUNGS` constant into `map_v3/tokens.jsx` (new file, ~20 lines) and import in `sheet-v2.jsx`:

```js
// map_v3/tokens.jsx (NEW)
export const WOUND_RUNGS = [
  { v: 0, label: 'HEALTHY',          pen: '',    sev: 'ok'   },
  { v: 1, label: 'STUNNED',          pen: '',    sev: 'warn' },
  { v: 2, label: 'WOUNDED',          pen: '-1D', sev: 'warn' },
  { v: 3, label: 'WOUNDED ×2',       pen: '-2D', sev: 'hurt' },
  { v: 4, label: 'INCAPACITATED',    pen: '',    sev: 'crit' },
  { v: 5, label: 'MORTALLY WOUNDED', pen: '',    sev: 'crit' },
  { v: 6, label: 'DEAD',             pen: '',    sev: 'dead' },
];
```

Then `sheet-v2.jsx` reads from this single source and renders all 7 rungs. The L3 fix below also depends on this canonical source.

**Acceptance criteria:**
- `map_v3/sheet-v2.jsx` renders 7 wound rungs (HEALTHY through DEAD).
- The wound ladder in `sheet-v2.jsx` and in `drop_v2/prototype/ground.jsx`'s WOUND_RUNGS produce identical labels.
- Sandbox test loads `sheet-v2.jsx` with a sample character at each wound tier (0-6) and asserts the right rung is active.

---

### 3.5 H1 — MAP label clarity

**Files touched:** `map_v3/combat-theater.jsx`.

**Change:** Around lines 104, 107, 109, the action cost labels read `−1D MAP if 2nd`. This is ambiguous (does it mean "this 2nd action gets -1D" or "you'll incur -1D MAP if you add a second action"?). Plus it doesn't communicate that *both* actions get the penalty.

**Two-part fix:**

1. **Rename the cost labels** to be unambiguous:
   - `cost: '−1D MAP if 2nd'` → `cost: 'declare 2nd → both at −1D'`
   - For `move`: same treatment.

2. **When the user actually declares a second action, the button labels of *all* declared actions update to show their effective dice pool**, not just the abstract MAP cost. E.g., if first action is `ATTACK · 5D+2` and second is `DODGE`, both buttons render as `ATTACK · 4D+2 effective` and `DODGE · 4D effective`.

The v3 already shows `2 actions · MAP −1D each` as a warning chip at ~line 1112 — preserve that. The fix is making the individual button labels at lines 102-111 echo the same effective-pool reality.

**Acceptance criteria:**
- Action cost labels read in plain language: "declare 2nd → both at −1D" (no ambiguity).
- When a second action is declared, the effective dice pool is shown on each action button.
- Sandbox test asserts the cost label string and the effective-pool computation.

---

### 3.6 H2 — AIM is not "free"

**Files touched:** `map_v3/combat-theater.jsx`.

**Change:** Line 105 currently:

```js
{ id: 'aim', label: 'AIM', icon: '⦿', enabled: true, cost: 'free · +1D next' },
```

Replace with:

```js
{ id: 'aim', label: 'AIM', icon: '⦿', enabled: true, cost: '1 action · +1D next round' },
```

**Optional extension (recommended):** support multi-round AIM accumulation in the cost display. The engine caps AIM at +3D after 3 rounds. Track aim rounds in the sample data and progress the label:

- Round 1 of aim → `1 action · +1D next round`
- Round 2 of aim → `1 action · +2D next round`
- Round 3 of aim → `1 action · +3D next round (capped)`

Implement only if the sample state can carry an `aim_rounds_held` counter; otherwise ship just the static rename and add a comment pointing to the engine source.

**Acceptance criteria:**
- AIM cost label reads `1 action · +1D next round`, not `free`.
- (If extension shipped) The label updates as AIM is held across rounds, capping at +3D.

---

### 3.7 H5 — FP rendering without hard cap

**Files touched:** `drop_v2/prototype/ground.jsx`.

**Change:** Line 37: `fp_max = 3` (default). Remove the denominator concept entirely. Replace the `fp/fp_max` constellation render with a count-of-glyphs render:

- Show one lit glyph (`●`) per current FP.
- Show 1-2 empty glyphs (`○`) for visual "headroom" (so the display has consistent width even at FP=0 or FP=1).
- No `/N` denominator anywhere.
- If FP exceeds 7 (rare edge case), show as `●×8 FP` or similar compact form.

Brian's stated preference is the glyph option (a) not the integer option (b). Implement (a).

The accompanying state:

- Remove the `fp_max = 3` constant.
- Remove any `Math.min(fp, fp_max)` clamps that would hide actual FP.
- The HUD chip just shows lit glyphs plus the headroom — no maximum implied.

**Acceptance criteria:**
- `grep -nE "fp_max|fpMax" drop_v2/prototype/ground.jsx` returns zero hits (except in deleted-line markers in version control).
- FP=0 renders as `○○○` (3 empty headroom slots).
- FP=2 renders as `●●○○○` (2 lit + 3 empty headroom).
- FP=5 renders as `●●●●●○○` (5 lit + 2 empty headroom).
- FP=10 renders as either `●●●●●●●●●●` or `●×10 FP` (designer's call — recommend the compact form for high counts).
- Sandbox test asserts no denominator rendering and correct glyph counts at multiple FP values.

**Note:** the `sheet-v2.jsx:30` line also has `fpMax: 5`. Apply the same treatment there. The sheet should show the same growing-constellation pattern.

---

### 3.8 H6 — Damage/stun terminology cleanup

**Files touched:** `map_v3/combat-theater.jsx`, plus any pose text using stun or wound terminology.

**Changes:**

1. **`map_v3/combat-theater.jsx:31`** — "1 stun applied" → `+1 stun · −1D actions for 1 round`. Always show the mechanical effect.
2. **Anywhere stuns accumulate** (the running total in sample state), show `Stuns: N · −ND actions until next round`. Never bare "1 stun" or "Stunned" without the mechanical caveat.
3. **Wound transitions** keep the correct ladder labels (post-B4 canonicalization), e.g. `→ WOUNDED ×2 (−2D actions)`.
4. **Distinguish wound state from stun state explicitly** in the damage event rendering. A damage event that causes a wound transition is rendered separately from a damage event that adds a stun. The current rendering can conflate these visually; split into two distinct event icons / colors.

**Acceptance criteria:**
- Stun-caused damage events always show `+N stun · −ND actions for N round(s)`.
- Wound-caused damage events always show `→ <wound-state> (mechanical penalty)`.
- The two event types are visually distinct in the damage feed.
- Sandbox test asserts both rendering paths.

---

### 3.9 M2 — Pose-log room-enter row de-emphasis

**Files touched:** `drop_v2/prototype/pose-log.jsx`.

**Change:** Lines 92–106 currently render the room-enter event as a large display-font banner ("YOU ARE IN [ROOM NAME] [SECURITY] [ZONE]"). Per the review, this duplicates the room context panel and pushes content off-screen.

Replace with a smaller, dim mono line:

```
→ entered Docking Bay 94 (SECURED)
```

- Font: mono, ~13–14px (matches other pose-log event lines).
- Color: dim (per the §4.6 `_DIM` palette).
- An arrow glyph (`→`) leads the line.
- The security tag in parens uses the §4.6 palette (`SECURED` in green, `CONTESTED` in yellow, `LAWLESS` in red).

The room *context panel* (vision §6.2) is the full source of room info; the pose-log only marks the transition.

**Acceptance criteria:**
- Room-enter rows render as a single ~14px mono line, not a display headline.
- The security tag color matches §4.6.
- Sandbox test asserts the row height is under 24px and the text content matches the new format.

---

### 3.10 M4 — Initiative ladder Perception label

**Files touched:** `map_v3/combat-theater.jsx` (InitiativeLadder component, referenced but not viewed in the original review — find by symbol grep at execution time).

**Change:** Wherever initiative values are rendered as bare numbers (e.g. `18`, `14`), label them as Perception rolls:

- Inline label: `Perception 18` or `init roll 18` (designer's call — recommend `init roll 18` to keep the column narrow).
- Tooltip on hover: `Perception roll · determines turn order this combat`.

**Acceptance criteria:**
- No bare integer initiative values in the InitiativeLadder.
- Tooltip is present.
- Sandbox test asserts the label string and tooltip text.

---

### 3.11 M5 — Stun mechanic explicit in damage outcomes

**Folds into H6.** No separate fix; the H6 acceptance criteria cover M5's stun ambiguity.

---

### 3.12 L1 — Wuher hostility tag

**Files touched:** `map_v3/data-mos-eisley.jsx`.

**Change:** Line 105: `kind: 'hostile'` → `kind: 'neutral'`. Wuher is gruff, not aggressive.

**Acceptance criteria:**
- Wuher NPC entry has `kind: 'neutral'`.
- Sandbox test asserts the field value.

---

### 3.13 L2 — Garrison → civic building rename

**Files touched:** `map_v3/data-mos-eisley.jsx`.

**Change:** Line 52: `"Garrison"` → `"Republic Outpost"` (recommended; minimal CW footprint on the planet but plausible) or `"Civic Hall"` (era-neutral).

Default: `Republic Outpost`. Aligns with the news ticker calling out Republic patrols (B3 holonet fix).

**Acceptance criteria:**
- `grep -nE "Garrison" map_v3/data-mos-eisley.jsx` returns zero hits.
- The new label appears.

---

### 3.14 L3 — Wound label string canonicalization

**Files touched:** All files rendering wound state.

**Change:** Per the canonical `WOUND_RUNGS` from B4 — every site that renders a wound label uses the canonical string. No `KILLED` (sheet-data.jsx), no `Mortal` (sheet-v2.jsx). Always full `MORTALLY WOUNDED` or canonical short form.

Audit-grep at execution time for all wound-label strings; verify each renders from `WOUND_RUNGS.find(r => r.v === N).label`, not from a literal.

**Acceptance criteria:**
- No literal wound strings outside the shared `WOUND_RUNGS` source.
- Sandbox test loads each file using wound rendering and asserts the rendered string matches `WOUND_RUNGS[tier].label`.

---

### 3.15 L4 — Docking Bay 94 cover consistency

**Files touched:** `map_v3/combat-theater.jsx` (pose text at lines 30, 42).

**Change:** Pose text references "loading crates" and "cargo lifter" as cover, but the Docking Bay 94 landmark illustration shows fuel cells, blast doors, and the circular pit. Reconcile in the pose text:

- Line 30: `"ducks behind the loading crates"` → `"ducks behind the stack of fuel cells along the back wall"`
- Line 42: `"drops to one knee behind the cargo lifter"` → `"drops to one knee in the shadow of the blast doors"`

Both new pose-text choices are consistent with the LM_DockingBay94 illustration in `map_v3/assets-landmarks.jsx`.

**Acceptance criteria:**
- New pose text matches landmark features visible in the LM_DockingBay94 illustration.
- Sandbox test asserts the new strings.

---

### 3.16 L5 — Canonical demo character

**Files touched:** Sample data across multiple files.

**Change:** Standardize on **Tey Voss** as the public-facing demo character (per the review's recommendation — Tey Voss already appears in more places). Replace `Tundra Vex` in `drop_sheet_v2/prototype/sheet-data.jsx` (and any other isolated-demo file) with Tey Voss. Maintain consistency across:

- `map_v3/sheet-v2.jsx` — already Tey Voss; preserve.
- `drop_sheet_v2/prototype/sheet-data.jsx` — change Tundra Vex → Tey Voss.
- Any other demo sample with a different name: change to Tey Voss.

Internal-only sheet variants can stay as Tundra Vex (this is the "internal use" path the review allows for).

**Acceptance criteria:**
- All public-facing demos use Tey Voss.
- Sandbox test asserts the demo character name across all relevant files.

---

## 4. Drop structure

### 4.1 Files modified (estimated)

| Path | Δ LOC est. | Purpose |
|---|---|---|
| `drop_v2/prototype/ground.jsx` | ~−40 / +5 | B2 (StanceChip removal), B3 (2 era fixes), H5 (FP) |
| `drop_v2/prototype/space.jsx` | ~+0 / ~10 lines edited | B3 (heavy era substitution) |
| `drop_v2/prototype/combat-hud.jsx` | ~+0 / ~10 lines edited | B3 (TIE → Vulture) |
| `drop_v2/prototype/tokens.jsx` | ~+0 / ~3 lines edited | B3 (NEW finds) |
| `drop_v2/prototype/pose-log.jsx` | ~−10 / +5 | M2 (room-enter row) |
| `drop_sheet_v2/prototype/sheet-data.jsx` | ~+0 / ~1 line edited | L5 (Tundra → Tey) |
| `map_v3/combat-theater.jsx` | ~+50 / ~5 lines edited | B1 (pass button — 2 sites), H1 (MAP), H2 (AIM), H6/M5 (damage/stun text), L4 (pose text) |
| `map_v3/sheet-v2.jsx` | ~+0 / ~10 lines edited | B3 (3 era fixes), B4 (wound ladder), H5 (fpMax echo) |
| `map_v3/holocron.jsx` | ~+0 / 1 line edited | B3 (ISB → SBI) |
| `map_v3/holonet.jsx` | ~+0 / 1 line edited | B3 (Imperial Patrol → Republic Patrol) |
| `map_v3/assembled-client.jsx` | ~+0 / 1 line edited | B3 (Sealed Imperial Disp.) |
| `map_v3/assets-landmarks.jsx` | ~+0 / 2 comments edited | B3 (Imperial-style civic) |
| `map_v3/map-navigator.jsx` (or wherever InitiativeLadder lives) | ~+0 / a few lines | M4 (Perception label) |
| `map_v3/data-mos-eisley.jsx` | ~+0 / 2 lines edited | L1 (Wuher), L2 (Garrison) |
| `map_v3/tokens.jsx` | ~+20 (NEW file) | B4 (shared WOUND_RUNGS source) |

**Total LOC delta: ~+80 added, ~−50 deleted, ~50 lines edited in place.** Small drop by codebase standards.

### 4.2 New files

- `map_v3/tokens.jsx` — small shared constants file holding `WOUND_RUNGS` (and any future shared map_v3 tokens). Mirrors the `drop_v2/prototype/tokens.jsx` pattern.

### 4.3 Deleted code

- `drop_v2/prototype/ground.jsx` — the `StanceChip` component definition and all its plumbing. ~30 lines of code + ~10 lines of supporting hooks/comments.

### 4.4 What does NOT ship in this drop

- The Phase 1 protocol substrate (drops 1.1–1.5 from vision §9). Separate work.
- The Force panel (vision §6.13) — deferred to a sheet redesign drop.
- The dynamic comms tab list — deferred to Phase 2 Drop 2.5.
- The renderer-integrated mini-map — deferred to Phase 3.
- Region panel (vision §6.2.1), typed news events (§6.10.1), contests sub-tab (§6.11.1) — those are Drop 2.11/2.12/2.13 per vision §9.
- Any change to `static/client.html`. The production port is the next drop after Brian signs off on this one.

### 4.5 Production port — what comes after

After Brian reviews the fixed JSX, **Tier 1 #4** opens:

- Port the fixed `map_v3/` JSX into `static/client.html` as the new SPA structure.
- Preserve the existing `static/client.html` functionality (chargen, login, command rail, current HUD) while replacing the visual surface.
- Wire to the existing WebSocket message stream.
- Smoke-test end-to-end against the in-process harness.

This is its own drop, not part of this one. The SPA port is multi-session if done thoroughly.

---

## 5. Drop execution plan

### 5.1 Recommended drop sequencing (one drop)

The 18 in-scope fixes are independent enough that they can all land in **one drop**. No fix depends on another except:

- B4 (wound ladder canonicalization) creates `map_v3/tokens.jsx`. L3 (wound label canonicalization) consumes it. **Land B4 first within the drop, then L3.**
- B3 (era contamination) is the bulkiest substitution pass. Land it as one cohesive sub-batch so the era audit grep test can run against the cleaned-up state in one shot.

### 5.2 Sub-batching within the drop

Suggested intra-drop ordering for engineering Claude:

1. **Sub-batch A — Wound ladder unification** (B4 → L3): create `map_v3/tokens.jsx`, update `sheet-v2.jsx`, refactor all wound-label consumers.
2. **Sub-batch B — B2 StanceChip removal** (B2): single-file delete + cleanup in `ground.jsx`.
3. **Sub-batch C — B1 pass-button**: edit `combat-theater.jsx` two sites (declaration + posing) + keyboard handler.
4. **Sub-batch D — Era contamination sweep** (B3): seven files, ~30 text substitutions. Single grep-driven pass with the substitution table from §3.3.
5. **Sub-batch E — Combat-theater mechanics clarifications** (H1, H2, H6, M4, M5): all in `combat-theater.jsx`.
6. **Sub-batch F — FP unhardening** (H5): `ground.jsx` and `sheet-v2.jsx` glyph constellation.
7. **Sub-batch G — Polish** (M2, L1, L2, L4, L5): small text edits across files.

After each sub-batch, run the relevant slice of the sandbox tests (see §6). The full drop is acceptance-tested as a unit.

### 5.3 Pre-flight checks (mandatory before code writing)

Engineering Claude must, before any code change:

1. Read this design doc end-to-end.
2. Read `design_review_may24_v1.md` end-to-end (the source review).
3. Read `web_client_vision_and_protocol_v1_3.md` §3.15 (canonical command list), §4.6 (palette + security duality), §10.10 (era-fidelity checklist), §10.11 (SYN deltas checklist).
4. Grep HEAD for every cited line number in §2.1 to verify nothing has shifted since this doc was written (drop_v2 + map_v3 files in the UI/UX zip).
5. Confirm `map_v3/composition-engine.jsx:56` and `map_v3/map-navigator.jsx:17-89` are the only false positives for the era-contamination grep — any new false positives go in the test allowlist.

### 5.4 Apply instructions (Windows dev box)

Mirrors the standard drop pattern:

1. Engineering Claude produces a zip mirroring the JSX files in their original directory structure.
2. `Expand-Archive -Force` the zip into the project root (or wherever the UI/UX working copy lives).
3. Verify modified files contain expected hooks per the substitution table in §3.3 and the changes catalogued in §3.1–§3.16.
4. Run the JSX sandbox tests (per §6).
5. Visual smoke: open the design canvas HTML files (`Field Kit Prototype.html`, `SW MUSH Redesign.html`, `Sheet Redesign Options.html`) and confirm each demo renders correctly with the fixes applied.

### 5.5 Drop discipline reminders

- **Explicit `encoding='utf-8'`** on any file write per the standing rule.
- **One self-contained drop** — implement, test, zip, handoff. Do not ship partial work.
- **Pre-flight grep before code writes** per architecture v50 §5.9 § (the SYN-sequence roll-up discipline scaled down to a single drop).
- **Test before zipping** — sandbox tests pass on Windows dev box before declaring done.
- **Handoff document** — a `HANDOFF_<date>_UI_BUGFIX.md` accompanies the zip, capturing the per-fix change list, the test results, and any interpretive calls made during execution.

---

## 6. Test plan

### 6.1 Test infrastructure

The existing test harness (`tests/` directory) is Python-driven; the JSX in `drop_v2/` and `map_v3/` is prototype-only and not currently exercised by Python tests. For this drop, **tests are written as standalone Node-runnable JSX assertions** that the engineering Claude can execute in the sandbox.

Each fix in §3 has a corresponding assertion or set of assertions. Suggested file: `tests/ui/test_design_drop_fixes.jsx` (or equivalent), with one test per fix:

```jsx
// tests/ui/test_design_drop_fixes.jsx

describe('B1 — pass button', () => {
  test('DeclarationBody includes pass entry', () => { /* ... */ });
  test('PosingBody shows ACCEPT AUTO-POSE button', () => { /* ... */ });
  test('Ctrl+P shortcut sends pass during posing', () => { /* ... */ });
});

describe('B2 — StanceChip removal', () => {
  test('ground.jsx has no StanceChip import or render', () => { /* ... */ });
  test('grep returns zero stance references', () => { /* ... */ });
});

// ... one describe block per fix
```

Total estimated test count: **~30 assertions across 18 in-scope fixes**.

### 6.2 Grep-based regression tests

Several fixes are best verified by grep regression tests, mirroring the field_kit_design_decomposition_v2.md §9 pattern:

```bash
# B2 — no stance
! grep -nE "StanceChip|stance.*chip|stance_chip" drop_v2/prototype/ground.jsx

# B3 — no era contamination (excluding allowlisted false positives)
! grep -inE "\b(Empire|Imperial|Rebel|Rebellion|Stormtrooper|TIE/|TIE-|TIE\b|X-wing|Vader|Death Star|ISB|Imperial Security Bureau|stormtroop)\b" \
    drop_v2/ map_v3/ \
    | grep -vE "(TIER|tier:|TIER_DEFS|tier_index|class.*tier|Tier [0-9])"

# H5 — no fp_max / fpMax
! grep -nE "fp_max|fpMax" drop_v2/prototype/ground.jsx

# L2 — no Garrison
! grep -n "Garrison" map_v3/data-mos-eisley.jsx
```

These greps go in a `tests/ui/grep_regressions.sh` (or PowerShell equivalent) that the drop tests against before zipping.

### 6.3 Visual smoke

After the drop applies, manually open the three demo HTML files in a browser:

1. **`Field Kit Prototype.html`** — verify StanceChip is gone, FP renders without denominator, era references are scrubbed.
2. **`SW MUSH Redesign.html`** — verify combat-theater shows pass button, MAP/AIM labels are unambiguous, wound ladder shows 7 rungs, news ticker shows "Republic Patrol", inventory shows "Sealed Senate Disp."
3. **`Sheet Redesign Options.html`** — verify sheet renders Tey Voss with the 7-rung wound ladder.

A 5-minute visual pass after the test suite green-lights.

### 6.4 Acceptance criteria for the drop as a whole

- ✅ All 18 in-scope fixes have a corresponding test assertion.
- ✅ All grep regression tests pass (zero unexpected hits).
- ✅ Visual smoke confirms each demo renders correctly.
- ✅ No engine (Python) file is modified.
- ✅ Drop zip is project-root-mirrored per the standard pattern.
- ✅ `HANDOFF_<date>_UI_BUGFIX.md` is included in the zip with the per-fix change list and test results.

---

## 7. Risks and open questions

### 7.1 Risks

**Risk 1 — Line numbers shift between this design and execution.** The JSX files are still being touched in other parallel work (unlikely but possible). Mitigation: §5.3 pre-flight requires re-grepping cited lines before code writes. Any shifted lines get re-located by symbol.

**Risk 2 — Cross-directory imports in the prototype.** B4 proposes importing `WOUND_RUNGS` from a shared source. If the prototype harness doesn't support cross-directory imports, the fallback is to duplicate the constant in `map_v3/tokens.jsx` (per the §3.4 design). Either way, the source-of-truth discipline is preserved.

**Risk 3 — The Ctrl+P keyboard shortcut (B1) conflicts with a browser shortcut.** Ctrl+P is browser print. Test on Firefox + Chrome + Safari; if conflict is non-trivial, fall back to Alt+P or just rely on the button click (no keyboard shortcut at all). This is a minor degradation if dropped.

**Risk 4 — Some era-contamination substitutions are interpretive.** For example, "Republic Patrol" vs "Trade Federation Scouts" vs "Bounty Hunter Posse" for the Jundland anomaly — engineering Claude picks one. Per the review's Path B framing, Brian accepts that engineering Claude will make some interpretive calls. The handoff doc captures every interpretive choice for Brian to override if desired.

**Risk 5 — The H6/M5 split between wound state and stun state may require a sample-data refactor beyond the simple labeling change.** If the existing sample state doesn't separate `wound_level` and `stun_count`, this drop introduces that separation. Manageable but slightly larger than the other fixes.

### 7.2 Open questions

**Q1 — H4 (Force panel) actually low-hanging?** The review puts H4 as Phase 2 work. But if the engineering work to add a conditional Force panel block to `sheet-v2.jsx` is small (~20 lines of JSX, gated on `forceSensitive: true`), it could fold into this drop. Engineering Claude's call after looking at the file.

**Recommendation:** If H4 is ≤30 lines of JSX, fold in. Otherwise defer.

**Q2 — L5 Tundra Vex / Tey Voss — keep both?** The review says standardize on Tey Voss for public demos and keep Tundra Vex for internal-only sheet examples. But it's not clear what "internal-only" means here — the prototype isn't split that way today. Default: standardize on Tey Voss everywhere; document Tundra Vex as available for future use.

**Q3 — The Lando reference in `sheet-data.jsx:126`** — leave or replace? Per §3.3 default: leave. The review flagged it as OT-coded but didn't put it in the era-contamination table. Document as polish; revisit if Brian wants.

**Q4 — Does the production port (Tier 1 #4) share the test infra with this drop, or stand up its own?** Recommend the production port writes Python-level integration tests against `static/client.html` while this drop's JSX tests stay scoped to the prototype directory. Two test surfaces, two purposes.

---

## 8. Companion documents

| Document | Status | Purpose |
|---|---|---|
| `design_review_may24_v1.md` | Reference | The 24-item issue catalog (source of truth) |
| `web_client_vision_and_protocol_v1_3.md` | Reference | The design-of-record (panels, palette, protocol) |
| `HANDOFF_MAY25_SYN10.md` | Reference | UI-pivot bridge content (data contracts, palette) |
| `sw_d6_mush_architecture_v50.md` | Architecture | §3.2 names this as Tier 1 #3 |
| `field_kit_design_decomposition_v2.md` | Reference | Earlier prototype-to-production decomposition (precedent for the grep-test pattern) |
| `field_kit_audit_and_remediation_v1.md` | Reference | The F1–F17 audit that the May 24 review built on |
| `GCW_AUDIT_REPORT.md` | Reference | Era-contamination methodology (substitution + structural + intentional pattern) |
| `HANDOFF_<date>_UI_BUGFIX.md` | OUTPUT | Engineering Claude's handoff after drop execution |

---

## 9. What this drop unblocks

After Brian signs off on the fixed JSX:

- **Tier 1 #4** — production port to `static/client.html` begins. Largest single piece of frontend work pre-launch.
- **Vision Phase 1 substrate drops (1.1–1.5)** can begin in parallel — they're protocol work, not visual work, and don't depend on the JSX.
- **Vision Phase 2 panel build-out** can be planned with a clean reference visual (the fixed JSX) instead of a contaminated one.
- **Claude Design re-engagement** (per vision §10.9 / §10.11) can use the fixed JSX as the new reference for any future visual work.

---

*End of bug-fix sprint design. Ready for engineering Claude execution.*
