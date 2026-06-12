# HANDOFF — Gundark Drops E + F: field gear & espionage kit (lane content complete)
## Session 2026-06-12 (6th) · Drops 7–8 · Rollup: `SW_MUSH_drops1-8_rollup_2026-06-12.zip` (CUMULATIVE — supersedes ALL prior zips; apply this one only)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then
`run_all_tests.bat`. Covers drops 1–8 at latest state. **Windows validation pending for all
eight** — four watch items below.

---

## 1. Drop 7 — Gundark Drop E: the outfitter, the sink, the seam

The fixes WERE the drop — pre-flight found the survival-gear loop broken at three joints:

- **⚑ Vek Nurren was a dangling trainer.** Five existing gear schematics (cooling_unit,
  breath_mask, radiation_suit, anti_theft_alarm, water_canteen) named him; he was seeded nowhere —
  the entire survival-gear teaching loop was phantom. (The near-collision with *Venn Kator*, the
  Docking Bay 94 ship-component trainer, is probably how it survived audits — now pinned
  distinct.) Seeded: a Sullustan ex-scout at **Lup's General Store**, `train_skills: [survival]`,
  seven schematics bound. In-game check: `talk vek` → `schematics` → craft a canteen.
- **⚑ `uses` never decremented** — radiation_suit's 10 uses and the alarm's 1 were decorative.
  Mitigation gear with `max_uses` now spends a use when it actually averts a hazard and is removed
  at zero, mutating **both stores** (db + the live session dict the hazard tick re-reads —
  stale-sync would have re-mitigated forever). Durables, equipment-slot, and legacy string matches
  untouched. **Windows watch #4: consumable mitigation gear now depletes.**
- **anti_theft_alarm finally does something** — wired into urban_danger's (empty) mitigation list;
  one averted pickpocket, then it falls apart.
- **New items on real consumers:** **Luma Flare** (4D thrown burn on the attack path + Drop D
  `single_use`) and the **Animal Excluder** — a new aversion seam in `roll_encounter`
  (`carried_keys` kwarg; post-pick 50% aversion for creature-templated picks only; cooldown still
  marks; "your animal excluder's ultrasonic whine turns it away" at the movement caller).

## 2. Drop 8 — Gundark Drop F: the carried-tool seam

§5's dominant pattern — skill-bonus gear — had **no consumer anywhere**. Now it does:
`perform_skill_check` applies the single best carried tool (`skill_bonus` on the gear dict;
never stacks; dialect-canonical; fail-open), placed at the chokepoint per the SRB.3 lead-bonus
precedent so every out-of-combat caller benefits. **Combat is structurally immune** — it never
calls the chokepoint (pinned), so a code slicer can't buff a blaster. Caught en route: the module
was missing a `json` import and the fail-open was masking the NameError.

**Roster, zero new NPCs:** Code Slicer (+1D security, A3) and UniTech Patch (+1D+2 security, A2)
under **Renna Dox**; Medscanner (+1D first aid, A2) under **Heist** — which properly answers Drop
E's med-aid deferral. Out with reasons: force detector (HOOK — quest artifact, never a recipe,
parsed-data pin), qualifier-bound bonuses (no-rewrite rule), plasma-cutter-as-weapon (fixed 7D at
150 cr), the blaster sight (combat mod, wrong seam), and the Avail-4/X devices → Drop G.

**Also: two pre-existing reds fixed with attribution.** `test_srb1_medic_stim` (four-entry pin)
and `test_srb1_stim_schematics` (hardcoded selector) were red in your clean upload — stale since
the medpac family landed in `_STIM_CATALOG` *with* correct schematics. The loop was closed; the
tests couldn't see it. If your Windows runs have been showing 2 mystery reds, these were them.

## 3. Verification

Sandbox: Drop E 19 + Drop F 14 · core craft/combat net **288** · chokepoint blast radius (SRB,
hazards, encounters, missions, era-clean) **273** · hygiene 9. Sandbox now has pytest-asyncio +
aiosqlite + bcrypt + aiohttp, so previously-unrunnable suites ran for real.

**Windows watch items (cumulative for drops 1–8):**
1. Drop 1 — trained skill pools jump (dialect unification).
2. Drop 4 — armor Dex penalties apply for the first time since v22.
3. Drop 6 — grenades consume on throw (frag/thermal retro-flagged; vetoable).
4. Drop 7 — consumable mitigation gear depletes.

## 4. The lane, and what's left

**Gundark content drops A–F are complete.** The roadmap's remaining lane item is **Drop G, the
finale**: R/X enforcement, the black-market loop (anti-vehicle grenade, the Firegems sabotage
device, the thermal-det craftability call, the X-band espionage devices), the `contraband: true`
field + security-scan hook (3a says it ships with the first contraband recipe — that's G), the
market-segmentation stock audit, and tuition. **G's tuition sub-scope is gated on your open
letter:** `CRAFT.schematic_tuition` — (a) 50%-of-base min 50 cr + free PC teach [recommended] ·
(b) flat per-band 100/250/500 · (c) keep free. Everything else in G can land without it.

Behind the lane (unchanged): powered-suit design pass · mines/breaching pass ·
`WEBIFY.commissary_vendor_mode` · CRAFT.HOOK passes (restraints; force-tech as a matched anti-Jedi
quest pair) · `CRAFT.market_segmentation_impl` · Lane C remainder + Lane F · Kamino · Drop-5
farming controls · `OBS.quality_and_boosts_not_combat_read`.

## 5. Session learnings

- **A missing consumer found once is a missing consumer everywhere.** The med-aid deferral (E)
  and the §5 roster (F) were the same gap; building the seam once retroactively re-opens every
  earlier deferral (macrobinoculars, gyro-grappler, med-aid all have a future home now).
- **Fail-open masks import errors.** The seam returned (0, None) for everything until
  smoke-tested — a try/except that protects a roll also protects a NameError. Smoke the happy
  path before trusting the guard.
- **Pre-existing reds get fixed WITH attribution, never silently** — verified against the clean
  upload first, so the changelog tells you which failures were already yours.
