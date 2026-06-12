# HANDOFF — Gundark Drop C: armor + Sela Tarn + the v22 dex-penalty latent
## Session 2026-06-11 (3rd) · Drop 4 · Rollup: `SW_MUSH_drops1-4_rollup_2026-06-11.zip` (20 files, CUMULATIVE — supersedes drops1-3)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then
`run_all_tests.bat`. One zip, all four drops at latest state. **Windows validation pending for
drops 1–4** — drops 1 and 4 both change combat math (watch items below).

---

## 1. What shipped

**Drop C content.** 10 non-powered armor schematics (3× Avail-1, 3× Avail-2, 4× Avail-3) + 10
`type: armor` rows — in **weapons.yaml**, because that's the registry wear/soak/sheet actually read;
the plan's separate armor.yaml was superseded by extend-don't-add. Difficulties recomputed in-test
from a §10-anchored unit rule (total protection DICE, loose pips ≥3 round up — the corondexx
worked-sample lands on exactly 14). Sub-systems with no consumer are notes; **§3.2 powered/space
suits are deferred wholesale** (no `powersuit operation` skill, no mount consumer — that's a design
pass, pinned by test so nothing rosters piecemeal).

**The trainer.** Sela Tarn — original character, ex-Judicial quartermaster — seeded at **Kayson's
Weapon Shop** (one storefront, two trades, per your Tatooine density directive). `talk sela` grants
the 10 schematics and her `train_skills: [armor_repair]` menu works for CP training. In-game check
when you walk it: `talk sela` → `schematics` → craft a vest → `wear` it → `+sheet` shows protection.

**⚑ The v22 latent (watch item #2).** Armor Dexterity penalties have NEVER applied: data stores
them signed (`"-1D"`) and `DicePool.parse` silently returns (0,0) on signed strings, so all three
combat consumers subtracted zero — Bounty Hunter Armor included, since v22. The producer now
returns the magnitude. **Combat pools for anyone in penalty armor correctly drop**; any test
pinning the old free-heavy-armor numbers was pinning the bug.

**Drop-1 ripple fixed:** trainer menus did a raw underscore `.get` against space-form PC skill
dicts — trained bonuses displayed as 0, and pre-unification, underscore `train_skills` entries were
silently omitted from menus entirely (Venn's list was incomplete). Canonicalized.

**Logged, not built:** `OBS.quality_and_boosts_not_combat_read` — combat reads damage AND
protection from the registry by key, so crafted quality and experiment boosts never reach combat
math. Convention-consistent today (Drop C deliberately matches weapons), but it means "better
crafted gear" is currently decay/value-side only and experiment boosts may be display-only. That
wants a deliberate quality→combat-stats design pass, probably alongside the crafting follow-ups —
your call on when.

## 2. Verification

Sandbox: Drop C suite 20 green (incl. full-loop landing→wear integration, soak parse of the new
pip-only protection strings, the BH-armor latent pin) · combined craft+combat batch 220 ·
era-cleanness 12 · hygiene 9. **Windows watch:** drop-1 pool jumps + drop-4 penalty applications,
`test_craft_p2_gundark_drop_c` (20), the world rebuild picking up `npcs_drop_craft_c_armorer.yaml`.

## 3. Queue

1. **Brian:** apply + suite run + resume the onboarding walk (drop 3 unblocked it); optional Sela
   walk above.
2. **Letters still open:** `ECON.p2p_cap_review` (a/b/c) · `CRAFT.schematic_tuition` (a/b/c).
3. **On "continue": Gundark Drop D — ordnance** (`demolitions`, unblocked). Pre-flight there:
   WeaponData already has `blast_radius` and a `grenade` type — first step is verifying the blast
   consumer in combat before rostering (the §8 named risk).
4. Then E (field gear, restraints stay out) · F (espionage, detector stays out) · G last (gating +
   tuition if (a)). Behind those: powered-suit design pass, commissary mode:'vendor', HOOK passes,
   Lane C remainder + Lane F, Kamino, Drop-5 farming controls.

## 4. Session learnings

- **Signed strings + unsigned parsers = silent zeros.** Same shape as the dialect bug: a lookup
  that can't fail loudly degrades to a legal-looking no-op. When data carries a sign convention,
  pin the parse at the producer.
- **"The plan said new file" loses to "the registry says otherwise."** The armor.yaml call only
  became visible by walking the live consumer chain first — pre-flight before rostering, every
  drop.
- **Co-location beats sprawl** for trainer NPCs under the density directive — and it reads better
  diegetically than a one-NPC shop.
