# Web client protocol ledger — v1.4

**SW_MUSH | Webify package · structured WS message ABIs**
**Status:** living ledger; one entry per push message the SPA renders.
**Companions:** `web_client_vision_and_protocol_v1_3.md` (vision/design, in
project knowledge), `CHANGELOG.md` (drop ledger), `TODO.json` (forward queue).

> **Provenance note (2026-06-10):** the 2026-06-07 Webify rollup's CHANGELOG
> entry lists this file as delivered, but the zip never carried it — a
> phantom-delivery caught by the standing grep-HEAD discipline on session
> pickup. Reconstructed in the UI-5/UI-6 drop from the handoff §5 pinned
> shapes, then extended with the newly shipped messages. Content below is
> authoritative as of 2026-06-10.

---

## 1. SHIPPED — public ABIs (do not break)

### 1.1 `region_state` (Webify UI-2, 2026-06-07)

Pushed by `server/session.py::_hud_sidebar_region` on HUD update, gated on
`room["wilderness_region_id"]`. Producer
`engine/territory_display.py::get_region_data_block(viewer_org_code=…)`.

```
{ region_slug, region_name, planet,
  security: 'lawless'|'contested'|'secured',
  description,
  ownership: { org_code, org_name, tier: 'foothold'|'dominant' } | null,
  influence: [ { org_code, org_name, score, tier, is_viewer } ],   # sorted desc
  viewer_org: str|null,
  resource_outlook: { best:{type,multiplier}, worst:{…}, all:{type:mult} },
  active_contest: { challenger_org, defender_org, phase,
                    secs_remaining, accumulation:{org:score} } | null }
```

Renderer `static/spa/m3_region.js` (`window.M3Region`; `.stop()` drains the
contest countdown interval).

### 1.2 `combat_state` per-combatant condition fields (Webify UI-3, 2026-06-07)

`engine/combat.py::to_hud_dict` adds to EACH combatant in the existing push:

```
poison_stacks: [ { source, damage, onset, ticks_left } ]   # onset>0 = not yet biting
restraint:     { grappler_id, kind:'grapple'|'constriction'|'choke',
                 hold_damage, source } | null
```

Renderer `m3_combat_inspector.js::buildConditionChips(c, isYou)`. Restraint
chip is **display-only** — ground break-free is automatic at round end
(`_resolve_flee`); there is no ground `breakfree` verb.

### 1.3 `inventory_state` (Webify UI-4a, 2026-06-07)

Pushed by `parser/builtin_commands.py::InventoryCommand` (WS only; Telnet
keeps the text dump). Producer `engine/items.py::build_inventory_state`.

```
{ equipped: { weapon: <item>|null, armor: <item>|null },
  carried:  [ <item> ] }                       # NO container/weight field
<item> = { key, name, slot, quality, condition, max_condition, quantity,
           crafter, experiment_count, stats:{…}, value }
```

Renderer `static/spa/m3_inventory.js`. Staged verbs branch by slot: weapon
`equip <name>`/`unequip`; armor `wear <name>`/`remove armor`; any
`look <name>`. `drop`/`give` do not exist and are never offered.

### 1.4 `shop_state` (Webify UI-4b, 2026-06-07)

Already emitted by `parser/shop_commands.py` (`_send_shop_browse` /
`_send_shop_dashboard`); UI-4b is the client render.

```
mode 'browse':    { focused_id, droids: [ { id, name, desc, tier, placed,
                    escrow, item_count,
                    inventory: [ { slot, name, price, qty, quality, crafter } ] } ] }
mode 'dashboard': { owner_name, total_escrow,
                    droids: [ { …, sales: [ { ts, item, qty, net, buyer } ] } ] }
```

Renderer `static/spa/m3_shop.js`. BUY stages the real
`buy <slot> from <shop name>`; dashboard is display-only (management stays in
the text `+shop` flow); haggling stays text.

### 1.5 `board_state` (Webify UI-5, 2026-06-10) — NEW

Pushed by `parser/bounty_commands.py::BountiesCommand` (the `bounties` verb;
WS only — Telnet keeps `format_bounty_board`). Producer
`engine/bounty_board.py::build_board_state(posted, claimed, now=None)`. The
pushed list is the SAME chain-visibility-filtered list the Telnet path
renders (`engine/chain_missions.filter_visible_bounties`), so tutorial-tagged
contracts never leak.

```
{ contracts: [ BountyContract.to_dict()
               + { expires_in_secs: int|null } ],   # server-derived, clamped ≥0
  claimed_id: str|null }
```

`BountyContract.to_dict()` carries: `id, tier('extra'|'average'|'novice'|
'veteran'|'superior'), target_name, target_species, target_archetype,
crime_description, posting_org, tip, reward, reward_alive_bonus,
target_npc_id, target_room_id, status, claimed_by, posted_at, claimed_at,
expires_at, collected_at, chain_bounty_id`.

The viewer's CLAIMED contract (if any) is prepended and sets `claimed_id`;
it is deduped if also present in the posted list. `expires_in_secs` is
derived server-side so the client never trusts its own clock against the
`expires_at` epoch.

Renderer `static/spa/m3_board.js` (`window.M3Board`; `.stop()` drains the
1s countdown interval — call on modal close). Staged verbs (real only):
`bountyclaim <id>` (ACCEPT; suppressed while the viewer holds a claim — one
claim at a time) and `bountytrack` (TRACK TARGET, the claimed card). There
is no abandon verb at HEAD, so none is offered. Tier hue ramp is token-only
(extra `--text-dim` → average `--text` → novice `--accent` → veteran
`--accent-bright` → superior `--warn`). `chain_bounty_id` ≠ "" renders a
small CHAIN tag. This message carries the NPC contract board only —
Dark-Side Notoriety (prestige) is a separate surface on the PC bounty board.

### 1.6 `hud_update.objective` (Webify UI-6, 2026-06-10) — NEW

A string field on the EXISTING `hud_update` push. `""` (or absent) = hide.
Derived in `server/session.py::_hud_active_jobs` →
`_objective_line(jobs)` from the first (highest-priority) active job:

```
priority: tutorial-chain step → mission → bounty → smuggle → spacer quest
formats:  tutorial  → step.objective
          bounty    → "Hunt <target> — <reward:,> cr bounty"
          mission   → "<label> — <objective>"
          smuggle   → "<label> — <reward:,> cr"
          quest     → objective text
truncation: 96 chars, "…"
```

The tutorial-chain entry is new in `active_jobs`
(`{type:'tutorial', label: step.title, objective: step.objective}`, corpus
via `engine.chain_events._get_corpus`). The bounty entry's matcher was
FIXED in the same drop (`claimed_by`/status `"claimed"` — the old
`accepted_by`/`"accepted"` check matched no contract ever).

Renderer: boxed line atop the vitals card (`#g-objective` in
`client.html::handleHudUpdate`).

### 1.7 `credit_event` (pre-existing; UI-6 juice riders, 2026-06-10)

Producer unchanged (`server/session.py::_hud_send_credit_event`):

```
{ type:'credit_event', credits:int, delta:int }
```

UI-6 adds two client-side riders in `handleCreditEvent` (no ABI change):
a ~700ms cubic-ease count-up on `#g-credits` animating from
`credits − delta` → `credits` (order-independent of the `hud_update`
render), and a 2.6s top-center reward toast (`#reward-toast`,
`+N cr` / `−N cr`, `--self`/`--warn` toned). The pre-existing
`data.reason` fallback (`'tx'`) is retained as-is; the producer does not
emit a reason field — plumbing ledger tags through is a separate,
unscheduled change.

---

### 1.8 `onboarding_state` (Webify UI-7, 2026-06-10) — NEW

Pushed by `server/session.py::_hud_sidebar_onboarding` on every HUD tick
while the character's tutorial chain is active (WS-only; sidebar-panel
section). Producer `engine/chain_events.py::build_onboarding_state(char)`,
layered on the same cached corpus as `get_active_step_info` (which gained
ADDITIVE fields `chain_total_steps`/`teaches`/`npc_role`/`npc_intro`/
`completed_steps` — `chain status`/`chain attempt` consumers unaffected).

```
active chain  → { active: true, chain_id, chain_name,
                  step:int, total_steps:int, completed_steps:[int],
                  title, objective, location, npc, npc_role, npc_intro,
                  teaches:[str], completion_type }
graduated     → { active: false, graduated: true, chain_id, chain_name }
no chain ever → (no push)
```

**Graduation memo semantics:** the session tracks
`_last_chain_step = (chain_id, step)`; the graduated payload is pushed
ONCE, only on the active→graduated transition within a session — a
reconnect after graduation pushes nothing.

Renderer `static/spa/m3_onboard.js` (`window.M3Onboard`; no intervals).
Panel `#onboard-panel`, first in the side-panel stack. Staged strings are
ONLY corpus-authored `teaches` tokens (`token + ' '`, never auto-sent) and
the real `chain attempt` (rendered only when
`completion_type == 'skill_check_passed'`). Coach pulses land only on
existing quick-action anchors (`look`→LOOK, `say`/`talk`→SAY,
`+bounties`→JOBS); finite CSS animation. First-run tour: 4 coach marks,
once per browser (`localStorage['m3_onboard_tour_done']`, cosmetic state
only), shown only while a chain is active; replayable via the panel-head
`?`. Full design: `web_onboarding_design_v1.md`.

---

## 2. RESERVED — names claimed; pin final shape when shipped

- **`buffs[]` on `combat_state` combatants** — the amber buff chip (UI-3
  tail). Gated on a buff↔combat-push integration: no producer at HEAD
  (no `Combatant.buffs`; the combat `Character` isn't dict-like for
  `engine.buffs.get_active_buffs`).
- **`shop_state` `mode:'vendor'` / `vendor_kind`** — **SHIPPED
  2026-06-12 (WEBIFY.commissary_vendor_mode drop).** Buy-side commissary
  fold-in; sellback explicitly deferred. Payload shape:
  `{"mode":"vendor","vendor_kind":"commissary","faction_code":<str lower>,
  "rank_level":<int>,"balance":<int>,"items":[{"key","name","slot","cost",
  "min_rank","desc","mark"}]}` where `mark` ∈ `{"buy","rank","short"}`.
  Pushed by `_status()` and re-pushed after a successful `_buy()` in
  `parser/commissary_commands.py`; rendered by `renderVendor` in
  `m3_shop.js`. Staged action: `+commissary buy <key>`. Sellback pending
  design call (bind-on-pickup / price model for faction-issued gear).
- **UI-8 crafting messages** — undesigned; after
  `T2.CRAFT.integration_design_pass`.
- **UI-7 Phase 2 candidates** (`web_onboarding_design_v1.md` §5):
  `in_step_location` room hint on `onboarding_state` · tutorial_v2 elective
  rail · a missions web modal.

---

## 3. Conventions (all messages)

- WS-only pushes; Telnet silently keeps its text path (`Protocol.WEBSOCKET`
  guard at the producer).
- Renderers never invent verbs: every staged command exists in the parser
  registry at HEAD, and state-changing commands are STAGED into the input,
  never auto-sent.
- Modules with intervals expose `.stop()` (M3Region, M3Board) and the modal
  close path calls it.
- Token-only CSS resolved from `client.html` `:root`; no new colours
  (alpha-of-token RGB literals follow the pre-existing pattern).
- Never render a field without a real producer; faucets and sinks land
  together.
