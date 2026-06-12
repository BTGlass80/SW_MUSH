# SW_MUSH — Clone Wars Director / Lore Pivot · Design v1

**Date:** April 25, 2026
**Author:** Opus parallel-track session (CW Director/Lore Pivot)
**Status:** Design-ready. Content authored; engine refactor scheduled.
**Type:** Drop design — schedules Drop 6a per `clone_wars_era_design_v3.md` §11.3
**Pre-reads:**
- `clone_wars_era_design_v3.md` §8 (Director/lore pivot audit)
- `clone_wars_era_design_v3.md` §11.3 (item 7 — Director engine data-fication)
- `clone_wars_space_pivot_design_v1.md` (companion drop — same parallel-safe pattern)
- `roadmap_v34.md` Priority F

---

## 1. Why this exists

`clone_wars_era_design_v3.md` §8 audited the Director AI and world-lore systems and identified them as the two biggest content gaps in the era pivot. Per §8.4:

> Six workstreams. Five are content (lore rewrite, zone tones, director prompt, ambient events, NPC brain — automatic inheritance). One is engine: data-fy faction model and zone baselines.

`HANDOFF_CLONE_WARS_ERA_PIVOT.md` flagged one specific deferred item:

> Director `zone_baselines` values for all new Clone Wars zones — v3 shows the schema and example rows, but populating all ~30 zones with specific faction influence starting scores is Drop 6 authoring work.

This drop closes that item, plus the rest of the §8 content workstreams, in three new YAML files. The engine refactor is scheduled as Drop 6a per §11.3.

---

## 2. What ships in this drop (already authored)

### 2.1 `data/worlds/clone_wars/lore.yaml` (NEW)

The CW lore corpus — 32 entries replacing the GCW `SEED_ENTRIES` in `engine/world_lore.py`. Coverage:

- **Factions (8):** Galactic Republic, CIS, Jedi Order, Sith, Hutt Cartel, Bounty Hunters Guild, Independent Spacers, Separatist Council
- **People (3):** Chancellor Palpatine, Count Dooku, General Grievous
- **Jedi (4):** The Jedi Council, Jedi Temple on Coruscant, Master and Padawan, Lightsaber Construction
- **Clone troopers (3):** Clone Troopers, Kaminoan Cloners, ARC Troopers and Commando Units
- **CIS military (3):** Battle Droids, MagnaGuard, Trade Federation
- **Republic military (2):** Republic Navy, Kuat Drive Yards
- **Coruscant (4):** Coruscant, the Galactic Senate, Chancellor's Emergency Powers, Coruscant Underworld, CoCo Town/Dex's Diner
- **Other locations (2):** Kamino, Geonosis
- **War concepts (3):** Outer Rim Sieges, War Profiteering, Mandalore
- **Reframed GCW locations (3):** Mos Eisley, Nar Shaddaa, Tatooine
- **Tech (1):** Holonet News

Schema mirrors `world_lore` SQLite table + `SEED_ENTRIES` dict shape exactly. Each entry has title, keywords, content, category, optional zone_scope, priority. Zone-scoped entries trigger preferentially when the player is in matching zones; global entries trigger via keyword match anywhere.

Per `clone_wars_era_design_v3.md` §8.2 target ("~50-55 total entries"), this drop covers the critical/high-priority set. The remaining 15-20 medium/low-priority entries (Petranaki Arena detail, individual Senator profiles, secondary CIS council members, etc.) are post-launch enrichment — not gating.

### 2.2 `data/worlds/clone_wars/director_config.yaml` (NEW)

The Director's behavioral knobs:

- **`valid_factions`** — six joinable factions (republic, cis, jedi_order, hutt_cartel, bhg, independent) plus `npc_only_factions` for sith and separatist_council
- **`zone_baselines`** — 33 zones × 6 factions, all with starting influence scores: 27 ground zones across 6 planets + 6 space narrative-tone zones. Scores reflect the §13 user decisions: Tatooine and Nar Shaddaa are Hutt-dominated neutral; Coruscant is Republic-dominated with Jedi Order spike at Temple; Kuat is Republic-aligned industrial; Kamino is locked-down Republic; Geonosis is CIS-dominated.
- **`system_prompt`** — full Clone Wars rewrite of the Director's static prompt. Replaces the GCW prompt at `engine/director.py:678-715`.
- **`milestone_events`** — five day-one milestones: `dark_side_stirring` (Sith atmospheric, per §13), `separatist_offensive`, `republic_victory`, `jedi_lost`, `hutt_war_profiteering`. Each has trigger config, cooldown, narrative priority, output type, and flavor template.
- **`holonet_news_pool`** — ten Holonet News flavor lines for atmospheric Director rolls when no milestone applies.
- **`rewicker`** — translation table mapping legacy GCW faction codes (`imperial`, `rebel`, `criminal`) to CW codes, and legacy GCW zone keys (`spaceport`, `streets`, `cantina`, `shops`, `jabba`, `government`) to closest CW zones.

The rewicker is a transitional mechanism — once the engine fully era-parameterizes the faction enum and the zone-key lookup, it can be deleted.

### 2.3 `data/worlds/clone_wars/ambient_events.yaml` (NEW — additive)

Ambient event lines for the four new CW planets and the six space narrative-tone zones. Schema mirrors `data/ambient_events.yaml` exactly:

- **Coruscant (6 zones):** senate, temple, upper, midlevels, lower, works — 5-7 lines each
- **Kuat (3 zones):** main_spaceport, orbital, city_embassy — 6 lines each
- **Kamino (3 zones):** tipoca_command, clone_facility, ocean — 6 lines each
- **Geonosis (4 zones):** arena, foundries, wastes, tunnels — 6-7 lines each
- **Space narrative-tone (4):** coruscant, kuat, kamino, geonosis — 4 lines each

Tatooine and Nar Shaddaa zones already have ambient pools in the global `data/ambient_events.yaml`. Per the file's REWICKER NOTES section, those pools get a small set of CW-flavored additions during the engine refactor (clone troopers on leave, holovid war news, etc.) rather than full re-authoring.

Total CW ambient lines authored: ~95. Per `clone_wars_era_design_v3.md` §8.6 target (~170 lines), this is roughly 55% of the projected coverage. The remaining ~75 lines are deeper variation per zone — also post-launch enrichment, not gating.

### 2.4 `data/worlds/clone_wars/era.yaml` (EDIT — CW-only file)

Three new entries in `content_refs`:

```yaml
lore: lore.yaml
director_config: director_config.yaml
ambient_events: ambient_events.yaml
```

This builds on the previous Space Pivot drop's edit to `era.yaml` (which added `space_zones`, `starships`, `traffic_archetypes`). The base era.yaml structure and `registry_policy` block from that drop are preserved.

---

## 3. What's deferred (engine refactor — Drop 6a scope)

Three modules need refactoring. None are deeply structural; the heaviest item (director.py) is a ~200-line refactor that moves source constants to data without changing behavior.

### 3.1 `engine/world_lore.py` — load SEED_ENTRIES from YAML

`engine/world_lore.py` defines `SEED_ENTRIES` as a 61-entry list literal (line 284). The refactor adds:

- `load_seed_entries(era: str) -> list[dict]` — reads `data/worlds/<era>/lore.yaml`, returns the same shape as the current literal
- `seed_world_lore` (existing function, line 779) — modified to consume the era-loaded list rather than the source constant

Rollback path: keep the source constant as `_GCW_LEGACY_SEED_ENTRIES`. Engine reads from YAML when the feature flag is on; falls back to the legacy constant otherwise.

The CW lore corpus is fully additive — DB seeds via the same `seed_world_lore` mechanism, idempotent, safe to re-run. The flag flip happens in Drop 6a step 5.

### 3.2 `engine/director.py` — extract VALID_FACTIONS, DEFAULT_INFLUENCE, system_prompt

The biggest refactor. Three source constants become loader-fed values:

- **`VALID_FACTIONS`** (line 48) — `frozenset({"imperial", "rebel", "criminal", "independent"})` becomes `frozenset(loaded_config.valid_factions)`. About 30 references to `VALID_FACTIONS` across the file (most internal), all of which become `frozenset` derived.
- **`DEFAULT_INFLUENCE`** (line 57-64) — currently 6 generic GCW zones. Becomes `loaded_config.zone_baselines` — 33 zones for CW.
- **`system_prompt`** (line 678-715) — currently a multi-line string literal. Becomes `loaded_config.system_prompt`. The prompt's `{faction_list}` template substitution is wired in via `loaded_config.valid_factions`.

The `Director.__init__` and `Director.process_world_state` methods consume the loaded config rather than the source constants. The engine init path becomes:

```python
def __init__(self, era: str = None):
    self.era = era or get_active_era()
    self.config = load_director_config(self.era)
    self.valid_factions = frozenset(self.config.valid_factions)
    self.default_influence = self.config.zone_baselines
    self.system_prompt = self.config.system_prompt
    # ... rest unchanged
```

Same rollback pattern: keep the literals as `_GCW_LEGACY_*` constants until proved equivalent.

### 3.3 `engine/ambient_events.py` — merge global + era-specific pools

Currently reads `data/ambient_events.yaml` directly. Refactor:

- New `load_ambient_pools(era: str) -> dict[str, list]` that reads global + era-specific files, merging with era-key-precedence
- Existing dispatch becomes: lookup specific zone-key (e.g., `coruscant_senate`) first; fall back to generic-key (e.g., `cantina`) if specific not present
- Pool additions documented in `ambient_events.yaml`'s REWICKER NOTES are merged into the generic pool when era == clone_wars

### 3.4 `ai/npc_brain.py` — automatic inheritance (NO CHANGE)

Per `clone_wars_era_design_v3.md` §8.7: "NPC brain pulls relevant lore dynamically from the world_lore table based on player dialogue keywords. When we rewrite the lore, NPC dialogue adapts automatically."

No code changes here. Verifying that NPC dialogue uses CW lore correctly is a smoke test in §5.4, not a refactor.

---

## 4. Drop sequence (6a sub-drops)

Each sub-drop ships independently behind the same feature flag (`config.use_yaml_director_data: bool`, default `False` until proven byte-equivalent on GCW).

| Sub-drop | Scope | Effort | Gates |
|---|---|---|---|
| 6a.1 | `world_loader.py` extension: `load_lore`, `load_director_config`, `load_ambient_pools` (validators + dataclasses + tests) | Small (~½ session) | F.0 Drop 1 (shipped) |
| 6a.2 | `engine/world_lore.py` refactor: era-aware `SEED_ENTRIES` source. Test asserts CW-loaded entries match expected count + shape. | Small (~½ session) | 6a.1 |
| 6a.3 | `engine/director.py` refactor: `VALID_FACTIONS`, `DEFAULT_INFLUENCE`, `system_prompt` consume loaded config. Behind feature flag. Regression test asserts GCW-loaded YAML produces byte-equivalent behavior to current hardcoded path. | Medium (~1 session) | 6a.1 |
| 6a.4 | `engine/ambient_events.py` refactor: era-aware pool merge with global + CW additions. | Small (~½ session) | 6a.1 |
| 6a.5 | Author `data/worlds/gcw/lore.yaml`, `director_config.yaml`, `ambient_events.yaml` — GCW counterparts (regression test asset + legacy archive). | Small (~½ session) | 6a.1 |
| 6a.6 | Flip `use_yaml_director_data` default to `True` for `clone_wars` era only. GCW continues on hardcoded path. | Trivial | 6a.1–5 |
| 6a.7 | Delete hardcoded fallbacks once both eras run on YAML stably. | Small | 6a.1–6 |

**Total effort:** ~3 implementation sessions across 7 sub-drops. None block Priority F's parallel content drops (F.0 Drops 2-4, F.5, F.6/F.6.5, F.10).

**Parallel-safety:** 6a.1 only adds loader functions. 6a.2-4 add dispatch wrappers without removing legacy paths. 6a.6 is a config flip. 6a.7 is the only destructive change and runs last. Merge conflict surface with main-track work is small.

---

## 5. Test plan

### 5.1 6a.1 — loader tests

`tests/test_world_loader_director.py` — new file:

- `test_load_lore_clone_wars` — loads, validates 32 entries, schema correct
- `test_load_director_config_clone_wars` — 33 zone_baselines, 6 valid_factions, system_prompt non-empty
- `test_load_ambient_pools_clone_wars` — loads, validates per-zone shape
- `test_lore_zone_scope_resolves_to_known_zones` — every zone_scope token (when set) matches a defined zone in `zones.yaml`
- `test_director_config_baselines_match_zones_yaml_keys` — every zone_baselines key resolves to a defined zone
- `test_lore_keywords_unique_or_documented` — keyword collisions are warnings, not errors
- `test_director_milestone_events_have_required_fields` — id, trigger, cooldown_hours, narrative_priority, output_type, flavor_template

### 5.2 6a.2 — world_lore equivalence tests

`tests/test_world_lore_yaml.py` — new file:

- `test_gcw_yaml_seed_entries_match_legacy_constant` — once 6a.5 ships GCW YAML, byte-equivalence
- `test_clone_wars_loads_32_entries` — count check
- `test_clone_wars_factions_lore_present` — title-name search ensures core entries are present
- `test_seed_lore_idempotent_on_clone_wars` — re-running seed does not duplicate

### 5.3 6a.3 — director equivalence tests

`tests/test_director_yaml.py` — new file:

- `test_gcw_yaml_baselines_match_legacy_dict` — gates 6a.5 GCW YAML
- `test_gcw_yaml_factions_match_legacy_frozenset` — same
- `test_clone_wars_baselines_for_temple_high_jedi_score` — sanity: `coruscant_temple.jedi_order >= 90`
- `test_clone_wars_baselines_for_geonosis_high_cis_score` — sanity: `geonosis_foundries.cis >= 80`
- `test_clone_wars_system_prompt_mentions_jedi_temple` — atmospheric verification
- `test_director_milestone_dark_side_stirring_fires_on_threshold` — milestone trigger logic with mocked dark-side kill cluster

### 5.4 Integration smoke

- Boot game with `active_era: clone_wars`; ask an NPC at Temple about the Jedi Order; confirm response references Council, Padawan training, current war.
- Move PC to `tatooine_mos_eisley`; trigger Director adjustment; confirm `republic` and `cis` stay low while `hutt_cartel` is the dominant axis.
- Trigger `dark_side_stirring` milestone via test harness; confirm Holonet ambient broadcast.
- Move PC to `coruscant_lower`; check ambient event pool produces lower-level lines, not generic streets lines.
- Confirm `nar_shaddaa_lower` ambient still draws from generic + CW additions (Hutt war profiteering line shows up in pool).

---

## 6. Open questions

### 6.1 Influence score sums

Some zone_baselines have `republic + cis > 100` (Coruscant Senate: 90+5; Coruscant Temple: 70+0; Geonosis Foundries: 5+90). The Director currently treats influence as 0-100 per faction independently — these are not normalized. Confirming this is the intended math, since the factions are now 6 instead of 4 and the GCW values implicitly assumed only 4.

**Recommendation:** ship as authored — independent dimensions. If the Director's adjustment math implicitly relies on a 4-faction sum-bound, it needs adjusting in 6a.3. Test in §5.3 catches this.

### 6.2 Rewicker drift risk

The `rewicker.faction_codes` map (`imperial → republic`, etc.) is convenient for legacy code paths but creates a long-term coupling. If a future feature uses `imperial` as a dimension code (e.g., a "former Imperial" reputation axis) the rewicker will silently coerce it to `republic`.

**Recommendation:** flag the rewicker as transitional; remove it during 6a.7 alongside the deletion of legacy fallbacks. Any code path still using GCW codes at that point is a bug.

### 6.3 Lore corpus completeness

Per §8.2 target, the audit projected ~50-55 total entries; this drop ships 32. The remaining 18-23 are medium/low priority (specific Senator profiles, individual Council members, Petranaki gladiator history, etc.). Choosing what to add vs defer.

**Recommendation:** ship 32 at launch. The §8.7 NPC-brain inheritance means lore additions are zero-friction post-launch; new entries can be authored as the world demands. 32 covers all the "must have" hooks.

### 6.4 Holonet News template substitution

The `holonet_news_pool` entries include `{name}`, `{sector}`, `{jedi_general_name}` template tokens. The Director needs a substitution mechanism that resolves these against current world state.

**Recommendation:** simple Python str.format with a context dict. Director substitutes from `world_state` digest values where they exist; falls back to a name pool (e.g., a list of generic Jedi General names) where they don't. This is small new logic, lands in 6a.3.

### 6.5 Tatooine/Nar Shaddaa CW additions to global pool

Per the REWICKER NOTES section in `ambient_events.yaml`, three lines each are additions to the global file's `cantina`, `spaceport`, and `streets` pools. The merge logic ("when era == clone_wars, add these lines to the generic pool") is small but new.

**Recommendation:** ship the merge logic in 6a.4. The lines are documented in YAML comments today; 6a.4 promotes them to a structured `era_additions` block.

---

## 7. Acceptance criteria

The 6a stack is complete when:

1. With `active_era: clone_wars` and `use_yaml_director_data: True`:
   - `world_lore` table seeds with 32 CW entries; querying for "republic" returns the Galactic Republic entry; "jedi" returns Jedi Order + Council + Temple
   - Director instance loads with 6 valid_factions and 33 zone_baselines
   - Director's system_prompt mentions Coruscant, Jedi Temple, and Outer Rim Sieges (textual sanity)
   - `coruscant_temple` has `jedi_order: 95`; `geonosis_foundries` has `cis: 90`
   - Ambient events at `coruscant_senate` produce CW-flavored lines; at `tatooine_cantina` produce a mix of generic + CW additions
   - `dark_side_stirring` milestone fires correctly on test-harness threshold
2. With `active_era: gcw` and `use_yaml_director_data: True`:
   - Engine produces byte-equivalent values to legacy hardcoded path (6a.5 regression test passes)
3. All 6a test files (§5.1–5.3) green
4. NPC dialogue smoke test (§5.4) passes — Jedi Temple NPC responds with CW-appropriate context, not GCW

---

## 8. Roadmap insertion

Add to `roadmap_v34.md` Tier 2 / Priority F as Drop 6a (placement before F.7 — Pivot enablement):

```
| F.6a (Drop 6a.1) | Director/lore loader extensions | ❌ |
| F.6a (Drop 6a.2) | world_lore.py YAML refactor | ❌ |
| F.6a (Drop 6a.3) | director.py YAML refactor + rewicker | ❌ |
| F.6a (Drop 6a.4) | ambient_events.py merge logic | ❌ |
| F.6a (Drop 6a.5) | GCW counterpart YAMLs (test asset + archive) | ❌ |
| F.6a (Drop 6a.6) | Flag default flip for CW; GCW unchanged | ❌ |
| F.6a (Drop 6a.7) | Delete hardcoded fallbacks (post-stability) | ❌ |
```

Drop 6a does not block:
- F.0 Drops 2-4 (planet content authoring)
- F.5 (Coruscant Underworld + housing + test characters)
- F.6 / F.6.5 (Tutorial rework + FDTS rewicker)
- F.10 (Space Pivot — independent stack)

Drop 6a **does** block:
- F.7 (Pivot enablement engine — assumes 6a's data-fication done)
- F.9 (Live pivot cutover — without 6a, the live CW build has GCW Director behavior)

---

## 9. Sign-off

This design closes the third deferred item from the original CW pivot handoff:

- ~~Galactic coordinate / space zone planning~~ → closed by `clone_wars_space_pivot_design_v1.md`
- ~~Ship roster audit~~ → closed by `clone_wars_space_pivot_design_v1.md`
- ~~Director `zone_baselines` values for all new Clone Wars zones~~ → closed by §2.2 (33 zones authored)

Two deferred items from `HANDOFF_CLONE_WARS_ERA_PIVOT.md` remain:

- **Tutorial chain step-by-step design** — 8 chains enumerated, not yet written. Future drop.
- **Village quest chain dialogue trees** — Act 1/2/3 structure designed, dialogue not. Drop 10.

Both can run as parallel drops. Tutorial chains are the bigger item (~30 step-objectives); Village dialogue is smaller (~15-20 dialogue tree branches).

Content for the Director/Lore Pivot is ready in `data/worlds/clone_wars/`. Engine refactor scheduled as Drop 6a. Drop is parallel-safe with the main track.

*— Opus, parallel CW track session, April 25, 2026*
