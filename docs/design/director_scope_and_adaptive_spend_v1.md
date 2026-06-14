# Director AI — Scope Review + Adaptive-Spend Design (v1)

> ## ⚠️ POINT-IN-TIME — captured ~commit `e58b0fc` (post-Drop-42). MAY BE SUPERSEDED.
> Read-only design review; re-verify file:line against HEAD before building. The session
> also touches `director.py` — coordinate.

Game-designer pass over the Director AI against the current game scope, plus Brian's
adaptive-spend mechanic (baseline $20 always-on, toggle fidelity up/down, and let the
Director flag high-ROI moments to spend more).

## 0. THE HEADLINE FINDING — the Director only runs MOS EISLEY (1 of 6 planets)

Verified at HEAD: `VALID_ZONES` (`director.py:108-111`) is a hardcoded frozenset of **6 zones,
all Mos Eisley** (`spaceport, streets, cantina, shops, jabba, government`). The code itself
admits it (`director.py:1631-1632`): *"Director tracks 6 Mos Eisley zones; outer planets retain
their base security level (no Director influence tracking yet)."* Its fallback line is literally
*"Mos Eisley continues under the twin suns"* (`director.py:1790`).

**So the entire rest of the galaxy has NO living-world AI.** Coruscant, Kamino, Kuat, Geonosis,
Nar Shaddaa — every planet you built — sit at static base security with zero Director activity.
A player on Nar Shaddaa or in the Coruscant Underworld experiences no world evolution at all.

**And the config is ALREADY WRITTEN for them.** `director_config.yaml:231-270` defines zones for
the other planets (`senate_district`, `kuat_orbital`, `geonosis_foundries`, `geonosis_arena`,
`nar_shaddaa_lower`, …) — the engine just never loads them past the 6 Mos Eisley hardcodes. This
is the single biggest Director gap, bigger than the economic blindness below: the living world
is confined to one city. Loading the full zone graph (the "multi-zone realignment" in §6) should
arguably be the FIRST expansion, not a $40 swing — it's mostly a config-load + per-zone tracking
change, and the data exists.

## 1. Scope verdict — an early-slice narrator in a much bigger game

The Director today is, honestly, **"a faction-war + security-narration engine wearing the
title of Director."** It perceives the FACTION/SOCIAL layer well — per-org treasury, member
counts, violations, requisitions, PC faction-standings, online-PC narrative records
(`compile_digest` `director.py:535-745`) — and acts through a coherent but narrow surface:
nudge zone influence (±5), fire a world event, post ambient text, deliver ≤2 PC hooks, issue
≤3 faction orders, flip transient security overlays.

But the game it now sits in is far larger, and the Director is **structurally blind** to all
of it: the crafting/harvest/region-quality economy, the planetary trade loop, territory
control + player cities + city tax, the threat-band difficulty axis, T5 questlines, and
communal objectives. The only economic signal it sees is per-org treasury (`director.py:734`).
It runs a war narrative over **6 Mos Eisley zones** while the config defines 26 zones across
planets the engine never loads (`director.py:108-111` vs `director_config.yaml:73-136`).

## 2. Two live bugs (verified at HEAD) — fix BEFORE any expansion

1. **The Director's #1 lever is broken.** When Claude returns `influence_adjustments` (its most
   central action), `director.py:896` calls `await self._apply_influence_delta(...)` — **a
   method defined NOWHERE** (only `_set_influence`, an absolute-score setter, exists at :459).
   Runtime `AttributeError` every time it tries to nudge influence. Its primary lever has been
   silently dead.
2. **Cost telemetry logs zeros.** `director.py:1097-1104` hardcodes `tok_in=tok_out=0` into
   `log_event`, so `@director budget` reports ~$0 spent forever, and the in-memory breaker
   resets on restart. You cannot responsibly run a richer/faster Director without this fixed —
   it's the prerequisite for the whole adaptive-spend mechanic.

## 3. The cheap-win that changes everything: ECONOMY EYES

Because every credit movement already routes through `adjust_credits(char_id, delta, "tag")`,
giving the Director economic perception is a **PURE READ** — a per-turn faucet/sink rollup by
tag added to `to_digest_dict()` (`director.py:323`). No new write seam. This single change
converts it from a war narrator into an actual game director that can see a smuggling boom, a
deflation, or a player getting rich. Paired cheap reads: per-zone activity (stop discarding the
zone arg `ActionDigest` already accepts), threat_band per zone, a coarse player-wealth line.

## 4. THE BUDGET INSIGHT (verified math): breadth is nearly free; cadence is the cost

- Haiku $1/MTok in, $5/MTok out. Cadence = `FACTION_TURN_INTERVAL=1800s` (30 min) → ~1,440
  calls/mo. `max_tokens=1000` out. Current digest is TINY (<1k in-tok).
- **$20/mo affords ~8,900 input tokens/call** at 30-min cadence. A FULL-SCOPE digest (economy
  + territory + threat + questline) is ~4k tokens. A richer ~4k-in/1.5k-out call costs:
  **60-min = $8/mo · 30-min = $16.56/mo · 15-min = $33/mo.**
- So a **full-scope-aware Director at 30-min cadence is UNDER $20.** You pay extra only to make
  it think *more often* or run a *second* pass — not to make it *smarter per call*.

## 4b. LOCKED DESIGN DECISIONS (Brian, 2026-06-13)

- **A. Economy interventionism = SOFT NUDGES.** Director seeds opportunities (caravans, buyers,
  bounties) players can take or ignore; never changes prices/yields directly, never hard levers.
- **B. Reacting to rich/powerful players = OPPORTUNITY RESPONSE.** Wealth/power makes you a magnet
  for content (merchants, heist rumors, faction courtship, bounties on you); NEVER a tax or
  rubber-band.
- **C. Player cities/territory = READ-AND-NARRATE ONLY.** The Director can reference a player city
  in a beat but cannot endorse/contest/pressure player-owned property. (Revisit post-launch.)
- **D. Skip empty turns = YES, with an OVERNIGHT EXCEPTION.** Skip the API turn when 0–1 players
  online — BUT if the world has been stale through the day/evening (no faction turn fired for a
  long window AND players were online earlier), fire **one** catch-up turn overnight so the world
  visibly moved by morning. (One bounded extra call, not a return to always-on.)
- **E. Auto-escalation = AUTONOMOUS up to $30/mo, MANUAL extra level to $40.** The governor may
  self-escalate spend on high-ROI moments up to a **$30/mo autonomous ceiling**; a **manual
  `@director fidelity max`** unlocks the **$40 tier** (the second "economy brain" pass / 15-min
  cadence) only when Brian flips it.
- **F. Advisory channel = YES.** The Director returns an optional `recommend_fidelity` field
  ("a player cornered the kyber market — faster cadence would let me seed a rival while they're
  online"), surfaced to admin. Brian's "let it flag high-ROI" idea — cheap (one response field).
- **G. Budget posture = AIM $20, AUTO to $30 when story is popping, MANUAL $40 toggle.** Default
  operation baselines near $20; the autonomous governor climbs toward $30 during busy/exciting
  windows; $40 is a deliberate Brian-flipped tier for when the game is going strong.

## 4c. THE FULL SPEND-DIMENSION SPACE (Brian's question: "is frequency the only knob?")

**No — frequency was an under-framing. Spend buys aliveness along FIVE dimensions, and the
cheapest, most impactful ones are NOT frequency.** What makes a world feel alive, ranked by
bang-per-dollar:

1. **BREADTH (what the Director can SEE) — nearly FREE.** A richer digest (economy, territory,
   cities, threat, questlines, per-PC state) costs a few thousand input tokens at $1/MTok — pennies.
   This is the single biggest aliveness gain and it barely touches the budget. *Already in the $20
   baseline.* A world-AI that can't see the economy can't feel alive no matter how often it thinks.

2. **DEPTH per beat (how SPECIFIC each action is) — cheap (output tokens).** A bigger
   `max_tokens` lets the Director write a *specific, personalized* beat ("the Hutts noticed Vex's
   spice haul; a Rodian fence named Greeta is asking after them at the cantina") instead of a
   generic one ("crime is up in the spaceport"). Specificity is what reads as alive. Output is the
   $5/MTok side, so this costs more than breadth but is still cheap per call.

3. **REACTIVITY (how FAST it responds) — the EXPENSIVE one (the frequency knob).** Cadence is the
   only dimension that multiplies BOTH input and output every call, so it dominates cost. It buys
   "the world reacts while you're still online" — real, but the priciest aliveness-per-dollar.

4. **THE FREE LOCAL LAYER (Ollama) — $0, and underused.** `ai/npc_brain.py` + `engine/ambient_events.py`
   already exist: local-model NPC barks, ambient room flavor, reactive one-liners. This is where
   MOST moment-to-moment aliveness should live — an NPC commenting on a player, a cantina reacting
   to a brawl, ambient chatter — and it costs NOTHING. **The Claude Director should DIRECT the
   cheap local layer, not replace it:** the Director (paid, occasional) sets the *theme/state*,
   the local layer (free, constant) fills every room with reactive texture between turns. Spending
   more on Claude when the free layer is idle is the wrong lever.

5. **PERSISTENCE / MEMORY (does the world REMEMBER?) — cheap (input tokens).** Feeding the Director
   multi-turn memory (recent decisions, ongoing arcs) instead of only "last 30 minutes" lets it
   tell *continuing stories* (a faction campaign that builds over an evening) instead of amnesiac
   one-shots. Cheap (it's input), high aliveness, and the current digest is amnesiac
   (`time_period='last_30_minutes'` only).

**THE DECISION (Brian, 2026-06-13): breadth, depth, memory, and the Ollama texture layer are
NOT knobs — they are ALWAYS ON. They're what the Director *is*, not a spend tier.** Making them
adjustable would be a category error (no one should ever choose "should the world-AI see the
economy?" — the answer is always yes). So:

- **Breadth (sees the whole game): always on.** Part of the baseline Director, free.
- **Memory (remembers across turns): always on.** Multi-turn rolling context, free.
- **Depth (writes specific, personalized beats): always on.** A sensible fixed `max_tokens` that
  affords specificity every turn — not a dial.
- **Ollama local texture layer: always on.** Constant free NPC/ambient reactivity between Claude
  turns, themed by the Director's current state.
- **Reactivity (cadence): THE ONLY KNOB.** It's the only dimension that actually costs more per
  call, so it's the only thing the governor (and the manual toggle) moves. Everything else is a
  constant.

This simplifies the build: the **SpendGovernor is a CADENCE controller**, not a 5-dimension
controller — it sets `_turn_interval` against the budget ceiling and triggers the optional model
bump only at the manual $40 tier. The always-on dimensions ship once in the baseline Director and
never vary. A world feels alive from constant free Ollama texture + an always-rich, always-
remembering Director writing specific beats — with *how fast* it does so the only thing that
scales with spend.

## 4d. CORRECTED BUDGET MATH (galaxy-wide, Brian's catch 2026-06-13)

The earlier "$16.56/mo" used a 4k-token PARTIAL digest. The real **galaxy-wide** digest (26
zones × 6 factions + economy rollup + per-PC + multi-turn memory) is **~5,500 input tokens**.
Honest numbers (Haiku, 1.5k output, with **skip-empty-turns at ~40% server occupancy** — Brian's
decision D, which is what buys back the headroom the galaxy digest costs):

| Config | Always-on | With skip-empty (~40%) |
|---|---|---|
| 30-min, single event | $18.79 | **$7.52** |
| 30-min, RICH multi-event (~3.7k out) | $35 | **$14.00** |
| 45-min, rich multi-event | $23 | **$9.33** |

So the **galaxy-wide, multi-event, full-scope Director lands ~$14/mo with skip-empty** — under
$20 WITHOUT touching cadence. Cadence 30→15 nearly DOUBLES cost for a marginal feel change
(Brian: "30 vs 15 won't make much difference") — confirming it's the worst knob.

## 4e. ALMOST NOTHING IS A KNOB — the good stuff is cheap or free (Brian, 2026-06-13)

Brian's repeated instinct ("just do it automatically / build it in") is correct because the
high-aliveness dimensions are cheap or free. Final model:

**ALWAYS-ON, FREE:**
- Breadth, memory, **focus** (concentrate the turn's attention where players are — automatic, not
  a knob; empty zones get one upkeep line, populated zones get the rich beat).
- **The Ollama layer — and its EXPANSION (the biggest missed opportunity).** The local model
  already has an **idle queue** (`npc_brain.py:306`, `director.py:1564` "queue idle Ollama rewrite
  for atmospheric headline") — the "spare local capacity does background enrichment" pattern is
  BUILT, just underused. Two free expansions: (1) when barking is quiet, the idle queue does
  background enrichment instead — it's a work SCHEDULER, not just a chattiness dial; (2) **enliven
  the large TEMPLATED surface** that reads identically every time today — `wilderness_anomalies.py`
  (15 flavor pools), `missions.py` (15), `bounty_board.py` (6), `encounter_texture.py` (5) are all
  `random.choice` from fixed templates; route them through Ollama for unique contextual prose at
  $0 API cost. **This is the single highest-value aliveness work in the design and it's free.**

**ALWAYS-ON, CHEAP (build in, NO knob — the numbers make gating pointless):**
- **Multi-event rich turns** (~3-4 consequential actions/turn vs 1): ~$14/mo at 30-min skip-empty.
  Build in; no need to slow cadence to afford it.
- **Sonnet on the ~10 genuinely dramatic beats/month** (city founded, war, kyber cornered): auto-route
  to Sonnet — **+$0.39/mo**, basically free, produces the standout moments.
- **Periodic Opus "big think"** every ~2 days: a deeper world-shaping turn that sets up arcs —
  **+$2.94/mo** (daily $5.87, weekly $0.84). Build it in on a schedule; too cheap to gate.

**THE ONE MANUAL KNOB:** cadence — demoted to a rarely-touched escalation (auto ≤$30 on hot
windows, manual `@director fidelity max` → $40), because it's the most expensive and least
felt dimension.

**Net at the recommended fully-loaded always-on config** (galaxy digest + multi-event +
Sonnet-on-drama + Opus-every-2-days + skip-empty): **~$17-20/mo** — the $20 target, fully loaded,
with cadence doing NO work. The $30/$40 tiers become "burst during a big event," not normal
operation.

## 5. THE MECHANIC — Adaptive Spend Governor (Brian's design)

Brian's ask: keep a $20 tier always on, toggle fidelity up/down, and let the Director flag
when more spend = high player ROI. **This is buildable with zero architectural change** — the
three fidelity levers are ALREADY runtime-mutable instance state:

**ALWAYS-ON (baseline Director, not governed — ship once, never vary):**

| Dimension | Seam | Cost | State |
|---|---|---|---|
| Breadth (sees the whole game) | digest assembly | ~free (input) | always full-scope |
| Memory (remembers across turns) | digest assembly | ~free (input) | always multi-turn |
| Depth (specific beats) | fixed `max_tokens` (`director.py:844`) | cheap (output) | always specific |
| Local texture (Ollama) | `ai/npc_brain.py`, `ambient_events.py` | **$0** | always on, Director-themed |

**THE ONLY GOVERNED KNOB:**

| Knob | Seam | Cost | $20 baseline | Auto (≤$30) | Manual $40 |
|---|---|---|---|---|---|
| **Cadence** | `self._turn_interval` (`director.py:377`) | EXPENSIVE (×in+out) | 30 min | →18 min on hot windows | 15 min |
| Model (manual tier only) | `generate(model=...)` | varies | Haiku | Haiku | richer model |

The **SpendGovernor is a cadence controller**: it moves `_turn_interval` against the ceiling
(auto up to $30 on high-ROI windows, baseline ~$20 otherwise), and the manual `@director fidelity
max` unlocks the $40 tier (15-min + the optional model bump / second economy pass). Everything in
the always-on table is a fixed constant the governor never touches.

### Design: a `SpendGovernor` that sets those three knobs each turn

- **Baseline tier ($20, always on):** full-scope digest, Haiku, 30-min cadence. The default,
  self-funding under the breaker.
- **Manual override (up/down):** `@director fidelity <eco|low|standard|high|max>` (slots into
  the existing `@director` subcommand dispatch, `director_commands.py:60`). Sets a floor/ceiling
  on the governor. "eco" mode drops to 60-min Haiku for a quiet server; "high/max" forces faster
  cadence. Persisted so it survives restart.
- **Auto-governor (the clever part — DEMAND-DRIVEN spend):** each turn, BEFORE the API call, a
  cheap **local heuristic** scores "is something worth reacting to right now?" from signals the
  digest already gathers — and raises fidelity only when the score is high:
  - **High-ROI triggers** (spend more): many players online; a big economic event in-window
    (market cornered, city founded, a wealth spike, a territory flip, a communal-objective
    surge); a questline-completion wave; a player in a dramatic moment (near-death, big heist).
  - **Low-ROI triggers** (spend less): 0–1 players online, no notable activity → drop to eco
    cadence or **skip the API turn entirely** (huge saver — an empty server shouldn't pay to
    narrate to nobody).
  - The governor adjusts `_turn_interval` / model / digest-depth for the NEXT turn(s) within the
    budget ceiling, and **logs WHY** ("escalated: 8 players + city founded → 15-min Haiku").

### The Director recommending its own spend (Brian's "flag high-ROI" idea)

Two flavors, both cheap:
1. **Automatic (the governor above):** the local heuristic IS the Director flagging high-ROI
   moments — it just acts on them directly instead of asking. This is the recommended default
   (no human in the loop needed for it to feel alive).
2. **Advisory (optional):** the LLM can return an optional `recommend_fidelity` field in its
   response ("a player just cornered the kyber market — a faster cadence here would let me seed
   a rival buyer while they're online"). Surface it to admins via `@director status` / a news
   line. Brian (or an auto-rule) decides. This makes the *Director itself* the one saying
   "spend here, it's worth it" — exactly your idea — at the cost of one extra response field.

### Why this respects the $20 ceiling AND enables big swings

The governor is **bounded by the breaker** — it can never exceed `monthly_budget_cents`
regardless of triggers (the existing circuit breaker at `claude_provider.py:108` is the
backstop). So "always-on $20" is guaranteed. Raising the ceiling to $30/$40 just gives the
governor more room to escalate on hot moments — the **big swings become "how high can the
governor climb when the game is exciting,"** not a flat always-higher spend. You get the
fidelity exactly when players would feel it, and pay baseline when they wouldn't.

## 6. The fidelity ladder (what each spend level buys)

| Tier | Cadence | Model | Digest | ~Cost/mo | Feel |
|---|---|---|---|---|---|
| **eco** | 60 min | Haiku | core | ~$8 | quiet-server floor; skips empty turns |
| **$20 standard (default)** | 30 min | Haiku | full-scope | ~$16.56 | full-game-aware, always on |
| **$30 high** | 15–20 min | Haiku | full + deep economy | ~$25–30 | reacts while you're still online |
| **$40 max / big swing** | 15 min | Haiku + occasional richer model on hot turns, OR a 2nd "economy director" pass between faction turns | full + planetary multi-zone | ~$33–40 | runs the whole galaxy, not one city; notices you cornered the kyber market within 15 min and seeds a rival |

The governor moves UP and DOWN this ladder automatically within the active ceiling; the manual
toggle sets the ceiling.

## 7. Design forks for Brian

- **Interventionism:** how hard-handed is an economy-aware Director? (A) narrate-only, (B) soft
  levers — seeds opportunities players can take or ignore, (C) hard levers — actively seeds
  shortages/suppresses yields. **Recommend B** ("events create opportunities, not obligations" —
  the existing prompt principle).
- **React-to-rich/powerful player:** opportunity (merchants, heist rumors, faction courtship —
  fun) vs. corrective (prices rise, hunters escalate — feels punishing). **Recommend
  opportunity-only — wealth/power is a magnet for CONTENT, never a tax.**
- **Auto-governor authority:** does it escalate spend autonomously up to the ceiling, or only
  *recommend* and wait for admin/Brian? **Recommend autonomous within the ceiling** (it's
  bounded by the breaker; asking defeats "feels alive"). Advisory field as a bonus.
- **Skip-empty-turns:** confirm the Director should skip the API call when 0–1 players online
  (big saver, but means no world-evolution while you're away — usually correct for a small MUSH).

## 8. Relation to T3.15 + sequencing

**Re-scope T3.15** from "Director CW tuning" to **"Director scope expansion + adaptive spend"** —
tuning the knobs of a Director that only perceives the early slice is rearranging deck chairs;
the high-value move is giving it economy/spatial/threat perception + the governor FIRST, then
T3.19's telemetry tuning. (T3.15 gates a few other items — preserve those as deps on the
expanded scope.)

**Build sequence (all in `director.py` + `claude_provider.py` — collision with the session's
director work must be coordinated):**
1. **Fix the two bugs** (`_apply_influence_delta` define/rename to use `_set_influence` with a
   read-modify-write; real token logging) — prerequisite, smallest, unblocks honest budget.
2. **MULTI-ZONE LOAD (the headline fix — and it's CHEAP, re-ranked up from a "$40 swing").**
   Load `VALID_ZONES` from the already-authored `director_config.yaml zone_baselines` instead of
   the hardcoded 6-Mos-Eisley frozenset (`director.py:108-111`). Verified small: influence is
   already persisted generically by `zone_id` (`_get_influence`/`_set_influence`, no schema
   change — new zones just get rows); the Director already has a per-instance `self._zones.keys()`
   zone-set pattern (`director.py:873`); `VALID_ZONES` is consumed in only ~6 places. The config
   is full, not stubs (Tatooine 8 zones, Nar Shaddaa, etc., with real CW faction baselines). So
   the galaxy-wide living world is a CONFIG-LOAD change, not a big engineering lift. **Biggest
   player-facing impact of anything here, lowest cost. Do it early.** (Token cost: the digest
   grows to ~26 zones of influence — pushes input toward 4-6k, still well under the $20 budget
   since input is cheap.)
3. **Economy eyes + cheap-win reads** into the digest (pure reads).
4. **Soft economic levers** (reuse the DONE world-event flag consumers + region_quality source).
5. **The SpendGovernor** (the three-knob controller + `@director fidelity` toggle + the
   local-heuristic auto-escalation + optional advisory field).

## Collision note

Read-only doc. The build edits `engine/director.py` (digest, faction-turn body) and
`ai/claude_provider.py` (`generate` must return per-call usage) — both shared with the session's
director work. Sequence via the drop workflow; `tests/test_director_cw_faction_mapping.py` (6) +
the 80 director + 178 era-cleanness suites are the regression floor. Fold the two bug fixes into
the same build (a richer/faster Director without accurate telemetry is irresponsible).

*Scope review: workflow task `weteu0osa.output`. Budget math verified against
`claude_provider.py` + `director.py` constants.*
