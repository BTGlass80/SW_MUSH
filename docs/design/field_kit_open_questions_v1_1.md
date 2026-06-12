# Field Kit Design — Open Questions Resolution v1.1

**Companion to:** `field_kit_design_decomposition_v1.md`
**Supersedes:** `field_kit_open_questions_v1.md` (all five decisions resolved)
**Generated:** April 24, 2026
**Resolution authority:** Brian (April 24, 2026)
**Guiding principle invoked:** Stay true to WEG D6 R&E — house rules are tolerated only where the source is silent or the engine demands a deliberate departure.

---

## Resolutions Summary

| # | Question | Resolution | Net effect |
|---|---|---|---|
| **D1** | Should F7 (StanceChip) ship? | **REMOVE F7 — not WEG** | Prototype scope reduces by 1 finding |
| **D2** | Add `combat_state.theatre` field? | **ADD** (small server change before Drop D) | Drop D unblocked; clean theatre signal |
| **D3** | Drop B scope — player commands too? | **Option 3** — NPC/Director/system in B; player commands in follow-up B′ | Drop B stays at 6–8 hrs; B′ scheduled separately |
| **D4** | Stance modifier values | **REMOVE — moot** (F7 is gone) | n/a |
| **D5** | `pose_event` deduplication key | **Option 1** — composite `speaker_id:timestamp_ms:text_hash` | Documented spec for Drop B |

---

## D1. F7 StanceChip — REMOVED (not WEG)

### What the prototype does

The Field Kit v2 prototype includes a `StanceChip` in the ground HUD that cycles three values: `cautious`, `standard`, `all-out`. The chip emits a `stance <value>` command to the parser. The prototype's intent: a persistent, round-spanning posture modifier separate from per-action declarations.

### WEG verification

Searched the canonical R&E rulebook (`WEG40120.pdf`, the *Star Wars Roleplaying Game, Second Edition, Revised and Expanded*) and the *Imperial Sourcebook* (`WEG40092.pdf`) for terminology:

| Term | Hits in R&E | Hits in Imperial SB | Verdict |
|---|---|---|---|
| `stance` | 0 (rules) | 3 (narrative — "official stance of the Empire", "cautiously") | **Not a mechanic** |
| `cautious` | 0 (rules) | 0 (rules) | Not a mechanic |
| `all-out` | 0 | 0 | Not a mechanic |
| `berserk` | 0 | 0 | Not a mechanic |
| `defensive posture` | 0 | 0 | Not a mechanic |
| `aggressive posture` | 0 | 0 | Not a mechanic |

**Conclusion:** Per-round combat stance is not a WEG D6 R&E mechanic. The closest things WEG has are:

- **Full Reaction** (R&E line 2458): "A reaction skill can also be used for a 'full reaction'" — `dodge` becomes `fulldodge`, `parry` becomes `fullparry`, etc. This is **per-declaration**, not per-stance.
- **Aim / Preparation** (R&E line 6380): aiming at a target for one or more rounds gives a bonus to the next attack. Per-action, time-spent.
- **Multiple Action Penalty** (engine-verified): -1D per additional declared action beyond the first.

These are all per-action declarations, not posture modes. WEG's combat declaration model **is** the stance system — the buttons in Drop D's `GroundDeclarationPanel` already carry the stance signal.

### Decision

**REMOVE F7 from scope.** The prototype's StanceChip is a UI invention that doesn't correspond to a WEG mechanic. Shipping it would either:

1. Be inert (no engine effect), making it false advertising in the UI; or
2. Require house-rule modifiers (D4) that depart from R&E without justification.

Both options violate the WEG-fidelity guiding principle.

### What replaces F7

**Nothing — and that's fine.** The 8-button declaration panel (`attack`, `dodge`, `fulldodge`, `parry`, `cover`, `move`, `aim`, `pass`) already gives players the stance-equivalent expression WEG supports:

- Want a "cautious" round? Declare `fulldodge` or `cover`.
- Want an "all-out" round? Declare `attack` with `aim` from the previous round (or just multiple attacks accepting the MAP penalty).
- Want a "standard" round? Declare `attack` once.

No persistent state needed; no chip needed.

### Document-level effect

- v32 §16F: F7 row removed from the 14-finding table → **13 findings** total
- `field_kit_design_decomposition_v1.md` Drop C: remove the `StanceChip` integration point; Drop C effort drops from 5–7 hrs to **4–5 hrs**
- The acceptance criteria for Drop C should drop the F7 line and instead add: *"No StanceChip / stance-mode UI present (F7 removed per WEG fidelity)."*
- v32 §19 Priority A1 effort estimate revised: **~26–37 hrs total** (was 28–40)

---

## D2. `combat_state.theatre` field — ADD

Small server-side prerequisite for Drop D.

### What to add

In `engine/combat.py`:

1. Add a `theatre` attribute to `CombatInstance` — string literal `'ground'` or `'space'`. Default `'ground'`.
2. Set it in the constructor based on context — `parser/combat_commands.py` paths set it to `'ground'`; `parser/space_commands.py` space-combat-resolution paths set it to `'space'`.
3. Add it to `to_hud_dict()` at line 471 — extend the returned dict with `"theatre": self.theatre`.

### Why

The decomposition's Drop D needs to dispatch between the cyan space-combat HUD (`combat-hud.jsx`) and the amber ground-combat HUD (`ground-combat-hud.jsx`). Without `theatre`, the client has to reverse-engineer which mode it's in — fragile coupling between `space_state` and `combat_state`.

A single explicit field at the source is the right primitive.

### Effort

~15 minutes server-side, plus the test that asserts the field is present in both space and ground combat instances (~15 minutes). Total: **30 minutes**, included in Drop D's 8–12 hour estimate.

### Risk

Backward compat: existing combat_state consumers don't read `theatre`, so adding the field is non-breaking. The tests that lock combat_state shape will need their assertion lists extended to include `theatre`; ~5 minutes of test maintenance.

---

## D3. Drop B Scope — NPC/Director/System First, Player Commands as Drop B′

Per recommendation. **Drop B as currently scoped covers:**

- `engine/director.py` — ambient narration paths
- `engine/hazards.py` — hazard tick messages
- Room broadcast paths
- `ai/npc_brain.py` — NPC dialogue
- `engine/encounter_*.py` — encounter narration (boarding already typed; rest pending)
- `engine/combat.py` — combat narration outside the existing posing panel

**Drop B′ (separate session, scheduled after Drop B lands) covers:**

- Player `say` / `sayit` commands
- Player `pose` / `:` shorthand
- Player `whisper`
- Player `mutter`
- Any other player-issued narration commands

### Rationale

The "Room says..." mis-render bug — the actual user-visible problem — lives in the NPC/Director/system narration paths. That's where the misclassification regex bites. Player-issued narration is already attributed correctly ("you pose:", "Test Jedi says:"), so migrating those is consistency work, not bug fix work.

Splitting prevents Drop B from ballooning into a 14-hour session that touches every narration emit site. The bug fix lands in 6–8 hours; the consistency pass follows when convenient.

### Document-level effect

- `field_kit_design_decomposition_v1.md` Drop B: scope confirmed as currently written
- Add a note: **Drop B′ exists and is scheduled after Drop B lands.** Effort: ~3–4 hrs.
- v32 §19 Priority A1: Drop B′ added as a sub-bullet under Drop B with its own effort line

---

## D4. Stance Modifier Values — MOOT

Resolved by D1. F7 is removed; no stance system exists; no modifiers needed. v32 §16F should not contain any "stance" reference at all.

---

## D5. `pose_event` Deduplication Key — Composite

Per recommendation. Canonical form:

```python
def make_dedup_key(speaker_id: int | None, text: str, timestamp_ms: int) -> str:
    """Composite dedup key. Cheap to compute, no server-side state needed.

    Handles the actual dedup case (room broadcast + speaker self-echo arriving
    within milliseconds) without false positives on rapid-fire identical poses.
    """
    speaker_part = str(speaker_id) if speaker_id is not None else "system"
    text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{speaker_part}:{timestamp_ms}:{text_hash}"
```

### Behavior

- **True duplicate** (same speaker, same text, same millisecond): same key → client suppresses second arrival
- **Rapid-fire identical pose** (speaker says "hmm." three times across 800ms): three different keys (different `timestamp_ms`) → all three render, as intended
- **System events** without a speaker: `speaker_part = "system"`, still uniqued by timestamp+hash

### Client-side dedup window

Suggested: 250ms. Two pose_events with the same `dedup_key` arriving within 250ms of each other → suppress the second. Past 250ms, treat as legitimate distinct events.

### Document-level effect

`field_kit_design_decomposition_v1.md` Drop B should incorporate this in the §4 schema definition. The `make_pose_event()` builder in `engine/pose_events.py` (new file) auto-computes `deduplication_key` if not supplied.

---

## Net Updates to the Decomposition Doc

Apply these specific edits to `field_kit_design_decomposition_v1.md`:

### Edit A — Drop C scope (§5)

Remove F7 from the bullet list. The new Drop C scope is:
- F1 Wound ladder rebuild (7 rungs)
- F5 FP dots clamp at fpMax
- F8 Stun cap from STR.dice
- F10 Wound ladder penalty alignment

Effort revised: **4–5 hrs** (was 5–7).

### Edit B — Drop D server-side prerequisites (§6)

Replace:
> `combat_state` payload should include `pose_window_seconds` (already happens? verify in `engine/combat.py` posing window emit)

With:
> `combat_state` payload includes `pose_deadline` ✅ confirmed at `engine/combat.py:560` (ISO-8601 UTC string, not seconds-remaining; client computes countdown locally each tick).
>
> `combat_state.theatre` field is **NEW for v32** — must be added to `engine/combat.py:CombatInstance.to_hud_dict()` before client integration. Set `'ground'` for parser/combat_commands paths, `'space'` for parser/space_commands resolution paths. ~30 minutes server change.

### Edit C — Drop D acceptance (§6)

Add line:
> `combat_state.theatre` field present in both ground and space combat fixtures. Tests verify `theatre == 'ground'` for ground-room combats and `theatre == 'space'` for ship-vs-ship combats.

### Edit D — F7 removal in §2 finding table (the 14-finding summary)

Remove the F7 row entirely. Update the header to "13 findings resolved" (was 14).

### Edit E — Drop B note about player-command migration

After the migration checklist in §4, add:
> **Drop B′ — Player Command Narration Migration** (separate session, scheduled after Drop B lands; ~3–4 hrs):
> - `say` / `sayit` commands
> - `pose` / `:` shorthand
> - `whisper`
> - `mutter`
>
> Drop B′ is consistency work, not bug fix work. Player-issued narration is already attributed correctly today; migrating is so the entire narration pipeline goes through one typed code path.

### Edit F — Drop B schema (§4)

Update the `make_pose_event` signature to include the canonical dedup key:

```python
def make_pose_event(
    speaker: str,
    text: str,
    *,
    speaker_id: int | None = None,
    mode: str = 'pose',
    to: str | None = None,
    timestamp_ms: int | None = None,
    deduplication_key: str | None = None,
) -> dict:
    """If timestamp_ms is None, uses time.time() * 1000.
    If deduplication_key is None, computes composite from
    speaker_id, timestamp_ms, sha1(text)[:8].
    """
    ...
```

Client-side dedup window: **250ms**.

### Edit G — Total effort revised

Top of doc says "~28–40 hours total". Revise to **~26–37 hours total** (Drop C lost ~1–2 hrs from F7 removal).

---

## Updates to v32 §16F

Apply these specific edits to `sw_d6_mush_architecture_v32.md`:

### Edit H — Finding count

Change `**14 findings resolved in v2 prototype**` to `**13 findings resolved in v2 prototype** (F7 stance UI dropped from scope per WEG fidelity — see Open Questions §D1)`.

### Edit I — F7 row removed

Remove the F7 row from the 14-finding table.

### Edit J — Drop C effort

Change Drop C effort cell from `5–7 hrs` to `4–5 hrs`.

### Edit K — Total

Change the Priority A1 total from `~28–40 hrs total` to `~26–37 hrs total`.

### Edit L — Add Drop B′

Under the 5-drop table, add a 6th row for Drop B′:

| **B′ — Player Command Narration Migration** | Migrate `say`/`pose`/`whisper`/`mutter` narration to typed `pose_event`. Consistency follow-up to Drop B. | 3–4 hrs | — |

This makes Priority A1 actually 6 drops at ~29–41 hrs (B + B′ split). Decompose intent unchanged.

### Edit M — Add WEG-fidelity invariant note

Add to v32 §16F a closing note:

> **WEG-fidelity invariant for Field Kit work:** UI features must correspond to a WEG D6 R&E mechanic or a documented house rule with explicit reasoning. The prototype's `StanceChip` was removed in this rollup because per-round stance is not a WEG mechanic and the action declaration system already provides stance-equivalent expression (`dodge`/`fulldodge`/`parry`/`fullparry`/`aim`). This invariant applies to all future Field Kit additions.

---

## Updates to v32 §19 Priority A1

Single edit:

> Priority A1 effort: ~28–40 hrs → **~29–41 hrs** (split into 6 drops with B + B′; F7 removed)

---

## Memory Edits

Per Section 5 P4 of v1: don't pre-emptively update memory. After Drop A actually lands, suggest adding:

> "Field Kit Design implementation in flight per architecture v32 §16F. F7 (stance) was dropped from scope (not WEG). Drop A landed [date]. Other Sonnet sessions should check `field_kit_design_decomposition_v1.md` and `field_kit_open_questions_v1.md` before starting UI/UX work."

---

## What the Parallel Chat Should Do With This Document

1. Read `field_kit_design_decomposition_v1.md` first.
2. Apply Edits A–G to it as in-place corrections during Drop A (the tokens drop is the cheapest place to make doc edits stick — open the file once, fix everything, commit).
3. Reference the resolved D1–D5 picks above when a question comes up. No backtracking required.
4. If a 6th unresolved question surfaces during implementation, surface it back to this Opus chat for a decision rather than guessing.

---

*End of Open Questions Resolution v1.1*
