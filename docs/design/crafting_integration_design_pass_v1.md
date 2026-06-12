# SW_MUSH — Crafting Integration Design Pass (T2.CRAFT.integration_design_pass)
## Version 1.0 — June 10, 2026
## Companion to: `gundark_crafting_integration_design_v1.md` (the unexecuted integration plan), `Guide_07_Crafting.md` (documented shape), `sourcebook_mining_crafting_exp_design_v1.md` §6 (experiment engine design)
## Gates: **UI-8 (Webify crafting panel)** and the Lane C craftable/lootable gear families

---

## 0. TL;DR

Brian's suspicion — *"sourcebook content meant to buff crafting was never wired"* — is confirmed,
and the situation is worse than unwired content. The HEAD audit (every claim below is
symbol-level-verified against the 2026-06-10 11:35 upload) found:

1. **An entire prior bugfix drop is a phantom.** The CHANGELOG carries a full
   `T2.DEF.t5_discoverability` entry (5 bugs fixed, 13 tests, Files list) — **none of it is in
   HEAD.** The `craft` verb crashes on every invocation; `resources` crashes for anyone holding
   resources; the `schematics` listing prints garbage. The drop's own tests vanished with it,
   which is why the suite stayed green.
2. **Even before that phantom, the output pipeline leaks.** Crafted weapons are appended to a
   `session.items` attribute that does not exist anywhere in the codebase (silent
   AttributeError → **the item evaporates** while the player is told it was added). Six
   `equipment`-type schematics have **no landing branch at all**. The `component` and
   `survival_gear` branches write legacy bare-list inventory JSON that **destroys the
   character's resource stacks** under the current dict format.
3. **The Gundark integration plan (≈180-item catalog → crafting families) was never executed.**
   It is still a valid plan; its own Step-0 pre-flight questions are now answered in §3.1.

The pass therefore splits into **Phase 0 (remediation — the loop must work before it can be
buffed)** and **Phase 1+ (the actual integration: Gundark families, taxonomy growth, UI-8)**.
Phase 0 is mechanical and fully specified in §2; nothing in Phase 1+ starts until it ships,
and **UI-8 stays gated** until Phase 0 + the §4 ABI are accepted.

---

## 1. HEAD findings (the audit of record)

### 1.1 What is wired and healthy ✅

Verified live, with consumers:

| Surface | Evidence |
|---|---|
| Survey/harvest loop | `SurveyCommand` + `engine/harvest.py` `YIELD_TABLE`; weekly region quality variance (`engine.region_quality`) |
| Resource stacks | `add_resource`/`consume_components`/`check_resources` (`engine/crafting.py` §409–530); dict-format inventory `{"items":[],"resources":[]}` |
| Teach/trainers | `TeachCommand`; 6 trainer NPCs bound by name in `schematics.yaml` (`Doc Vashar, Heist, Kayson, Renna Dox, Vek Nurren, Venn Kator`) |
| Experiment engine | SHIPPED (Gundark Q1.3 = present): `resolve_experiment*`, `DEFAULT_EXPERIMENT_PARAMS` w/ per-output_type axis blocks, per-item `experiment_count/breakdown_dice` on `ItemInstance` |
| T5 gating | 5 drop-only wilderness mats in `RESOURCE_TYPES`, `T5_WILDERNESS_MATERIALS`, q75+ gate; drop hooks in landmark/anomaly call sites |
| Crafted-goods market | `npc_refuses_buyback` (economy audit v2 §1.3) pushing player crafts to vendor droids; vendor droid stock/sell loop |
| Consumable consumers | `attributes.consumables` ← consumed by `UseCommand` + `StimCommand` (SRB.1) + `engine/buffs.py` |
| Ship-component consumer | `+ship/install` reads `type == "ship_component"` inventory dicts (`parser/space_commands.py:1654`) |
| Hazard-gear consumer (intent) | `engine/hazards.py::_has_mitigation` checks inventory keys vs `mitigation_items` — **but see F5** |

38 schematics across 5 output_types (`weapon` 11, `component` 9, `consumable` 7,
`equipment` 6, `survival_gear` 5), including the 5 T5 recipes.

### 1.2 Findings — broken (severity order)

**F1 — PHANTOM DROP: `T2.DEF.t5_discoverability` (CHANGELOG ~line 1215, dated 2026-06-02 region) is entirely absent from HEAD.** Evidence: `tests/test_crafting_discoverability.py` does not exist; all five "fixed" bugs are live at HEAD:
- **F1.D — `craft` verb crashes on EVERY invocation.** `CraftCommand` passes `quality_base`
  (float) to `resolve_craft`, which requires a `SkillCheckResult` →
  `AttributeError: 'float' object has no attribute 'fumble'` (reproduced in-sandbox).
  No smoke covers the verb (E7/E8 explicitly deferred in
  `tests/smoke/scenarios/economy_progression.py` docstring) — root enabler for everything here.
- **F1.C — wrong skill field.** `schematic.get("skill", "repair")` — no schematic carries
  `skill`; the data field is `skill_required`. Every craft rolls a nonexistent "repair" skill
  → permanent `[auto]` quality-60 path; craft quality divorced from crafter skill.
- **F1.B2 — `resources` crashes.** Listing reads `r['amount']`; stacks store `quantity` →
  `KeyError` for any character holding resources (`parser/crafting_commands.py:190`).
- **F1.B1 — `schematics` listing garbage.** Reads `resource_requirements` (a key no schematic
  has → "Needs: none" ×38) instead of `components` (`:224`).
- **F1.A — `check_resources` diagnostics** conflate quantity-blocked with quality-blocked.

**F2 — Crafted weapons evaporate.** Weapon branch of `_create_finished_item`
(`parser/crafting_commands.py:941–945`) and `_give_item_to_char` (`:74–79`) call
`ctx.session.items.append(item)` — **no `Session.items` exists anywhere** — inside a
swallowed-AttributeError try. Components are consumed, "added to your inventory" is printed,
the item is gone. The real path is `db.add_to_inventory(char_id, item_dict)`
(`db/database.py:4659`) — which also fires the F.8.c.2.b₂ `item_acquired` tutorial hook the
current code bypasses.

**F3 — `output_type: equipment` has no landing branch.** Six schematics (`comlink_bug,
lockpick_simple, lectroticker, tracker_basic, t5_hyperdrive_surge_converter,
t5_mil_spec_ion_engine_core`) fall through `_create_finished_item` silently: skill check rolls,
components consumed on success, **no item, no message**. (Note: the two `t5_*` entries are ship
parts and are likely mis-typed data — they belong under `component` so `+ship/install` can
consume them. The other four are genuine gear → §3.2.)

**F4 — `component`/`survival_gear` branches destroy resource stacks.** Both parse the inventory
column expecting a bare list; under the current dict format (`get_inventory` docstring:
"current dict format") `isinstance(inv, list)` fails → `inv = []` → the branch writes a
**bare list containing only the new item**, dropping `items` AND `resources`. Crafting a ship
component deletes every resource you own. Fix: `db.add_to_inventory` (same as F2).

**F5 — Survival gear never mitigates hazards for dict-format inventories.**
`hazards._has_mitigation` iterates the inventory top-level — under dict format that iterates
the *keys* `"items"`/`"resources"`, never the item dicts. Also reads
`char.get("equipped_weapon")`/`("worn_armor")` from the row dict, where those live inside the
`equipment` JSON, not as row columns → the equipped/worn checks are dead too. Fix: iterate
`items` via the tolerant raw-shape read; use `engine.items.equipment_keys` for the slots
(same canonicalization as the 2026-06-10 straggler sweep).

**F6 — `electronic` resource type is undeclared** (Gundark Q1.2 = finding **(b)**).
`sensor_mask` and `comm_jammer` consume `electronic`, which is not in `RESOURCE_TYPES`;
`add_resource` rejects unknown types → **the type can never be acquired; both recipes are
permanently uncraftable.**

**F7 — Two weapon `output_key`s dangle.** `stun_pistol` and `blaster_carbine` resolve to no
`data/weapons.yaml` entry → a crafted instance would carry a key the registry can't resolve
(sheet shows the raw key; `attack` falls to default damage). Either add the two WEG-statted
entries or retire the schematics.

**F8 — Zero end-to-end coverage.** E7 (craft loop) / E8 (experiment paths) smoke scenarios were
deferred for harness reasons. F1.D survived **at least 8 days** because of this.

---

## 2. Phase 0 — remediation drop (BLOCKS everything else)

One drop, `parser/crafting_commands.py`-centric. Faucet/sink note: this is repair of an
existing faucet, not a new one — no pairing obligation triggered.

| # | Fix | Site |
|---|---|---|
| P0.1 | Re-deliver the phantom: pass the real `SkillCheckResult` to `resolve_craft` (except-branch builds an auto-success `SimpleNamespace`, per the original entry); roll `skill_required`; `schematics` reads `components`+`skill_required` w/ craftable flag; `resources` reads `quantity`; `check_resources` quantity-vs-quality diagnostics | `parser/crafting_commands.py`, `engine/crafting.py` |
| P0.2 | Weapon landing → `await ctx.db.add_to_inventory(char_id, item.to_dict() + type:"weapon")`; delete `_give_item_to_char`; chain hook fires for free | `parser/crafting_commands.py` |
| P0.3 | `component`/`survival_gear` landings → `db.add_to_inventory` (no raw column writes) | same |
| P0.4 | NEW `equipment` branch → `db.add_to_inventory` with `type:"equipment"` durable dict (key/name/quality/crafter); re-type the two `t5_*` ship parts to `component` in `schematics.yaml` (additive field edit, comment-preserving) | same + `data/schematics.yaml` |
| P0.5 | `_has_mitigation`: iterate `items` from the tolerant raw read; slots via `equipment_keys` | `engine/hazards.py` |
| P0.6 | Formalize `electronic` as the 7th harvestable type: add to `RESOURCE_TYPES` + `HARVESTABLE_RESOURCE_TYPES` + urban/tech-zone rows in `harvest.YIELD_TABLE` (city survey finding electronics scrap is era- and fiction-clean) | `engine/crafting.py`, `engine/harvest.py` |
| P0.7 | Resolve the two dangling weapon keys: WEG-stat `stun_pistol` + `blaster_carbine` into `data/weapons.yaml` (R&E stats exist for both; re-stat from WEG only) | `data/weapons.yaml` |
| P0.8 | Tests: restore-equivalent of the 13 phantom tests + new coverage for P0.2–P0.7 + **E7/E8 smoke scenarios** (harness already gained the seeding/tick extensions other smokes use — verify, then unblock) | `tests/` |

Acceptance: a character can survey → buy/learn → craft each of the five output_types →
find the item where its consumer reads it (sheet/attack, `use`, `+ship/install`, hazard
mitigation, inventory) → sell/stock it. That sentence becomes smoke E7.

## 3. Phase 1+ — the integration (what "buff crafting" actually means)

### 3.1 Gundark plan: Step-0 answers (its hard precondition, now satisfied)

| Q | Answer at HEAD |
|---|---|
| 1.1 schema | Confirmed: `key/name/skill_required/difficulty/trainer_npc/components[]/output_type/output_key/base_cost` + ship extras |
| 1.2 `electronic` | Finding **(b)** — latently broken; P0.6 formalizes it |
| 1.3 experiment engine | **Shipped**; extend its category table per new families |
| 1.4 output enum | `weapon/consumable/component/survival_gear` land (post-P0); `equipment` lands at P0.4; **`armor` and `explosive` still need branches** when their families arrive |
| 1.5 output tables | weapons.yaml (weapons+armor); consumables in `_CONSUMABLE_STATS` (parser-local — should migrate to data, see 3.3); no gear/explosive tables yet |
| 1.6 skills | 12 `skill_required` values live incl. `armor_repair`, `security`, `survival` — the plan's needed skills already exist |
| 1.7 trainers | Bound by **name string** in YAML; 6 seeded. New families need new trainer seeds (slug-binding upgrade optional, not blocking) |
| 1.8 era gate | B3 static test live; apply extraction §8 filters to all new strings |

### 3.2 Scope confirmation

Adopt the Gundark §2 scope filter as written (availability-code banding; prototypes/uniques →
loot; era-cut items stay cut). The §9 decisions it requested from Brian remain open — listed in
§5. The four genuine `equipment` schematics (comlink_bug, lockpick, lectroticker, tracker)
become the **reference implementations** for the gear family before any new ones are added.

### 3.3 Structural moves (extend-don't-add)

- **Consumable stats out of the parser.** `_CONSUMABLE_STATS` is a parser-local dict consumed
  by medical/buffs; migrate to `data/consumables.yaml` + a registry in `engine`, so Gundark
  stim/med families are data drops, not parser edits.
- **Faucets and sinks land together.** Each new craftable family ships only with its sink
  (vendor-droid market + NPC salvage floor already exist; Lane C craftable/lootable families
  stay gated behind **Drop-5 farming controls** exactly as memory records).
- **Experiment axes** for new families: add category blocks to `DEFAULT_EXPERIMENT_PARAMS`
  (gear: reliability/concealment axes; explosive: yield/stability) — only when each family lands.

### 3.4 UI-8 `crafting_state` ABI (reserved in protocol ledger v1.4 — to pin as §1.9 on acceptance)

Push on `schematics` / `resources` / `craft` (WS-gated, Telnet text unchanged — the
UI-1→7 pattern). Single message, three sections:

```
crafting_state = {
  "schematics": [ {key, name, skill, difficulty, craftable: bool,
                   components: [{type, quantity, min_quality, have, have_at_quality}],
                   output_type, t5: bool} ],
  "resources":  [ {type, quantity, quality} ],
  "last_result": {success, partial, fumble, quality, name} | null
}
```

`craftable` + per-component `have/have_at_quality` are exactly the P0.1 `check_resources`
diagnostics — the panel renders what the engine already computes; **no field without a
producer**. Verbs staged real: `craft <name>`, `survey`, `buyresources`, `experiment <axis>`.
Panel design follows the Webify pack visual language (deferred item #7 in the pack README).

## 4. Drop sequence

1. **CRAFT.P0** — remediation (one drop; §2 table). *Gates everything.*
2. **CRAFT.P1** — Gundark Drop A per its plan (first availability band), consumables-to-data
   migration, experiment axes for the shipped families.
3. **UI-8** — `crafting_state` + panel (after P0 proves the loop and Brian accepts §3.4).
4. **CRAFT.P2+** — further Gundark bands; armor/explosive branches when those families arrive;
   Drop-5 farming controls unlock the Lane C craftable/lootable families.

## 5. Design calls pending Brian

1. **Gundark §9 decisions** (carried, still open): availability-band cutoff for craftability;
   black-market gating model for restricted items; whether `Demolitions` enters as a new
   trained skill or maps to an existing one.
2. **§3.4 ABI acceptance** before UI-8 work starts.
3. **P0.7 alternative:** if you'd rather not stat `stun_pistol`/`blaster_carbine`, the two
   schematics retire instead (player-facing copy: trainer "no longer teaches" them).

---

*Audit performed 2026-06-10 against `SW_MUSH_upload_20260610_1135.zip`; every finding carries a
file:line or reproduction in the session log. The phantom-drop finding (F1) is logged in
TODO.json (`PHANTOM.t2_def_t5_discoverability`).*
