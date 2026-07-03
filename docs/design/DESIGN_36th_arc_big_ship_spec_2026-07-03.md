# DESIGN — The 36th T3.24 Arc: "The Phantom Tonnage" (civilian big-ship combat venue)

Status: BUILDABLE. Resolves `QUEST.t3_24_36th_arc_skill_pool_exhausted` via **Fork B** (additive civilian
big-ship VENUE unlocks the one structurally-fresh shape: a real combat step fought *aboard* a capital-class
liner). HEAD-verified against every loader, matcher, and balance-guard cited below (2026-07-03).

Author: Opus design-synthesis. Brian approved "you pick" the concept.

---

## 1. Concept (one paragraph)

A merchant-combine **civilian bulk-freight liner, the *Ardent Span***, docked at Kuat's Supply Space
Station, runs a **phantom-tonnage / ghost-manifest smuggling front**: it books bonded bulk freight, but its
manifest core is doctored so a large slice of its true loaded mass moves as undeclared contraband tonnage
for a syndicate, hidden behind forged manifest entries that make the declared tonnage match the bonded
cargo. KSF inspectors clear it on the papers. An independent bonded-tonnage auditor, **Suli Verrin**, has
caught the *Ardent Span* squawking a manifest tonnage its scanned hull-mass cannot be carrying, but a
suspicion cannot pull a bonded liner's registry — she needs a neutral hand to bring back the live proof. The
player boards the liner, **scans the true loaded mass against the declared tonnage** (a `sensors` check that
proves the phantom tonnage), **fights through the illegally-manned, rigged gun-deck** the syndicate keeps to
guard the contraband run (the big-ship COMBAT beat, aboard a capital-class ship), **slices the doctored
manifest core** to surface the ghost entries (a `computer programming` check), and **stands down the liner's
enforcer captain, Renk Talo**, once the deck is cleared and the manifest is exposed. With the true mass, the
sliced manifest, and the captain stood down, the shippers' survey board / KSF pulls the *Ardent Span*'s
bonded registry. A freelance favor — open to anyone, no faction required.

This is the **first accessible arc whose combat step is fought aboard a capital-class big ship**, which is
the genuinely-fresh SHAPE the roster lacks (arcs 33/34 use capital-ship skills only as bench/board
skill-checks: *The Papered Refit* explicitly does its combat in a ring corridor, *The Blank Ticket* is
combat-free by design — "no place for a firefight"). It also gives the otherwise-stranded reactive skill
**`dodge`** its natural, non-awkward home (the combat step's teach-chips), per the design call's stated
"bonus alignment."

---

## 2. The seam reality (why the combat is authored the way it is) — READ FIRST

There is **NO capital-ship-as-combatant seam**. `ALLOWED_COMPLETION_TYPES`
(`engine/tutorial_chains.py:59`) has no `ship_destroyed` / `space_combat_won`; space combat
(`engine/starships.py`, `parser/space_commands.py`) emits **no chain event**. The wilderness-anomaly
multi-phase "wave" machinery (`engine/wilderness_anomalies.py`) is **parallel and unbridged** — its spawner
hardcodes `is_anomaly_target` and never passes `chain_enemy_template`, and its payout never calls
`on_combat_won`. Reusing either to drive a chain step would require NEW engine code and is therefore OUT of
scope (additive-only).

**The honest composition that needs ZERO engine change:** model "the big-ship gun-deck fight" as
**person-scale ground combat aboard the ship**, via the one real chain combat seam — `combat_won` against a
statically-authored NPC tagged `ai_config.chain_enemy_template`, resolved by
`parser/combat_commands.py::_try_auto_resolve` → `engine/chain_events.py::on_combat_won`. The **capital-ship
identity comes from the VENUE** (a boardable multi-room capital liner interior, which does not exist today),
not from a ship-vs-ship mechanic. This is the fresh SHAPE; the combat mechanic itself reuses the proven
single-foil pattern shared by all 11 existing combat arcs.

> **FORK logged for Brian (NON-blocking):** a *true* ship-vs-ship capital combat step (fly the liner, trade
> turbolaser fire, disable it) has no seam and is a separate, deliberate future design+build. This arc does
> **not** need it and must **not** wait on it. See §10.

---

## 3. Reuse map (compose, do not rebuild)

| Concern | Existing engine reused | Seam / entry point |
|---|---|---|
| Questline container + state | `engine/tutorial_chains.py` + `engine/chain_events.py` (`kind: questline`, `active_questline` slot) | `load_tutorial_chains` → `_parse_chain`/`_parse_step`; `_try_advance` |
| Step 1 & 5 (talk / stand-down) | `talk_to_npc` completion | `parser/npc_commands.py::_post_talk_hooks` → `on_talk_to_npc` (keys off `completion.npc`) |
| Step 2 & 4 (skill checks) | `skill_check_passed` completion | player `chain attempt` → `parser/chain_commands.py::_handle_attempt` → `engine.skill_checks.perform_skill_check` → `on_skill_check_passed` |
| Step 3 (gun-deck combat) | `combat_won` completion + static `chain_enemy_template` NPC | `parser/combat_commands.py::_try_auto_resolve` → `on_combat_won` (`_match_combat_won`) |
| Venue rooms | `engine/world_loader.py::load_planets` hand-built room set (pattern (a)) | new rooms in `planets/kuat.yaml`, cross-referenced by slug |
| NPC placement | `engine/npc_loader.py` content_refs.npcs drop | new `npcs_drop_generalized_questline_phantom_tonnage.yaml` |
| Rewards (4 funnels) | `engine/chain_rewards.py` (`adjust_credits`, `adjust_rep`, `add_to_inventory`, achievements) | per-step `reward` + `graduation` |
| Achievement | `engine/achievements.py` | `data/achievements.yaml` key `phantom_tonnage_cleared` |

**Explicitly NOT reused (and why):** `staged_event` / `world_events` cult machinery and
`wilderness_anomalies` multi-phase combat — neither bridges to the chain step engine without new code; the
concept does not require them. This arc is pure chain-step composition.

---

## 4. The venue (4 new rooms, new zone, one additive anchor exit)

`ships.yaml` **cannot** be used — `engine/ship_loader.py` materializes each entry as a single bridge-room
stub, not a walkable multi-room interior. Author the liner as a **hand-built room set** (world_loader
pattern (a)) appended to `planets/kuat.yaml`.

**Anchor:** room `id: 322`, slug `kuat_supply_station`, "Kuat - Supply Space Station"
(`planets/kuat.yaml:511`), zone `kdy_orbital_ring`. Thematically exact ("Freighter traffic is constant and
heavy. KSF inspectors board every incoming vessel") and mechanically clean — it currently has exactly ONE
exit (`hub: kuat_ring_transit_hub`), so adding one boarding exit is minimal and collision-free. It is an
orbital station (not an exterior planetary-surface room), so the coordinate golden-snapshot guard does not
pin it and adding an exit does not touch it.

**Additive edit to room 322** — add ONE line to its `exits:` dict (do not delete/reorder existing lines):

```yaml
    exits:
      hub: kuat_ring_transit_hub
      gangway: kuat_liner_gangway        # <-- ADD: board the docked bulk liner Ardent Span
```

(Use `gangway` as the exit key, NOT `board` — `board`/`boardship` are live commands; a distinctive exit key
avoids any parser collision. `gangway` becomes the movement alias the player types.)

**New zone** — append to `data/worlds/clone_wars/zones.yaml` (mirror the `kuat_sabotaged_yards` block at
zones.yaml:480; additive, comment-preserving):

```yaml
  kuat_bulk_liner:
    name_match: "Ardent Span"
    narrative_tone: >
      A merchant-combine bulk-freight liner riding the Supply Station's
      inspection queue, bonded and cleared on its papers — and, below the
      manifest, a hull whose true loaded mass its declared tonnage cannot
      account for, an illegally-manned gun-deck, and a doctored manifest core.
    # phantom_tonnage 36th-arc venue (2026-07-03): the boardable civilian
    # capital-class liner interior for the T3.24 "The Phantom Tonnage" arc.
    # Contested — a syndicate contraband front sitting inside a KSF-cleared berth.
    properties:
      security: contested
      threat_band: frontier
```

**New rooms** — append under the `rooms:` list in `planets/kuat.yaml` (next free id after 334 is 335). A
linear boarding corridor; `out` = toward the exit, `in` = deeper into the ship. Coordinates (29, 4–7) sit in
clean empty space up-left of the ring cluster (existing ring rooms occupy x 31–38; the map already tolerates
duplicate coords, e.g. two rooms at 32,8, so this is safe):

```yaml
  # ══════════════════════════════════════════════════════════════════════
  # THE ARDENT SPAN — civilian bulk-freight liner interior (phantom_tonnage
  # 36th accessible questline, 2026-07-03). Boarded from the Supply Space
  # Station (room 322) via its `gangway` exit; a linear four-room interior.
  # zone: kuat_bulk_liner. No exterior-surface coords -> not snapshot-pinned.
  # ══════════════════════════════════════════════════════════════════════
  - id: 335
    slug: kuat_liner_gangway
    name: "Ardent Span - Boarding Gangway"
    short_desc: "The cleared boarding gangway of a bonded bulk-freight liner riding the inspection queue."
    description: >
      The Ardent Span's boarding gangway runs off the Supply Station's
      inspection apron — a combine bulk hauler, bonded and stamped, its
      manifest lodged clean against the berth. The hull reads honest on the
      papers. It does not read honest on a sensor sweep: the loaded mass
      the frame is carrying is more than the declared tonnage the manifest
      swears, and the difference is the whole racket.
    zone: kuat_bulk_liner
    map_x: 29
    map_y: 7
    security_level: contested
    exits:
      out: kuat_supply_station
      in: kuat_liner_gundeck
  - id: 336
    slug: kuat_liner_gundeck
    name: "Ardent Span - Rigged Gun-Deck"
    short_desc: "A civilian liner's illegally-manned gun-deck, kept crewed to guard the contraband run."
    description: >
      No bonded civilian bulk hauler carries a manned gun-deck. The Ardent
      Span does — a run of point-defense mounts crewed and hot, kept to keep
      anyone who reads the true tonnage from reaching the manifest core.
      The syndicate's deck-boss holds it, and the way aft to the core runs
      straight through him.
    zone: kuat_bulk_liner
    map_x: 29
    map_y: 6
    security_level: contested
    exits:
      out: kuat_liner_gangway
      in: kuat_liner_manifest_core
  - id: 337
    slug: kuat_liner_manifest_core
    name: "Ardent Span - Manifest Core"
    short_desc: "The liner's manifest core, where the declared tonnage is doctored to bury the ghost mass."
    description: >
      The manifest core is where a liner's cargo record is written and
      bonded. The Ardent Span's has been doctored: forged entries that make
      the declared tonnage match the bonded freight while the ghost mass — a
      syndicate's contraband run — rides undeclared beneath it. Slice the
      core and the ghost entries surface against the true loaded mass.
    zone: kuat_bulk_liner
    map_x: 29
    map_y: 5
    security_level: contested
    exits:
      out: kuat_liner_gundeck
      in: kuat_liner_bridge
  - id: 338
    slug: kuat_liner_bridge
    name: "Ardent Span - Command Bridge"
    short_desc: "The liner's bridge, where its enforcer captain runs the ghost-manifest front."
    description: >
      The Ardent Span's bridge, where the enforcer captain who runs the
      ghost-manifest front kept the whole racket squared: the bonded papers
      up top, the doctored core below, the gun-deck between them. With the
      deck cleared, the true mass read, and the manifest sliced open, there
      is nothing left for him to hold — only the choice to stand down.
    zone: kuat_bulk_liner
    map_x: 29
    map_y: 4
    security_level: contested
    exits:
      out: kuat_liner_manifest_core
```

Connectivity: `kuat_supply_station --gangway--> kuat_liner_gangway <--in/out--> gundeck <--> manifest_core
<--> bridge`. Reachability is satisfied (every step `location` is a real loaded slug). Note the chain
auto-teleports the player to each step's `location` on advance (`chain_graduation.apply_step_teleport`), so
the exits also give manual walk-back and the `chain attempt` location guard a real place to stand.

---

## 5. The arc (chains.yaml) — 5 steps, exact mechanical mapping

Append one `kind: questline` chain to `data/worlds/clone_wars/tutorials/chains.yaml`. Mirror the *Papered
Refit* block (11587–11908) for prose voice and field shape. Order follows the concept beats: brief → board &
prove tonnage → gun-deck combat → slice manifest → stand down captain.

**Header:**
```yaml
  - chain_id: kuat_phantom_tonnage
    chain_name: "The Phantom Tonnage"
    description: >
      [Multi-sentence premise in the Papered-Refit register: the Ardent Span, a merchant-combine bulk-freight
      liner bonded and cleared at Kuat's Supply Space Station, running a phantom-tonnage / ghost-manifest
      smuggling front; Suli Verrin, an independent bonded-tonnage auditor who caught it squawking a manifest
      tonnage its hull-mass can't carry and needs a neutral hand for the live proof; end with:] A freelance
      favor — open to anyone, no faction required.
    archetype_label: "Freelance Operator's Favor"
    faction_alignment: independent
    starting_zone: kdy_orbital_ring
    starting_room: kuat_supply_station
    prerequisites:
      - chargen_complete
    duration_minutes: 25
    locked: false
    kind: questline

    graduation:
      credits: 300
      faction_rep:
        independent: 5
      items: []
      achievements: ["phantom_tonnage_cleared"]
      drop_room: kuat_supply_station
      follow_up_hint: >
        [Epilogue in Verrin's voice: with the true loaded mass read on the berth, the doctored manifest core
        sliced open to its ghost entries, and the enforcer captain stood down, the shippers' survey board /
        KSF pulls the Ardent Span's bonded registry; the combine that fronted the run loses the ship's bond;
        the contraband tonnage that would have moved on a clean manifest does not; and the berths carry a
        name for a hand who will scan a bonded liner's true mass, walk its rigged gun-deck, and slice a
        doctored manifest core against its own papers. No Senate office and no Jedi looked twice at a bonded
        civilian hauler — the shippers' own survey board did, once the phantom tonnage sat on its desk.]
```

**Steps (mechanical fields are EXACT — do not alter skill / difficulty / on_fail / type / rewards):**

| # | title (suggested) | location | npc | npc_role | teaches | completion | reward |
|---|---|---|---|---|---|---|---|
| 1 | "The Tonnage That Doesn't Weigh" | `kuat_supply_station` | `Suli Verrin` | instructor | `["talk"]` | `type: talk_to_npc` / `npc: "Suli Verrin"` | `faction_rep: {independent: 2}` |
| 2 | "A Mass the Manifest Can't Carry" | `kuat_liner_gangway` | `"(none)"` | contact | `["sensors"]` | `type: skill_check_passed` / `skill: "sensors"` / `difficulty: 11` / `on_fail: "retry_allowed"` | `faction_rep: {independent: 2}` |
| 3 | "The Deck That Shouldn't Be Crewed" | `kuat_liner_gundeck` | `Hakko Vurm` | antagonist | `["attack", "dodge"]` | `type: combat_won` / `enemy_template: "phantom_tonnage_gundeck_boss"` / `enemy_count: 1` | `credits: 150` + `faction_rep: {independent: 3}` |
| 4 | "The Manifest That Was Written Twice" | `kuat_liner_manifest_core` | `"(none)"` | contact | `["computer programming"]` | `type: skill_check_passed` / `skill: "computer programming"` / `difficulty: 13` / `on_fail: "retry_allowed"` | `faction_rep: {independent: 3}` |
| 5 | "A Front With Nothing Left to Hold" | `kuat_liner_bridge` | `Renk Talo` | instructor | `["talk"]` | `type: talk_to_npc` / `npc: "Renk Talo"` | `faction_rep: {independent: 2}` |

Each step also needs `objective`, `npc_intro`, `npc_complete`, `next_hint` prose (write in the Papered-Refit
voice). `npc_complete` is author-only narration (no runtime consumer — see schema note) but is loader- and
verifier-required, so it must be present. `next_hint` on step 2 must name the `sensors` skill and
`chain attempt`; on step 4, `computer programming` and `chain attempt`; on step 3, `attack` / `dodge`.

**Why this passes every balance guard (verified):**
- `test_questline_reward_tier_consistency`: TOTAL = 150 (step 3) + 300 (grad) = **450 credits**; rep =
  2+2+3+3+2+5 = **17 independent**, independent-only. Identical to every shipped freelance arc → the
  "all-identical" assertions hold.
- `test_questline_skill_difficulty_winnability`: difficulties 11, 13 ∈ [6,15]; non-decreasing (11 ≤ 13);
  both `on_fail: retry_allowed`; both int. All pass. (Both exact strings/values are already shipped:
  `sensors`@11 at chains.yaml:4155, `computer programming`@13 pattern at 3966/@14 elsewhere.)
- `test_questline_foil_winnability_band`: the single foil is stat-cloned from the proven `papered_refit_enforcer` (§6).
- `test_chain_corpus_reachability_invariant`: all 5 locations are real slugs; `sensors` +
  `computer programming` are canonical (both shipped); `enemy_template` resolves to the tagged NPC (§6); no
  `room_entered` / `item_acquired` completions used.

---

## 6. NPCs — new file `npcs_drop_generalized_questline_phantom_tonnage.yaml`

Three NPCs. Only the gun-deck boss carries `chain_enemy_template` (so only he is read by the foil
winnability band). `room:` fields match the room **display names** exactly (the loader places by name).
Original, era-clean characters; WEG R&E D6.

**Suli Verrin** (giver, steps 1 offer) — human, independent bonded-tonnage auditor. `room: "Kuat - Supply
Space Station"`. `ai_config.hostile: false`. Modest civilian sheet (mirror Ormo Delth's non-combat giver
shape). Dialogue: names the racket, hands off the proof task.

**Hakko Vurm** (combat foil, step 3) — Weequay syndicate gun-deck deck-boss. `room: "Ardent Span - Rigged
Gun-Deck"`. **Stat block cloned verbatim from the proven-in-band `papered_refit_enforcer`** (Vodran Sekk),
so the foil-winnability guard passes by construction:

```yaml
  - name: Hakko Vurm
    room: "Ardent Span - Rigged Gun-Deck"
    species: Weequay
    description: >-
      [Weequay deck-boss holding the illegally-manned gun-deck of a civilian bulk liner, kept crewed to keep
      anyone who reads the true tonnage from reaching the manifest core; a worn blaster pistol loose at his
      hip; muscle for a contraband run, not a spacer — he settles it with a blaster on the deck plating.]
    char_sheet:
      attributes:
        dexterity: 3D
        knowledge: 2D
        mechanical: 2D
        perception: 3D+1
        strength: 2D+2
        technical: 2D
      skills:
        blaster: 4D
        dodge: 3D+1
        brawling: 3D+1
        intimidation: 3D+2
        streetwise: 3D
        search: 3D
      weapon: blaster_pistol
      move: 10
      force_points: 0
      character_points: 3
      dark_side_points: 1
    ai_config:
      chain_enemy_template: phantom_tonnage_gundeck_boss
      personality: >-
        [Contemptuous while the papers hold and the tonnage stays buried; immediately violent the moment a
        neutral hand comes aboard reading the true mass and moving toward the manifest core. Plants himself on
        the gun-deck between the boarder and the core; would rather down a hand on the deck plating than let
        the ghost tonnage be read. Combat foil for the confrontation beat — the syndicate's muscle, settled
        with a blaster, aboard the liner.]
      knowledge:
        - "[He holds the Ardent Span's rigged gun-deck for the syndicate running its ghost-manifest front.]"
        - "[A neutral hand has come aboard reading the liner's true loaded mass against its declared tonnage and is moving aft toward the doctored manifest core; he draws on whoever carries the live proof.]"
      faction: criminal
      dialogue_style: >-
        Flat, contemptuous — names the manifest as bonded and the tonnage as squared before the threat.
      hostile: true
      combat_behavior: aggressive
      fallback_lines:
        - "['That manifest's bonded, friend — tonnage squared, papers stamped. Whatever you think you read off this hull, it doesn't reach any board. Off the deck.']"
        - "[Hakko Vurm comes off the gun-deck mounts as you come up from the gangway with a sensor read, and lets his hand fall loose to the worn blaster.]"
        - "[Last time — off the deck, or you don't walk that read anywhere. This liner's clean on its papers. I'm the part of it that keeps a read hull from reaching a survey desk.]"
```

**Renk Talo** (stand-down captain, step 5) — human, the liner's enforcer captain. `room: "Ardent Span -
Command Bridge"`. `ai_config.hostile: false` (he is **talkable and stands down** — the confrontation is
verbal, the gun-deck already cleared and the manifest sliced; a `talk_to_npc` completion requires a present,
talkable NPC). Modest sheet. Dialogue: yields, front collapsed.

**Add the file to `era.yaml` `content_refs.npcs`** (append one line in the block at era.yaml:196+, alongside
the other `npcs_drop_generalized_questline_*` entries):
```yaml
    - npcs_drop_generalized_questline_phantom_tonnage.yaml  # T3.24 36th arc (2026-07-03): 3 NPCs for "The Phantom Tonnage" aboard the Ardent Span (Suli Verrin giver, Hakko Vurm gun-deck foil [chain_enemy_template], Renk Talo stand-down captain). Original, era-clean, WEG D6.
```

---

## 7. Achievement — `data/achievements.yaml`

Append (mirror `papered_refit_cleared` at achievements.yaml:929; `cp_reward: 3` is required by
`test_questline_reward_tier_consistency::test_freelance_achievements_share_cp_reward`):

```yaml
  - key: phantom_tonnage_cleared
    name: "The Phantom Tonnage"
    description: "[Broke a phantom-tonnage / ghost-manifest smuggling front aboard the civilian bulk-freight liner Ardent Span at Kuat: scanned the true loaded mass against the declared tonnage (sensors), fought through the illegally-manned rigged gun-deck, sliced the doctored manifest core to surface the ghost entries (computer programming), and stood down its enforcer captain — the shippers' survey board pulled the liner's bonded registry.]"
    category: profession
    icon: "📦"
    cp_reward: 3
    trigger: {event: "chain_graduation", count: 1, chain_id: "kuat_phantom_tonnage"}
```

---

## 8. Reward-band source (copied, not invented)

**Named source arc: `kuat_papered_refit` ("The Papered Refit").** Every magnitude is copied from it (which
is itself the freelance-tier canonical enforced by the reward-consistency guard):

- Graduation: `credits: 300`, `faction_rep: {independent: 5}`, `items: []`, `cp_reward: 3` achievement.
- Per-step rep: 2 / 2 / 3 / 3 / 2; single `credits: 150` on the climactic combat step.
- Arc TOTAL: **450 credits + 17 independent rep** — identical to Papered Refit and all peers.

No new magnitude is introduced anywhere.

---

## 9. Files to create / edit (exact)

**Create:**
1. `data/worlds/clone_wars/npcs_drop_generalized_questline_phantom_tonnage.yaml` — 3 NPCs (§6).
2. `tests/test_generalized_questline_phantom_tonnage.py` — per-arc structural slice test (mirror
   `tests/test_generalized_questline_papered_refit.py`: asserts the chain loads, the 5-step
   talk→skill→combat→skill→talk shape, the reward totals, the foil tag resolves). Required by the per-drop
   new-test-file hygiene rule.

**Edit (all additive / comment-preserving per the `world-yaml` skill):**
3. `data/worlds/clone_wars/planets/kuat.yaml` — append rooms 335–338 (§4) + add one `gangway:` exit line to
   room 322's `exits:` dict.
4. `data/worlds/clone_wars/zones.yaml` — append the `kuat_bulk_liner` zone (§4).
5. `data/worlds/clone_wars/era.yaml` — append the new npc-drop line to `content_refs.npcs` (§6).
6. `data/worlds/clone_wars/tutorials/chains.yaml` — append the `kuat_phantom_tonnage` questline (§5).
7. `data/achievements.yaml` — append `phantom_tonnage_cleared` (§7).
8. `CHANGELOG.md` + `TODO.json` — same commit: add the drop entry; **move
   `QUEST.t3_24_36th_arc_skill_pool_exhausted` from `design_calls_pending_brian` to
   `design_calls_resolved_recent`** (resolution: Fork B, built as "The Phantom Tonnage").

**Validation before commit (all real, all at HEAD):**
- `python -m pytest tests/test_chain_corpus_reachability_invariant.py tests/test_questline_reward_tier_consistency.py tests/test_questline_skill_difficulty_winnability.py tests/test_questline_foil_winnability_band.py tests/test_questline_directory.py tests/test_generalized_questline_phantom_tonnage.py -x`
- `python tools/verify_tutorial_chains.py` (schema linter — requires every step field incl. `npc_complete`).
- AST/syntax validate every touched `.py`; YAML-validate every touched data file.
- Full `run_all_tests.bat` is the merge gate (Brian runs it).

---

## 10. Flagged forks / risks a builder must respect

1. **(Design fork, NON-blocking — log for Brian, do not resolve in-drop.)** A *true* capital-ship-as-combatant
   step (ship-vs-ship turbolaser/gunnery `combat_won`) has **no seam** and is a separate future
   design+build. This arc deliberately realizes "big-ship combat" as **ground combat aboard** the liner. If
   Brian later wants a real ship battle, that is a new `ALLOWED_COMPLETION_TYPES` value + a space-combat →
   chain bridge — out of scope here. The 36th arc must ship on the composition above regardless.

2. **(Balance choice, decided conservatively.)** `enemy_count: 1` (a single gun-deck boss), matching all 11
   shipped combat foils and the winnability guard's implicit single-foil model. A multi-foil "wave"
   (`enemy_count: 2`) would be genuinely fresh but **no open-world questline ships >1 today**, and two
   simultaneous band-foils is an untested soft-lock risk (the fun-drive's recurring wall). Per Brian's
   "conservative on balance numbers" standing preference, ship `enemy_count: 1`; a 2-wave is a deliberate,
   playtested balance item to raise separately if desired — NOT to guess into this drop.

3. **(Era-cleanness — satisfied, but verify in prose.)** Keep the racket a **generic civilian syndicate /
   contraband** front and KSF (Kuati Security Forces, established in kuat.yaml) as the only on-stage
   authority. NO Imperial/Empire/Rebel/TIE strings; NO canonical Clone Wars figures; NO Republic-Navy
   warship framing (the *Ardent Span* is a **civilian merchant bulk-freight liner**, keeping the arc
   `independent`/faction-neutral like all 35 peers). "Kuat"/"KDY"/"KSF"/"combine"/"bonded tonnage" are all
   era-clean.

4. **(Skill-spread overlap — accepted by the fork, noted.)** The freshness is on the **SHAPE** axis (first
   aboard-a-capital-ship combat), not the skill axis. `sensors` (arc 10) and `computer programming` (arc 9)
   are each reused once; this is inherent to Fork B and does **not** trip any code guard (only the loop's
   self-imposed "fresh spread" lane rule, which Brian's Fork-B choice supersedes). `dodge` — one of the four
   otherwise-stranded reactive skills — rides the combat step's teach-chips, its natural home.

5. **(No phantom producers/consumers — verified.)** Every authored field has a live consumer: `location`→
   teleport + attempt-guard; `completion.type/skill/difficulty/enemy_template`→ real matchers/seams;
   `reward`/`graduation`→ `chain_rewards`; achievement key→ registered in achievements.yaml. `npc_complete`
   is the one loader-required-but-unrendered field (schema-known; authored as narration, expected unseen).

---

## 11. Buildability verdict

**BUILDABLE = true.** Every arc step maps to a real, HEAD-verified completion type + engine seam + shipped
skill slug / proven foil template; the venue is authored additively via the live `world_loader` hand-built
room path with a single collision-free anchor exit; every reward magnitude is copied from a named existing
arc; and the whole drop passes the four balance guards + reachability invariant by construction. No new
top-level system, no new engine code, no engine seam invented. The one genuine gap (ship-vs-ship combat) is
flagged as a non-blocking future fork, not a dependency.
