# HANDOFF — Webify UI implementation (m3 client delta)

**SW_MUSH · Clone Wars era (~20 BBY) · WEG D6 R&E · 2026-06-07**
**For:** a fresh chat picking up the web-UI work. This doc is **self-contained** — read it top to bottom and you have everything to start. Pairs with the design source (below) and `claude_design_package_v2.md` (the delta list).

---

## 0. Mission

Implement the **Webify package** — a set of **small, surgical web-UI drops** that extend the existing m3 SPA with the genuinely-missing gameplay panels (inventory, shop, bounty board, region) plus two BUFFs (combat condition chips, objective/juice). Claude Design produced the visual design + an interactive prototype; this chat translates that design into **production vanilla JS**, one tested/packaged drop per surface.

**The single most important framing:** this is a **DELTA on a substantial existing client**, not a rebuild. Brian's words: *"buff the current UI, not recreate it."* The painted maps and tier renderers are **protected** (very painful to change). Every new surface is a side-panel or modal that **slots into the existing shell** using the existing tokens and idioms.

---

## 1. Project facts you must operate under

**Stack:** Python 3.14 / aiohttp / aiosqlite / SQLite / vanilla-JS SPA. Web-first (Telnet degrades gracefully, never a veto). Sole dev: **Brian (BTGlass80)**, who gives terse approvals ("A", "go", "roll up") and wants self-direction with minimal check-ins — flag only genuine design forks.

**Regression split (critical):** Brian runs the full pytest suite (~7,700+ tests) on his **Windows dev box — that is ground truth.** This sandbox runs **only targeted checks**: `python3 -m unittest` for the changed module + **AST validation** of touched Python. `pytest`, `aiosqlite`, `aiohttp`, `ruamel`, `pyflakes` are **not installed in sandbox** — their absence is an environment limit, **not a test failure**. For web work, jsdom tests live at `tests/spa/test_m3_<name>.py` via `spa_dom_harness.run_with_dom()`.

**Drop discipline (every drop):**
- **Phantom-delivery prevention is the chronic failure mode** → **grep HEAD at symbol level** before claiming anything exists or is absent. Every field/message you render must have a real producer; every command a button stages must be a real `parser/` verb. **Never invent a command.**
- **Extend, don't add** — route through existing systems/modules; don't build parallel infrastructure.
- **Atomic root-mirrored zips** for `Expand-Archive -DestinationPath . -Force` from the project root.
- **AST-validate** all touched Python before packaging.
- **CHANGELOG.md + TODO.json updated in the same drop** (a hygiene test enforces this).
- **Session-rollup zips supersede earlier same-session zips.**
- **B3 era-cleanness:** no Imperial/Rebel/Empire/TIE/stormtrooper/clone-trooper/X-wing/Death-Star in production/UI strings (comments, era-map keys, `replaces:` metadata are exempt). **Q1 canon:** canonical figures never as open-world NPCs (institutional/absence framing). Anchor-NPC labels from the canonical CW set only (Republic Sentinel, CIS Tactical Droid, Hutt Enforcer, Jedi Watchman, …) — never "Imperial Patrol."

**Architecture-of-record:** `sw_d6_mush_architecture_v51.md` (note: may lag HEAD — the real record is CHANGELOG.md newest-first + TODO.json `_notes`). `SCHEMA_VERSION = 42`.

---

## 2. The operating assumption — DELTA on the existing client

### 2.1 PROTECTED — do **not** rebuild or significantly rework (changes only on large + Brian-approved ROI)

1. **Painted substrate maps + tier renderers** — `m3_tier_{galaxy,system,planet,city,interior,wilderness}_body.js`, `m3_tier_registry.js::getTierRenderer`, `map-modal` (zoom/pan/LOD/legend), the substrate seeds. Territory/region data surfaces in **panels** and as **overlay markers on the existing map** (a data layer the renderer already anticipates) — **never a map rewrite**.
2. **Chrome + composition engine** — `m3_composition_engine.js`, the datapad/cockpit shell, the `client.html :root` tokens. New panels **slot into** this via the existing `.side-panel` pattern + a modal pattern.
3. **The built panels** — combat HUD, character sheet, Force palette, CP meter, cockpit, and the five side panels. We **extend in place**; we don't restart.

### 2.2 Already built (HEAD-verified) — the baseline you extend, do not duplicate

`static/client.html` + `static/spa/m3_*` already ship and wire:
- **Maps + tier nav** (painted, modal, LOD).
- **Combat HUD** (`m3_combat_theater`/`_inspector`): initiative, range bands, wound/stun track, **action buttons**, **dice transparency with margins** (`combat_resolution_event`/`combat_state`), `combatant-strip`, `target-panel`, `combat-decl-panel`.
- **Character sheet** (`m3_sheet`): attrs, **equipped weapon/armor** (`sheet_renderer.py`), wound ladder, FP, DSP, CP, Force, background editing.
- **Force palette** (`g-force-control/sense/alter`, `sheet-tab-force`).
- **CP milestone meter** (`g-cp-fill` + `g-cp-val`, keyed on `cp_progress`: `ticks_to_next`/`ticks_per_cp`/`pct`).
- **Vitals strip** (wound track with **delta/after** rendering, credits panel, recent rooms).
- **Room panel** (occupants/`present`, **exit-chips/exit-btns**).
- **Cockpit/space** (instrument, hyper, hull, shields, power-alloc, crew-assign, target-lock, `space_state`/`space_choices`+countdown, boarding).
- **Side panels:** Reputation (`rep_change`), Achievements (`achievement_unlocked`/`achievements_status`), Mail (`mail_status`), Places (`places_status`), City.
- **Live feedback events:** `credit_event`, `rep_change`, `rank_up`, `achievement_unlocked`, `news_event`.
- **RP stream** (`pose_event`/`chat`/`ooc`/`ambient_bark`) — **stays text, always.**
- **Master HUD pipeline:** `handleHudUpdate(data)` consuming name/species/template/faction/reputation/environment/wounds/credits/cp.

---

## 3. The work — the Webify delta (6 surfaces + 2 deferred)

Design source = the uploaded **`design_handoff_webify/`**: `README.md` (the spec) + `webify/*.jsx` (the React/Babel prototype) + `Webify Pack.html` (interactive — click JOBS/SHOP/INVENTORY/REGION/COMBAT to walk states). **Production is vanilla — translate the *design*, not the JSX.** Handoff mockups in `handoff_shots/*.png` (bounty, shop, shop_buy, inv, inv_delta, region_combat, droidshop, highlight). All surfaces draw **only** from `client.html :root` tokens (no new colors/fonts) and reuse existing idioms (`.side-panel`/`.side-panel-head`, `.room-sec-badge`, the segmented condition bar, the `.cri-wound-track` delta arrow `from → to ▲/▼`, `.exit-chip`).

Each surface below gives the **HEAD-verified** engine source + push message + the **real** staged commands + what stays text. **Re-confirm every symbol against your HEAD at symbol level before building (phantom discipline).**

### Build order (do them in this sequence)

**Drop UI-1 — scroll-on-move fix** *(XS, standalone, do first — the clunk Brian named)*
- Client-only. On the room-change event the stream appends the new room but doesn't re-anchor scroll, so the new room isn't pinned. Fix: scroll-to the injected room marker on the room-change event + a one-beat highlight sweep. Investigate the `client.html` stream handler + `m3_adapter.js` room-change path. jsdom test on anchor + highlight. No server change; Telnet unaffected.

**Drop UI-2 — Region panel** (`#6` · smallest NEW surface, contract pinned — proves the side-panel-slot pattern)
- Right-column **sibling of the room panel** (reuse `.side-panel` chrome). **No new engine logic — a wiring drop.**
- **Data (HEAD-verified):** `engine/territory_display.py::get_region_data_block(db, region_slug)` — signature confirmed; returns `{region_slug, region_name, planet, security:'lawless'|'contested'|'secured', description, ownership:{org_code,org_name,tier:'foothold'|'dominant'}|null, influence:[{org_code,org_name,score,tier}], resource_outlook:{best,worst,all}, active_contest:{challenger_org,defender_org,phase,secs_remaining,accumulation}|null}`. **TWEAK/Q3:** add an optional `viewer_org` param so the block can flag the viewer's influence row (the function already has internal highlight/viewer refs ~L379–433 — check whether they already cover this before adding).
- **Push:** `region_state` wrapping the block, on entering a wilderness region; hide in cities/ships/interiors. `GET /api/region/{slug}` optional.
- **Render:** security badge (secured=green/contested=amber/lawless=red); influence ladder with threshold ticks at **50 (foothold) / 100 (dominant)** on a 0–150 scale, viewer row boxed `◂ you`; resource chips (>1.05 green / <0.95 red, best glows); active-contest tug-of-war bar off `accumulation` + live countdown off `secs_remaining`.
- **Don't-invent rails:** only those three security values; only foothold/dominant/no_presence; Anchor-NPC labels from the canonical set; independent PCs see contest/outlook **disabled, not hidden**.
- **Stays text:** region description prose stays in the stream.

**Drop UI-3 — Combat condition chips** (`#2` · small BUFF on the built combat HUD)
- Add a chip rail to each combatant strip in `m3_combat_theater`/`m3_combat_inspector`.
- **Data (HEAD-verified, on each combatant in the combat push, `engine/combat.py` + `engine/buffs.py`):** `poison_stacks:[{source,damage,onset,ticks_left}]` (onset>0 = not yet biting), `restraint:{grappler_id, kind:'grapple'|'constriction'|'choke', hold_damage, source}|null`, `buffs:[{display_name,stacks,max_stacks,bonus}]`. Expose these on the combat HUD message.
- **Chips:** POISON (green ☣, `×N`, `onset N` or `<damage>·<ticks>t`, **pulses** when biting at onset 0); restraint (red — GRAPPLED/CONSTRICTED/CHOKED by `kind` + `hold_damage`, pulses); buff (amber, `display_name ×stacks`, `bonus`).
- **TWEAK/Q5 — restraint chip is DISPLAY-ONLY (NO `breakfree` button).** Confirmed at HEAD: ground break-free is **automatic** — a restrained combatant **cannot flee** and the break-free **opposed roll runs at round end** (`engine/combat.py::_resolve_flee`, "break-free roll runs at round end" ~L1861). There is **no ground `breakfree`/`struggle` verb** (`breakfree` exists only in `space_commands.py` for boarding). So the chip shows the restraint + `hold_damage` + the can't-flee state + a small "auto break-free at round end" note, and stages **no command**. *(Design fork, do NOT assume: if Brian wants player agency, a manual ground `breakfree` action is a small `combat.py` add — flag it, don't build it unprompted.)*
- **Stays text:** posing, called shots, all fight narrative.

**Drop UI-4 — Inventory panel + Shop card** (`#4`+`#3` · build together; shared item/value plumbing — the loot→equip→sell→buy loop)

*Inventory (`#4`, NEW-IN-SHELL, Brian's #1):* a "carried items" modal — left = equipped slots, right = carried list + an action footer previewing the **stat delta** of equipping the selected item.
- **Data (HEAD-verified):** `engine/items.py` `ItemInstance`; equipment is stored **one ItemInstance per slot** via `parse_equipment_json(raw)` / `serialize_equipment(item)` (**Q4 confirmed: one ItemInstance per slot — the design's assumption holds**; still confirm all equip/unequip call sites use the per-slot form before this drop). Carried list + container come from the inventory blob.
- **Q1 resolution — use a dedicated `inventory_state` push** (do NOT fold into the sheet): the modal needs carried + container + per-item stats/value that the sheet doesn't carry, and a separate push keeps the built sheet untouched. Shape: `{equipped:{weapon,armor}, carried:[{key,name,slot,quality,condition,max_condition,quantity,crafter,stats,value}], container:{name,cap_kg,used_kg}}`.
- **Render:** quality → 5-pip gauge (50 = 3 pips); condition → 3px bar (green>66/amber>33/red); `[Modified ×N]` green when `experiment_count>0`; crafter byline. **Delta preview** = each axis `from → to ▲/▼`, compared by **D6 pips** (`1D=3 pips`, so `+1D` beats `+2`) — use the engine's real pip totals.
- **Staged commands (real, never auto-send):** `equip <item>` · `unequip <slot>` · `drop <item>` · `give <item>=<who>` · `look <item>`.

*Shop card (`#3`, FILL the `handleShopState` stub):* one modal for both vendor kinds; **Sell tab first/default** (arrive with loot, offload, re-kit). `handleShopState` is currently an explicit stub ("Future enhancement: render an inline shop card") — render what it anticipates.
- **Trigger:** shops are **vendor-bound** — the card opens from a specific vendor **present in the room** (HERE list / vendor-droid object), NOT a global button. Server pushes `shop_state` scoped to that vendor; header reflects `shop_name` + `vendor_kind`.
- **Data:** `shop_state` push merging `engine/commissary.py::COMMISSARY_STOCK` (NPC) and `engine/vendor_droids.py` slots (player droid) into one shape keyed by `vendor_kind`: `{shop_name, vendor_id, vendor_kind:'npc'|'droid', faction, player_rank, sellback_pct (vendor_droids.PRICE_FLOOR_PCT), rep_modifier_pct, stock:[{key,name,slot,cost,min_rank,quality,stats}]}`. **Q2: one shape keyed by `vendor_kind` is fine.**
- **TWEAK/Q2 — staged commands branch by `vendor_kind` (NOT "buy <slot#> from <shop>"):**
  - SELL: **`sell <item>`** to a present NPC vendor (25–50% base value; `SellCommand`, key `"sell"`). Selling **resources to a player vendor droid** = **`sell <resource> to <shop>`** (routes to the droid buy-order system).
  - BUY: commissary → **`+commissary buy <key>`**; vendor droid → **`droid buy …`** (`builtin_commands.py`; confirm the exact arg form at HEAD).
  - **Fidelity note (HEAD):** NPCs **refuse well-made crafted items** (`engine/items.py::npc_refuses_buyback` — `crafter` set AND `quality ≥ 50`); the sell card should mark those rows "refused — list on a vendor droid."
- **Render:** sell rows show `worth <value>` + `+<round(value*sellback_pct)>` and a SELL chip; buy rows show struck `cost` → `round(cost*(1+rep_modifier_pct/100))` with a `▼/▲ N% rep` note; rows where `min_rank > player_rank` dimmed with a `RANK N` badge + disabled BUY.
- **Stays text:** haggling/flavor banter; the transaction mechanics are buttons.

**Drop UI-5 — Bounty / jobs board** (`#5`, NEW-IN-SHELL · completes the earn half)
- Modal board: tier filter row → contract cards sorted by reward.
- **Data (HEAD-verified):** `engine/bounty_board.py` `BountyContract.to_dict()` list + viewer `claimed_id`: `{id, tier:'extra'|'average'|'novice'|'veteran'|'superior', target_name, target_species, target_archetype, crime_description, posting_org, tip, reward, reward_alive_bonus, target_room_id, status, expires_at}`. Tier ramp = `PAY_RANGES`; tier hue mirrors `_TIER_COLORS` (white→yellow→bright-yellow→red→magenta).
- **Push:** `board_state`.
- **Card:** tier stud, target line, crime, `reward` + `+<alive_bonus> alive`, **live countdown** (red <30 min), expandable DETAILS (posting_org, id, tip). One claim at a time.
- **Staged commands (real):** `bountyclaim <id>` (ACCEPT) · `bountytrack` (shown once claimed). On claim: set the objective line (UI-6), fire the toast, drop a reward pose row. Note `chain_bounty_id` (the tutorial-chain dispatcher advances on claim — surface tutorial contracts identically, maybe with a small CHAIN tag).

**Drop UI-6 — Objective line + reward juice** (`#9` · BUFF on vitals strip; the connective layer, once 1–5 give it something to say)
- **Objective line:** `hud_update` gains an `objective` string; render as a boxed line atop the vitals card; claiming a bounty / accepting a job updates it.
- **Juice (moderate — all on existing surfaces, opacity/transform/color only, ≤16 ms/frame; no new primitives):** credit **count-up** on `credit_event` (cubic ease ~700 ms); **reward toast** (top-center, tier/tone hue, ~2.6 s) on sale/purchase/bounty-claim; **condition-chip pulse** on active poison/restraint; delta-arrow reveal on inventory select. These layer onto the existing `credit_event`/`achievement_unlocked` feeds.

### Deferred (by design — not in this package)
- **`#7` Crafting/harvest panel** — **gated on `T2.CRAFT.integration_design_pass`** (the crafting holistic re-design Brian queued; design the loop before the panel).
- **`#8` Onboarding overlay** — build **after** UI-1…UI-6 ship, so the coach-marks point at the real, working loop. Coach-mark layer **over the existing client** (not a new sandbox); `onboarding_state` + the `F.8.c.2.b` completion hooks (11 `completion.type` → `tutorial_chains.advance_step`).

---

## 4. The two tweaks, restated (so they're not missed)

1. **Combat restraint chip = display-only.** Ground break-free is **automatic at round-end**; no `breakfree` command exists for ground combat. Do **not** stage a `breakfree` button. (Manual-agency variant = a flagged design fork, not a default.)
2. **Shop buy/sell commands branch by `vendor_kind`.** Real verbs: `sell <item>` (NPC vendor) / `sell <resource> to <shop>` (droid buy-order); `+commissary buy <key>` (commissary) / `droid buy …` (vendor droid). **Not** "buy <slot#> from <shop>." And reflect NPC craft-refusal (`npc_refuses_buyback`).

All other Claude Design open questions are resolved in §3 (Q1 separate `inventory_state`; Q2 one `shop_state` keyed by `vendor_kind` with branched commands; Q3 add optional `viewer_org`; Q4 one-ItemInstance-per-slot confirmed; Q5 break-free automatic).

---

## 5. Per-drop checklist

For each drop:
1. **Pre-flight:** grep HEAD at symbol level for every engine symbol, message field, and command verb the drop touches (confirm they still exist as §3 states). Check YAML/JSON validity of anything you'll edit.
2. **Build:** extend the named existing `m3_*` module or add a new `m3_<name>.js` that slots into the shell via the existing `.side-panel`/modal pattern; draw only from `:root` tokens. Add the engine push/REST + branch the staged commands per §4. **Preserve the Telnet text path beside any new structured emission** (add-beside, don't replace).
3. **Collect protocol additions** into **`web_client_vision_and_protocol_v1_4`** (each new message pinned as a public ABI).
4. **Test:** jsdom `tests/spa/test_m3_<name>.py` (structure/attrs/text from the push); `python3 -m unittest` for any changed engine module; **AST-validate** touched Python. (Brian runs full pytest on Windows.)
5. **Hygiene:** update **CHANGELOG.md** (newest-first) + **TODO.json** in the same drop.
6. **Package:** atomic **root-mirrored** zip (`Expand-Archive -DestinationPath . -Force` from project root); round-trip verify from a clean extract; `present_files` with a succinct summary. Session-rollup zips supersede earlier same-session zips.

---

## 6. Key files & references

| Need | Where |
|---|---|
| Live client + tokens (`:root`) + the `handleShopState` stub + `handleHudUpdate` | `static/client.html` |
| SPA conventions / `svgEl` / jsdom harness | `static/spa/README.md` |
| Combat HUD (extend for chips) | `static/spa/m3_combat_theater.js`, `m3_combat_inspector.js` |
| Sheet (equipped already here) | `static/spa/m3_sheet.js`; `engine/sheet_renderer.py` |
| Room-change path (scroll fix) | `static/client.html` stream handler + `static/spa/m3_adapter.js` |
| Region data contract | `engine/territory_display.py::get_region_data_block` |
| Inventory/equipment | `engine/items.py` (`ItemInstance`, `parse_equipment_json`, `serialize_equipment`, `npc_refuses_buyback`) |
| Shop sources | `engine/commissary.py` (`COMMISSARY_STOCK`), `engine/vendor_droids.py` (`PRICE_FLOOR_PCT`, `buy_from`); commands in `parser/builtin_commands.py` (`SellCommand`, `droid buy`), `parser/commissary_commands.py` |
| Bounty board | `engine/bounty_board.py` (`BountyContract.to_dict`, `PAY_RANGES`, `_TIER_COLORS`, `chain_bounty_id` via `engine/chain_missions.py`) |
| Combat condition state | `engine/combat.py` (`poison_stacks`, `restraint`, `_resolve_flee`), `engine/buffs.py` |
| The delta framing + protected assets | `claude_design_package_v2.md` |
| Full surface inventory (context) | `claude_design_complete_surface_inventory_v1.md` |
| Current-client audit + design law | `claude_design_package_readiness_v1.md` |
| **Design source (the prototype to translate)** | uploaded `design_handoff_webify/` (`README.md`, `webify/*.jsx`, `Webify Pack.html`) + `handoff_shots/*.png` |

---

## 7. First action

Re-extract the working tree from Brian's upload, then **Drop UI-1 (scroll-on-move fix)** — XS, standalone, touches no protected asset, fixes the clunk Brian named, and proves the extend-in-place loop. Then UI-2 (region) → UI-3 (combat chips) → UI-4 (inventory + shop) → UI-5 (bounty board) → UI-6 (objective + juice). Then UI-7 onboarding (over the now-real loop) and UI-8 crafting (after its design pass).

*Operating assumption for every drop: extend the built client, protect the maps. Translate the design, not the JSX. Never invent a command.*
