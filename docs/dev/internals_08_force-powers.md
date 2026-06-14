# Developer Internals — Guide_08_Force_Powers.md

Extracted from `data/guides/Guide_08_Force_Powers.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

### 🔧 Developer Internals

**File:** `engine/character.py` — Force attributes stored as `DicePool` fields:
```python
control: DicePool = field(default_factory=lambda: DicePool(0, 0))
sense: DicePool = field(default_factory=lambda: DicePool(0, 0))
alter: DicePool = field(default_factory=lambda: DicePool(0, 0))
```

`force_sensitive: bool` gates access. `Character.get_attribute("control")` returns the pool. `_has_force_skill(char, skill)` in `force_powers.py` checks `pool.dice > 0 or pool.pips > 0`.

### 🔧 Developer Internals

**File:** `engine/force_powers.py` — `POWERS` dict (lines 81–183): 8 `ForcePower` dataclass entries.

**`ForcePower` dataclass** (lines 69–78):
- `key`: Internal name (command argument)
- `name`: Display name
- `skills`: List of required Force skills (e.g., `["control", "sense", "alter"]`)
- `base_diff`: Base difficulty number
- `dark_side`: If True, automatically awards 1 DSP
- `combat_only`: If True, only usable during active combat
- `target`: `"self"`, `"room"`, or `"target"`
- `description`: Help text

**`list_powers_for_char(char)`** (lines 192–198): Filters POWERS to only those where the character has at least 1D in all required skills.

### 🔧 Developer Internals

**`resolve_force_power(power_key, char, skill_reg, target_char, extra_diff)`** (lines 228–332):

1. Looks up power from `POWERS` dict
2. Builds skill pool: `min(pools, key=total_pips)` for combination powers
3. Applies wound penalty via `apply_wound_penalty()`
4. Rolls via `roll_d6_pool()` against `base_diff + extra_diff`
5. Dispatches to power-specific resolver function
6. If `power.dark_side`: awards 1 DSP, checks for fall (see section 5)
7. Returns `ForcePowerResult` with all metadata

**`ForcePowerResult` dataclass** (lines 211–225): `power`, `success`, `roll`, `difficulty`, `margin`, `narrative`, `dsp_gained`, `fall_check`, `fall_failed`, `heal_amount`, `pain_suppressed`, `targets_felt`, `damage_dealt`.

**Individual resolvers** (lines 339–459): Each power has its own `_resolve_*()` function:
- `accelerate_healing`: Decrements `char.wound_level` by 1 step
- `control_pain`: Sets `result.pain_suppressed = True`
- `remain_conscious`: Narrative only (command layer handles mechanical effect)
- `life_sense` / `sense_force`: Narrative results (caller fills actual room data)
- `telekinesis`: Narrative with margin display
- `injure_kill`: Opposed Alter margin vs. `roll_d6_pool(target.strength)`, applies `target.apply_wound()` on positive effective damage
- `affect_mind`: Margin determines suggestion strength (10+ strong, 5–9 moderate, 1–4 weak)

### 🔧 Developer Internals

**DSP mechanics** (lines 462–491):
- `DSP_FALL_THRESHOLD = 6` — Fall check triggered at this count
- `_dsp_warning(dsp)` — Escalating warning text based on count
- `_resolve_fall_check(char, skill_reg)`: Rolls `Willpower` pool via `roll_d6_pool()` against `char.dark_side_points * 3`. Returns True if resisted.

**DSP is applied in `resolve_force_power()`** (lines 309–329): After power-specific effects but before returning. This means dark side powers always award DSP even on a failed roll — the act of *reaching for* the dark side is what corrupts, not whether it works.

**Storage:** `Character.dark_side_points: int = 0` in `engine/character.py`. Persisted to DB.

## 9. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/force_powers.py` | ~509 | 8 power definitions, ForcePower/ForcePowerResult dataclasses, resolve_force_power(), individual resolvers, DSP/fall check |
| `parser/force_commands.py` | ~344 | 3 commands (force, powers, forcestatus), target resolution, narrative delivery |
| `engine/character.py` | ~588 | Control/Sense/Alter DicePool storage, force_sensitive flag, dark_side_points |
| `engine/dice.py` | ~381 | roll_d6_pool(), apply_wound_penalty() |

**Total Force system:** ~853 lines of dedicated engine/parser code.

---

*End of Guide #8 — Force Powers*
*Next: Guide #9 — CP Progression*

