# HANDOFF — Webify UI drops (UI-1 → UI-4b) + equipment-instance untangle

**Date:** 2026-06-07 · **Project:** SW_MUSH (Star Wars D6 R&E, Clone Wars ~20 BBY)
**This handoff supersedes:** `HANDOFF_webify_ui_implementation_2026-06-07.md` (the design/plan handoff). That doc is still the authority for the *design intent* of the remaining drops; this one records what is actually shipped and what's next.

---

## 0. TL;DR

Five drops shipped and verified this session, packaged as one cumulative atomic rollup:

**APPLY THIS:** `SW_MUSH_webify_UI1_thru_UI4b_rollup_2026-06-07.zip`
From the Windows project root: `Expand-Archive -DestinationPath . -Force`. Then run the full suite (`run_all_tests.bat`). The zip is root-mirrored; 26 files (15 modified + 11 new). All earlier same-session zips are **superseded** — ignore `...ui1_ui2...`, `...UI1_UI2_UI3...`, `...untangle_rollup...`, `...UI1_thru_UI4a...`.

Shipped: **UI-1** scroll-on-move · **UI-2** region panel · **UI-3** combat condition chips · **equipment-instance untangle** (foundational refactor) · **UI-4a** inventory panel · **UI-4b** shop card.

**Next in build order:** UI-5 bounty board → UI-6 objective/juice → UI-7 onboarding → UI-8 crafting. **One decision is waiting on Brian:** the commissary↔vendor-droid shop merge (`UI-4b.commissary_vendor_merge`, in `design_calls_pending_brian`).

---

## 1. Environment & standing disciplines (read before touching anything)

**Working tree (sandbox):** `/home/claude/head` (Brian's HEAD, extracted from his upload zip). Does **not** persist between chats. Clean reference for diffing: `/tmp/ref`. Round-trip verify dir: `/tmp/verify`. Outputs: `/mnt/user-data/outputs/`. Design docs + handoffs: `/mnt/project/`.

**Sandbox tooling:** `pytest` works; `jsdom` is installed at `/tmp/node_modules` (use `NODE_PATH=/tmp/node_modules` for SPA tests). **Absent (NOT failures):** `aiohttp`, `aiosqlite`, `ruamel`, `pyflakes`. DB/server-integration tests fail at *import* (before any edited code runs) — that is the environment, not a regression. **Brian's Windows box runs the full ~7,700-test pytest — that is ground truth.** Sandbox = targeted `python3 -m pytest` + AST validation only.

**`tests/spa/` is slow under jsdom** (the map/composition tests). Run *targeted* SPA tests with `timeout 110`; never the whole dir at once.

**Disciplines enforced every drop (do not relax):**
- **Phantom-delivery prevention** — grep HEAD at the symbol level before claiming anything exists/absent/delivered. Trust the filesystem over handoff prose and memory.
- **"Extend, don't add"** — prefer extending existing producers/symbols over new ones.
- **Atomic root-mirrored zips** for `Expand-Archive -DestinationPath . -Force` (no `head/` prefix; root-relative paths).
- **AST-validate** every touched Python module; **YAML-validate** data files.
- **CHANGELOG.md + TODO.json updated in the same drop as code** (enforced by `tests/test_todo_and_changelog_hygiene.py` + `tests/test_encoding_hygiene.py`).
- **Session-rollup zips supersede** earlier same-session zips; each new rollup includes ALL prior drops.
- **B3 era-cleanness** — no Imperial/Rebel/Empire/TIE in prod/UI strings (comments + era-map keys exempt).
- **Token-only CSS** — resolve from `client.html` `:root` variables; no new colours.
- **Never render a field without a real producer; never invent a parser command/verb; never auto-send a fabricated command.** Faucets and sinks land together.
- Brian communicates **tersely** ("Continue", "B, go", "UI-5"). Self-direct; flag only genuine design forks; log forks in `design_calls_pending_brian` rather than guessing.

**Packaging procedure (proven):** compute authoritative delta with `diff -rq /tmp/ref head | grep -vE "__pycache__|\.pyc|\.pytest_cache|node_modules"`; build zip from an explicit relative-path file list (`cd head && zip -X "$OUT" $FILES`); verify each path exists first; round-trip by `cp -r /tmp/ref /tmp/verify && cd /tmp/verify && unzip -o`, AST-check, run targeted tests with `NODE_PATH=/tmp/node_modules`; then `present_files`. Edit TODO.json via `json.load`/`json.dump(indent=2, ensure_ascii=False)` + trailing newline + re-validate.

---

## 2. What shipped this session (per drop)

### UI-1 — scroll-on-move (client-only)
`static/client.html`: `renderEventToActiveLog` special-cases `room-enter` to **re-anchor the stream to the new-room banner regardless of scroll position** (the old clunk: while scrolled up in history, a move silently bumped the unread pill and you never "landed"). `anchorRoomEnterRow()` + rAF re-pin + a one-beat `@keyframes m3-room-sweep` highlight (token `--accent`). Telnet untouched. Test `tests/spa/test_m3_scroll_on_move.py` (3).

### UI-2 — Region-control panel (NEW side panel)
`static/spa/m3_region.js` (`window.M3Region`) renders the `region_state` push: security badge, ownership, a **0–150 influence ladder** with 50 (foothold) / 100 (dominant) ticks and the viewer's row boxed `◂ you`, weekly resource chips, an active-contest tug-of-war + live countdown. Server push `server/session.py::_hud_sidebar_region` (gated on `room["wilderness_region_id"]`). Producer `engine/territory_display.py::get_region_data_block` extended additively (kw-only `viewer_org_code`). Panel hides on every room change and re-shows iff still in a region. Test `tests/spa/test_m3_region.py` (5). **Note:** `M3Region.render` starts a 1s countdown `setInterval` — tests call `M3Region.stop()` before returning so Node drains.

### UI-3 — Combat condition chips
`engine/combat.py::to_hud_dict` adds normalized `poison_stacks` + `restraint` per combatant to the existing `combat_state` push. `static/spa/m3_combat_inspector.js::buildConditionChips(c,isYou)` renders POISON / RESTRAINT chips (pulse while biting/held); returns `null` for non-creature fights → zero DOM in ordinary combat. **Restraint chip is DISPLAY-ONLY** (no `breakfree` verb — ground break-free is automatic at round-end). **Buff chip DEFERRED** (no producer at HEAD — buffs aren't wired into combat). Test `tests/spa/test_m3_combat_chips.py` (4).

### Equipment-instance untangle (foundational — see §3)
Canonicalized the corrupting `equipment` JSON shapes. **This is the prerequisite UI-4a was built on. Read §3.**

### UI-4a — Inventory panel (NEW modal)
New `inventory_state` push assembled by `engine/items.py::build_inventory_state(equipment_raw, carried, registry=None)` — equipped read via the untangle's `read_equipment`; name/slot/value(`WeaponData.cost`)/stats resolved from the weapon registry by key; condition/quality/crafter/experiment_count from the `ItemInstance` (equipped) or carried dict. `parser/builtin_commands.py::InventoryCommand` pushes it (WS-only; Telnet keeps the text dump). Client `static/spa/m3_inventory.js` (`window.M3Inventory`): equipped cards (left) + carried list (right) + **stat-DELTA footer** comparing the selected carried item vs the equipped same-slot item by **D6 pips (1D=3)** computed client-side from dice strings (a relative base like `STR+1D` → no arrow, never misleading). Quality→5-pip gauge (50≈3), condition→3px green/amber/red bar, `[Modified ×N]`, crafter byline. **Real verbs only, branched by slot:** weapon `equip <name>`/`unequip`; armor `wear <name>`/`remove armor`; any `look <name>`. **`drop`/`give` do not exist and are never offered.** State changes are STAGED into the input, never auto-sent. **No container/weight bar** (no encumbrance model at HEAD). Opens via `inventory`/`inv`/`i` (incl. a new **INV** quick-action button). Tests `tests/test_inventory_state.py` (6) + `tests/spa/test_m3_inventory.py` (3).

### UI-4b — Shop card (NEW modal; client-only — renders an existing push)
`parser/shop_commands.py` **already emitted** `shop_state` (modes `browse` + `dashboard`) for vendor-droid browse/management, but `handleShopState` was an empty stub — web players saw nothing. `static/spa/m3_shop.js` (`window.M3Shop`) renders both modes into the shared `.inv-modal` chrome. **browse** = room vendor droids (picker when >1; focus follows server `focused_id` or a client tap) → the focused droid's stock rows with a **BUY** action staging the real `buy <slot> from <shop name>` (the `buy` command routes `… from …` to `_handle_buy_from_droid`); staged, never auto-sent. **dashboard** = owner view: total escrow, per-droid escrow/placed/stock + recent sales — **display-only** (management stays in the text `+shop` flow). Haggling stays text. **No engine change.** Tests `tests/spa/test_m3_shop.py` (3). See §4 for the flagged commissary fork.

---

## 3. The equipment-instance untangle (foundational — internalize this)

**The problem:** the character `equipment` column had **three mutually-corrupting on-disk shapes** all writing to the same column:
1. flat key strings — `{"weapon":"blaster_pistol","armor":"…"}`
2. top-level single instance (weapon-only, from old EquipCommand) — `{"key":"…","condition":…}`
3. per-slot `ItemInstance` (canonical) — `{"weapon":{…},"armor":{…}}`

These fought each other: `equip` wrote shape 2 and **clobbered armor**; `unequip` wrote `"{}"` and **wiped armor**; `wear` wrote shape 1; the sheet read only shape 2; the HUD read a `name` field `ItemInstance` never serialized (so the HUD weapon name was **always blank**); and shape 2 **silently dropped the equipped weapon on reload** (`from_db_dict`'s `equip.get("weapon")` → "").

**The fix (canonical = per-slot ItemInstance, shape 3):** three helpers in `engine/items.py`:
- `read_equipment(raw)` → `{"weapon": ItemInstance|None, "armor": ItemInstance|None}` — tolerant of all three shapes + empty/list/None, exception-tolerant (never raises).
- `equipment_keys(raw)` → `{"weapon": str, "armor": str}` — key-only drop-in for display/lookup sites.
- `write_equipment(weapon=None, armor=None)` → canonical JSON, omits empty slots, round-trips through `read_equipment`.
(`parse_equipment_json`/`serialize_equipment` kept for back-compat.)

**Readers migrated (now tolerant of every shape):** `engine/character.py::from_db_dict` (fixes the reload bug), `engine/sheet_renderer.py` (×3), `engine/locks.py` (also fixes a latent `.lower()` crash on a shape-3 dict), `server/session.py::_hud_equipped_weapon` (now resolves the display NAME from the registry), `parser/builtin_commands.py::InventoryCommand`.

**Writers canonicalized + slot-preserving:** `equip`/`unequip`/`wear`/`remove armor`/`repair` (`builtin_commands.py`), weapon-experiment success + failure (`crafting_commands.py`), the ship-vendor weapon buy (`space_commands.py`). Every writer now reads both slots and **preserves the other slot**. Also **fixed a pre-existing `new_credits` NameError** in `RepairCommand`'s success line (would crash every successful repair).

**KNOWN LIMITATION (logged, deferred — `TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES`):** the `Character` object still holds `equipped_weapon`/`worn_armor` as **bare key strings**, so `Character.to_dict()` can't carry instance condition/quality. This is **safe today**: `to_dict()` is NOT an equipment-persistence path — every durable write goes through `save_character(equipment=…)`, and the tolerant readers handle `to_dict`'s flat-key output. The full fix (Character holds `ItemInstance`s) ripples through combat/sheet/everywhere `equipped_weapon` is used as a key — it's a separate larger pass, and it folds toward the T3.20 reload-invariant work.

**Rule going forward:** read equipment via `read_equipment`/`equipment_keys`; write via `write_equipment` (preserving the untouched slot). Never hand-roll `json.loads(char["equipment"]).get("weapon")` again.

Tests: `tests/test_equipment_untangle.py` (15) — cross-shape read normalization, key-only view, write→read round-trip + idempotence, slot preservation (incl. unequip-keeps-armor), and a `Character.from_db_dict` **reload round-trip** for all shapes.

---

## 4. ⚑ Decision waiting on Brian — commissary↔vendor-droid shop merge

Logged as `UI-4b.commissary_vendor_merge` in `TODO.json::design_calls_pending_brian`.

UI-4b shipped the shop card rendering the **existing** `shop_state` (in-room player vendor droids; BUY = `buy <slot> from <shop>`). The original handoff sketched ONE shape keyed by `vendor_kind` (`'npc'|'droid'`) folding in the **commissary** — but the commissary is a **separate system**: faction requisition, rank-gated stock, `+commissary buy <key>`, **no in-room vendor** (`engine/commissary.py`, `COMMISSARY_STOCK` keyed by faction_code). Different trigger, different model. Not built speculatively.

**Decision needed:** (1) what opens the commissary card — a faction quartermaster NPC in HQ, the `+commissary` command, or a unified shop trigger? (2) one merged card (`mode:'vendor'` on `shop_state`) or a separate `commissary_state`? (3) confirm the buy/sell verbs to stage: `+commissary buy <key>` (requisition), `sell <item>` (NPC buyback — must reflect `npc_refuses_buyback`: crafted AND quality ≥ `CRAFTED_NPC_BUYBACK_MAX_QUALITY`=50 → "refused — list on a vendor droid"), `sell <resource> to <shop>` (to a droid). Rank/rep gating + sellback modifiers render once decided.

**My recommendation:** add a third `shop_state` `mode:'vendor'` into the same message so `m3_shop.js` branches by mode; trigger from a faction quartermaster NPC present in HQ rooms; dim rows where `min_rank > player_rank`.

---

## 5. Protocol ABIs (pinned in `web_client_vision_and_protocol_v1_4.md`)

**SHIPPED / pinned (public ABIs — don't break):**
- `region_state` (UI-2)
- `combat_state` per-combatant condition fields `poison_stacks` + `restraint` (UI-3)
- `inventory_state` (UI-4a) — `{ equipped:{weapon|null, armor|null}, carried:[…] }`; **no container field**; `<item> = {key,name,slot,quality,condition,max_condition,quantity,crafter,experiment_count,stats{…},value}`.
- `shop_state` (UI-4b) — modes `browse` `{focused_id, droids:[{id,name,desc,tier,placed,escrow,item_count,inventory:[{slot,name,price,qty,quality,crafter}]}]}` and `dashboard` `{owner_name,total_escrow,droids:[{…,sales:[{ts,item,qty,net,buyer}]}]}`.

**RESERVED (names claimed; pin their final shape when shipped):**
- `board_state` (UI-5) — bounty board: `BountyContract.to_dict()` list + viewer `claimed_id`.
- `hud_update.objective` (UI-6) — an `objective` string on the existing `hud_update`; boxed line atop the vitals card.
- `buffs[]` on `combat_state` (UI-3 tail) — the amber buff chip, gated on a buff↔combat-push integration (no producer yet).
- a future `mode:'vendor'`/`vendor_kind` on `shop_state` for the commissary (pending §4).

---

## 6. Next steps (build order)

1. **UI-5 — Bounty board.** Producer: confirm `BountyContract.to_dict()` shape at HEAD + how the board/claims are queried; emit `board_state` (list + viewer `claimed_id`). Client: `m3_board.js` modal/panel. Stage only real claim/abandon verbs (confirm them at HEAD first). Add to the wireup test's expected load order + bump the count.
2. **UI-6 — Objective/juice.** Add an `objective` string to the existing `hud_update`; render a boxed line atop the vitals card. Find the objective producer (accepted-mission/tutorial objective) at HEAD before wiring.
3. **UI-7 — onboarding** (after the loop ships) and **UI-8 — crafting** (after `T2.CRAFT`).
4. **Commissary fork (§4)** — whenever Brian decides; a `mode:'vendor'` slots into `m3_shop.js`.

Each future drop: fold into a fresh cumulative rollup that includes ALL prior Webify work; pin new protocol messages in `web_client_vision_and_protocol_v1_4.md`; update CHANGELOG + TODO same drop; round-trip verify from clean `/tmp/ref`.

---

## 7. Key file references (the map)

**Client (`static/client.html`, ~11k lines):** `:root` tokens lines ~14–58 (`--accent`/`--accent-bright`/`--accent-dim`/`--self`/`--warn`/`--text`/`--text-dim`/`--screen`/`--screen-dim`/`--font-mono`/`--font-display`). Quick-action row `id="qa-row"` (~4109; LOOK/POSE/SAY/**INV** buttons; wired by `wireQuickActions` ~5375 — `data-action="send"`→`sendCmd`, `"stage"`→`stageCommand`). SPA `<script>` tags ~4430–4450 (order pinned by `tests/spa/test_client_wireup_42a.py::EXPECTED_SPA_LOAD_ORDER` — **add new m3_*.js there + bump the "N expected" comment**). WS dispatch `switch` ~11099–11110 (`region_state`/`combat_state`/`shop_state`/`inventory_state`/`sheet_data` cases). Input staging: `activeInputEl()` ~5240, `stageCommand` ~5247, `sendCmd` ~5301, `stageRawCommand` (added UI-4a). Inventory modal: markup before `boot-overlay`; handlers `handleInventoryState`/`openInventoryModal`/`closeInventoryModal`/`stageFromInventory`. Shop modal: shares `.inv-modal` chrome (ids `shop-modal*`); `handleShopState`/`openShopModal`/`closeShopModal`/`stageFromShop`. `inv-*` + `shop-*` CSS after the `.sheet-panel` rules.

**SPA modules (`static/spa/`):** `m3_region.js`(new UI-2), `m3_inventory.js`(new UI-4a), `m3_shop.js`(new UI-4b), `m3_combat_inspector.js`(UI-3). Conventions: IIFE + `'use strict'` + local `el()` helper + `window.M3X` export. Harness `tests/spa/spa_dom_harness.py::run_with_dom(script_paths, setup_js)` — loads scripts under jsdom, runs `setup_js`, returns the JS var `result` parsed as JSON.

**Engine (`engine/`):** `items.py` — `ItemInstance` (fields key/condition/max_condition/quality/crafter/experiment_count/breakdown_dice/experiment_log/effective_mods; props `.is_armor`/`.is_broken`/`.is_modified`; `to_dict`/`from_dict`/`new_from_vendor`); helpers `read_equipment`/`equipment_keys`/`write_equipment`/`build_inventory_state`; `npc_refuses_buyback`, `CRAFTED_NPC_BUYBACK_MAX_QUALITY`=50. `weapons.py` — `WeaponData` (key/name/weapon_type/skill/damage/scale/cost/ammo/ranges/protection_energy/protection_physical/dexterity_penalty/…; `.is_ranged`=len(ranges)==4, `.is_armor`=weapon_type=='armor'); `get_weapon_registry()` → `.get(key)`/`.find_by_name()`. `combat.py::to_hud_dict`. `territory_display.py::get_region_data_block`. `character.py::from_db_dict` (~654; `to_dict` ~555). `commissary.py` (`COMMISSARY_STOCK`, `commissary_stock_for`, `purchase_commissary`). `vendor_droids.py` (`PRICE_FLOOR_PCT`=0.5, `sell_to_droid`).

**Parser (`parser/`):** `builtin_commands.py` — `InventoryCommand`, `Equip`/`Unequip`/`Wear`/`RemoveArmor`/`RepairCommand`. `shop_commands.py` — `_droid_to_dict`, `_send_shop_dashboard`/`_send_shop_browse` (the `shop_state` producers), `BrowseCommand`, `ShopCommand` (`shop buy droid <tier>`, etc.). `space_commands.py` — `buy` command (routes `buy <X> from <Y>` → `_handle_buy_from_droid` ~5613). `crafting_commands.py` — experiment success/failure writers.

**Server (`server/session.py`):** `send_hud_update`, `_hud_sidebar_region`, `_hud_equipped_weapon`, `send_json`, `Protocol` enum (WS push pattern: `from server.session import Protocol; if ctx.session.protocol == Protocol.WEBSOCKET:`).

**DB (`db/database.py`):** `get_inventory(char_id)` → **list** of item dicts; `_get_inventory_raw` → `{"items":[],"resources":[]}`; **`SCHEMA_VERSION` is 43** (the arch doc `sw_d6_mush_architecture_v51.md` still says 42 — flag this drift; CHANGELOG + TODO are authoritative until the v52 reconciliation).

**Trackers:** `CHANGELOG.md` + `TODO.json` at repo root (authoritative). `design_calls_pending_brian` / `design_calls_resolved_recent` / `tech_debt` arrays in TODO.json.

---

## 8. Verification status (this session)

Round-trip verified the final rollup from a clean `/tmp/ref` + applied zip: AST-clean on all 8 touched Python modules; **47 targeted tests pass** (inventory_state 6, untangle 15, hygiene 9, encoding 2, shop jsdom 3, inventory jsdom 3, wireup 9). The 4 core Webify SPA tests (scroll 3, region 5, combat-chips 4) verified green earlier in the session alongside the new modules. **DB/server tests are not runnable in-sandbox** (aiohttp/aiosqlite absent) — run them on the Windows box.

**Known pre-existing failure, NOT from this session (flag for the Windows box):** `tests/spa/test_m3_substrate_hybrid.py::test_tier1abody_with_substrate_emits_image_and_skips_procedural` fails `10 != 9` in the untouched `/tmp/ref` baseline.

---

## 9. One-liner to resume in a fresh chat

> "Apply `SW_MUSH_webify_UI1_thru_UI4b_rollup_2026-06-07.zip`. Webify UI-1→UI-4b + the equipment untangle are shipped (see this handoff §2–§3). Continue with UI-5 (bounty board) — or settle the commissary shop-merge fork (§4) first. Honor the disciplines in §1; grep HEAD before claiming anything; package a cumulative rollup; verify from `/tmp/ref`."
