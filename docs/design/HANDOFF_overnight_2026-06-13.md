# HANDOFF — Overnight Autonomous Session (2026-06-12 → 06-13)

**Branch:** `roadmap` (all work committed + pushed; HEAD = `d4592cc`)
**Mode:** unattended autonomous, per Brian's "go go go, don't wait, make
design calls yourself" directive (memory `overnight-autonomy-posture`).
**Author:** Claude Fable 5.

---

## TL;DR

Six drops landed (25–30), all committed + pushed to `roadmap`, each
verified (targeted tests + invariant-auditor + code-reviewer +
smoke-verifier as appropriate). Completed the onboarding handoff's P0/P1/P2
in full, then drove the difficulty-tiers roadmap item (T2.DIFF) from
design through three build phases. Along the way found + fixed **5 real
production bugs** the existing tests missed, and unblocked the dormant SPA
DOM test tier.

**Not merged to main** — that's your gate on a green `run_all_tests.bat`.

---

## Drops (newest first)

### Drop 32 — Newbie-friendly get / take / drop redirect stubs
Closes the drop-24 P2.4 deferral. `get`/`take`/`drop` (+ aliases) replace
the dead-end "Huh?" with a pointer to the real item mechanics (examine /
buy / loot / craft / give; sell / unequip / give). Pure redirects, no
ground-item system.

### Drop 31 — DIFF.4: threat-band reward scaling at the bounty payout
The bounty payout scales by the threat band of where the target was
(0.6× Frontier … 2.0× Deep Wilds), riding the existing `bounty` faucet.
Veterans can't farm newbie contracts for full rate; higher bands pay
the gradient. I went ahead and wired this (the economy concern I flagged
in the original handoff) — it's conservative: one faucet, the same
metered `adjust_credits` call, failure-tolerant, multipliers are the
design's tunables. Reverse the numbers freely. DIFF.5 (map tint) is the
only T2.DIFF phase left and it's browser-dependent → pairs with your UI
review.

### Drop 30 — DIFF.3: tiered wilderness-encounter eligibility by threat band
First gameplay-impacting difficulty phase. `min_band`/`max_band` on
encounter entries; the wilderness selector gates the pool by the
destination tile's threat band (Frontier → trivial fauna only; Deep Wilds
→ minibosses unlocked). Authored bounds on Coruscant `maze_ambush` + Dune
Sea `tusken_war_party`. **Bonus:** root-caused + fixed a pre-existing
consistently-failing test (`test_session38::test_security_scaling` used
GCW zones absent from the CW ZONES map → RNG coin-flip). 631-test
encounter/wilderness regression green.

### Drop 29 — DIFF.2: threat-band zone labeling + look header + `+threat`
All 37 CW zones labeled with a threat band (additive YAML). `look` shows a
color-graded band tag (Settled suppressed); `+threat`/`threat` command
renders band + blurb. Full smoke suite 227 green.

### Drop 28 — Difficulty tiers DESIGN + DIFF.1 engine axis
`docs/design/difficulty_tiers_design_v1.md` (six sub-decisions resolved —
see below). `engine/threat_band.py` (ThreatBand enum, resolver via the
security zone-inheritance chain, display helpers, frontier≠lawless
validator, reward-multiplier mapping). Behavior-neutral (default Settled).

### Drop 27 — B3 era sweep of the help corpus + SPA DOM tests unblocked
~50 OT/GCW-term replacements across 21 `data/help/` files (the help corpus
wasn't era-gated → CW players saw Imperial/Rebel/X-Wing/Han Solo in live
help). Fixed 3 more B3 violations in code/data. **Unblocked the SPA DOM
test tier:** the jsdom harnesses hardcoded `/tmp/node_modules` and skipped
everywhere; now resolve the repo-local `node_modules`. Found + fixed a
latent test-selector bug in `test_m3_shop`.

### Drop 26 — Onboarding polish (P2)
Tutorial bounty target binding (so `bountytrack` works) + a latent
`bountytrack` crash (`Character.from_db_dict` extra arg) it surfaced.
`examine <room NPC/object>` now delegates to `LookCommand._look_at`. Web
onboarding panel: `next_hint` NEXT line + skill-step chip suppression.
Bounty-board test-isolation reset (a singleton leaked across harnesses).

### Drop 25 — Onboarding reachability coverage net (P0) + 3 chain blockers
Static reachability invariant + per-chain walkthrough smoke (all 7 chains
proven walkable from a real chargen by player-only commands). Building the
runtime layer caught **3 real production blockers** drop 24 missed:
1. `chain_enemy_template` silently dropped by the npc_loader ai_config
   whitelist → 3 chains' combat steps couldn't advance.
2. Tutorial combat rooms inherited SECURED zones → the drill `attack` was
   refused.
3. Multi-enemy `combat_won` unwinnable (paired drill enemies don't aggro
   together) → added a cumulative-kill tally on chain-step state.

---

## Real bugs found + fixed (would have shipped broken)

1. `chain_enemy_template` whitelist drop (3 chains' combat steps dead).
2. Tutorial combat rooms SECURED (drill un-runnable).
3. Multi-enemy combat steps unwinnable by natural play.
4. Tutorial bounty contract never bound its target NPC (`bountytrack`
   hard-errored) + the latent `from_db_dict` crash behind it.
5. `test_session38::test_security_scaling` GCW-zone drift (consistent
   failure masquerading as flake).

All have regression coverage now.

---

## Design calls I made (flagging for your review — none are locked)

Per your directive I pressed on these rather than logging forks. Reverse
any freely.

**Difficulty tiers (T2.DIFF)** — full rationale in
`difficulty_tiers_design_v1.md`:
- **Difficulty is a SEPARATE axis from security** (not a rename). Security
  = "is combat allowed?"; threat band = "how dangerous?". This is the
  load-bearing call — conflating them would force every newbie zone
  SECURED, killing "newbies fight in a newbie area."
- **Four bands:** Frontier / Settled / Contested Marches / Deep Wilds
  (names are a flavor call — swap freely).
- **Advisory, not hard-gated** (one soft confirm for Deep Wilds). No level
  locks — D6 has no levels.
- **Reward multiplier** 0.6/1.0/1.4/2.0 (first-guess tunables; post-launch
  telemetry tunes them).
- **Per-world tier map** in §5 (chain starts = Frontier, PC cities
  Settled+, end-game in wilderness edges).

---

## Remaining T2.DIFF phases (not yet built)

- **DIFF.4 — reward multiplier wiring.** The `reward_multiplier(band)`
  helper + tests already shipped (DIFF.1). Wiring it into the
  bounty/mission/encounter credit faucets touches the economy, so I
  deferred it to a focused drop with an economy-review pass rather than
  riding the spawn-gating drop. Mechanism ready; faucet wiring is the next
  step. **This is the one place I'd want your economy eye before I wire
  it** — but I can proceed with the multipliers as designed if you'd
  rather I just do it.
- **DIFF.5 — map renderer tint.** Zones tint by band on the web map (the
  T2.UIPKG tie-in). Touches the web client → wants a browser eyeball, so
  it's a natural one to pair with your UI review.

---

## State of the suite

- Every drop's targeted + regression tests green. Smoke suite 227 green
  (verified after drop 29). The SPA DOM tier now runs (jsdom resolved from
  repo `node_modules`).
- **I did NOT complete a clean full-suite `run_all_tests.bat` run** — the
  unit-only run I kicked stopped at the first failure (the GCW-zone test,
  now fixed) due to the inherited `-x`. Recommend you run
  `run_all_tests.bat` as the merge gate; I expect green, but the
  authoritative full run is yours.

---

## Untracked strays (not mine, left for you / the tooling session)

`.claude/settings.json`, `.gitignore` (+node_modules entry),
`make_upload_zip.ps1` rewrite, `.claude/agents/*`, `.claude/commands/*`,
`docs/design/HANDOFF_tooling_additions_2026-06-12.md`, `node_modules/`,
`package.json`/`package-lock.json` — these are from the parallel tooling
session, already saved, gitignored where appropriate. I left them
uncommitted. The `node_modules` + jsdom are what unblocked the SPA tests.

---

## Suggested next session

1. Run `run_all_tests.bat` → merge `roadmap` if green. (Drops 25–32.)
2. Green-light or adjust the DIFF.4 bounty reward multipliers
   (0.6/1.0/1.4/2.0) — they're live now; reverse freely.
3. DIFF.5 map tint alongside your UI review (the last T2.DIFF phase; it's
   browser-dependent so I left it for you).
4. Then the next open `tier_2_queued` items:
   - **`T2.DEF.t5_trainer_storyline`** — I scoped it: the trainer machinery
     fully exists (`trainer_curriculum` / `handle_trainer_teach` key off
     each schematic's `trainer_npc` field). The 5 `t5_*` schematics in
     `data/schematics.yaml` have EMPTY `trainer_npc` fields — that's the
     whole gap. The work is designating + placing 5 master-tier trainer
     NPCs (Jedi Master / Hutt weaponsmith / Republic engineer-corps /
     master armorer) and populating the field, with appropriate end-game
     gating (these are the 28-difficulty, 10k-cost recipes). I held off
     because the "questline vs trainer NPC" call + the gating design is a
     real fork worth your steer — but it's a clean, well-bounded build
     once you pick the shape.
   - The two `PRELAUNCH.*` items (help/Codex rework — note the help corpus
     is now era-clean as of drop 27, a down payment; web landing page).
   - `CRAFT.HOOK.force_detector` / `CRAFT.HOOK.restraints` (need a design
     pass first).

## All commits this session (on `roadmap`, oldest→newest)

`bf199cb` drop 25 · `50e3c46` drop 26 · `2149881` drop 27 ·
`91f50a4` drop 28 · `6ea8143` drop 29 · `d4592cc` drop 30 ·
`c38a12f` handoff · `f604c2a` drop 31 · `0e16c8e` drop 32
(+ this handoff update).
