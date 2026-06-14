# HANDOFF — Crafting/Harvesting Integration Review (parallel session → main session)

> ## ⚠️ POINT-IN-TIME — captured at commit `54a9375` (Drop 41). MAY BE SUPERSEDED.
> The codebase moves fast (the session ships multiple drops/day). Findings here may already
> be actioned or made stale by drops landed since. (Confirmed: the session already consumed
> part of this — commit `e58b0fc` "Record crafting-review fork decisions + queue
> armor/consumable quality-combat build".) **Re-verify every file:line and every "still open"
> claim against HEAD before acting.** Treat as a head-start, not current truth.

> **FOR THE MAIN SESSION'S WATCH:** *"check for landed findings at each drop boundary;
> integrate non-conflicting as follow-ups, STOP+log real conflicts. Deliberate check
> BEFORE ship-part install."* This doc is structured for exactly that decision.
>
> Produced read-only at commit **`54a9375` (Drop 41)**. Re-verify file:line against HEAD
> before acting — you move between drops (you're in a world_writer/planet drop right now).
> The crafting/harvest/economy code is CLEAN as of this writing, so these findings are valid
> against current HEAD; your CURRENT drop (world-building) does NOT touch any of it.

## TL;DR — the graph is HEALTHY; one real gap (quality→combat for armor/consumables)

Full audit (4-lane gear-source-graph map + synthesis, T2.CRAFT.integration_design_pass).
Verdict: **the recipe/material/economy backbone is sound.** No phantom recipe inputs, no
orphan faucets, no mint-credit loops, all 5 T5 drop hooks live. The ONE real structural
finding: **crafted quality reaches combat for WEAPONS ONLY** (Drop 19 fix). For **armor and
consumables it is stored-but-decoration** — the half-closed `OBS.quality_and_boosts` gap.

---

## ⚠️ BEFORE SHIP-PART INSTALL — read this first (your named checkpoint)

Your ship-part-install work wires `t5_hyperdrive_surge_converter` + `t5_mil_spec_ion_engine_core`
through `+ship/install` (`parser/space_commands.py:1616`) so they DO something in combat/space.
The audit found the directly-relevant precedent and trap:

- **The pattern that WORKS (copy it):** crafted WEAPON quality reaches combat via
  `engine/items.py:626 crafted_combat_pips`, which reads the equipped **ItemInstance** quality
  (not the bare key) and folds quality-band + experiment pips into damage/accuracy, hard-capped
  (+1D dmg / +1 to-hit). Combat reads the instance via `read_equipment(...)['weapon']`
  (`combat_commands.py:1675`). **Ship-part effects should read the installed ItemInstance the
  same way** — do NOT key off a bare item key, or you'll repeat the armor bug below.
- **The trap to AVOID:** crafted ARMOR quality is a PHANTOM in combat — `get_armor_protection`
  (`engine/character.py:457`) reads only the bare `worn_armor` key, so a q95 vest soaks like a
  q40. The ship-part install must thread the **instance** (with its quality/experiment axes)
  into the combat/space-effect read, mirroring the weapon path, or the crafted T5 ship parts
  will install but their quality won't matter — the same decoration bug, in space.
- **No graph blocker:** both T5 ship-part materials have LIVE drop hooks
  (`deep_dune_iron` ← krayt dragon T3; `scavenged_republic_tech` ← Coruscant Underworld harvest
  scavenge 7%@q75), and both recipes are well-formed. The gap is purely consumer-side (effects),
  which is exactly what your drop builds. **No conflict — this audit is INPUT for your drop.**

---

## 🟢 SAFE TO INTEGRATE (non-conflicting follow-ups — pick up freely)

These don't touch code you're hot in; additive or contained.

1. **Rare-material vendor gap (1-line data, INDEPENDENT, safe anytime).** `rare` is the only
   base type with no `buyresources` entry (`parser/crafting_commands.py:1580-1587`
   `NPC_RESOURCE_PRICES` omits it). Loop still closes via harvest, so non-blocking — but a
   non-wilderness player can't buy past a rare bottleneck. **Brian-confirm whether intentional**
   (rare = earned, looks deliberate); if not, one NPC_RESOURCE_PRICES line. No combat/harvest
   overlap.
2. **Retire/fix dead `stat_bonus` (contained string/flag, low risk, lands between drops).**
   `engine/crafting.py:97-101` QUALITY_TIERS `stat_bonus` ("minor/moderate combat bonus")
   is read by NOBODY in combat — the craft message at `crafting.py:765-768` promises a bonus
   that doesn't exist (the real weapon bonus is the independent `items.py` pip path). Either
   drop the promise string or replace it with the actual pip delta. Touches only the
   `resolve_craft` message — contained.

## 🔴 STOP + RECONCILE (real conflicts / design forks — log, don't blind-integrate)

3. **DESIGN FORK (Brian call required — do NOT guess):** disposition of the 3 decoration gaps
   (armor-quality→soak, consumable-quality→potency, stat_bonus). Option A = make them real
   (consistent with the Drop-19 weapon precedent); Option B = stop rendering the promise. A is
   precedent-consistent BUT armor-soak + consumable-potency are **balance-sensitive (power
   creep)** — a genuine fork, not mechanical. **This is the gate for items 4 & 5.** Log in
   `design_calls_pending_brian` (suggest id `CRAFT.quality_combat_read_armor_consumables`).
4. **Armor-quality→soak wiring — HIGHEST COLLISION RISK.** Touches `engine/combat.py` soak path
   (~1649-1657), `engine/character.py:457-480 get_armor_protection`, `engine/items.py` pip
   helpers (~605-678), `parser/combat_commands.py` resolve. **`combat.py`/`items.py` are shared
   with any live combat/equipment edit.** Also intersects the open
   `TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES` debt — may want to BUNDLE with that
   refactor rather than bolt on. **Land solo on a quiet combat window; do not run concurrent
   with combat/equipment edits. Gated on item 3.**
5. **Consumable-quality persistence — DIRECT hot-path conflict.** Touches
   `parser/crafting_commands.py:1296-1299` (the consumable-deliver branch — the SAME file region
   your harvest/teach/crafting drops edit) + `parser/medical_commands.py`. Changes the consumable
   storage shape (bare count → quality-bearing), needs migration-tolerant read. **Must be
   sequenced AFTER your crafting edits settle — never concurrent.** Gated on item 3.

---

## Collision map (per your trajectory, not just current position)

| Finding | Files | vs. your lane | When |
|---|---|---|---|
| #1 rare vendor | crafting_commands.py (data const) | independent | anytime |
| #2 stat_bonus | crafting.py (message) | contained, shared file | between your drops |
| #3 design fork | (doc only) | none | now (Brian) |
| #4 armor soak | combat.py, character.py, items.py | HIGH — shared combat/equipment | solo, quiet window; gated |
| #5 consumable quality | crafting_commands.py, medical_commands.py | HIGH — your hot file region | after your crafting settles; gated |

You're currently in a **world-building drop** (world_writer.py, planet YAMLs) — **zero overlap
with any finding here right now.** The overlap returns when you re-enter the crafting lane
(your pending design calls are crafting-heavy) and at ship-part install (see top).

## What needs Brian (not the session)
- Item 3 (the quality-combat-read fork for armor/consumables) — balance call.
- Item 1 (is the rare-no-vendor gate intentional?) — quick confirm.

## What's mechanical (session can pick up once gated/sequenced)
- Items 1, 2 now; items 4, 5 after Brian rules item 3 and the lane is quiet.

*Audit artifacts: full node map + synthesis in workflow task `wlex51uuu.output`. Recipe
backbone, T5 drop-hook status, and faucet/sink ledger all verified clean at Drop 41.*
