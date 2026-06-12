# HANDOFF — Gundark Drop G: tuition, contraband, the black market
## Session 2026-06-12 (7th) · Drop 9 · **THE GUNDARK LANE IS COMPLETE (A–G)**
## Rollup: `SW_MUSH_drops1-9_rollup_2026-06-12.zip` (CUMULATIVE — supersedes ALL prior zips)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then
`run_all_tests.bat`. Covers drops 1–9 at latest state. Sandbox ran the **entire net green: 602
tests, zero failures.**

---

## 1. What shipped (your decision a, implemented same-session)

**Tuition.** Trainer recipes now cost **half base cost, floor 50 cr** (`schematic_tuition`,
charged under its own ledger tag — a sink that scales with the recipe). Talking to a trainer
grants their **cheapest recipe free, once per character** ("first lesson's on the house"), lists
the rest with prices, and the new **`learn <name>`** command buys them one at a time — trainer
must be in the room, broke students get refused cleanly, and the free lesson works through
`learn` too if they skip the chat. **PC-to-PC teaching stays free** (pinned). I verified before
building that no tutorial chain depends on trainer grants — the KDY chain uses its own
`+craft fetch` flow — so first-free is pure diegesis, kept anyway.

**⚑ Windows watch #5 (behavior change):** trainers no longer hand over whole catalogs on hello.
Existing characters keep everything they've learned; new learning costs credits.

**Contraband, shipped WITH its enforcer (3a).** `contraband: true` recipes flag the **landed
item**, and **patrol boardings sweep carried inventory**: same Con-15-to-hide flow as cargo —
fail and the goods are **confiscated** (the band's risk-side sink) plus a Class-4 infraction.

**The black market.** Disruptor Pistol (6D+2, diff 24) · Predator Rifle (7D, diff 26 — the
Heroic cap) · Anti-Vehicle Grenade (7D, single-use, 26). All q70 materials, all contraband, all
taught by **Gundark himself** — the catalog's in-fiction compiler, a Whiphid dealer in the Nar
Shaddaa Undercity Market, who tells every student the truth: *"Carry it past a boarding and it's
theirs, not yours. I teach you to BUILD it so the loss is survivable."* The lane closes on its
own bookend.

**Calls resolved by recommendation (vetoable):** thermal detonator **stays uncraftable** — the
icon's scarcity is its identity, and a craftable 10D would own the ordnance economy. Firegems
aren't a recipe (natural gems; the hyperdrive-sabotage hook stays logged for the cartel lane).

**Pin discipline:** drops A, B, and C each carried a "no contraband yet" guard — all three
flipped WITH the drop into scope pins (exactly the band, nothing lawful), so a stray flag on a
lawful recipe fails loudly.

## 2. Verification

Drop G suite 19 · **full net 602/602** (craft A–G, P0, crafting state, skill keys, combat incl.
the umbrella, economy, patrol + Q1 + era sweeps, SRB, hazards, wilderness, encounters, hygiene).

**Windows watch items, cumulative drops 1–9:**
1. Drop 1 — trained skill pools jump · 2. Drop 4 — armor Dex penalties finally apply ·
3. Drop 6 — grenades consume on throw · 4. Drop 7 — mitigation gear depletes ·
5. **Drop 9 — trainer catalogs cost tuition.**
In-game walk for G: fly somewhere patrol-heavy carrying a crafted disruptor and comply with a
boarding; visit Gundark in the Undercity Market; `talk` then `learn predator rifle`.

## 3. The lane ledger, A→G

A: foundations + consumables migration · B: 14 lawful weapons + the skill-key P0 ·
C: 10 armor + Sela Tarn + the v22 dex-penalty latent · D: ordnance + single-use consumption ·
E: Vek Nurren + the uses sink + the excluder seam · F: the carried-tool seam + espionage kit ·
G: tuition + contraband + Gundark. Net new this lane: **~40 recipes, 3 NPCs, 5 engine
mechanics** (skill-key canonicalization, single-use, mitigation consumption, encounter aversion,
tool bonuses, tuition/contraband) — every faucet landed with its sink.

## 4. What's next (the queue, post-lane)

1. **Brian:** apply + the full Windows suite for drops 1–9.
2. The backlog resumes at the deferred design passes and the broader roadmap:
   **`CRAFT.market_segmentation_impl`** (vendor stock audit vs the new ~40-recipe catalog —
   now the natural immediate follow-up, since the craft economy it segments is finally whole) ·
   powered-suit pass · mines/breaching pass · `WEBIFY.commissary_vendor_mode` · CRAFT.HOOK
   passes (restraints; the force-detector + suppression-cage anti-Jedi quest pair) · Lane C
   remainder + Lane F · Kamino · Drop-5 farming controls ·
   `OBS.quality_and_boosts_not_combat_read`.
3. On "continue" I'd take **market segmentation** unless you point elsewhere.

## 5. Session learnings

- **Replace a free flow with a paid one by keeping ONE free path open** — first-lesson-free cost
  nothing and made the tuition change feel like worldbuilding instead of a paywall.
- **A "yet" pin is a promise with a due date.** Three suites carried the same no-contraband
  guard; shipping the enforcer meant flipping all three in the same drop — and the flipped pins
  are stronger (scope, not absence).
- **End a content lane on its own fiction.** The catalog's author selling the catalog's
  contraband isn't just flavor — it gave the gating mechanics a diegetic home for free.
