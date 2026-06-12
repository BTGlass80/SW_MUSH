# SW_MUSH — Drop F.6 Content Half: CW Tutorial Chains YAML · Design v1

**Date:** April 26, 2026
**Author:** Opus parallel-track session (CW continuation, second half)
**Status:** Content shipped in this drop alongside Drop 6a.5 + 6b
**Drop number:** F.6 (content side; engine side is a separate session)
**Pre-reads:**
- `clone_wars_era_design_v3.md` §10 (Tutorial Rework)
- `tutorial_system_design.md` (existing GCW tutorial structure & schema cues)
- `roadmap_v34.md` Drop F.6 row
- `gcw_counterparts_and_lore_expansion_design_v1.md` (the design from this drop's first half — same drop pattern)

---

## 1. Why this exists

Drop F.6 (Tutorial Rework) is on the roadmap as a "substantial drop —
estimated similar to the original tutorial's build-out" per
`clone_wars_era_design_v3.md` §10. The existing tutorial is hardcoded in
`build_tutorial.py` (~2200 lines) and `engine/tutorial_v2.py` (~2250
lines), both GCW-keyed. The CW rework needs:

1. **Content** — 8 profession chains × 4-6 steps each, with NPC dialogue,
   completion criteria, rewards, cross-references to CW factions and
   zones.
2. **Engine refactor** — generalize the tutorial state machine, add a
   chain loader, build new tutorial-zone rooms.

This drop ships **the content half**. Same parallel-safe pattern as
Drop 6a.5: ship structured data the engine session will consume, with a
validator proving it's well-formed and cross-references resolve.

The engine half is a separate session — likely one full implementation
sitting (as the design doc estimates).

---

## 2. What ships

A single file under `data/worlds/clone_wars/tutorials/chains.yaml`,
plus a validator at the repo root.

### 2.1 `data/worlds/clone_wars/tutorials/chains.yaml` (NEW, ~1200 lines)

Eight chain definitions matching `clone_wars_era_design_v3.md` §10.2:

| # | Chain | Faction | Start | Steps | Duration |
|---|---|---|---|---|---|
| 1 | Republic Soldier | `republic` | `kamino_tipoca` | 5 | 22 min |
| 2 | Republic Intelligence | `republic` | `coruscant_upper` | 5 | 25 min |
| 3 | **Jedi Path (LOCKED)** | `jedi_order` | `tatooine_dune_sea` | 1 (stub) | 0 min |
| 4 | Separatist Commando | `cis` | `geonosis_foundries` | 5 | 22 min |
| 5 | Separatist Agent | `cis` | `coruscant_lower` | 5 | 25 min |
| 6 | Bounty Hunter | `bounty_hunters_guild` | `nar_shaddaa_promenade` | 5 | 22 min |
| 7 | Smuggler | `independent` | `tatooine_spaceport` | 5 | 22 min |
| 8 | Shipwright/Trader | `shipwrights_guild` | `kuat_orbital` | 5 | 22 min |

**Total: 36 step records**, 35 in unlocked chains plus 1 stub for the
Jedi Path. Per-step contains NPC dialogue (intro + completion line),
objective, completion criteria (typed event hook), and reward.

### 2.2 `verify_tutorial_chains.py` (NEW, ~220 lines)

Schema + cross-reference validator. **219 checks pass** at authoring
time:
- 4 top-level shape checks (schema_version, chains list, count == 8)
- ~26 per-chain shape checks × 8 chains
- ~3 per-step structural checks × 36 steps
- 6 Jedi Path locked-stub checks
- 2 chain uniqueness checks (id + name)

Cross-reference checks include:
- Every `faction_alignment` resolves to `organizations.yaml`
  (factions: republic/cis/jedi_order/hutt_cartel/bounty_hunters_guild/
  independent — plus guilds: mechanics_guild/shipwrights_guild/
  medics_guild/slicers_guild/entertainers_guild/scouts_guild). Note: the
  validator merges factions and guilds into a single ID-space; a chain
  can align to either.
- Every `starting_zone` resolves to `zones.yaml`.
- Every `faction_intent: <code>` prerequisite resolves to a known
  faction code.
- Every `graduation.faction_rep` faction code resolves.
- Every `completion.type` is from the allowed set.

---

## 3. Schema design

The schema at the top of `chains.yaml` documents the per-chain and
per-step fields formally. Highlights:

**Per chain:**

```yaml
chain_id: republic_soldier              # unique snake_case
chain_name: "Republic Soldier"          # display
faction_alignment: republic             # → organizations.yaml code
starting_zone: kamino_tipoca            # → zones.yaml key
starting_room: tipoca_briefing_chamber  # NEW tutorial-zone room
prerequisites:                          # gating flags
  - chargen_complete
  - faction_intent: republic
duration_minutes: 22
locked: false                           # Jedi Path = true
graduation:                             # what happens at finish
  credits: 500
  faction_rep:
    republic: 50
  items: ["dc15_blaster_rifle", "republic_light_armor", "comlink_basic"]
  achievements: ["sworn_to_the_republic"]
  drop_room: coruscant_works_landing_zone
  follow_up_hint: "..."
steps: [...]
```

**Per step:**

```yaml
- step: 1                               # 1-indexed, contiguous
  title: "Reporting In"
  location: tipoca_briefing_chamber     # zone key OR new tutorial room
  npc: "Major Tarrn"                    # display name
  npc_role: instructor | contact | antagonist
  teaches: ["look", "+sheet"]           # commands the step exercises
  objective: "Look around, check your sheet, and report to Major Tarrn."
  npc_intro: |
    "Stand at attention, trooper..."    # opening line on entry
  completion:
    type: talk_to_npc                   # event hook type
    npc: "Major Tarrn"
    requires_first:                     # ordered prerequisites
      - command: "look"
      - command: "+sheet"
  npc_complete: |
    "Good. Records check out..."        # NPC reaction line
  reward:
    credits: 0
    faction_rep:
      republic: 5
  next_hint: "The combat simulator hatch is east. Type `east`."
```

**Allowed `completion.type` values** (matched against engine event hooks
in the engine session):

| Type | Triggers when |
|---|---|
| `command_executed` | Player types a specific command (with optional `target_contains`, `contains_any`) |
| `talk_to_npc` | Player issues `talk <npc>` (with optional `requires_first` ordered prerequisites) |
| `combat_won` | Combat resolves with player victorious vs `enemy_template` |
| `skill_check_passed` | Specific skill roll succeeds (with optional `fallback` and `on_fail`) |
| `mission_accepted` | Mission ID accepted from a board |
| `mission_completed` | Mission ID completed |
| `bounty_accepted` | Bounty ID pulled from BHG board |
| `item_acquired` | Specific item enters inventory (optional `method`) |
| `item_used` | Specific item used via `use` |
| `room_entered` | Player enters a specific room slug |
| `prerequisite` | Engine flag check; never event-driven (used by Jedi Path stub) |

---

## 4. Cross-reference resolution

### 4.1 Zones used by chains

All chain `starting_zone` values resolve to `zones.yaml` keys. Several
step `location` values are **new tutorial-zone rooms** that the engine
session will build with `tutorial_zone: true` properties (matching the
existing core-tutorial Landing Pad pattern):

**25 new tutorial-zone-only rooms identified:**

- Republic Soldier path (3): `tipoca_briefing_chamber`,
  `tipoca_combat_sim`, `tipoca_transport_pad`
- Republic Intelligence (5): `republic_intel_safehouse_alpha`,
  `coruscant_upper_judicial_plaza`, `coruscant_midlevels_freight_district`,
  `coruscant_works_landing_zone` *(also shared with Republic Soldier
  graduation)*, `dexs_diner`
- Separatist Commando (3): `geonosis_foundry_briefing`,
  `geonosis_foundry_drill_pit`, `tatooine_outskirts_cis_safehouse`
- Separatist Agent (5): `crystal_jewel_cantina`,
  `coruscant_works_lockers`, `coruscant_works_freight_corridor`,
  `coruscant_lower_freight_dock`, *(uses `coruscant_midlevels_freight_district` from #2)*
- Bounty Hunter (3): `nar_shaddaa_bhg_chapter_house`,
  `nar_shaddaa_promenade_bhg_lounge`, *(warrens already in zones.yaml)*
- Smuggler (4): `tatooine_spaceport_dock_94`,
  `tatooine_market_smugglers_alley`, `nar_shaddaa_landing_dock_e`,
  *(several space zones already in zones.yaml)*
- Shipwright/Trader (4): `kdy_apprentice_bay_7`,
  `kdy_apprentice_diag_bench`, `kdy_apprentice_parts_crib`,
  `kuat_orbital_apprentice_lounge`
- Jedi Path stub (1): `jedi_temple_gates` *(referenced as graduation
  drop_room only — Jedi Path itself runs no steps)*

**Note on Coruscant rooms:** Several rooms named in the chains
(`crystal_jewel_cantina`, `dexs_diner`, `coruscant_upper_judicial_plaza`,
`jedi_temple_gates`) are also called out in
`clone_wars_era_design_v3.md` §2.3.1 as Coruscant landmarks that the
full Coruscant buildout will include. The engine session can either:
(a) build them as tutorial-zone-only and let the Coruscant buildout
  later replace them with live-world versions, or
(b) defer the tutorial chains' use of those room slugs until the
  Coruscant buildout lands.

The cleaner path is (a) — tutorial-zone-only versions during tutorial,
then the chain's `graduation.drop_room` points at the live-world version.

### 4.2 Faction codes used by chains

All resolve to `organizations.yaml`:

- `republic` (faction): chains 1, 2
- `cis` (faction): chains 4, 5
- `jedi_order` (faction): chain 3 (locked)
- `bounty_hunters_guild` (faction): chain 6
- `independent` (faction): chain 7
- `shipwrights_guild` (guild): chain 8

Chain 7 (Smuggler) graduates with both `independent` and `hutt_cartel`
faction rep — it's authored as the unaligned-default path that
naturally leans Hutt-friendly.

Chain 8 (Shipwright) graduates with both `shipwrights_guild` and a
small bonus to `mechanics_guild` — guild adjacency, validates against
`organizations.yaml` `guilds:` entries.

---

## 5. Locked Jedi Path

Per `clone_wars_era_design_v3.md` §10.2 line 3:

> **Jedi Path** (hidden/locked until Village unlock — stub in tutorial,
> unlock post-Village)

This drop ships the stub. The Jedi Path chain has:

```yaml
chain_id: jedi_path
locked: true
locked_message: >
  The Jedi path is not available at character creation. To unlock it
  you must find a hidden village in the Jundland Wastes and complete
  the Master's trials. Begin your career on another path — the Force
  will find you in time.
prerequisites:
  - chargen_complete
  - jedi_path_unlocked         # set by Village quest chain
  - force_sensitive            # set during chargen (50% chance) or
                               # via Village quest narrative path
duration_minutes: 0
steps:
  - step: 1
    title: "(Locked — Village Quest Required)"
    completion:
      type: prerequisite
      flag: jedi_path_unlocked
```

Engine behavior: when a player attempts to select `jedi_path` at
chargen, the chain selector rejects it and surfaces `locked_message`
instead. The Village quest chain (Drop F.8) sets `jedi_path_unlocked`
on completion. Only then does the chain become available — and even
then the player still needs the `force_sensitive` flag (50/50 chargen
roll, or earned through the Village trials).

This matches `clone_wars_era_design_v3.md` §0 ("Force-sign fairness:
No one fully gated. Non-seeded characters pursue Village via
longer/harder path; roads exist for all").

---

## 6. What this enables for Drop F.6 engine work

The engine session will:

1. **Add `engine/tutorial_chains.py`** (or extend `engine/tutorial_v2.py`)
   with a chain loader consuming this YAML file. State-tracking JSON
   gets a new key:
   ```python
   "tutorial_chain": {
       "chain_id": "republic_soldier",
       "step": 3,
       "started_at": <ts>,
       "completed_steps": [1, 2]
   }
   ```

2. **Generalize the chain selector.** The current tutorial code branches
   on a fixed list of 8 elective modules. The CW rework adds an
   orthogonal axis — profession chain — that runs alongside the
   electives (or replaces them, depending on engine session decisions).

3. **Wire completion type → engine event hooks.** The 11 `completion.type`
   values map to existing engine hooks (parser, NPC, combat, mission,
   bounty, inventory, movement). A few may need new minimal hooks
   (e.g. `item_used` may not have a hook today; `skill_check_passed`
   exists but needs to be exposed to the tutorial state machine).

4. **Build the 25 new tutorial-zone rooms.** Add a `build_tutorial_chains.py`
   (or extend `build_tutorial.py`) that walks the chain definitions
   and creates rooms with `tutorial_zone: true` properties. NPCs get
   created the same way as the current core tutorial's Kessa Dray /
   Sand Raider.

5. **Implement the locked-chain rejection path.** When a player picks
   `jedi_path` at chargen and lacks `jedi_path_unlocked`, surface
   `locked_message` and prompt for re-pick.

The validator script in this drop ports straight into pytest as
`tests/test_tutorial_chains_yaml.py` — its 219 checks become the
launch regression for the engine refactor.

---

## 7. What this drop does NOT do

- **Does not replace the existing GCW tutorial.** `build_tutorial.py`
  and `engine/tutorial_v2.py` are unchanged. The CW chains YAML sits
  alongside until the engine refactor consumes it.
- **Does not build the 25 new tutorial rooms.** That's an engine task.
- **Does not author the GCW counterpart.** Per `clone_wars_era_design_v3.md`
  §11.1, the GCW path is "retired to reference" with a clean-slate DB
  wipe at pivot — there's no GCW tutorial chain set to build because
  the existing GCW tutorial is being replaced wholesale, not migrated.
- **Does not author the Village quest chain.** That's Drop F.8.
- **Does not author the FDtS quest chain.** That's the separate "From
  Dust to Stars" content drop, post-tutorial.

---

## 8. Sign-off

Drop F.6 content half: shipped, validated (219 checks green), parallel-safe.

The engine session can begin against this YAML as its content asset,
porting the validator into pytest as the gating regression test, then
implementing the loader, state machine, and room builder.

*— Opus, parallel CW track continuation pt 2, April 26 2026*
