# HANDOFF — Economy audit v2 §1.3: NPC vendors stop price-supporting crafted goods
**Date:** 2026-06-02
**Drop zip:** `SW_MUSH_session_consolidated_20260602.zip` — **consolidated** (now 37 files), root-mirrored; apply with `Expand-Archive -DestinationPath . -Force`.

The real lever behind #10. The survey cooldown throttled the free-material *input*; this closes the craft → NPC-sell *output* loop.

## The exploit (audit_v2 §1.3)

Craft a Tier-1 item from ~55 cr (or free, surveyed) materials → sell it to an NPC for ~200 cr. A >250 cr/craft credit engine that needs no buyer. Worse than the raw profit: the NPC buyback **set the floor price for the entire crafted-goods market**, so player vendor droids never had to discover their own floor (SWG's pre-NGE mistake). The existing sell-price *quality bonus* (≥80 → +30%, ≥60 → +15%) made it worse — NPCs paid a premium for exactly the high-quality crafts that should go to players.

## The fix (the audit's preferred "indirect" option)

NPC vendors **refuse well-made player crafts** — *"too well-made for scrap — list it on a vendor droid"* — pushing them to the player vendor market where price discovers itself. Low-quality crafts (`quality < 50`) and all factory/vendor items still sell to NPCs as salvage (which usefully liquidates glut).

- `engine/items.py`: new tunable `CRAFTED_NPC_BUYBACK_MAX_QUALITY = 50` + `npc_refuses_buyback(item)` → `True` iff the item has a (non-empty) `crafter` **and** `quality >= 50`.
- `parser/builtin_commands.py`: `SellCommand` consults the helper right after identifying the item, **before** any pricing or the `item_sale` ledger write — refuses with the in-character message and returns. Help text updated.

## Why it's safe

- The gate keys on a **non-empty `crafter`**, which only `ItemInstance.new_crafted` sets. Factory items (`new_from_vendor`, `crafter=None`) and synthetic `crafter=""` fixtures are **not** gated — normal resale is unaffected.
- The `sell <resource> to <shop>` and `sell cargo` routes dispatch earlier in `SellCommand` and are untouched.
- The old quality bonus is now unreachable for crafted items (gated at ≥50) and irrelevant for factory items (quality 50); left in place, harmless.
- Threshold is tunable in one place.

## Validation

**Sandbox (done):**
- `py_compile` clean; helper smoke-verified (crafted q50/q80/q100 refused; crafted q49/q0 and factory pass).
- `tests/test_npc_buyback_crafted.py` — **+6** (helper logic, boundary at threshold, threshold pinned at 50, structural pin that the gate precedes the credit write).
- **152 passed** across the sell/craft/weapon-adjacent suites (`test_cities_phase4b`, `test_session56_craft_crew_umbrellas`, `test_syn6c_t5_crafting_and_harvest_nodes`, `test_weapons_unit`, + new) — no regression. (`test_cities_phase4b` sells a `new_from_vendor` item, correctly not gated, so city-tax-on-sell still works.)

**Pending on your box:**
- Full suite.
- Smoke: equip a **high-quality crafted** weapon → `sell` → confirm the refusal message and that it stays equipped; then a **low-quality craft** (q<50) and a **factory** weapon → confirm both still sell (and the `item_sale` shows under `@economy velocity`).

## Tuning / optional tightening

- `CRAFTED_NPC_BUYBACK_MAX_QUALITY` (default 50) — raise to refuse fewer crafts, lower to refuse more.
- The audit also offers a "direct" option I did **not** add: a 10–15% salvage *rate* for the crafted items NPCs still buy (quality < 50). The gate alone closes the high-quality money-printer; say the word if you want the salvage-rate too.

## Bookkeeping
- `CHANGELOG.md` — entry prepended.
- `TODO.json` — `_notes` + `T2.ECON.audit_v2_1_3_npc_buyback`.

---

## Session zip — 37 files
Whole session, superseding earlier zips: Drop 0a-2, Mos Eisley P1+P2, respawn-grace wiring, #17 velocity alerts, F1/R1 ledger completion, #10 survey cooldown, the three test-health fixes, and this §1.3 NPC-buyback gate. Plus running `CHANGELOG.md` / `TODO.json`.

Next candidates: the audit's "direct" salvage-rate tightening, the remaining Phase-3 economy features (#12 dynamic prices, #13–16), the larger remediation roadmap drops, or the two near-closed audit docs. Say "continue" and I'll keep rolling.
