# Consumable Quality → Potency — Design v1

**Status:** PROPOSAL (resolves the consumable half of `CRAFT.armor_consumable_quality_combat`).
**Author:** Claude Opus 4.8 (1M), 2026-06-13. Drop 44 shipped the armor half; this
doc decides the consumable potency model before building drop 45.
**Decides:** the open design fork `CRAFT.consumable_quality_potency_model`
(`TODO.json::design_calls_pending_brian`).
**Greenlit principle:** Option A — crafted quality SHOULD affect consumable combat
output (like weapons/armor). Brian: *"quality should absolutely matter"* +
*"avoid power creep… but don't stall; a design doc/analysis first is fine."*

---

## 1. The problem, grounded in HEAD

Crafted consumables store quality at craft time but **discard it** — the value
appears only in the delivery message:

```
# parser/crafting_commands.py:1296-1305
consumables = attrs.setdefault("consumables", {})
current = consumables.get(output_key, 0)
consumables[output_key] = current + 1          # ← bare int count; quality dropped
...
f"(quality {quality:.0f}/100)"                  # ← shown, never stored
```

So a q95 stimpack and a vendor q50 stimpack are **mechanically identical**. The
half-closed `OBS.quality_and_boosts` gap, consumable side.

### What a consumable actually does (HEAD-verified magnitudes)

| Consumable | Catalog effect | Magnitude (pips; 3 pips = 1D) |
|---|---|---|
| `stimpack` | buff `stat_modifiers {strength: 3}` | **+1D STR** |
| `adrenaline_shot` | buff `{strength: 6}` | **+2D STR** |
| `combat_stim` | buff `{dexterity: 3}` | **+1D DEX** |
| `focus_stim` | buff `{knowledge: 3}` | **+1D KNO** |
| `medpac` | `heal_wound_levels: 1` | −1 wound level (discrete) |
| `medpac_advanced` | `heal_wound_levels: 2` | −2 wound levels (discrete) |
| `medpac` (basic, drop A 3rd) | `heal_wound_levels: 1` | −1 wound level (discrete) |

Buffs flow through `add_buff(char, buff_type, **overrides)` (`engine/buffs.py:461`),
which merges `{**template, **overrides}` — so an override of `stat_modifiers`
cleanly scales potency without touching the template. Heals flow through the
discrete `heal_wound_levels` branch (`medical_commands.py:1076-1112`).

---

## 2. The balance asymmetry (why this is a genuine fork, not a copy-paste)

The weapon/armor precedent caps the quality delta at **+2 pips**. That is safe
*there* because the base is large:

- A weapon does ~4–5D damage. +2 pips ≈ **+10%**.
- Armor soaks alongside Strength (often 3–4D combined). +2 pips ≈ **+10–15%**.

A **stim buff base is only +1D (3 pips).** Bolting the same +2-pip delta on gives
+1D+2 ≈ **+5 pips = +67%** of the granted bonus. The *same cap number* is a wildly
different proportional boost because the base is tiny. Copying +2 verbatim would
make a q95 stimpack nearly as strong as the next tier up (`adrenaline_shot`, +2D),
collapsing the consumable tier ladder — textbook power creep.

`adrenaline_shot` is the worst case: +2D base; a +2-pip delta = +2D+2, brushing
+3D — a 33% boost on an already-premium stim.

**Conclusion:** the consumable cap must be *tighter* than the armor/weapon +2, and
keyed to the proportional impact on a small base, not copied from the large-base
precedent.

---

## 3. The model decision

### Two candidate models (from the seam map)

- **P1 — pip-delta-on-base** (mirror weapons/armor): add a quality-band pip to the
  buff's magnitude. Boosts high quality above baseline.
- **P2 — quality-factor multiplier** (mirror starship `_quality_factor`,
  `engine/starships.py:1333`): scale the whole modifier ×0.5/0.75/1.0. *Reduces*
  low quality rather than boosting high.

### DECISION: P1, but with a **+1-pip cap** (not +2) and a **+1-pip floor at q50**

The model is P1 (consistent with the ratified weapon/armor precedent and the
"quality should matter" intent — a high-quality stim should be *better*, the
intuitive direction). But the cap is **halved** relative to armor/weapons to
respect the small base:

```
def crafted_consumable_potency_pips(quality) -> int:
    # tighter band than weapons/armor: a stim base is only +1D, so even +1 pip
    # is a meaningful (+33%) boost. Cap +1 / floor -1.
    #   ≤49  → -1   (shoddy: a botched stim is slightly weaker)
    #   50-69 → 0   (vendor baseline; q50 = unchanged)
    #   70-100 → +1 (any fine/superior crafted stim: one pip, no more)
```

Rationale for collapsing 70–100 to a single +1 (vs the armor 70-89=+1 / 90-100=+2
split): on a 3-pip base, the difference between +1 and +2 is the difference between
+33% and +67%. Capping the whole "good crafted" band at +1 keeps even a perfect
q100 stim strictly below the next catalog tier, preserving the tier ladder. A
crafter's reward for q95 vs q75 is **reliability** (hitting the +1 band) and the
non-combat quality signalling, not a runaway magnitude.

This is applied as an override to **`stat_modifiers`** only — every modified stat
in the buff gets the pip (e.g. a hypothetical multi-stat stim scales each), but
the **magnitude per stat is +1 pip max**.

### Worst-case check under P1/+1

| Consumable | Base | q95 under P1/+1 | Δ | vs next tier |
|---|---|---|---|---|
| `stimpack` (+1D STR) | 3 | 4 pips (+1D+1) | +33% | still < adrenaline (+2D) ✓ |
| `adrenaline_shot` (+2D STR) | 6 | 7 pips (+2D+1) | +17% | top tier; bounded ✓ |
| `combat_stim` (+1D DEX) | 3 | 4 pips | +33% | bounded ✓ |

No q-anything stim reaches the next tier's base. Power-creep-safe.

### Medpacs (heal): quality does NOT scale heal magnitude

Heal levels are **discrete** (1/2/1). Quality cannot cleanly add a fractional
wound, and bumping a q90 medpac to heal 2 instead of 1 would (a) double its power —
a far bigger swing than the +1 pip stims get — and (b) churn the
`test_craft_p2_gundark_drop_a.py::TestMedpacConsumer` heal-shape pins.

**Decision:** medpac heal magnitude stays discrete and quality-independent.
Instead, **crafted medpac quality grants a pip bonus to the First-Aid/Medicine
skill roll** that gates the heal (the `perform_skill_check` already run before the
success branch). Quality there means the heal is *more reliable* (more likely to
succeed and avoid the "ragged wound, kit spent for nothing" fail), not larger. Same
quality band (+1/0/-1), applied to the roll, not the effect. This is the heal-side
analogue of "quality = reliability."

> *Sub-decision:* if even the roll bonus is deemed out-of-scope for drop 45, the
> fallback is medpac quality is purely cosmetic (stored, shown, no mechanical
> effect) — explicitly NOT a phantom because the design says so. Recommend the
> roll bonus; it's cheap and keeps quality meaningful for the medic kit.

### Other consumables

- **`breaching_charge`** (drop 40 ordnance): no potency mechanic — it's a binary
  "does the Demolitions check vs a fixed obstacle difficulty." Quality stays
  **inert** (stored, no combat effect). Could later grant a Demolitions roll pip,
  same as medpacs; out of scope for drop 45.

---

## 4. Storage migration (the mechanical core of drop 45)

Quality must be **persisted at delivery**. The storage shape changes from a bare
int to a quality-bearing entry:

```
# BEFORE:  attributes.consumables[key] = 3
# AFTER:   attributes.consumables[key] = {"count": 3, "quality": 87}
```

### Per-key, single quality, max-on-recraft

A character holding a heterogeneous stack (a q40 + a q90 stimpack) is modeled with
**one quality per key**, taking the **max** on re-craft/stack:

```
new_quality = max(existing_quality, incoming_quality)
```

Per-unit quality (a list of instances) is over-engineering for fungible stims and
would bloat the attributes blob. Max-on-recraft means a crafter's best result sets
the bar; it's the simplest rule that makes "craft a better one" always an upgrade.
(Average-weighted was considered; max is simpler and strictly player-friendly.)

### Migration-tolerant read (the four `engine/buffs.py` helpers)

All four helpers assume `consumables[key]` is a bare int and must read the new
shape while tolerating the legacy one. Centralize the normalization:

```
def _normalize_consumable_entry(v) -> dict:
    # legacy bare int  → {"count": v, "quality": 50}   (vendor baseline)
    # new dict         → {"count": v["count"], "quality": v.get("quality", 50)}
    # anything else    → {"count": 0, "quality": 50}
```

- `has_consumable` / `get_consumable_count` → read `.count` via the normalizer.
- `consume_consumable` → decrement `.count`; **return the consumed unit's quality**
  (was `bool`) so the apply path can scale potency. New signature:
  `consume_consumable(char, key) -> int | None` (quality on success, None on empty).
  This ripples to **every caller** — `medical_commands.py:911-926, 1114-1120`,
  `engine/breaching.py` (treats the return as truthy — `None`/`int` both work for a
  truthiness check, but verify), and `test_srb1b_stim_consumable_wiring.py`.
- The delivery write at `crafting_commands.py:1296-1305` writes the dict shape with
  max-on-recraft.

> **Back-compat note:** legacy bare-int consumables read as q50 (vendor) — so a
> player's existing pre-migration stims keep working at baseline potency. No DB
> migration script needed; the read coerces lazily, the next write upgrades the
> shape. (Mirrors how the equipment column tolerates all historical shapes.)

### The smoke assertion that breaks

`tests/smoke/scenarios/economy_progression.py:160-201` asserts
`consumables.medpac > 0` (count on a bare int). After the shape change this must
become `consumables.medpac["count"] > 0`. Update in the same PR (sequence-known
breakage, not a surprise).

---

## 5. Drop 45 build checklist (once this doc is ratified)

1. `engine/consumables.py` (or `buffs.py`): add `crafted_consumable_potency_pips`
   funnel (cap +1/floor -1) + `_normalize_consumable_entry`.
2. `engine/buffs.py`: migrate the 4 helpers to the normalizer;
   `consume_consumable` returns quality. Keep `_read/_write_consumables_dict`.
3. `parser/crafting_commands.py:1296`: delivery writes `{count, quality}`,
   max-on-recraft.
4. `parser/medical_commands.py`: thread the consumed quality →
   `add_buff(target, buff_type, stat_modifiers=<scaled>)` for stim entries; →
   First-Aid roll pip for medpac entries.
5. Update callers of `consume_consumable` for the new return type.
6. Tests: new `tests/test_consumable_quality_potency.py` (storage migration legacy
   int → dict, quality persisted + max-on-recraft, scaled buff magnitude, cap
   enforcement, consume returns quality, medpac heal UNCHANGED + roll bonus);
   update `test_srb1b_stim_consumable_wiring.py` for the return shape; update the
   `economy_progression` smoke assertion.
7. CHANGELOG + TODO (close the consumable half of
   `CRAFT.armor_consumable_quality_combat`; resolve
   `CRAFT.consumable_quality_potency_model`).

---

## 6. Open questions for Brian (small; recommend proceeding on the defaults)

1. **Consumable cap = +1 (not +2).** Recommended for the small-base reason above.
   *Confirm, or set a different number.*
2. **Medpac quality → First-Aid roll bonus** (not heal magnitude). Recommended.
   *Confirm, or rule "medpac quality cosmetic only."*
3. **Max-on-recraft per-key quality.** Recommended over per-unit/average. *Confirm.*
4. **breaching_charge quality inert** for drop 45. Recommended. *Confirm.*

All four have a clear recommended default; per the "don't stall" steer, drop 45 can
proceed on these defaults unless Brian overrides. Logged in
`design_calls_pending_brian::CRAFT.consumable_quality_potency_model`.
