# HANDOFF — P2P cap removal + Gundark Drop D (ordnance + consumption)
## Session 2026-06-11 (5th) · Drops 5–6 · Rollup: `SW_MUSH_drops1-6_rollup_2026-06-11.zip` (CUMULATIVE — supersedes all prior; apply this one zip)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then
`run_all_tests.bat`. Covers drops 1–6 at latest state. **Windows validation pending for all six.**
(Housekeeping: last session ended at your usage wall right after the TODO update — the
decision-recording handoff folds into this one.)

---

## 1. Drop 5 — P2P cap removed (your decision a, recorded + implemented)

Both S51 enforcement blocks are gone — nothing in the trade path refuses on volume. Kept: the 5%
tax, the `p2p_transfer`/`p2p_tax` ledger tags, the alt-account [TRADE BLOCKED] prohibition, and the
rolling-window read — which now feeds a **fail-open velocity alert** (caution at the old 1,500,
critical at 7,500; `@economy` shows them; telemetry can never disturb a completed trade).
All three old-policy pin sites were rewritten **with** the drop — tier2, S51 constants, and the EE8
smoke scenario (now: a 6,000-cr trade completes, tax shows, alert lands) — plus guards so a future
"fix the test by restoring the cap" fails loudly. The sandbox ran the S51 DB-harness suites for
real this time (aiosqlite/bcrypt/aiohttp installed): 105 green.

## 2. Drop 6 — Gundark Drop D: ordnance, scoped by two pre-flight facts

The §8 "blast risk" pre-flight found more than blast: **`blast_radius` has no combat consumer**
(frag/thermal single-target behavior is the precedent — blast stays data + notes), and **ammo is
wholly unmodeled** — every grenade at HEAD was an infinite-use weapon. Craftable explosives on top
of that would be a permanent-weapon printer, so per faucets-and-sinks the drop ships a small
consumption mechanic: `single_use` rows are cleared from the equipment slot at attack
**declaration** (resolution rolls the action's captured strings, so the early clear is safe; an
explicit `with … damage …` override never eats the grenade).

**⚑ Windows watch item #3 (behavior change, vetoable):** frag_grenade and thermal_detonator are
retro-flagged `single_use` — grenades stop being infinite, with an "expended with the throw" line.
If you'd rather grandfather the old behavior, say the word and I'll lift the retro flags.

**Roster (demolitions per your b=a, Kayson-bound per a=b):** Incendiary Grenade (Avail 1 — Old
Republic jump-trooper issue, era-gold) · a frag-grenade schematic over the existing row ·
the Merr-Sonn Stun Grenade (6D stun-only, **book-rechargeable — the sanctioned `single_use: false`
exception**, pinned). Thermal stays uncraftable (pinned). Deferred with reasons: gas/glop/smoke
(effect-primary), mines/breaching/detonite (placement mechanics — their own pass), nets
(restraints), missiles (launchers), anti-vehicle + **Lowickan Firegems** (contraband → Drop G; the
Firegems hyperdrive-sabotage gem is flagged for the cartel plot lane — it's a turnkey assassination
hook).

## 3. Verification

Sandbox: P2P suite 16 + economy batch 105 · Drop D suite 17 · combined craft A–D + skill-keys +
combat batches **256 green** (incl. the session54 combat umbrella) · hygiene 9. **Windows watch
items now three:** drop-1 trained-pool jumps · drop-4 armor dex penalties live · drop-6 grenade
consumption + the rewritten economy pins.

## 4. Queue

1. **Brian:** apply + suite run + onboarding walk (drop 3 unblocked it). Letter still open:
   **`CRAFT.schematic_tuition`** (a = 50%-of-base tuition + free PC teach · b = flat per-band ·
   c = keep free).
2. **On "continue": Gundark Drop E (field gear)** — restraints stay HOOK-gated out; pre-flight
   there is the search-bonus-gear consumer question (does anything modify `perform_skill_check`
   from carried gear?).
3. Then F (espionage, scan-loop thin pass) · **G last** (trainer gating, R/X enforcement, tuition
   if (a), black-market loop: anti-vehicle grenade, Firegems, the thermal-det craftability call).
4. Behind the lane: powered-suit design pass · mines/breaching design pass ·
   `WEBIFY.commissary_vendor_mode` · CRAFT.HOOK passes · `CRAFT.market_segmentation_impl` (stock
   audit, with Lane C/G) · Lane F · Kamino · Drop-5 farming controls ·
   `OBS.quality_and_boosts_not_combat_read` (quality→combat design pass).

## 5. Session learnings

- **"The named risk" is usually the visible half.** Blast was flagged; the infinite-ammo hole was
  the real economy threat sitting next to it. Pre-flight the whole consumer chain, not just the
  flagged field.
- **Consume at commitment, not resolution** — when an engine resolves declared actions from
  captured strings, the declaration point is the safe place to mutate equipment.
- **Policy reversals must flip their pins in the same drop**, with guards against re-flipping.
  Three suites pinned the cap; all three now pin its absence.
