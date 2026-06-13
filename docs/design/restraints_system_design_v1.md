# Restraints / Handcuffs — Design v1

**Status:** PROPOSAL → BUILD (resolves `CRAFT.HOOK.restraints_state_model`).
**Author:** Claude Opus 4.8 (1M), 2026-06-13, under the decide+build charter.
**PvP norm (Brian-decided):** **consent/defeat-gated** — a PC may only cuff
another PC who CONSENTS or who has been DEFEATED (incapacitated in combat). Never
a healthy unwilling PC.
**Posture:** conservative balance (tight escape, no grief vectors); features-first.

---

## 1. What exists at HEAD (verified)

- **Ephemeral combat grapple** — `Combatant.restraint` (`engine/combat.py:256`), a
  per-combat hold dict `{grappler_id, kind, hold_damage, source}` set by creature
  constriction special-attacks (`engine/creature_special_attacks.py` `_csa`).
  Combat-only, NOT persisted, cleared when combat ends. Penalizes the held actor's
  attack pool (`combat.py:1119`) and blocks fleeing (`combat.py:1921`).
- **Wound/defeat state** — `WoundLevel` IntEnum (`character.py:33`):
  `INCAPACITATED = 4` is the "defeated, can't act" threshold.
- **Per-char persistent state** rides the `characters.attributes` JSON
  (no-migration pattern, e.g. `consumables`); `pvp_flagged` is the column
  precedent for combat-PvP state.
- **No handcuff items, no persistent restraint state today.**

The persistent handcuff system is **distinct from** the ephemeral grapple (a
grapple is a combat hold you contest each round; cuffs are a lasting condition
that survives logout) but reuses its restriction *intent*.

## 2. The model

### 2.1 State (persistent, no migration)

Restraint state lives in `attributes.restraint` (JSON, mirrors `consumables`):

```jsonc
attributes.restraint = {
  "applied_by": "<cuffer name>",     // who cuffed them (display + release auth)
  "applied_by_id": <char_id>,        // for release-authority checks
  "item_key": "binders",             // the cuff item used
  "escape_difficulty": 15,           // WEG difficulty to break free
  "applied_at": <unix epoch>         // for display / future timeout
}
```

Absent key = not restrained (every existing character unchanged → live-safe).
Engine module `engine/restraints.py` owns read/apply/release/escape, mirroring
`engine/buffs.py`'s consumable helpers (tolerant JSON read, `save_character`
persists).

### 2.2 The cuff action — `cuff <target>` (consent/defeat-gated)

`cuff <target>` (alias `restrain`, `bind`). Requires:
1. The cuffer **holds a cuff item** (a crafted/bought `binders` consumable-style
   item, single-use to apply — consumed on apply, like a charge). *(Faucet/sink:
   the binders item is the sink; no credit faucet added.)*
2. Target is in the same room.
3. **The consent/defeat gate (Brian's norm):** target is EITHER
   - **defeated** — `wound_level >= INCAPACITATED` (4), OR
   - **consenting** — has an opt-in `attributes.restraint_consent` flag the target
     sets via `allow restrain` (for RP/willing captures), OR
   - an **NPC** (no consent needed for NPCs — they're not players to grief).
   A healthy, non-consenting PC **cannot** be cuffed → "They're not subdued or
   willing — you can't get the binders on them."
4. Not already restrained.

On success: write `attributes.restraint`, consume the binders item, announce to
the room. Escape difficulty = a conservative fixed value from the item (binders =
15 = Moderate; better cuffs later can raise it).

### 2.3 What restraint blocks (mirror the grapple restriction set)

While `attributes.restraint` is present, the character **cannot**:
- **move** (MoveCommand) — "You're bound — you can't move until you break free."
- **attack** (combat declaration) — bound hands can't wield.
- **equip / wear / unequip / remove** — can't manipulate gear.

It **allows** social verbs (say/pose/emote/whisper), `look`, and the escape
attempt — a cuffed prisoner can still talk and struggle. (Mirrors the grapple
"allows social" intent; bound ≠ silenced.)

### 2.4 Escape — `escape` / `struggle` (WEG Strength)

`escape` runs `perform_skill_check(char, "lifting", escape_difficulty)` (the
funnel). `lifting` is the **Strength-governed** skill in the registry, so this is
a WEG-faithful Strength roll — note `perform_skill_check(char, "strength", ...)`
does NOT work (the skill→attr map sends the bare attribute name "strength" to the
perception default). On success: clear `attributes.restraint`, announce freedom. On failure:
stay bound, flavor line. **Conservative:** a single fixed difficulty (15), no
margin-scaled partial progress in v1 — keeps it simple and not too easy. One
attempt per command (no spam-free auto-escape).

### 2.5 Release — `uncuff <target>` / `unbind`

The cuffer (or anyone with the cuffs' authority) can release: `uncuff <target>`
clears the target's restraint. Authority = `applied_by_id` matches, OR the
releaser is an admin. (A captor frees their prisoner; a third party can't unless
admin — keeps capture meaningful.)

### 2.6 Logout survival

State is in `attributes` → persisted by `save_character` → a cuffed prisoner who
logs out stays cuffed on return. (This is the whole point of "persistent" vs the
ephemeral grapple.)

## 3. Conservative-balance choices (per charter)

- Escape difficulty 15 (Moderate) fixed — not trivial, not impossible; retunable
  later (a tunable when T3.19 lands).
- Binders are single-use (consumed on apply) — a sink, no faucet; you must
  acquire/craft them.
- No cuffing healthy unwilling PCs (the grief guard).
- No mechanical damage from being cuffed (it's a restriction, not a DoT).
- Release authority is captor-or-admin (capture stays meaningful).

## 4. Out of scope v1 (future increments)

- **Cuffing NPCs.** v1 cuffs PCs only — NPCs have no `attributes` column (their
  state lives in `char_sheet_json`), so persistent NPC restraint needs separate
  plumbing. The consent/defeat gate is fundamentally a PvP feature anyway; "capture
  the bandit" is a later increment. (Decided 2026-06-13 under the conservative
  charter — keep the slice bounded.)
- Cuff *quality* affecting escape difficulty (folds into the crafted-quality
  system once binders are craftable with quality).
- Timed auto-release / struggle-progress bars.
- Dragging a cuffed prisoner between rooms (captor-led movement).
- Gagging (silencing social verbs).

## 5. Build plan (one drop)

1. `engine/restraints.py` — `get_restraint`/`apply_restraint`/`release_restraint`/
   `attempt_escape`/`is_restrained` + the consent/defeat gate helper. Mirrors
   `engine/buffs.py`.
2. `data/` — a `binders` item (weapons.yaml or a consumable entry) + its acquisition
   (buyable/craftable; conservative — make it a vendor item first, cheap sink).
3. Parser verbs: `cuff`/`uncuff`/`escape` + `allow restrain` consent toggle
   (extend an existing command file, e.g. combat_commands or a new restraints_commands).
4. Gates: cuffed-check in MoveCommand, combat attack declaration, equip/wear/unequip/remove.
5. Tests: `tests/test_restraints.py` — apply/escape/release round-trip, the
   consent/defeat gate (healthy PC rejected, defeated PC ok, consenting PC ok, NPC
   ok), each block (move/attack/equip), logout survival, release authority.
6. CHANGELOG + TODO (close CRAFT.HOOK.restraints).

**Faucet/sink:** binders item is a pure sink (acquired by spending/crafting,
consumed on use). No credit faucet. ✓
