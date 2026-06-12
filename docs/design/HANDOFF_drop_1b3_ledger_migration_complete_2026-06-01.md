# HANDOFF — Drop 1.b.3: complete the credit-write migration
**Date:** 2026-06-01  •  **Base:** post Drop 1.b.2 (same session)
**Zip:** `SW_MUSH_drop_1b3_ledger_migration_complete_2026-06-01.zip` (root-mirrored — `Expand-Archive -DestinationPath . -Force`)

---

## 1. What this is

The **final** tranche of the F1 ledger migration, consolidated into one drop per your roll-up directive. Every credit movement under `engine/` + `parser/` now routes through `Database.adjust_credits` — the single function that does the atomic `credits += delta` **and** writes `credit_log` in one place. (This is exactly the "one function called every time credits move that writes the ledger" design — it's now universal; new credit flows just call `adjust_credits(char_id, delta, "tag")`.)

**~30 sites across 22 source files converted:** encounters ×5 (texture/anomaly/patrol/pirate/hunter), housing ×8, buildings, hazards, sleeping (theft transfer → loss+gain), chain_rewards, intel_handlers, npc_space_traffic ×3, tutorial_v2 ×2, wilderness_anomalies ×2, spacer_quest ×2, space_commands ×7 (refuel/docking/weapon/fine/trade), builtin (p2p batch + bacta + trade_goods), smuggling ×3, bounty, crafting, and the `mission_commands` failed-check `else` no-op tail.

**New `city_tax` system sink:** `apply_city_tax` now logs the city's slice as a `char_id=0` ledger entry. It does **not** double-count — `char_id=0` entries are excluded from player faucet/sink totals; this only makes the city-tax drain legible by source on `@economy`, exactly like `p2p_tax`. **DECISION:** I defaulted this to YES; it's a one-line behavioural add — say the word if you'd rather not log it.

---

## 2. The headline guarantee

`tests/test_drop1b3_ledger_migration_complete.py` is a **tree-wide structural pin**: it walks every `.py` under `engine/` + `parser/` and asserts **zero** `save_character(... credits ...)` and **zero** direct `log_credit(` calls survive (the only allowed matches are 2 rST docstring mentions in `chain_rewards.py`). That one negative test guards the *entire* migration (1.a → 1.b.3) — if anyone reintroduces a bypass, it fails.

---

## 3. Validation

- `py_compile` clean on all 22 source files.
- **pyflakes undefined-name scan** clean. (This caught a class of bug `py_compile` can't: removing a local that a later display line still references → runtime `NameError`. Four were found and fixed — space weapon-purchase "remaining", housing rent balance, smuggling reward balance, bounty reward balance. **Lesson re-confirmed: pyflakes-scan after every credit-write sweep.**)
- **Test-harness fix:** two per-file stubs (`_MiniDB` in `test_syn9_player_buildings.py`, `_MockDB` in `test_f8c2d_chain_rewards.py`) implemented `save_character` but not `adjust_credits`, so converted paths threw `AttributeError`. Both were given an `adjust_credits` (syn9: real atomic SQL mirror; f8c2d: recorder shim + balance seed). I checked the full 28-file stub blast radius — only these two reach a converted path.
- **Sandbox regression — GREEN (~1,400 tests):** the 4 ledger pins (`drop1a/1b1/1b2/1b3`), `economy_validation`, `session51_economy_hardening` (p2p tax), `pg1_death_a/b`, `pg2_pc_bounty_session1/2`, `bounty_board_unit`, `syn6a`/`syn6c`, `syn5`/`syn7a`/`syn7b`/`syn8`, the 12-file village `f7*` batch, `syn9_player_buildings`, `f8c2d_chain_rewards`, `cities_phase4b` (city_tax + buy path).

### ⚠️ Not run in-sandbox (please run on Windows)
Several heavier suites boot a full-server harness that exceeded the sandbox execution timeout, so I could **not** run them here:
`session39`, `session57a_ship_expansion`, `session57b_space_umbrellas`, `session63_bulk_premium` (space paths), `session46_encounter_dispatch`, `kd5b_sweep_npc_space_traffic`, `session55_jobs_umbrellas`, `session58_cleanup_umbrellas`, `b1d2_housing_codeflow_era_aware`, `q1_2_extended_sweep` (spacer_quest), `srb2_morale_aura`.

These paths were converted with the same mechanical pattern, are **pyflakes-clean** (no dangling refs), and the harness they use builds a **real** per-class DB (so the stub gap does not apply). Residual risk is low, but **your full ~4,854-test run is the ground truth** — if any of the above are red it'll almost certainly be one more display-var rename of the kind pyflakes already swept.

---

## 4. Source-tag taxonomy (complete, for the dashboard)

Faucets/sinks now on the chokepoint, grouped:
- **missions/bounty:** `mission`, `bounty`, `bh_insurance_hit`, `bh_insurance_hit_partial`, `bh_bounty_payout`, `bh_guild_treasury_sink`(sys), `bh_insurance_pay`, `bounty_expire_refund`
- **crew/vendor:** `crew_wage`, `vendor_droid_deploy`, `vendor_purchase`, `vendor_escrow_collect`, `vendor_buy_order_escrow`/`_refund`/`_payout`, `vendor_droid_upgrade`
- **harvest/entertainer/death:** `harvest`, `entertainer_perform`, `corpse_credit_return`
- **space:** `space_encounter_reward`, `space_anomaly_reward`, `space_patrol_fine`, `space_pirate_extortion`, `space_hunter_bounty`, `space_hunter_settlement`, `ship_refuel`, `ship_weapon_purchase`, `space_fine`, `docking_fee`, `trade_goods`, `npc_boarding_fine`, `npc_pirate_extortion`, `npc_pirate_bounty`
- **housing/buildings:** `housing_purchase`/`_deposit_refund`/`_rent`/`_rename`/`_upgrade`/`_refund`, `shopfront_purchase`/`_refund`, `player_building_construct`
- **world/quest:** `hazard_theft`, `theft_loss`, `theft_gain`, `chain_reward`, `intel_handover`, `tutorial_reward`, `wilderness_anomaly_reward`, `spacer_quest`, `spacer_quest_ship`
- **misc/system:** `bacta_tank`, `bacta_tank_refund`, `resource_vendor`, `smuggling`, `smuggling_fine`, `p2p_transfer`, `p2p_tax`(sys), `city_tax`(sys)

---

## 5. What's left in the economy wave

- **1.c** — `+finances` (a player's own per-source credit_log breakdown) + `@economy throttle <pct>`. The `@economy` dashboard already exists (S51); only these two surfaces remain. Last item in Drop 1.
- Then **0b** (TRADE_GOODS remap), **Drops 2–5**, and the **approved-deferred GCW-retirement** drop.
