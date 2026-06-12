# HANDOFF — Drop 2: death reconciliation [F12, G2, R8]

**Date:** 2026-06-01
**Base:** `SW_MUSH_upload_20260601_2217.zip` + Drops 1.b.4/1.c + 0a-4 (same session)
**Zip:** `SW_MUSH_drop_2_death_reconciliation_2026-06-01.zip` (root-mirrored — `Expand-Archive -DestinationPath . -Force`)
**Status:** Code complete; sandbox-validated. **No income created** (insurance is a *sink* on the killed target; the payout still lands in Drop 3). Anti-grief *reduces* a faucet (griefer loot), never adds one.

---

## 1. Headline: the F12/G2 "CRITICAL" premise was wrong — and the truth is better

The remediation plan listed **F12/G2 as CRITICAL/OPEN: "death drops *all* gear — `_snapshot_and_clear_inventory` wipes equipped + loose + resources."** A symbol-level audit at HEAD shows that is **factually incorrect for this build**:

- Equipped gear lives in a **separate `characters.equipment` column** (a JSON dict), written only by `EquipCommand`/`UnequipCommand`.
- `death._snapshot_and_clear_inventory` reads `db._get_inventory_raw`, which returns **only the `inventory` column** (`{items, resources}`). It snapshots and clears *that*. It **never reads or writes `equipment`.**

So **equipped gear is already preserved on death** — exactly the behavior the plan's "surgical change" line asked for, met by schema. The doc's whole "bring code to guide" framing for part 1 was chasing a bug that isn't there. (The guide, Guide_19 §3, says loose items move to the corpse and *"your equipped weapon stays equipped"* — the engine satisfies the player-facing promise: you keep your weapon.)

**What Drop 2 therefore actually delivers:** a regression pin locking in the (already-correct) equipped-preservation, plus the four parts that genuinely did *not* exist.

---

## 2. What shipped

### A. Equipped-preservation pin (corrected F12/G2) — `engine/death.py` + test
- Added a clarifying comment at the snapshot site documenting that `equipment` is intentionally untouched.
- `tests/test_drop2_death_reconciliation.py::TestEquippedGearPreserved` pins it two ways: a **runtime** test (equip a pistol, die, assert the `equipment` column is byte-identical while `inventory` is cleared) and a **structural** test (death.py contains no `SET equipment =` / `save_character(...equipment...)`). A future inventory refactor that merged equipped into `inventory` would now fail loudly instead of silently dropping players' weapons.

### B. Anti-grief (NEW — none existed) — `engine/death.py`, migration v37
Repeated PvP kills of the **same victim by the same killer** inside `GRIEF_WINDOW_SECONDS` (30 min) diminish the **corpse loot the killer profits from**:
- `loot_factor` by repeat index: **1.0 → 0.5 → 0.25 → 0.0** (`GRIEF_LOOT_FACTORS`), clamped to 0.0 thereafter.
- `_record_pvp_death_and_loot_factor()` records each PvP death and returns the factor; `_apply_loot_factor()` scales the corpse snapshot (keeps a proportional prefix; 0.0 → empty).
- **Environmental/NPC deaths (`killer_id is None`) never diminish and record nothing** — griefing is a PvP-only concept.
- **Respawn grace:** each PvP death records `grace_until = now + RESPAWN_GRACE_SECONDS` (60s); `get_respawn_grace_until(db, char_id)` is the read the **combat layer** calls to refuse lethal damage during the window. *(The death/ledger side is complete; the combat-layer enforcement read is a one-line consumer wiring flagged in §5 — it does not block this drop.)*
- All anti-grief steps are **best-effort / fail-open**: a logging or DB hiccup can never deny a legitimate killer their loot, grant infinite invulnerability, or block the death flow.
- Migration **v37**: `recent_pvp_deaths(victim_id, killer_id, died_at, grace_until)` + two indices. Rows are time-bounded in every query, so staleness is harmless (a prune job is optional, not required).

### C. Insurance rescale to flat + % (R8) — `engine/death.py`
The BH insurance hit was **pure 10%**, which barely bit small bounties. Now **`INSURANCE_FLAT (250) + ceil(INSURANCE_PCT% )`**. Example: a 1,000-cr bounty hit goes 100 → **350**; a 10,000-cr hit goes 1,000 → **1,250**. The 80/20 payout split to the BH/treasury is unchanged. (The insurance *payout to the policyholder* is still deferred to Drop 3 per the plan.)

### D. Death-stakes zone warnings (NEW framing) — `parser/builtin_commands.py`
- **LAWLESS** one-time warning now states the loss explicitly: *"Death here means losing everything you carry — your loose gear drops to a lootable corpse. Your equipped weapon stays with you."* (The last line is accurate to the engine and reassuring — you don't lose your blaster.)
- **CONTESTED** now gets its own one-time heads-up (previously lawless-only): *"If you die here, your loose gear drops to a corpse others can loot."* Tracked via `session._contested_warned`.

---

## 3. A test I had to change (yours), and why

The insurance rescale (correct, intended) breaks two assertions in **`tests/test_pg2_pc_bounty_session2.py`** that pinned the old pure-10% amount:
- `TestFireInsuranceHappy` — expected target debited exactly 1,000 on a 10k bounty.
- `TestFireInsurancePartialDebt` — expected 700 debt (1,000 hit − 300 cash).

I updated **only those two**, and rewrote them to **derive the expected hit from `INSURANCE_FLAT`/`INSURANCE_PCT`** rather than hardcoding a number — so they stay correct if you tune the flat/pct later. The 80/20 payout assertions, the no-BH/no-bounty no-ops, the debt-CRUD, pay, void, and expiry-refund cases were **not** touched. I verified no *other* test in the file asserts a hardcoded insurance-hit amount (the other credit assertions at lines ~886/1045 are debt-pay and expiry-refund flows, independent of the hit formula).

---

## 4. Validation (sandbox)

- **Compile:** clean (touched files + full `engine`/`parser`/`db` tree).
- **pyflakes:** no undefined names introduced.
- **New:** `test_drop2_death_reconciliation.py` — **16 pass.** Equipped-preserved (runtime + structural), loot_factor progression + window-reset + different-killer + environmental-exempt, `_apply_loot_factor` math, respawn-grace record/read, insurance flat+% verified against the **real `adjust_credits` credit_log** (delta 350 for a 1k bounty), v37 registered.
- **Regression — GREEN:** `pg1_death_a` (35), `pg1_death_b` (24), `pg2_pc_bounty_session1` (39), `pg2_pc_bounty_session2` (39, incl. the two repaired assertions), `security_zone_coverage` (2). No test pins the warning strings (confirmed), so the copy changes are safe.
- **E2E:** real `Database.initialize()` applies through **v37**; `recent_pvp_deaths` + `economy_config` both PRESENT.
- **Windows ground truth** remains authoritative — run `run_all_tests.bat`. The only behavior changes are: insurance hit magnitude (covered), griefer corpse-loot reduction (new, PvP-repeat only), and two new/upgraded zone-entry strings.

---

## 5. Follow-ups (flagged, not blocking)

1. **Combat-layer grace enforcement (one-line consumer):** the death side records `grace_until` and exposes `get_respawn_grace_until()`. To make respawn-grace *bite*, the combat damage path (`engine/combat.py`) should, before applying lethal damage to a PC, check `await get_respawn_grace_until(db, target_id) > now` and no-op/redirect if so. I did not wire this here because it touches the live combat loop and deserves its own small, carefully-tested drop (and `_grace_timer_handle` scaffolding already exists in `combat.py:587`, suggesting an intended home). **The data + API are ready.**
2. **`recent_pvp_deaths` prune job (optional):** rows are harmless when stale (all lookbacks are time-bounded), but a periodic `DELETE WHERE died_at < now - GRIEF_WINDOW_SECONDS` would keep the table tiny. Nice-to-have.
3. **Pre-existing, unrelated:** `pc_bounty_commands.py:239` uses deprecated `datetime.utcnow()` (warning only).

---

## 6. State of the plan

- **Drop 1 (ledger):** complete (1.a/1.b/1.c) — chokepoint + `@economy throttle` + `+finances`.
- **Drop 0a-4:** done (housing era-flavor; the bulk "sweep" reclassified as the deferred GCW-retirement drop).
- **Drop 2 (this):** complete — equipped-preservation pinned, anti-grief + respawn-grace, insurance flat+%, death-stakes warnings.

**Next, in plan order:** **Drop 3** is the center of gravity (playstyle loops + the aspirational sink stack B1–B5 + the insurance *payout*) — but it explicitly **"lands with/after Drop 0b"** so faucets don't outrun the sink, and 0b (trade re-map) is era-gated. So the natural sequence is **0b first**, then **Drop 3**. Alternatively, the small standalone wins: **0a-3** (tutorial-chain CW migration) or **0a-2** (starter quest — broker already decided: new non-canon Kuat KDY broker). Your call.

*End.*
