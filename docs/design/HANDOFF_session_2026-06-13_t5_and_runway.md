# HANDOFF — Session 2026-06-13 (t5-trainer arc + runway)

**Branch:** `drop/t5-questline-engine` (built on `roadmap`, which carries
the overnight drops 25–32). **NOT merged to main or roadmap** — your
`run_all_tests.bat` gate.
**Author:** Claude Opus 4.8 (1M), attended → autonomous session with Brian.

---

## TL;DR

Eight drops (33–40), all committed + verified, on the feature branch.
Completed the **T5 master-trainer questline arc** end-to-end, wrote the
**ambient-NPC-life** post-launch design you asked for, logged the
**parallel tooling session's** records, and cleared the **entire greenlit
runway**: all 5 world-event flag consumers, commissary sellback,
Director CW faction mapping, and breaching charges. Then hit the edge of
what's design-resolved and **logged 2 genuine forks** (with recommended
shapes) rather than build them blind. Every drop: targeted tests +
reachability/walkthrough where relevant + the read-only verify fan-out +
227-test smoke green. Nothing merged.

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

## Forks I LOGGED instead of building (your judgment needed)

I cleared everything design-resolved, then stopped at genuine forks
rather than guess (your "log real forks" rule):
1. **`CRAFT.breaching_obstacle_placement`** (drop 40) — the breach
   mechanic works, but no world-data object-seeding path exists, so
   obstacles are admin-placeable now but not authored at scale. Open:
   seeding loader vs admin-only vs gate-real-map-exits (the map-entangled
   option). Rec: small additive object-seeding loader; defer exit-gating.
2. **`T2.DEF.t5_ship_part_items`** — the hyperdrive/ion t5 parts craft but
   are inert in space; wiring them needs a NEW install mechanic (no
   `install` verb / ship-component apply path exists). Logged with a
   recommended shape (player `install <part>` at a shipyard, consume on
   install, one-per-stat cap, write to ships.systems, owner-gated). Not
   built blind.
3. **`CRAFT.harvest_skill_flavor`** — confirmed `HARVEST_SKILL='survival'`
   is live (the rec's status quo). Left as your flavor call (Survival vs a
   post-launch Technical/Search override); no build, not blocking.

(Plus the standing pending calls from before this session — see
`design_calls_pending_brian`.)

## State of the suite
- Every drop's targeted tests green. Full chain/questline/crafting/
  rewards/economy/director/breaching regressions green. **227-test smoke
  green after each drop.** Reachability invariant green for all chains.
- **I did NOT run `run_all_tests.bat`** (the full ~7,700 Windows suite) —
  that's your merge gate. I expect green; the authoritative run is yours.

## Suggested next session
1. Run `run_all_tests.bat`; merge `drop/t5-questline-engine` (33–40) if
   green. (Separately decide on `roadmap` 25–32.)
2. Apply `TOOL.settings_apply` after the parallel session's settings.json
   lands.
3. The 3 forks above when you want to steer them.
4. Pre-launch: ambient-life **Phase 0** DB scaffolding (T3.22).

## Untracked strays (NOT mine — parallel sessions)
`data/guides/*`, `Guide_27`, `tools/guide_lint.py`, `docs/dev/` (guides
session); `sw_d6_mush_architecture_v52.md`,
`HANDOFF_readiness_sequencing_review_2026-06-13.md` (readiness session);
`.claude/settings.json`/`.gitignore`/`make_upload_zip.ps1`/`.claude/agents`/
`.claude/commands`/`package*.json`/`node_modules` (tooling session). All
left untouched and out of my commits.
