# Pre-launch QA campaign — findings (2026-06-16)

Produced by the multi-agent QA-playthrough campaign (12 finders: 6 player-journey
walks driving the live in-process harness + 4 content-completeness audits + 2
balance/era reviews → 1 synthesis). 56 raw findings → deduped/ranked below.
**Launch readiness: BLOCKED.** The headline blockers were independently
**verified against HEAD by the main Opus session** (notes inline). The synthesis
correctly *dropped* a batch of false-positive "blockers" from one agent that ran
against a stale/un-rebuilt DB (it claimed 0/287 rooms have slugs + all chains
reference non-existent slugs — but the YAML carries 467 `slug:` entries,
`get_room_by_slug` works via `json_extract`, and `test_smoke_chain_walkthrough`
passes 7/7).

---

## 🔴 BLOCKERS — core launch loops non-functional in production (all VERIFIED)

### B1. `sqlite3.Row.get()` AttributeError — a whole bug CLASS (test-invisible) ★ root cause
**VERIFIED EMPIRICALLY:** production sets `row_factory = aiosqlite.Row`
(`db/database.py:1598` + read pool `:1708`); `aiosqlite.Row` **is** `sqlite3.Row`,
which has **no `.get()`** (a one-line repro raises `AttributeError`). The main
`fetchall`/`fetchone` wrappers (`db/database.py:1769`) return **raw Row objects**
("return all rows as a list of Row objects") — they do **not** dict-convert. So
**every `.get()` call on a raw row crashes in production**. The reason the
~7,700-test suite is green: test stubs return dict-converted rows, so the real Row
type is never exercised. This is a systemic test-methodology blind spot.

- **Scope:** ~163 `*row.get(` sites (234 broader) across engine/parser/server/db.
  An unknown subset are real bugs (the rest access rows that were dict-converted
  upstream — needs a per-site origin trace, OR a root-cause fix at the wrapper).
- **Confirmed-broken cluster (the death/recovery arc):** `get_wound_state`
  (`db/database.py:5213`, `row.get` on a raw row → raises on every call) breaks the
  1-hour wound auto-recovery (the `-1D` wounded penalty becomes **permanent**);
  `get_corpse`/`get_corpses_in_room`/`get_decayed_corpses` return raw rows that
  `engine/death.py` `.get()`s → **bacta tank** (charges 500cr, leaks a raw error,
  never heals), **bacta pack** (consumes item, no heal), **loot-own-corpse**
  (returns nothing), **corpse decay** (silently destroys all gear, never returns
  bound items, orphans the row).
- **Fix options:** (a) ROOT-CAUSE — make `fetchall`/`fetchone`/`read_fetchall`
  return `dict(row)` (kills the whole class in one place; REQUIRES first auditing
  for positional `row[0]`/`row[1]` access, which dicts don't support); or (b)
  TARGETED — `dict()`-wrap the corpse/wound returns + index-access in
  `get_wound_state`, then sweep the other 163 sites separately. **Add a regression
  test that runs against a real `aiosqlite.Row`, not a dict-converting stub** — this
  is the test-gap that hid the entire class.
- **Lane:** `engine/death.py` is AVOID-LANE + `db/database.py` is core-DB →
  **ATTENDED-Opus.** The root-cause option is design-touching core DB (like the
  read-pool).

### B2. All weapon vendors are dead — `vendor` flag dropped on NPC load (VERIFIED)
`engine/npc_loader.py` `_build_ai_config` (~L286-297) builds the AI-config dict but
has **no `vendor` pass-through**, so `ai_config_json` never carries it. The buy
consumer `parser/space_commands.py:4172` reads `ai_cfg.get("vendor")` → always
falsy → "No merchant here sells weapons." in **every** room incl. Kayson's shop.
NPCs **do** declare `vendor: true` in YAML (verified: mos_eisley population,
planets/*, etc.), so the producer is real — the flag is lost at the DB-write seam.
**The buy-gear credit sink is entirely dead.** Fix: add
`"vendor": ai.get("vendor", False)` to the config dict + a round-trip test (the
existing test only checks the YAML source, not the DB write). **Lane:** loop-safe.

### B3. Faction comms reach 0 recipients — wrong character key (VERIFIED)
`server/channels.py` `get_faction()` (~L108-116) reads `char["faction"]` then
`attrs["faction"]`, but membership lives in `char["faction_id"]` (verified:
`ALTER TABLE characters ADD COLUMN faction_id TEXT DEFAULT 'independent'`). Every
member resolves as `independent` → `broadcast_fcomm` delivers to 0 recipients and
the sender gets no echo/error. Kills **`faction channel`** and leader
**`faction announce`**. Fix: read `char.get("faction_id")` first; echo a
send-confirmation regardless of recipient count. **Lane:** loop-safe.

---

## 🟠 HIGH

- **H1. Phantom item registry (4 agents converged):** ~40+ item keys referenced by
  faction rank equipment (`organizations.yaml`), commissary (`commissary.py`),
  tutorial rewards (`chains.yaml`, ~25), and Jedi-village rewards
  (`village_trial_crystal`, `village_pendant`) are **not defined in the item
  registry**. Players get broken/empty grants on faction rank-up, commissary
  purchase, and most tutorial graduations. Structural root: no registry home for
  non-weapon items (armor/consumables/quest items must fit `weapons.yaml`). Needs an
  authoring pass + a cross-registry consistency test (none exists). *Verify the
  exact list + whether resolution hard-fails vs silently no-ops before sizing.*
- **H2. Faction missions un-acceptable (3 compounding defects):** `post_faction_mission`
  inserts `data='{}'` → the general board discards them; the board footer says
  `mission accept <id>` but the verb is `accept`; and faction missions use integer
  DB ids while the in-memory board holds slug ids → `accept 1` → "No mission 1". A
  member who posts a faction mission dead-ends with no explanation.
- **H3. Harvest credit-margin uncapped** (`engine/harvest.py apply_skill_margin
  ~283-289` vs the capped quality bonus ~161): fixed Easy/6 difficulty doesn't scale
  with skill, so a high-skill harvester reliably top-bands and a Wild-Die explosion
  nets several-thousand-cr pulls on a 30-min/region cooldown. The unclosed
  `TUN.harvest` tail of the never-finished economist pass (`T2.ECON.review`). Cap
  the margin (~2.0) and/or scale difficulty by region tier.
- **H4. Planet trade pricing/supply dead** — `current_zone` is popped on every land
  (`space_commands.py` LandCommand ~L1369), so the next docked buy/sell reads an
  empty planet: "Cannot determine current planet", trades run at flat 100%
  (source-discount + demand-premium never apply), and the per-planet supply cap that
  prevents infinite farming is bypassed. Fix: set `current_zone` to the destination
  orbit zone on land (or store `docked_planet` separately).

## 🟡 MEDIUM
- **M1.** Pilot can be **permanently stranded in space**: launch fuel cost
  (`50 + speed*10`) can leave < the 25cr docking fee, LandCommand refuses, no
  emergency-landing/distress path. Add a pre-launch reserve check or a free
  emergency landing when credits < docking fee.
- **M2.** Era-cleanness (B3) leaks in **shipped player-facing text** the era-scrub
  test misses (it only sweeps `static/*.html`): `data/help/commands/+events.md:30`
  renders "Rebel Strike Planning"; `coruscant.yaml` room 237 says "anti-Human
  resistance organization" (Sequel-era "Resistance"). Fix both + extend the
  era-scrub test to sweep `data/help/**` and `data/guides/**`.
- **M3.** Shop stock fails for fresh/legacy chars: `shop_commands.py
  _find_in_inventory` guards `str` but not `list`; schema default inventory is `'[]'`
  (a bare list) → `inv.get('resources')` raises (swallowed) → "not found" even when
  present. Normalize list-form inventory before access.
- **M4.** **5 MORE dead achievement hooks** (beyond the 5 just wired): `on_attack_hit`,
  `on_survived_wound`/`on_survived_mortal_wound`, `on_planet_visited` (also a
  name mismatch: YAML `planets_visited` vs hook `planets_visited`), `dark_side_atoned`
  (the deferred one). Wire or remove so they don't show 0% forever.
- **M5.** Resources never decay + harvest cooldown is per-region not global
  (`engine/harvest.py`) — a slow-inflation vector flagged in the FINAL economy audit.
- **M6.** Village Quest steps 3-10 are stubbed/non-functional (only 1-2 have handlers)
  — if the wizard routes players in, it dead-ends. Confirm reachable-at-launch vs gated.
- **M7.** `Guide_09` CP-progression math is stale/self-contradictory after the v23
  retune (200/400/10): still states the old ~1 CP/wk rate + 7-month timeline.

## 🟢 LOW
- L1. Insight trial passes instantly without talking to Saro (`accuse_insight_fragment`
  hardcodes `correct=2` fallback when the Saro flag is unset).
- L2. 0D force-attribute lockout: a char with control/sense/alter = `'0D'` reads as
  Force-sensitive (key-presence reconstruction) but every Force command rejects them.
- L3. `advance_skill()` docstring + a dead if-branch claim "cost doubled above
  attribute" but never doubles (cost is correct per WEG; the docstring/branch is dead).
- L4. `LandCommand` has no `in_hyperspace` guard — landing mid-jump leaves
  `docked_at` set AND `in_hyperspace=True` (impossible state, mis-teleports next tick).
- L5. Stale duplicate `docs/design/Guide_09` shows pre-v23 numbers, unguarded by the
  rework test — will mislead the next author consulting the corpus.
- L6. P2P velocity alert may be silent (cap removed by design) — confirm the
  fail-open velocity alert actually posts to a monitor.
- L7. 5 empty space zones (space_tatooine/coruscant/kuat/kamino/geonosis) defined with
  no rooms — cosmetic validation noise; populate or remove from `zones.yaml`.

---

## Coverage gaps (what the campaign could NOT verify — needs a human or follow-up)
- **Browser SPA** (`m3_assembled_client.js` minified) — 7 server→client event types
  (`achievement_unlocked`, `hud_update`, `mail_status`, `news_event`, `places_status`,
  `world_event`, …) unverified at the pixel level. Needs a human in a browser.
- **Timer/tick-driven systems** never run: ship tick loop
  (`server/tick_handlers_ships.py`), hyperspace arrival, sublight transit, NPC
  space-patrol ticks, anomaly/deepscan.
- **No concurrency/load testing:** the T3.21 read pool has no live callers under
  concurrent sessions; multi-session WAL consistency + throttle-state leakage untested.
- **Long-session balance feel** is a human judgment call (CP pacing, uncapped milestone
  CP, harvest margins over weeks).
- **Content flows needing 2 live chars:** padawan-master bond handshake, Hermit
  invitation, live in-room `talk Saro`, full NPC combat-to-kill (RNG), space combat.
- **The world-audit reachability/slug claims** ran against a stale/un-rebuilt DB →
  false positives (dropped). A clean from-YAML world rebuild should confirm.

## Method note (the systemic lesson)
The Row.get() class + the era-leaks + the dead hooks all share one root: **curated /
stub-based tests pass while the real runtime type or whole files/objects go
unchecked.** Standing follow-up: (1) DB-boundary tests that exercise real
`aiosqlite.Row`; (2) extend the era-scrub AST sweep beyond `static/*.html` to
`data/**`; (3) the cross-registry item-consistency test; (4) a from-YAML world
rebuild before re-running the reachability audit.
