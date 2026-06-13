# HANDOFF — Session 2026-06-13 (t5-trainer arc + runway)

> **THIS IS THE FRESH-CHAT PICKUP POINT** for continuing main development.
> Read this top section first; the rest is the full session detail.

**Status: MERGED + PUSHED.** `main` = origin/main = **`07fbd70`** (drops
24–43 + bookkeeping; fast-forwarded, no merge commit). The feature branch
`drop/t5-questline-engine` is also pushed. The full single-threaded suite
did NOT complete in the merge agent's harness; merge signal was **565
targeted tests green + the 2 known count-pin canaries reconciled + 8
clean 227-test smoke runs**. A **separate xdist session** is running the
full suite to triage anything that slipped — see
`HANDOFF_xdist_suite_triage_2026-06-13.md`.

**Gates lifted** (per Brian): `git merge`, `git push`, and
`run_all_tests.bat` removed from the settings.json deny list; destructive
guardrails (reset --hard, checkout, clean, rebase, rm -rf, Remove-Item)
kept. `pytest-xdist 3.8.0` installed.

**Companion handoffs:** `HANDOFF_xdist_suite_triage_2026-06-13.md` (the
full-suite triage session); `HANDOFF_crafting_integration_review_2026-06-13.md`
(the parallel crafting audit — its 2 forks are now DECIDED, see below).

**Branch:** built on `roadmap` (overnight drops 25–32) → now all on `main`.
**Author:** Claude Opus 4.8 (1M), attended → autonomous session with Brian.

---

## TL;DR

**11 drops (33–43) + 2 bookkeeping commits + 2 post-launch design docs**,
all committed + verified, on the feature branch. Completed the **T5
master-trainer questline arc** end-to-end; cleared the **entire greenlit
runway** (all 5 world-event flag consumers, commissary sellback, Director
CW faction mapping, breaching charges + world-seeded obstacles, harvest
skill override); **verified the t5 ship-part install loop already works**
(didn't rebuild a redundant mechanic); wrote **3 post-launch designs**
(ambient NPC life T3.22, party skill challenges T3.23) + logged the
parallel tooling session's records. **Coordinated live with the parallel
crafting-integration review**: read its findings when they landed,
integrated the safe one (dropped a phantom craft-message promise), logged
its 2 real forks for you, and confirmed zero conflict with shipped work.
Every drop: targeted tests + reachability/walkthrough where relevant +
227-test smoke green. **Nothing merged** — your `run_all_tests.bat` gate.

---

## Commits this session (`drop/t5-questline-engine`, oldest→newest)

| Commit | Drop | What |
| --- | --- | --- |
| `e811ab5` | 33 | T5-questline arc A — multi-slot chain engine + `mastery` verb |
| `ec79109` | 34 | T5-questline arc B slice 1 — "The Hermit's Trial" (Jedi/lightsaber) + the schematic gate + per-step reward consumer + rep tuning |
| `c6931ff` | 35 | T5-questline arc B slices 2–5 — the other 4 master trainers + tooling-session CHANGELOG/TODO log |
| `294679b` | 36 | World-event flag consumers 2/5 (rare_vendor + krayt_bounty) + this handoff |
| `698dade` | 37 | World-event flag consumers 3/5 (distress + hutt_auction + brawl) — all 5 done |
| `1c0376c` | 38 | Commissary sellback (anti-laundering refund + bind-to-channel) |
| `ec92ea8` | 39 | Director CW faction-order mapping layer |
| `0afece2` | 40 | Breaching charges (breach verb + demolitions check) |
| `68470a7` | — | Bookkeeping: handoff refresh + 2 logged forks |
| `54a9375` | 41 | Harvest per-region skill override (Republic-tech salvage → Search) |
| `a7f40e3` | 42 | Breaching obstacle placement — world-data seeding + 3 authored obstacles |
| `254b7e1` | — | Design: party skill challenges (post-launch, T3.23) |
| `5160eec` | 43 | T5 ship-part effects VERIFIED (already working) + crafting-review integration |

---

## What landed, by area

### T5 master-trainer questlines — roadmap item `T2.DEF.t5_trainer_storyline` DONE
Design: `docs/design/t5_trainer_questlines_design_v1.md`. Your 4 resolved
forks (gated questline EACH, RICH, rep≥50 + Contested/Wilds, generalize
the chain engine).
- **Engine (33):** single-slot chargen-only chain engine → 2nd mid-game
  questline slot (`active_questline`) via a `state_key` param (onboarding
  byte-neutral), `kind: questline` field, slot-aware dispatcher +
  teleport, the `mastery [start|status|abandon]` command + NPC-offer hook.
- **Content (34–35):** 5 rich 5-step questlines, each unlocking one t5
  schematic, each with an original CW trainer + themed enemy in a
  Contested/Wilds zone (Vehn Tasaal/lightsaber, Vossk/blaster,
  Corso Venn/hyperdrive, Dax Orrin/ion, Sabra/armor). Data-driven
  walkthrough test walks ALL 5 to graduation through the live dispatcher;
  all-5-gated invariant.
- **The gate:** t5 recipe hidden until questline graduated AND faction
  rep ≥ 50, enforced in both `talk`/teach and `learn`.

### Two mid-arc decisions you made (both implemented + pinned)
1. **Per-step chain rewards → ship for all chains** (`apply_step_rewards`
   was items-only; now delivers credits via a metered faucet + rep via
   the funnel).
2. **Faction rep → "tune lower"** (twice): every onboarding chain now
   leaves a player at **recognized (~8–13)**, the questline at **18** —
   the rep-50 t5 gate is earned through play. Pinned by a ceiling test.

### Ambient NPC life (your post-launch request)
`docs/design/ambient_npc_life_design_v1.md` + TODO **T3.22**. Idle-Ollama
background sim, Python-first/Ollama-preemptible, no unprompted PC
interaction v1, **DB scaffolding lands pre-launch** (empty CREATE TABLE +
JSON `extra` columns) so the post-launch build never migrates a live DB.

### World-event flag consumers — ALL 5 done (drops 36–37)
The WORLDEVENT.flag_effect_consumers gap is fully closed. Thin consumers
over existing seams (contraband_scan pattern): `rare_vendor` (buy
discount), `krayt_bounty` (bounty tier-bump), `distress_active` (forces a
MEDICAL/premium mission), `hutt_auction` (rep-gated rare purchase at +40%,
fail-closed), `brawl_active` (forces the d66 brawl beat).

### Commissary sellback (drop 38) — `ECON.commissary_sellback` DONE (all 3 pieces)
Vendor refusal of faction-issued gear + a `+commissary sell` 50%-refund
channel (faucet smaller than the purchase sink → buy/sell is a net loss,
pinned) + bind-to-channel give/trade (same-faction-only).

### Director CW faction mapping (drop 39) — `DIRECTOR.faction_model_cw_mapping` DONE
The LLM Director can now issue CW faction-orders: `normalize_faction_order_code`
maps GCW aliases → CW org codes at the order boundary; the digest carries
a CW faction legend. ZoneState axis math untouched. Partially retires
`TD.DIRECTOR_FACTION_MODEL_GCW`.

### Breaching charges (drop 40) — `CRAFT.mines_breaching_split` breaching half DONE
`breach <target>` + `engine/breaching.py` (Demolitions check vs a
`breachable` room object, single-use charge, no blast-on-players) +
craftable `breaching_charge`. Placed mines stay deferred.

### Parallel tooling session — logged per your request
CHANGELOG + TODO (`TOOL.tooling_additions` done, `TOOL.settings_apply`
pending you — the deferred settings.json allow/deny lines).

---

## The 3 "go for all 3" items — all resolved
After I logged them as forks, you said "go for all 3." Final state:
1. **Harvest skill override (drop 41)** — you chose per-region override;
   `coruscant_underworld → search` for Republic-tech salvage. DONE.
2. **Breaching obstacle placement (drop 42)** — you chose "seed objects
   now, exits later"; added the first object-seeding-at-world-build path +
   3 authored obstacles. DONE (map-exit gating deferred).
3. **T5 ship-part install (drop 43)** — turned out **already working** (the
   "inert" claim was stale; CRAFT.P0.3/P0.4 wired it). I verified instead
   of rebuilding (a new mechanic would've been redundant) and closed the
   verification gap with `test_t5_ship_part_effects.py`. DONE.

(Your install sub-decisions — shipyard full vs aboard ×0.66, consume,
one-per-stat cap — are how the EXISTING `_install_mod` already behaves,
modulo the exact ×0.66; if you want the aboard-vs-shipyard reduced-boost
split specifically, that's a small follow-up on the working base — noted,
not built, since the base already installs+effects correctly.)

## Crafting-integration review — landed + handled (both forks DECIDED)
The parallel review (`HANDOFF_crafting_integration_review_2026-06-13.md`)
landed mid-session. I integrated the safe finding (dropped a phantom
craft-message that promised a combat bonus no code delivers, drop 43) and
Brian DECIDED both real forks:
1. **`CRAFT.quality_combat_read_armor_consumables` → BUILD IT (Option A).**
   Crafted quality SHOULD matter for armor + consumables (like weapons).
   **Queued as `CRAFT.armor_consumable_quality_combat`** (tier_2) — NOT yet
   built; it's a careful combat-collision drop: read the worn-armor
   INSTANCE quality in `get_armor_protection` and fold a HARD-CAPPED soak
   delta (mirror the weapon +1D pip-cap, no power creep); **bundle the
   armor half with the `TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES`
   migration**; land solo on a quiet combat window (combat.py/items.py/
   character.py are HIGH collision). Consumable half threads quality into
   potency, sequenced after — and consider a separate (tighter) cap there,
   since potion-potency is the riskier power-creep knob. **This is the top
   real build item for the next dev session.**
2. **`CRAFT.rare_resource_no_vendor` → RESOLVED, keep gated.** Rare
   materials stay player-sourced (harvest/hunt → give/trade to crafters);
   intentional sink-side design. No change made.

(Plus the standing pending calls — see `design_calls_pending_brian`.)

## State of the suite
- **565 targeted tests green** across every module touched this session +
  the 2 count-pin canaries reconciled (`test_f7c1_village_trials` NPC
  count 201→211 = the 10 t5-trainer NPCs; coruscant-landmark already
  clean). **227-test smoke green after every code drop** (8 passes).
  Reachability invariant green for all chains.
- The **full single-threaded `run_all_tests.bat`** did NOT complete in the
  merge agent's harness (background reaping + self-inflicted contention).
  The **xdist session** (`HANDOFF_xdist_suite_triage_2026-06-13.md`) is the
  full-suite gate — run it / check its results before treating main as
  fully green.

## Suggested next session
1. **Confirm the full suite** via the xdist session (or `run_all_tests.bat`
   directly now that it's un-gated) — the targeted + smoke signal is
   strong but not a substitute for the full run.
2. **Build `CRAFT.armor_consumable_quality_combat`** (Brian-greenlit, top
   item) — the careful combat-collision drop above; bundle armor with the
   equipment-instance migration.
3. The standing forks in `design_calls_pending_brian` (several crafting
   long-poles + the world-event/director calls).
4. Pre-launch: ambient-life **Phase 0** DB scaffolding (T3.22). Post-launch
   designs ready: ambient life (T3.22), party skill challenges (T3.23).
5. Apply the rest of `TOOL.settings_apply` if the tooling session hasn't.

## Untracked strays (NOT mine — parallel sessions)
`data/guides/*`, `Guide_27`, `tools/guide_lint.py`, `docs/dev/` (guides
session); `sw_d6_mush_architecture_v52.md`,
`HANDOFF_readiness_sequencing_review_2026-06-13.md` (readiness session);
`.claude/settings.json`/`.gitignore`/`make_upload_zip.ps1`/`.claude/agents`/
`.claude/commands`/`package*.json`/`node_modules` (tooling session). All
left untouched and out of my commits.
