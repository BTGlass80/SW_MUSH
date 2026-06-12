# HANDOFF — Suite triage → Crafting remediation → Webify UI-8 → Gundark Drop A
## Session 2026-06-10 · Drops 3–8 · Rollup: `SW_MUSH_drops3-8_rollup_2026-06-10.zip` (35 files, cumulative)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then `run_all_tests.bat`.
The zip is **cumulative for the whole session** — it contains every file from the retired drops3-6 and
drops3-7 rollups at their latest state. No earlier zip from this session is needed or should be applied.

**Windows-validation status:** Brian's last suite run was against the **drops3-6** state
(2 failed / 8,039 passed — both failures fixed in drop 7). **Drops 7 and 8 have NOT yet been
Windows-validated.** The next `run_all_tests.bat` is the acceptance gate for both.

---

## 1. Where the session started

Fresh HEAD upload `SW_MUSH_upload_20260610_1135.zip`. Brian's suite: **6 failed / 7,988 passed**.
Root causes: a `+sheet` NameError (`equip_data`, engine/sheet_renderer.py:486) crashing every sheet
render, and a stale world-writer manifest golden count (280 → 287 after Lane D's 7 Geonosis rooms).

---

## 2. Drop-by-drop

### Drop 3 — Suite triage + equipment straggler sweep
- Fixed both suite failures above.
- The sheet crash triggered a symbol-level audit that found **12 more un-migrated equipment readers**
  (the equipment-untangle handoff's "all migrated" claim was false): attack ignored the equipped
  weapon, combat wear never applied, all fumbles wiped armor, plus look/sell/+weapons/+armor/shop/
  vendor/disarm sites. All 13 sites migrated to `read_equipment`/`equipment_keys`/`write_equipment`
  with armor preservation. `tests/test_equipment_reader_stragglers.py` (9) pins them.
- **Phantom recurrence:** `web_onboarding_design_v1.md` + `web_client_vision_and_protocol_v1_4.md`
  were in the UI-5/6/7 rollup's Files list but absent from Brian's tree (v1_4 phantomed TWICE).
  Restored from project copies; both are in this rollup.

### Drop 4 — `T2.CRAFT.integration_design_pass` (doc: `crafting_integration_design_pass_v1.md`, repo root)
Brian's suspicion confirmed and exceeded: the crafting loop itself was broken at HEAD.
- **F1 — PHANTOM DROP:** the entire `T2.DEF.t5_discoverability` drop (CHANGELOG-claimed, 5 bugs +
  13 tests) was absent from HEAD. `craft` crashed on EVERY invocation for 8+ days; the suite stayed
  green because the drop's tests vanished with it. Logged `PHANTOM.t2_def_t5_discoverability`.
- F2 crafted weapons evaporated · F3 `equipment` outputs had no landing branch · F4 component/survival
  landings destroyed resource stacks · F5 survival gear never mitigated hazards · F6 `electronic`
  undeclared (two recipes uncraftable; `buyresources electronic` ate credits) · F7 two dangling weapon
  keys · F8 zero verb-level coverage (root enabler).
- **Brian's eight decisions recorded** (TODO `design_calls_resolved_recent`): 1a electronic formalized ·
  2a armor/explosive/gear types, survival_gear folds into gear · 3a contraband = outlaw-tech ·
  4a curated ~70–90 schematics · 5 §10 rubric signed off · 6a stat the dangling keys · 7 UI-8 ABI
  accepted · 8a commissary → future `mode:'vendor'` slot. Plus the **mechanical-use mandate** (§3.2a):
  every craftable item ships only with its defined gameplay consumer; long-pole hooks queued as
  `CRAFT.HOOK.restraints` / `CRAFT.HOOK.force_detector`.

### Drop 5 — CRAFT.P0 (remediation implemented in full)
- All five phantom fixes re-delivered; quantity-vs-quality `check_resources` diagnostics
  ("need 3x metal — you have 1x" vs "have 5x but only 0x at q75+, best grade q72").
- Every craft landing → `db.add_to_inventory` (fires the tutorial `item_acquired` hook); NEW
  `equipment` branch; unhandled-output_type guard; the two mis-typed t5 ship parts re-typed
  `component` (surge converter: hyperdrive +3; engine core: speed +2 = one-slot cap reach).
- Hazards read dict-format inventory + canonical equipment slots. `electronic` in RESOURCE_TYPES +
  HARVESTABLE + city survey yields. `stun_pistol` (2D stun-only, 300cr) + `blaster_carbine` (5D,
  900cr) statted from the Gundark extraction; **`stun_only` wired** — the attack path forces stun mode.
- **P0.9 (found mid-drop):** `equip`/`wear` MINTED free pristine vendor instances (unlogged faucet;
  crafted instances unequippable); `unequip`/`remove` DESTROYED instances; `buy` destroyed the
  displaced weapon. All gear verbs now inventory-aware/instance-preserving via new `engine/items.py`
  helpers `find_carried_gear`/`instance_to_carried`/`carried_to_instance`. Acquisition is exclusively
  buy/craft/loot/trade. Verified no tutorial/chargen dependency on the mint.
- **E7/E8 smokes UN-DEFERRED** via direct DB state seeding (no cooldown/node harness extensions).
- Tests: `tests/test_craft_p0_remediation.py` (35 after drops 7–8 additions).

### Drop 6 — Webify UI-8 (crafting panel) → **Webify UI-1→UI-8 ALL SHIPPED**
- Producer `engine/crafting.py::build_crafting_state(char, last_result=None)` + `component_availability`
  — known schematics only; `craftable` flag = `check_resources` parity (pinned by test so they can
  never disagree).
- Push `_push_crafting_state` (WS-gated) from `schematics`/`resources`/`craft` (+`survey` since drop 7).
- Client `static/spa/m3_craft.js` (M3Craft) + craft modal in `client.html` (shares `.inv-modal`
  chrome), token-only `m3c-*` CSS, **CRAFT quick-action** (sends the real `schematics` verb).
  Component states: met `--self` / quality-blocked `--warn` (both numbers named) / quantity-blocked
  `--text-dim`; T5 stud `--accent-bright`. Staged real verbs only: `craft <name>`, `survey`,
  `buyresources <type> ` (trailing space).
- Protocol ledger: `crafting_state` pinned **§1.9** in `web_client_vision_and_protocol_v1_4.md`.
- Tests: `tests/test_crafting_state.py` (8) + `tests/spa/test_m3_craft.py` (4 jsdom); m3_craft.js in
  the wireup load order. **Caught pre-ship:** producer tests + E7 seeded the wrong attributes key —
  the real known-schematics key is **`schematics`** (per `add_known_schematic`), not `known_schematics`.

### Drop 7 — CRAFT.P1: the persistence no-op class (E7's first Windows catch)
Brian's run on drops 3–6: 2 failed / 8,039. E7 failed exactly as designed — craft reported success,
`consumables.medpac=0` on re-fetch. Root cause: **`db.save_character(id)` with NO kwargs is a silent
no-op** (`if not fields: return`). Seven sites believed they were saving:
1. `_save_char` (every crafting verb's "save") — now persists `attributes`, and is **deliberately
   attributes-only**: `db.add_to_inventory` does its own DB read-modify-write, so blanket-saving the
   dict's inventory after a delivery would clobber the landed item.
2. **Craft component consumption** — `resolve_craft` consumes dict-side; consumption never persisted
   → infinite materials across reload, every output type. Fixed with an **ordering-critical** save:
   `inventory=` immediately after `resolve_craft`, BEFORE `_deliver_item` (source-order pin enforces).
3. **Survey** — resources + cooldown never persisted. Explicit both-column save; survey joined the
   `crafting_state` push set (panel stages `survey`; ledger §1.9 updated).
4. **Teach target** — PC-taught schematics never persisted.
5. **Space salvage credits** — never persisted AND bypassed `adjust_credits`. Rerouted through the
   ledger chokepoint (`"space_salvage"` tag), dict synced from its return.
6. **Space salvage resources** — never persisted.
7. **`encounter_anomaly._award_resources`** — doubly broken: mutated a THROWAWAY COPY (`dict(char)`),
   then no-op saved.
- **Regression net:** `TestPersistenceNoOpClass` — an **AST-walk sweep** over `parser/` + `engine/`
  asserting no `save_character` call has positional args and zero keywords (AST, not regex: the regex
  draft flagged 4, of which 3 were false positives and 1 was my own docstring). Plus per-site pins.
- TODO hygiene fix: `last_updated` is bare ISO; prose lives in `last_updated_note`.

### Drop 8 — CRAFT.P2 / Gundark Drop A (foundation + consumables migration + first Avail-band)
Scoped by the mandate: only families whose **full loop exists at HEAD** (trainer + use-time consumer
+ output table). Explosives ship nothing (Demolitions decision open); a test pins that no
`contraband:` field ships before Drop G's enforcer.
- **⚑ Mandate fix #1 — crafted medpacs were INERT at HEAD.** Only the four stims had use-time
  mechanics; medpac tokens were dead weight (`_CONSUMABLE_STATS.heal_wounds` was a phantom field).
  Now: heal-kind `_STIM_CATALOG` entries (`medpac` first aid vs 10 heals 1 · `medpac_advanced` vs 12
  heals 2 · `medpac_fastflesh` vs 8 heals 1; all self-administration-ok, `buff_type: None`) + a heal
  branch in `_execute_stim_roll`'s success path reducing the `wound_level` column (inverse of the
  fumble branch, floors at healthy). Heal-kind entries **bypass the active-stim/overdose gate**.
  Verb: `stim <player> with medpac` / `stim me with medpac` (-1D self penalty inherited).
- **Consumables → data:** `data/consumables.yaml` (7 identity rows) + `engine/consumables.py`
  registry; `_CONSUMABLE_STATS` deleted. Division of responsibility: **yaml = identity,
  `_STIM_CATALOG` = mechanics** (storage-bifurcation tech debt stands, unification still tracked).
  A **three-way parity test** (schematic outputs ↔ identity ↔ mechanics) makes inert-token
  regressions unrepresentable.
- **`survival_gear` → `gear` fold** (decision 2a): 5 schematics re-typed; branch accepts both
  spellings, lands `type: "gear"`. Hazard-safe (`_has_mitigation` matches by KEY); existing player
  inventories untouched.
- **Armor landing branch** (Drop C infrastructure, sanctioned by §3.2a): ItemInstance-shaped so the
  P0.9 inventory-aware `wear` slots crafted armor intact. Content + armorer trainer arrive in Drop C.
- **Weapons (lawful Avail-2):** `heavy_blaster_pistol_t6` (Thunderer — 6D+2, 3-7/25/50, ammo 25,
  750cr, **no stun setting**) + `vibrorapier_duelist` (STR+3D melee, silent, 300cr). Schematics
  rubric-derived: difficulty 20/17 **recomputed in-test** from §5.1, q40 components = §5.2 Avail-2,
  Kayson-bound. (Caught mid-write: a phantom `max_damage` field in my draft yaml row — removed; the
  WEG 7D cap stays book-lore in `notes`, same as the existing capless vibroaxe.)
- Tests: `tests/test_craft_p2_gundark_drop_a.py` (18).

---

## 3. Verification state

- **Sandbox (this session's final state):** 134-test core batch green — P2 18 · P0/P1 35 ·
  crafting_state 8 · hygiene 9 · syn6c 40 · untangle 15 · stragglers 9. Webify SPA batch 21 green
  (jsdom). AST/YAML/JS validated; rollup round-trip verified from clean.
- **Windows:** drops 3–6 validated (2 known failures → fixed in 7). **Drops 7–8 pending** — the next
  full suite run gates them. Watch: E7/E8 smokes, `test_craft_p0_remediation` (35),
  `test_craft_p2_gundark_drop_a` (18), `test_crafting_state` (8), hygiene (`last_updated` ISO),
  updated goldens (syn6c 11→12 resource types; manifest 287).
- **Brian's browser walk (outstanding):** crafting panel end-to-end — `survey` → `schematics` →
  CRAFT button → craft a medpac (result banner; quality-blocked `--warn` states; survey refreshing
  MATERIALS live) → `stim me with medpac` to close the loop in-game. UI-5/6/7 fresh-chain review
  also still outstanding from the prior session.

---

## 4. Queue + open design calls

1. **Brian:** suite run + browser walk (above).
2. **Gundark Drops B–F** (`CRAFT.GUNDARK.dropB_F` in TODO): B weapons band · C armor + armorer
   trainer · D ordnance (**blocked on Demolitions call**) · E field gear · F espionage kit.
   Drop G (trainers/gating/contraband enforcement) last. Rubric mass-application is now
   test-audited (recompute pattern in test_craft_p2).
3. **Open §9 calls for Brian** (single letters fine): (a) Avail-band craftability cutoff;
   (b) Demolitions — new trained skill vs map to existing.
4. **`WEBIFY.commissary_vendor_mode`** (decision 8a, queued in tier_2) — can jump ahead of B–F.
5. **`CRAFT.HOOK.restraints` / `CRAFT.HOOK.force_detector`** design passes (long-pole; their items
   stay out of schematics.yaml until then).
6. Then the main roadmap: Lane C remainder + Lane F, Kamino, Drop-5 farming controls.

---

## 5. Session learnings worth keeping

- **The persistence no-op class:** any `save_character(id)` without field kwargs persists nothing.
  The AST-sweep test now makes the class unrepresentable — but the *lesson* is that "best-effort
  save" helpers must be audited for what they actually write.
- **Smokes earn their keep immediately:** E7 caught a real cross-cutting bug on its first run.
  The deferred-smoke pattern (defer for harness gaps, un-defer via direct DB seeding) works.
- **CHANGELOG str_replace slip (hit 3×):** inserting a new entry above an old header consumes that
  header unless the new_str RE-INCLUDES it. Always `grep -c "same-day drop"` after every insert.
- **Known-schematics attributes key is `schematics`**, not `known_schematics` (per
  `add_known_schematic`). Two test drafts seeded the wrong key this session.
- **Sandbox setup:** `pip install pytest --break-system-packages`; `npm install jsdom` in /tmp with
  `NODE_PATH=/tmp/node_modules`; jsdom harness requires setup_js to SET `result` (JSON-serialized),
  refs via `window.M3*`; test logs decode as **cp1252**.
- **`parser.medical_commands` imports clean in-sandbox** — catalog tests can be direct imports, no
  source-pin fallback needed there.
