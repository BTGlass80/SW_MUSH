# HANDOFF — Vendor-presence gate: vendors ≠ hagglers
## Session 2026-06-12 (8th cont.) · Drop 11 · Rollup: `SW_MUSH_drops1-11_rollup_2026-06-12.zip` (CUMULATIVE — supersedes ALL prior zips)

**Apply:** `Expand-Archive -DestinationPath . -Force` from project root → `run_all_tests.bat`.

## What shipped
Your call (a) + the disentangle: buying needs an in-room NPC with `ai_config.vendor: true` —
the `trainer: true` precedent applied to commerce. Lup haggles without being an arms dealer;
the desert sells nothing; the haggle uses THE VENDOR'S Bargain (fixing the old
first-Bargain-NPC-in-the-room bug). Refusal: "No merchant here sells weapons. Find a shop."

**Vendors (8):** Kayson, Sela Tarn, Lup, Ruzz-tha (Mos Eisley) · Trex Hovan (Coruscant Lower
City Black Market) · Halen Korr (Weapons Cache) + Reska Tol (Undercity Market) (Nar Shaddaa) ·
Sela Dorne (Geonosis). Kamino: none, deliberate (commissary world). **Gundark: NOT a vendor** —
teaches, never retails (pinned). An uncurated-vendor sweep test makes future vendor adds
deliberate decisions.

**⚑ Windows watch #7:** `buy` refuses outside vendor rooms. In-game check: `buy knife` in the
desert (refuse) → at Lup's (works, Lup's 4D Bargain in the haggle).

Watch items cumulative (drops 1–11): pools jump · armor dex penalties live · grenades consume ·
gear depletes · tuition charges · buy gates on stock · buy gates on vendor presence.

## Remaining follow-ups (logged, small): (b) `ship_weapon_purchase` tag rename → T3.19;
(c) tracking_fob `skill_bonus` one-field candidate, pending landing-shape check.

## Queue: powered suits · mines/breaching · WEBIFY.commissary_vendor_mode · CRAFT.HOOK passes ·
Lane C remainder + Lane F · Kamino · Drop-5 farming controls · OBS.quality_and_boosts_not_combat_read.
