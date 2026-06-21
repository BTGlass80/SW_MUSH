# Credit-sink integrity audit — 2026-06-21

Systematic sweep of every `adjust_credits` negative player sink, closing the
credit-integrity bug class (stale session-cache affordability pre-check, then an
unguarded `adjust_credits(char, -cost)` that a concurrent DB drain can drive
negative). Chokepoint contract: `adjust_credits(..., allow_negative=False)`
refuses an over-draw atomically and returns `None`.

Audit population: 109 `adjust_credits` calls / 13 already-guarded / 4 system
(char_id=0) / ~40 unguarded player negative sinks classified below.

## VULNERABLE — fixed-cost overdraw, MUST harden (22)

Fix = `allow_negative=False` + abort on `None`. "(reorder)" = state is created
BEFORE the debit, so the fix must debit-first (only create on success).

### engine/ (10)
- engine/buildings.py:384 — player_building_construct — debit-first already
- engine/commissary.py:217 — commissary_purchase — debit-first
- engine/dens.py:161 — den setup — debit-first (refund path exists)
- engine/encounter_pirate.py:78 — space_pirate_extortion — on None → fall through to `_start_pirate_combat` (the existing can't-pay branch)
- engine/gear_insurance.py:109 — gear premium — debit-first
- engine/housing.py:766 — home_prestige — debit-first
- engine/housing.py:1380 — housing_rename — abort before the rename write
- engine/titles.py:234 — vanity_title — debit-first
- engine/npc_space_traffic.py:1739 — npc_pirate_extortion — on None → return (False, "not enough credits")
- engine/spacer_quest.py:1013 — spacer_quest_ship — NO pre-check at all; guard + gate `_transfer_ship_ownership` on a successful debit

### parser/ (12)
- parser/builtin_commands.py:3092 — bacta_tank — debit-first
- parser/builtin_commands.py:3640 — repair — (reorder) item.repair()/save before debit
- parser/builtin_commands.py:5687 — p2p_transfer — guard offerer debit; abort BEFORE crediting recipient + system tax (else credits are minted)
- parser/crew_commands.py:179 — crew_wage — (reorder) hire_npc before debit
- parser/shipyard_commands.py:224 — ship_purchase — debit-first (refund scaffolding)
- parser/space_commands.py:1224 — ship_refuel (launch) — abort launch on None
- parser/space_commands.py:3917 — ship_refuel (misjump) — on None charge nothing, still apply misjump
- parser/space_commands.py:3965 — ship_refuel (jump success) — abort jump on None
- parser/space_commands.py:4282 — ground_weapon_purchase — (reorder) equip/save before debit
- parser/space_commands.py:4591 — ship_repair — debit-first (refund scaffolding)
- parser/space_commands.py:5908 — trade_goods — (reorder) cargo written before debit
- parser/spacer_quest_commands.py:230 — debt payoff — guard; don't persist cleared-debt attrs on None

## SAFE-BY-CONSTRUCTION — leave alone (12)
Debit is bounded by a freshly-read balance or clamped delta, so it can't overdraw
a fixed cost. (Residual second-order note: the `min(cached_credits, x)` fine
sites can still take a small partial overdraw if the *cached* balance is stale-
high; bounded by the cached amount, adversarial-to-player, lower priority — NOT
fixed in this sweep, tracked as a follow-up.)
- engine/death.py:541, :555 — bh_insurance (fresh get_character read)
- engine/debt.py:88 — min(payment, principal), gated on fresh read
- engine/encounter_hunter.py:96, :141, :160 — min(credits, x), fresh read
- engine/encounter_patrol.py:657 — space_patrol_fine — min(credits, fine)
- engine/hazards.py:432 — ≤5% of checked balance
- engine/npc_space_traffic.py:1382 — npc_boarding_fine — min(credits, fine)
- engine/sleeping.py:266 — theft_loss — fraction of read balance (zero-sum)
- parser/pc_bounty_commands.py:1126 — bh_insurance_pay — fresh get_character re-read
- parser/sabacc_commands.py:344 — clamped delta (max(0, credits-bet))
- parser/smuggling_commands.py:455, :559 — clamped delta
- parser/space_commands.py:1350 — docking_fee — min(credits, fee)
- parser/space_commands.py:5467 — space_fine — min(credits, fine)
- parser/spacer_quest_commands.py:201 — debt_payment — min(amount, principal, credits)

## INTENTIONAL-DEBT — leave alone (1)
- engine/housing.py:1135 — housing_rent — non-payment routes to the designed
  overdue/eviction counter, gated on a fresh read.
