# UX engagement roadmap — surfacing the invisible depth (2026-06-23)

**Origin:** Brian — after the dice-animation design (`dice_animation_and_ux_polish_2026-06-22.md`), "Any ideas on other UI adds like this that will make the game more engaging?" → "Let's go with plans for all and slot them in the todo/roadmap." This doc is the consolidated design for **eight** web-client engagement features. Each is queued in `TODO.json` (`tier_2_queued`, `UX.*`); the animated dice (`UX.dice_and_animation_polish`) is the ninth, already designed, and the shared discipline below is lifted from it.

Scope: **web client only** (`static/client.html` / `static/spa/m3_*.js`), per the web-first policy. Telnet graceful-degrades — every feature here is a surface over state telnet already reaches through text commands; none gate engine behaviour.

---

## The through-line: render the depth that already runs

SW_MUSH has enormous systemic depth that is almost entirely **invisible** — it lives in scrollback. The Director AI shapes faction turns, territory influence, world events and uprisings every tick; combat resolves a full D6 wound/cover/initiative model; the questline engine tracks multi-step goals; scenes/plots track live RP; the sheet carries every advancement. A player **cannot see almost any of it** unless they happen to type the right command at the right moment.

So the single biggest engagement win is not new content — it is **UI that surfaces the systems already running.** Read the gap analyses below and the pattern is overwhelming: nearly every feature here is *"compose existing producers into a panel,"* not *"build a new system."* The producers exist and are mostly already on the HUD wire. That makes this the cheapest large engagement lever available — and it is exactly the "extend, don't add" invariant applied to the client layer.

This also reframes "engagement" away from decoration. The dice doc drew the line: an addition must deliver **feedback or theme**, never decoration, and never fight the medium's strengths (speed + density + keyboard flow). Every feature below is held to that bar.

---

## Shared add-vs-detract discipline (applies to all nine)

These are repeated, deliberately, in each section — because on a fast text-first MUSH the failure mode (a dashboard that gates pace) makes play *worse* than the text we have. The non-negotiables:

1. **Never gate pace or information.** The text/feed is the source of truth and renders immediately; every panel is a *parallel mirror*, never a barrier. No feature here ever holds a turn, blocks input, or hides information until you hover/click.
2. **Optional + toggleable, zero cost when ignored.** Each is a collapsible panel / opt-in tab / off-by-default toggle following the existing client flag patterns (`fk_clean_mode`, the onboarding-tour flags, the sidebar `toggleSidePanel`). A player who never opens it loses nothing mechanical.
3. **Respect density + speed.** Lean payloads, no board-dumps, no layout reflow that pushes the input box, no animation that competes with reading. Render zero DOM when the relevant state is absent.
4. **Server stays authoritative; no phantom verbs/fields.** The client renders what a real producer sends; affordances map to real parser commands; nothing is rendered against absent data. (Every "surfaces X" claim in this doc was grep-verified against HEAD — see methodology.)
5. **Web-only; telnet graceful-degrades.** Each feature is a web surface over shared state; telnet keeps its first-class text verbs unchanged, with no regression.

If a feature breaks any of 1–5, it detracts and gets cut or reshaped. If all hold, it is pure upside.

---

## Priority + phasing at a glance

Ranked by my recommendation. "Core-experience" means it materially changes whether the game is legible/alive/discoverable (worth a pre-launch slice); "polish" is a satisfaction multiplier on something already working. Every pre-launch slice is small and rides existing seams; the heavier chrome is post-launch in each case.

| # | Feature (`UX.*`) | Tier | Engine touch | Pre-launch slice |
|---|---|---|---|---|
| 1 | `context_affordances_clickable_entities` | core-experience | small (`_hud_room_contents`) | CLAIM / name-click / SELL / FLEE on existing HERE + qa-row seams |
| 2 | `combat_hud` | core-experience | 1 line (`stun_count` in `to_hud_dict`) | cover + own wound track + hit flash + round-flow coaching |
| 3 | `living_world_situation_board` | core-experience | small (digest helper + HUD push) | influence ladder + world-events + filtered headlines behind a `SIT` tab |
| 4 | `presence_and_scene_ui` | core-experience | small (`active_scene` HUD block) | scene card (who's posing) + who's-online roster |
| 5 | `goals_objectives_tracker` | core-experience | small (one HUD producer) | questline + mission + bounty consolidated objectives panel |
| 6 | `command_palette_autocomplete` | core-experience | none (reuses reference API) | `Ctrl/Cmd+K` fuzzy palette over the access-filtered verb corpus |
| 7 | `living_character_sheet` | polish | none (payload complete) | delta-highlight changed values + Force/dark-side accent (client-only) |
| 8 | `sound_atmosphere` | polish | none | *(optional)* off-by-default zone-keyed ambient audio |
| — | `dice_and_animation_polish` | polish (slice = differentiator) | small (`drama` field) | animate the signature D6 roll on dramatic moments — see its own doc |

**Sequencing:** all of this sits **behind the hard launch blockers** (map-nav fix, the rally/communal-event rework, the QA tail). The core-experience slices (1–6) are the ones to consider folding into the pre-launch UI pass because they change legibility/onboarding, not just feel; 7–8 follow. `sound_atmosphere` additionally **follows the dice drop** (it borrows the `drama` tier for UI cues) and depends on audio-asset sourcing (the long pole).

---

## Grounding methodology + one latent bug surfaced

Every feature was grounded against HEAD by a parallel research+draft+phantom-audit pass (one pipeline per feature, two independent adversarial audit passes over each draft). "Surfaces X" claims cite real symbols; anything without a producer is in that section's **Gaps / new work**, never asserted as existing. The audits caught and corrected a handful of phantom citations (a non-existent `cost_logged` news event-type, `hud.inventory`→the real `hud.loadout`, `get_scene`→`get_scene_detail`, an inflated help-corpus count, and a missing `zones.yaml` `environment` data field) — all fixed in the sections below.

One audit finding is a **pre-existing latent bug, not a design gap, and worth a separate QA fix:** `_hud_room_contents` (`server/session.py:~1277`) does `from engine.combat import get_combat` inside a `try/except` to detect in-room combat — but **no `get_combat` symbol exists in `engine/combat.py` at HEAD.** The `ImportError` is silently swallowed, so `in_combat` is **always `False`** (NPC action affordances never reflect combat state). Active combats are tracked in the module-level `_active_combats` registry; there is no room→combat accessor. The `context_affordances` plan therefore treats in-combat detection (and the FLEE affordance) as **new work** that must add a real lookup — and this dead hook should be filed as its own QA item.

---

*The eight sections follow, each self-contained (what + why → add-vs-detract → existing systems it surfaces → gaps/new work → implementation sketch → phasing). Ordered by the priority table above.*

---

---

## Context-aware affordances + clickable entities

### What + why

The room already knows what you can do here — the server classifies every NPC by role, derives a `room_services` tag list, and detects combat. The client already renders occupants in the HERE panel with server-driven action buttons and rebuilds the `qa-row` quick-action set by context (TRAIN appears at a trainer, CRAFT at a station, HEAL when wounded). This feature *closes the loop* on that machinery: surface the **right verb for the moment** (BUY/SELL at a vendor, CLAIM when a live bounty target is standing in the room, FLEE in combat) and make the **named entities themselves clickable** (click an NPC name → examine; click a player → look) instead of forcing the player to retype names they can already see.

Engagement lever: **friction-to-action collapse.** A text-first MUSH punishes the player who half-remembers a verb or a target's exact name. Every context affordance removes one "what was the command again?" beat between intent and action — the single highest-leverage retention fix for new players, and a speed win for veterans who keep the keyboard. The bounty CLAIM affordance also pulls a **discovery lever**: right now a hunter must recognize the target's name from `+bounty/track` lore and manually `+bounty/collect` — the target can be in the room and the player never knows. Surfacing it converts a hidden win-condition into a visible one.

### Add vs detract discipline

This is a keyboard-driven text game. The affordance layer is an **accelerant, never a gate**:

- **Never gate pace or information behind a click.** Every affordance is a shortcut for a verb the player can still type. The HERE panel and `qa-row` mirror what the room text already says; they never *replace* it and never hold back information until you hover/click.
- **Server stays authoritative for *which* verbs.** The client renders the action list the server sends (`npc.actions`); it does not invent verbs. New affordances (CLAIM, SELL, FLEE) must each correspond to a real parser command — no phantom verbs.
- **Density & speed respect.** No new always-on panels. Bounty/FLEE/SELL ride the *existing* HERE rows and `qa-row` injection seam. No modals — item inspection uses an inline card pattern (mirror `m3_inventory.js`), never a popup that steals focus from the input line.
- **Optional / non-disruptive.** Clickability is purely additive markup; the existing reduced-motion + focus a11y guarantees (`test_a11y_reduced_motion_focus.py`) must continue to pass — no affordance steals keyboard focus or animates against `prefers-reduced-motion`.
- **Web-only; telnet graceful-degrades.** All of this is client render + a few extra payload fields. Telnet players keep `buy`/`sell`/`look`/`+bounty/collect` as typed verbs (already the case) and simply don't get the buttons — the standing web-first policy, no telnet regression.

### Existing systems it surfaces (verified)

- **NPC role + action producer** — `_classify_npc_role` (`server/session.py:78`), `_npc_actions` (`server/session.py:124`), `_derive_room_services` (`server/session.py:153`). Roles: hostile/guard/trainer/vendor/quest/mechanic/bartender/neutral. `_npc_actions` already gates `attack` on `in_combat` + `security_level`.
- **Room-contents payload builder** — `_hud_room_contents` (`server/session.py:1237`) emits `hud['room_contents'] = {npcs, players, vendor_droids}` and `hud['room_services']`. Combat-detection hook: `_hud_room_contents` (`server/session.py:1277`) does `from engine.combat import get_combat` inside a `try/except` -- but **no `get_combat` symbol exists in `engine/combat.py` at HEAD**, so the `ImportError` is swallowed and `in_combat` is silently always `False` (a latent dead hook; active combats live in the module-level `_active_combats` registry, with no room->combat accessor). In-combat detection is therefore *new work*, not an existing surface (and the dead hook is its own QA item). Vendor droids fetched via `db.get_objects_in_room(room_id, "vendor_droid")` (`db/database.py:5569`).
- **HERE panel renderer** — `renderHerePanel` (`static/client.html:8806`), role icons `_HERE_ROLE_ICONS` (`:8789`), button class map `_HERE_BTN_CLASS` (`:8798`, already includes a `sell` style), `here-actions` wrapper (`:8861`). Buttons send `sendCmd(action + ' ' + npc.name)`.
- **Smart quick-button row (G8)** — `getQuickMode` (`static/client.html:6365`), `_buildExploreButtons` (`:6375`, the TRAIN/CRAFT/HEAL injection seam), `updateQuickButtons` (`:6401`, preserves `data-action="move"` direction buttons across rebuilds and re-wires via `wireQuickActions`).
- **HUD dispatcher** — `handleHudUpdate` (`static/client.html:6839`): `renderHerePanel` at `:6846`, context-flag derivation `_roomHasTrainer`/`_roomHasCrafting`/`_lastWoundLevel`/`_playerCP` at `:6853-6868`, then `updateQuickButtons`.
- **Service icons** — `renderRoomDetailPanel` (`static/client.html:8505`), `SVC_ICONS` (`:8565`).
- **Bounty board** — `BountyBoard.find_by_npc(npc_id)` (`engine/bounty_board.py:531`) maps a room NPC's id → its `BountyContract`; `BountyContract.claimed_by`/`status` (`:218`) gate ownership; `generate_bounty` (`:340`) spawns the target with `target_room_id`. Parser: `BountyCollectCommand` `+bounty/collect` (`parser/bounty_commands.py:339`).
- **Crafting station** — `get_crafting_station_bonus` (`engine/buildings.py:650`); `crafting` also derives from `room_props.environment` in `_derive_room_services`.

### Gaps / new work (honest)

1. **Bounty-target-in-room detection + CLAIM affordance** — *new work, S–M.* No code cross-checks room NPCs against the caller's active contracts. **Tighter than the grounding's "Medium":** the board is the in-memory singleton (`get_bounty_board()`), so the cross-check is `board.find_by_npc(n["id"])` per NPC with `contract.claimed_by == char_id and status == CLAIMED` — **no N+1 DB query, no new index.** Adds `is_bounty_target: bool` + `contract_id` to npc_entries; client highlights the row and injects a CLAIM button (→ `+bounty/collect <id>`).
2. **NPC/player name clickability (examine/look)** — *new work, S.* Names are inert text today. Wrap `here-name` in a click target (or add a `look`/`examine` action) that sends `look <name>`. Pure client markup.
3. **SELL affordance at vendors** — *new work, S.* Vendor droids render only a BUY path. `_HERE_BTN_CLASS` already styles `sell`; add a SELL button when the player has sellable inventory (client checks `hud.loadout` presence -- the real HUD field; `hud.inventory` is not sent) → `sendCmd('sell ...')`. Verb exists.
4. **FLEE in combat** — *new work, S.* `qa-row` postcombat/explore modes have no FLEE. Inject FLEE into the button set when `in_combat`. **Decision needed:** the brief assumes a `flee` verb — verify/confirm the combat-disengage command name before wiring (do not invent the verb).
5. **Ground items / loot clickability** — *new work, L, post-launch.* No `ground_item` obj_type flows into `room_contents`; `LOOT` is text-only. Requires obj_type definition, payload extension, a new `renderGroundItems` section, and pickup/examine handlers. Largest chokepoint — **defer.**
6. **Rich inline item inspection** — *new work, M, post-launch.* Clicking a vendor slot only sends `look`. A non-modal detail card (reuse `m3_inventory.js` card pattern) showing damage/soak/quality is polish, not core.

### Implementation sketch

**Engine (extend the funnel, don't add a system).** All work lands inside the existing `_hud_room_contents` producer — no new HUD builder. In the NPC loop (`server/session.py:1284`), after `_npc_actions`, add the bounty cross-check against the singleton board:

```
board = get_bounty_board()
contract = board.find_by_npc(n["id"])
is_target = bool(contract and contract.claimed_by == char.get("id")
                 and contract.status == BountyStatus.CLAIMED)
if is_target:
    actions = actions + ["claim"]   # CLAIM verb → +bounty/collect <id>
npc_entries.append({..., "is_bounty_target": is_target,
                    "contract_id": contract.id if is_target else None})
```

Surface combat to the client for FLEE by FIRST adding a real room->combat lookup (the existing `get_combat` hook is dead -- see above; add a `get_combat(room_id)` accessor over `_active_combats`, or equivalent), then stamping `hud["in_combat"]` — the value exists; it just isn't emitted. SELL needs no engine change (verb + inventory presence are client-derivable).

**Wire payload (additive only).** `room_contents.npcs[]` gains `is_bounty_target` (bool) and `contract_id` (str|null); top-level `hud.in_combat` (bool). No field renames — existing consumers unaffected.

**Client renderer (mirror the named existing patterns).**
- *HERE panel* (`renderHerePanel`, mirror its existing per-NPC row build): when `npc.is_bounty_target`, add a `bounty-target` class to the row (red glow, reuse the `hostile` styling vocabulary) and render a CLAIM button that `sendCmd('+bounty/collect ' + npc.contract_id)`. Wrap `here-name` in a click handler → `sendCmd('look ' + npc.name)` for examine. Add the SELL button to vendor-droid rows when inventory is present.
- *qa-row* (mirror the `_buildExploreButtons` TRAIN/CRAFT injection): set `_roomHasBountyTarget` and `_inCombat` in the `handleHudUpdate` context-flag block (`:6853`), then inject CLAIM (when bounty target present) and FLEE (when `_inCombat`) the same way TRAIN is injected. `getQuickMode` priority gains `bountytarget` above `crafting`. `updateQuickButtons` already preserves direction buttons and re-wires — no change to its plumbing.

**Tests.**
- *jsdom client-contract* (new `tests/spa/test_gnd_ux_context_affordances.py`, mirror `test_gnd_ux_smart_buttons.py`'s static-parse + harness style): assert (a) `renderHerePanel` emits a `bounty-target` class and a CLAIM button when `room_contents.npcs[].is_bounty_target` is true; (b) CLAIM button command is `+bounty/collect <contract_id>`; (c) `_buildExploreButtons`/quick-row injects FLEE when `in_combat`; (d) name spans are clickable and send `look <name>`; (e) no new inline `onclick` lacking a window export (regression guard already in the sibling test); (f) no GCW/Imperial tokens in added blocks.
- *engine unit* (`tests/` for `bounty_board` + a session producer test): assert `_hud_room_contents` sets `is_bounty_target=True` + `contract_id` only for the NPC that is the caller's CLAIMED target, and `False` for a non-target NPC and for a contract claimed by a *different* character; assert `hud["in_combat"]` reflects the active-combat lookup (once a real room->combat accessor exists).

### Phasing

- **Pre-launch slice (core experience):** gaps 1–4 (bounty CLAIM, name clickability, SELL, FLEE) — all S/S–M, all ride existing seams, all close real "I didn't know I could do that / I had to retype the name" friction. CLAIM is the standout: it converts a hidden bounty win-condition into a visible one. Ship together behind the existing HERE/qa-row plumbing.
- **Post-launch (polish):** gaps 5 (ground items, L — needs a new obj_type + payload + panel) and 6 (rich inline item card, M). Real value, but additive surface area and no existing producer — correctly deferred.

This is **core-experience near-launch** for the affordance slice (it directly removes new-player friction and surfaces a win-condition), and **polish** for the ground-item/inspection tail.

---

## Combat HUD

**Origin:** UX-engagement sweep — a live combat panel (turn/initiative order, enemy condition, the player's own wound track, round flow, a brief hit/wound flash). Verdict: **add, but mostly already shipped.** Most of this exists in the combat strip (`handleCombatState` / `combatant-pip` / `renderCombatFeed`) — the HUD is real chrome today, not a greenfield build. The value here is *finishing* it: surface the data the engine already sends but the client drops on the floor (cover), promote the player's own wound state from a text label to a salient track, and add the *one* genuinely-new animation (a hit flash). Scope: **web client only** (`static/client.html` / `static/spa/*`). Telnet already graceful-degrades — combat resolution text streams as poses; the HUD is a web embellishment, never the source of truth.

---

### What + why

Text combat already works: you declare, the round resolves, poses stream. The engagement lever the HUD pulls is **legibility under pace** — in a D6 fight with 4+ combatants, an initiative ladder + at-a-glance wound/cover state lets a player read the board *between* keystrokes instead of scrolling pose history to reconstruct "who's hurt, whose turn, am I about to die." The feed (`renderCombatFeed`, `client.html:12469`) already gives the at-a-glance damage recap (you-hit green / you-took red / miss dim). The missing beats are: (1) **your own** wound state shown as a track, not a one-word color label buried in your pip; (2) a **brief flash** when a hit lands on you or your target, so a meaningful event grabs the eye without you parsing a feed row; (3) **cover** rendered at all — the engine sends it, the client ignores it, and cover is decisive for ranged tactics. This is feedback and legibility, not decoration: every pixel maps to a real mechanic a player must act on.

---

### Add vs detract discipline

A combat HUD on a text-first, keyboard-driven MUSH **detracts** the moment it gates pace or information. Non-negotiables:

1. **Never gate pace or information.** The pose/feed text is the source of truth and renders immediately. The HUD updates *in parallel* off the same `combat_state` push; it is never a barrier to declaring or reading an outcome. No HUD interaction is *required* to play — every combat command still works typed.
2. **Read-only / no new input path.** The HUD shows state; it does not become the only way to target or declare. Declaration stays through `combat-decl-panel` + typed commands (CLAUDE.md: extend, don't add a parallel input system). The HUD adds zero commands.
3. **Flashes are brief and bounded.** A hit flash is ≤600ms, fires on state-relevant events only (target == you, or target == your declared target), and is **rate-limited** so a multi-hit round doesn't strobe. A user toggle (`Off / Flashes-only / Full`, localStorage, mirroring the existing `fk_clean_mode`-style flag) lets power users kill it. No flash ever delays the feed row it accompanies.
4. **Respect density + speed.** Cover/buff/stun additions are compact chips/labels reusing the existing `qa-row` chip rail and pip meta line — they must not balloon the strip height or push the input box. Conditions render zero DOM when absent (the `buildConditionChips` returns-null pattern is the model).
5. **Web-only; telnet graceful-degrades.** No engine behavior is gated on the HUD. Telnet players get the same resolution text; they simply don't get the panel.

If any of 1–5 breaks, it detracts. All hold → pure legibility upside.

---

### Existing systems it surfaces (verified)

- **Wound ladder (engine):** `WoundLevel` 7-rung IntEnum (`engine/character.py:33`, HEALTHY=0 … DEAD=6) with `.display_name`, `.can_act` (≤ WOUNDED_TWICE), `.penalty_dice`. Stun is tracked separately as `Character.stun_timers` (`character.py:268`, `list[int]` rounds-remaining); stun count = `len(stun_timers)`, folded into `Character.total_penalty_dice` (`character.py:363`); the live gate is `Character.can_act_now` (`character.py:392`).
- **Round resolution + initiative (engine):** `CombatInstance.resolve_round` (`engine/combat.py:999`) is the sole action chokepoint; `roll_initiative` (`combat.py:716`) sorts `initiative_order` desc; per-swing it appends a compact feed record via `_record_feed_event` (`combat.py:1225`) — `{attacker, target, result, wound, weapon}` (`combat.py:1261`) — into the `recent_events` ring (`_FEED_RING_MAX=8`, `combat.py:164`).
- **The HUD serializer (engine):** `CombatInstance.to_hud_dict(viewer_id)` (`combat.py:777`) emits `{active, round, phase, theatre, combatants[], your_actions, waiting_for, pose_deadline, events}`. Each combatant already carries `wound_level`, `wound_name`, `initiative`, `declared`, `action_summary`, `cover` (`combat.py:842`), `aim_bonus`, `is_fleeing`, and `_conditions` (poison_stacks/restraint, `combat.py:787`). `events` = `recent_events[-_FEED_RING_SHOWN:]` (`combat.py:901`, shows last 4). Buffs are **explicitly deferred** at HEAD (`combat.py:790-794`: no `Combatant.buffs` field).
- **The push (engine):** `_send_combat_state` (`engine/combat_events.py:324`) calls `to_hud_dict(viewer_id=char['id'])` per session and sends a `combat_state` message; `theatre` ('ground'|'space') drives chrome tint. An inactive sentinel (`active:False`) clears the HUD.
- **Client chrome (already live):** `handleCombatState` (`client.html:12288`) is the sole `combat_state` entry — sets `ch-phase`/`ch-round`/`ch-deadline`, renders `combatant-pip`s sorted by initiative (`client.html:12369`) via `woundRung`/`woundColor` (`static/spa/m3_palettes.js`, injected), appends `M3CombatInspector.buildConditionChips` when present, then calls `renderCombatFeed` (`client.html:12469`). `M3CombatTheater.buildInitiativeLadder` / `buildTargetCard` / `buildYourStatus` (`static/spa/m3_combat_theater.js:210/287`) are ported right-rail builders **not yet wired into the live HUD**.

---

### Gaps / new work (must be built)

| # | Gap | Effort | Notes |
|---|-----|--------|-------|
| 1 | **Cover indicator on pips + ladder.** `cover` (0–4) is already in `to_hud_dict` but the client never reads it. | **Low (client-only)** | Add a compact label/icon ("½ COVER") to the pip meta line (`client.html:12403`) and `buildInitiativeLadder` rows. Reuse `COVER_NAMES` semantics from `combat.py:152`. No engine change. |
| 2 | **Player's own wound track.** Today your pip shows one word + a color. | **Low–Med (client; tiny engine for stun)** | New client builder: a 7-rung track (or filled bar) keyed off `wound_level`, color via existing `woundColor`. Render in a dedicated "your status" slot (wire up `buildYourStatus`). To show stun, engine adds `stun_count = len(char.stun_timers)` to the combatant dict in `to_hud_dict` (one line). |
| 3 | **Brief hit/wound flash.** `renderCombatFeed` appends rows silently. | **Low–Med (client-only)** | On each `combat_state`, diff `events`; for an event whose `target` is you (or your declared target) and `result == 'hit'`, apply a ≤600ms pulse class to that pip + wound track. CSS keyframes (`combatPulse` already exists). Rate-limit per round; honor the toggle. No engine change. |
| 4 | **Stun-count penalty hint on actions.** | **Low–Med (client + 1-line engine)** | With `stun_count` (gap 2) on the dict, the pip's `action_summary` can show "ATTACK [−1D stun]". Pure presentation off `total_penalty_dice` inputs. |
| 5 | **Round-flow coaching.** Phase badge pulses but doesn't teach. | **Low (client-only)** | A subtitle off `phase` + `waiting_for` + `your_actions` ("You've declared. Waiting for Jane & Throk."). All data already in the push; reuse the `guide-modal`/hint styling. NPE win. |
| 6 | **Target card.** `buildTargetCard` exists, unwired. | **Med (client-only)** | Track "current target" from the viewer's declared attack action (already in `your_actions`); feed that combatant's dict into `buildTargetCard`. Optional polish for multi-enemy fights. |
| 7 | **Buff chips.** Engine `buffs` not wired to combat. | **Med (engine + client) — DEFER** | Requires a real producer: thread active buffs into a new `_buffs()` normalizer in `to_hud_dict` + a `Combatant.buffs`/Character bridge (the code at `combat.py:790-794` documents *why* it's absent — no field, Character not dict-like). New work with an engine seam; **do not render a buff chip until that producer exists** (no-phantom-field invariant). Post-launch. |
| 8 | **Stun-KO countdown badge.** Stun-KO duration (`stun_duration_dice/unit`) reaches `combat_resolution_event` but not `combat_state`. | **Med (engine + client) — DEFER** | Needs `stun_knockout_until` threaded into the combatant dict + a client wall-clock tick. Post-launch polish. |

---

### Implementation sketch

- **Engine (extend the one serializer, add no system):** in `to_hud_dict` (`combat.py:777`), add `"stun_count": len(c.char.stun_timers) if c.char else 0` to each combatant dict (both the in-order loop ~`combat.py:836` and the late-joiner loop ~`combat.py:853`). That is the *entire* engine surface for the pre-launch slice — everything else (cover, wound track, flash, coaching) reads data already in the payload. No new funnel, no new push; `to_hud_dict` stays the single combat-serialization chokepoint (CLAUDE.md: extend, don't add).
- **Wire payload:** per-combatant dict gains exactly one key — `stun_count` (int). No other fields added pre-launch. Cover/wound/feed are unchanged. (Buffs + stun-KO countdown are deferred precisely so we don't ship a field with no producer.)
- **Client renderer (mirror existing patterns):** all additions hang off `handleCombatState` (`client.html:12288`) and the pip loop (`client.html:12369`), reusing established patterns — `woundColor` for the wound track, the `buildConditionChips` returns-null-when-empty convention for the cover label and coaching subtitle, the `qa-row` chip rail for compact chips, and a `combatPulse` keyframe (already defined) for the flash. Promote the "your status" wound track by wiring `M3CombatTheater.buildYourStatus`. Each new visual is a small builder accepting the palette `p` as first arg, matching the `m3_combat_theater.js` module convention. A `combat-hud` localStorage toggle (`Off/Flashes-only/Full`) mirrors the existing client setting flags.
- **Tests:**
  - *Engine unit:* extend the combat HUD-dict test to assert `to_hud_dict()` emits `stun_count` matching `len(stun_timers)` for a stunned vs healthy combatant (and that it survives the late-joiner path).
  - *Client contract (jsdom, the `tests/spa/test_m3_combat_theater.py` pattern):* load `m3_combat_theater.js` under jsdom, feed a `combat_state`-shaped fixture, assert: (a) a combatant with `cover:2` renders a cover label and `cover:0` renders none; (b) a `wound_level:3` combatant produces the wound track at rung 3 with the `woundColor` severity; (c) a feed event with `result:'hit', target:<you>` schedules the pulse class and the feed row is present *immediately* (flash never delays text); (d) `combat-hud:'Off'` suppresses the flash; (e) the coaching subtitle reflects `waiting_for`. Same harness: load module, exercise builder, inspect DOM via `.textContent`/`.classList`/`getAttribute`.

---

### Phasing

- **Pre-launch slice (core-experience):** gaps **1 (cover), 2 (wound track), 3 (hit flash), 5 (coaching)** + the one-line `stun_count` engine add. This is the legibility floor a real fight needs, and 3 of the 4 are client-only off data already shipped. Effort is low because the strip, the push, and the palette already exist — this *completes* live chrome rather than building new.
- **Post-launch (polish):** gap **4 (penalty hints)**, **6 (target card)**, **7 (buff chips — needs an engine producer first)**, **8 (stun-KO countdown — needs engine field)**. These need new engine seams or are multi-enemy niceties; none block launch.

This is **core-experience for the pre-launch slice** (combat is a primary loop and the HUD is its legibility layer), tipping to **polish** for the deferred engine-seam items.

---

## Living-world situation board

### What + why

The Director AI shapes a living galaxy every faction-turn — factions gain/lose zone influence, world events fire, communal uprisings build menace, holonet headlines drop — but today all of it is **buried in scrollback**. A player who steps away for ten minutes has no way to see that Black Sun just took a foothold in their home zone or that a cult uprising is cresting. The world *is* alive; the client just doesn't make it **legible**.

The situation board is a right-cartridge panel (`SIT` tab) that renders a lean, always-current **situation digest**: zone-faction influence ladder for the player's current zone, the live world-event ticker, the active uprising card (with a menace meter), and the last few holonet headlines. One glance answers "what is the galaxy doing *right now, here*?"

**Engagement lever: persistence-of-consequence + ambient pull.** This is a retention lever, not a content lever. It converts the Director's invisible labor into visible stakes the player can *react* to — "the galaxy moved while I was gone, and it moved *near me*." It gives a logged-in idle player a reason to act (defend a slipping zone, join a cresting uprising) and a returning player an at-a-glance reason to care. It pulls the same lever the region panel pulls for territory, extended from "this room's owner" to "this corner of the galaxy's trajectory."

### Add vs detract discipline

Non-negotiables that keep this an **add** for a text-first, keyboard-driven MUSH and not a dashboard that detracts:

- **Never gates pace or information.** The board is a *mirror*, never a *gate*. Every fact it shows is already reachable via `+news`, `+holonet`, and the region panel. It never holds a turn, never blocks input, never demands acknowledgement. Pure read-only surface.
- **Optional / toggleable.** It's one cartridge tab among others (`MAP/INV/JOBS/LORE/SIT`). A player who never clicks `SIT` loses nothing mechanical. Default tab stays `MAP`. No auto-popup, no forced focus-steal — at most one opt-in coach-mark ("galaxy's heating up") on the existing holonet ticker, dismissible and never repeated.
- **Respects density & speed.** Lean payload only (zone influence + active events + active uprising + last 5 headlines). No economy dump, no player records, no per-faction prose. Renders from the HUD tick already in flight — **zero new socket cadence**. Headlines truncate to one line; the ticker scrolls, it doesn't paginate.
- **Web-only; telnet graceful-degrades.** The panel is a web cartridge. Telnet players already have `+news` and the `render_board()` uprising lines; the board adds no telnet surface and removes none. No "requires web client" nag beyond the existing pattern.
- **No new authority.** The board never *computes* world state — it reads what the Director already produced. If `compile_digest()` and `world_events` disagree, that's an engine bug surfaced, not a board bug introduced.

### Existing systems it surfaces (verified)

All four data sources exist and are read-only producers — no new DB writes, no schema change:

- **World-state producer:** `engine/director.py:687 DirectorAI.compile_digest()` — the authoritative digest already sent to Claude: `zone_influence` (faction score per zone over `VALID_FACTIONS`) + `active_events`. `engine/director.py:1649 get_recent_log(db, limit)` — reads `director_log` rows (`timestamp, event_type, summary`) for the news feed.
- **World events:** `engine/world_events.py:689 WorldEventManager.get_status()` → `list[dict]` of `{type, name, zones, remaining_minutes, effects, headline}`; singleton via `get_world_event_manager()` (`world_events.py:709`). Already consumed by the holonet command.
- **Uprisings:** `engine/communal_objective_runtime.py:61 get_active(db)` → active `communal_objective` row (`cult_key, zone_label, menace, state`) or `None`; `render_board(active)` (`:485`) is the telnet formatter, JSON-shape available.
- **Territory (org control):** `engine/territory.py get_zone_territory_all(db, zone_id)` → `{org_code: influence_score}`, written through the `adjust_territory_influence()` funnel.
- **HUD push already carries zone state:** `server/session.py:1220 _hud_zone_influence(hud, db, room_row)` already pushes `hud['zone_influence']` as `{org → %}` each tick from `send_hud_update()` (`session.py:1992`); `Session.send_json(...)` (`:476`) is the broadcast seam, already used for `region_state` and `holonet_state`.
- **News / holonet command surface:** `parser/news_commands.py:91 NewsCommand.execute` (`+news`, reads `get_recent_log()`); `:167 HolonetCommand.execute` (`+holonet`, broadcasts `holonet_state` from `get_status()`); `server/web_portal.py:425 PortalAPI.handle_news`.
- **Client patterns to reuse:** `static/spa/m3_region.js:182 render(block)` — the proven RIGHT-CARTRIDGE world-state layout (influence ladder, security badge, ownership). `static/spa/m3_holonet.js:25 buildWorldEventsPanel(p, events)` + `:26 buildFactionMovementsPanel(p, moves)` — existing live-event and faction-delta renderers. Cartridge dispatcher: `static/spa/m3_assembled_client.js:733 buildRightCartridge` with the `switch(cartridge)` `case 'MAP'/'INV'/'JOBS'/'LORE'` block (`:777`) and the `tabs` pill array (`:737`). Message router: `static/client.html:13506 case 'region_state'` / `:13542 case 'holonet_state'` dispatch (`handleRegionState`/`handleHolonetState`).

### Gaps / new work (build honestly)

| New work | Why | Effort |
|---|---|---|
| **Lean situation-digest compiler (engine)** | `compile_digest()` is Claude-shaped (verbose, economy, player records). Need a small async snapshot helper assembling `zone_influence[player_zone]` + `get_status()` events scoped to zone + `get_active()` uprising + filtered last-5 news. **Extend the digest path, don't add a new producer.** | **Low** (~1–2h; aggregation of existing queries, no schema) |
| **HUD push helper** | New `_hud_situation_digest()` in `server/session.py` mirroring `_hud_zone_influence`, calling `send_json('situation_state', …)` from `send_hud_update()` each tick. | **Low** (~1–2h; thin wrapper) |
| **Client `m3_situation_board.js`** | New module composing `buildWorldEventsPanel` + `buildFactionMovementsPanel` + a region-style influence ladder + uprising card into one right-cartridge body. Add `'SIT'` to the tab array + `case 'SITUATION'` in the dispatcher; add `case 'situation_state'` to the client.html router. | **Medium** (~2–3h; reuses region.js + holonet.js patterns + existing CSS tokens) |
| **News event-type whitelist** | `director_log` carries admin/internal types (`faction_turn`, `era_milestone`, `economic_nudge`). The board must surface only player-facing types. **No existing filter found in `news_commands.py`** — this is new. Add an internal-type blocklist (`INTERNAL_NEWS_EVENTS`) and filter it out at the digest helper. | **Trivial** (~30m) |
| **Menace → threat-meter token** | Uprising `menace` (0–100) needs a visual scale. Mirror the existing influence-threshold/alert-level idiom; define `MENACE_*` thresholds + a threat-level CSS color token. Pure render. | **Low** (~1h) |

### Implementation sketch

**Engine (extend the digest path).** Add an async helper alongside `compile_digest`, not a parallel system:

```
async def compile_situation_digest(self, db, zone_key, session_mgr) -> dict:
    # zone_influence for the player's zone (faction scores), via existing _zones
    # active_events = [e for e in get_world_event_manager().get_status()
    #                  if zone_key in e["zones"] or not e["zones"]]
    # uprising = await communal_objective_runtime.get_active(db)  # zone-scoped
    # news = [r for r in await self.get_recent_log(db, 12)
    #         if r["event_type"] not in INTERNAL_NEWS_EVENTS][:5]
    return {"zone": zone_key, "influence": ..., "events": ...,
            "uprising": ..., "news": ...}
```

`INTERNAL_NEWS_EVENTS = frozenset({"faction_turn", "era_milestone", "economic_nudge"})` (the verified internal/admin types) lives in `director.py`; everything else is player-facing.

**Wire payload** (`send_json('situation_state', …)`, pushed from `send_hud_update` via `_hud_situation_digest`, only when the player is in a zone — same guard as `_hud_zone_influence`):

```
{ "type": "situation_state",
  "zone": "mos_eisley",
  "influence": [ {"faction": "black_sun", "pct": 41, "tier": "foothold"}, ... ],
  "events":    [ {"name": "...", "headline": "...", "remaining_minutes": 18, "zones": [...]} ],
  "uprising":  {"cult_key": "...", "zone_label": "...", "menace": 63, "state": "active"} | null,
  "news":      [ {"timestamp": ..., "event_type": "news", "summary": "..."} ] }
```

**Client renderer (mirror `m3_region.js`).** `M3SituationBoard.render(state)` returns a cartridge body: a `rgn-block`-style influence ladder (reuse the region ladder + `M3AssetsIcons.FACTION_ICONS` for per-faction color), then `buildWorldEventsPanel`-style event rows, then an uprising card whose menace bar uses the new threat token, then 3–5 truncated headline rows in the holonet `buildNewsRow` idiom. Register `'SIT'` in `buildRightCartridge`'s `tabs` array and add `case 'SITUATION': bodyContent = M3SituationBoard.render(state.situation); break;` to the `switch`. Add `case 'situation_state': handleSituationState(msg); return;` next to `handleRegionState` in `client.html`.

**Tests.**
- *Client contract (jsdom, mirror `tests/spa/test_m3_region.py` + `test_m3_region_wiring.py`):* `tests/spa/test_m3_situation_board.py` — load the module in the DOM harness, feed a fixture `situation_state`, assert the influence ladder, event rows, uprising menace bar, and news rows render; assert empty/`null` uprising degrades to no card (no throw); assert `'SITUATION'` is reachable from the cartridge dispatcher and `'SIT'` appears in the tab pills. Add an XSS-escaping assertion for headlines (mirror `test_xss_event_escaping.py`).
- *Engine unit:* `tests/test_situation_digest.py` — seed `director_log` with mixed event types + an active `communal_objective` + a `world_events` event, call `compile_situation_digest`, assert the payload shape, the news filter drops the internal `faction_turn`/`economic_nudge` types, events are zone-scoped, and uprising menace passes through. Reset the `world_events._manager` singleton in teardown (known isolation gotcha).

### Phasing

**Pre-launch slice (core-experience, ship it):** influence ladder + active world-events list + last-5 filtered headlines, pushed on the existing HUD tick, behind the `SIT` cartridge tab. This is the legibility payoff of the whole Director investment and it's cheap (reuses three existing renderers and the existing socket cadence). Without it the living galaxy stays invisible to most players — that's a core-experience gap, not polish.

**Post-launch (polish):** the uprising menace-meter visual scale; the opt-in holonet-ticker coach-mark ("galaxy heating up — check Situation"); the optional `GET /api/portal/situation` REST surface for the web-portal landing page's live-galaxy widget; per-faction movement-delta animation. None of these gate the core read; all layer on once the base board is live.

**Verdict:** the data layer is core-experience and pre-launch; the chrome is polish. The board itself is the cheapest large win available for "make the living world *felt*," because every producer already exists and is already on the wire.

---

## Presence + scene/social UI

### What + why

A web-client sidebar that makes the social layer **visible and joinable** without leaving the keyboard: a live *who's-in-this-scene* card on the right rail (scene title, type, participant list with per-player pose counts), the existing real-time pose stream it already feeds, and a global *who's-online* roster you can open to find an active scene to walk into.

**Engagement lever: discoverability of other humans.** A MUSH lives or dies on whether a logged-in player can *see* that other people are around and that RP is happening *right now*. Today that signal is invisible on the web client — you only know who's in your room from the `HERE` panel, and you can't tell a quiet room from one with a hot 40-pose scene running. This surfaces the already-tracked presence + scene state so a player's first 60 seconds answer "is anything happening, and can I join it?" — the single highest-leverage retention question for a social game. It pulls **social proof** (others are here, posing) and **low-friction join** (see the scene → walk in → compose), reusing machinery that already exists server-side.

### Add vs detract discipline

Non-negotiables that keep this an ADD for a text-first, keyboard-driven MUSH and not a chat-app skin:

- **Never gate pace or information behind it.** The pose stream (`handlePoseEvent` → `appendEvent`, client.html:12848/5596) stays the source of truth and is never blocked, throttled, or summarized by the panel. The sidebar is a *secondary* view; the main event log keeps full fidelity and full speed.
- **Optional + toggleable, off-cost-free.** Both panels are collapsible cards in the existing right-rail (`.side-panel`). Collapsed = zero render cost and zero polling. State persists per-client. A keyboard player who never opens them loses nothing.
- **Respect density & speed.** No animations on the pose-count/participant deltas beyond the rail's existing idiom; no modal that steals focus from the command line; no auto-scroll hijack. The who's-online roster polls only while *expanded* (5–10s), and the scene card piggybacks the existing HUD push — **no new always-on timer**.
- **Composer is additive sugar, never the only path.** `say`/`emote`/`pose`/`ooc` from the command input remain first-class and unchanged. The composer (if built) emits the *same* parser commands; it adds mode shortcuts and name-targeting, it does not replace typing.
- **Web-only; telnet graceful-degrades.** Telnet keeps `+who` (builtin_commands.py:2095) and `+scenes`/`+plots` text commands verbatim. No telnet regression; the panels are a web surface over shared state, never a fork of the model.

### Existing systems it surfaces (verified at HEAD)

- **Online presence (ephemeral, session-scoped):** `Session.last_activity` / `Session.is_in_game` / `Session.is_idle()` (server/session.py:370/2216/2209). No DB persistence — presence is computed from live sessions.
- **Who's-online REST:** `WebPortal.handle_who()` → `GET /api/portal/who` (server/web_portal.py:385) already returns `{online:[{name,species,location_area,idle_seconds,faction}], count, uptime_seconds}`, iterating `session_mgr.all` filtered by `is_in_game`. **Public by design** — `SEC.player_online_activity_visibility` resolved (online status is intentional social discovery, not private).
- **Room participants in HUD:** `Session._hud_room_contents()` (server/session.py:1237) builds `hud['room_contents'] = {npcs, players:[{id,name}], vendor_droids}` from `session_mgr.sessions_in_room(room_id)` (server/session.py:2271, wilderness co-location aware). Rendered by `renderHerePanel` in the existing `here-panel` card.
- **Scene + plot model (live, schema v13+/v16+):** `engine.scenes.get_active_scene(db, room_id)` (engine/scenes.py:231), `get_active_scene_id` (:226), `capture_pose` (:303), `start_scene` (:246, auto-adds creator via `_add_participant` :609), `get_scene_detail` returns pose log + `participants` (:577). Tables: `scenes`, `scene_poses`, `scene_participants`; plots via `plots` + `plot_scenes` join (db/database.py:688/698). Round-robin `PoseOrder` class with `add_participant`/`remove_participant` (engine/scenes.py:59/103/108).
- **Typed pose broadcast:** `engine.pose_events.make_pose_event(...)` + `SessionManager.broadcast_json_to_room(room_id, 'pose_event', payload, ...)` (server/session.py:2344), emitted by `SayCommand`/`EmoteCommand` (builtin_commands.py:1916/2059). Consumed by `handlePoseEvent` (client.html:12848).
- **HUD pipeline:** `Session.send_hud_update()` (server/session.py:1992) — the per-tick/per-login producer; `_hud_room_contents` is invoked from here. **This is the funnel we extend, not a new system.**

### Gaps / new work (honest)

Everything below is **new work** — none of it exists at HEAD:

| New work | Effort | Notes |
|---|---|---|
| `hud['active_scene']` block in `send_hud_update` (scene_id, title, type, started_at, pose_count, participant_count, creator_name) | **S** (~30 LOC, engine seam already there via `get_active_scene`) | The keystone. Drives the whole Phase-1 client card. |
| Per-participant pose counts merged into the block (`participants:[{id,name,pose_count}]`) | **S** (~20 LOC, `GROUP BY char_id` on `scene_poses`) | Powers "who's posing." |
| `M3ScenePanel.js` — right-rail scene card consuming `hud.active_scene` + `hud.room_contents` | **M–L** (~600–900 LOC SPA module) | Mirrors `M3CombatTheater` (right-rail, DI `init(deps)`). |
| `M3PresencePanel.js` — global who's-online card polling `/api/portal/who` (or new auth-gated endpoint) | **M** (~500 LOC) | Polls **only while expanded**. |
| `/api/hud/who` auth-gated richer endpoint (optional; adds `in_scene`, room detail) | **S** (~40 LOC web_portal.py) | Only if we want logged-in-only enrichment over the public list. |
| `M3PoseComposer.js` — mode shortcuts + name-targeting, emits existing parser commands | **M–H** (~600–1000 LOC) | **Polish.** Additive only; command line stays primary. |
| Real-time participant join/leave push (`scene_participants_update`) on room entry/exit | **S–M** (~30–50 LOC in MoveCommand; reuses `_add_participant` :609) | Without it the Phase-1 card refreshes only on HUD tick (acceptable for slice). |
| `M3SceneArchive.js` + `/api/hud/scenes` browser/plot-discovery modal | **L** (~1200+ LOC) | **Post-launch.** Telnet `+scenes`/`+plots` covers parity. |
| `M3PoseOrderStrip.js` turn indicator over `PoseOrder` state | **M** (~400 LOC) | **Post-launch polish.** Marshal `PoseOrder` into `hud.active_scene.pose_order` first. |

### Implementation sketch

**Engine (extend the funnel, no new system).** Add `Session._hud_scene_context(hud, db, room_id)` and call it from `send_hud_update` right after `_hud_room_contents` (server/session.py ~2103):

```
scene = await engine.scenes.get_active_scene(db, room_id)   # :231, returns None if idle
if scene:
    counts = {row['char_id']: row['n'] for row in await db.read_fetchall(
        "SELECT char_id, COUNT(*) n FROM scene_poses "
        "WHERE scene_id=? AND is_ooc=0 GROUP BY char_id", (scene['id'],))}
    hud['active_scene'] = {
        'scene_id': scene['id'], 'title': scene['title'],
        'type': scene['scene_type'], 'started_at': scene['started_at'],
        'creator_name': scene.get('creator_name'),
        'pose_count': sum(counts.values()),
        'participants': [{'id': p['id'], 'name': p['name'],
                          'pose_count': counts.get(p['id'], 0)}
                         for p in hud['room_contents']['players']],
    }
# else: leave key absent → client clears the card
```

No new credit/dice/influence movement, so no funnel-function obligation; this is read-only HUD marshalling. Each block stays try/except-guarded per the existing `send_hud_update` contract.

**Wire payload.** `hud_update` gains one optional key, `active_scene` (absent ⇒ no scene ⇒ card hidden). Real-time fidelity continues to flow over the existing typed `pose_event` (`broadcast_json_to_room`, server/session.py:2344) — the card is a *header*, the event log is the body. Optional `scene_participants_update` typed message (Phase 3) for instant join/leave without waiting for the next HUD tick.

**Client renderer (mirror `M3CombatTheater`).** New `static/spa/m3_scene_panel.js` following the proven DI pattern (`init(deps)` with injected `escapeHtml`, as in m3_combat_theater.js:67). Add a collapsible `id="scene-panel"` card in the right rail next to `here-panel`; render `renderScenePanel(hud.active_scene)` from `handleHudUpdate` (same hook `renderHerePanel` uses). Empty/absent `active_scene` ⇒ hide the card. Participant rows show name + a small pose-count chip (qa-row/badge idiom). `M3PresencePanel` follows the same shape, fed by `fetch('/api/portal/who')` only while expanded.

**Tests.**
- *Client contract (jsdom, tests/spa/):* `test_m3_scene_panel.py` mirroring `test_gnd_ux_sidebar_panels.py` — static-parse `static/client.html` for `id="scene-panel"`, assert `renderScenePanel` defined and invoked from the HUD handler; DOM-runtime test via `spa_dom_harness` feeding a synthetic `hud.active_scene` and asserting the title + participant rows + pose-count chips render, and that absent `active_scene` clears the card. XSS pass: scene title routed through `escapeHtml` (extend `test_xss_event_escaping.py`).
- *Engine unit (tests/):* harness test on `_hud_scene_context` — start a scene (`start_scene`), capture N poses across 2 chars (`capture_pose`), assert `hud['active_scene'].pose_count == N`, per-participant counts correct, IC-only (ooc excluded), and the key **vanishes** after `+scene/stop` flips status off `active`. Remember the world-events singleton reset gotcha if any test touches it.

### Phasing

- **Pre-launch slice (core experience, ship it):** Phase 1 engine `active_scene` HUD block (**S**) + Phase 2 `M3ScenePanel` right-rail card (**M–L**). This is the retention payload — "a scene is happening here, here's who's posing." Cheap server side, bounded client side, no new timers, telnet untouched.
- **Pre-launch if budget allows:** `M3PresencePanel` global who's-online over the existing public `/api/portal/who` (**M**). High social-proof value, low engine cost; the endpoint already exists.
- **Post-launch (polish):** `M3PoseComposer`, `M3SceneArchive`/plot browser + `/api/hud/scenes`, `M3PoseOrderStrip`, and the auth-gated `/api/hud/who` enrichment. All are quality-of-life over a model that already works via command line + telnet text commands.

**Verdict:** the *scene card* is **core experience** (it directly pulls the join-RP lever and is cheap); everything past the global roster is **polish**.

---

## Goals / objectives tracker

**What + why**

The web client already renders a single living goal — the onboarding step (`onboarding_state` → `M3Onboard.render`). The moment a player graduates, that panel goes dark and the client stops telling them what to do next, even though they now carry real, persistent goals: an accepted mission, a claimed bounty, an active mid-game questline. The tracker extends the *one good thing the NPE panel already does* — a titled objective with a NEXT pointer and a one-key action — past graduation, so the keyboard player always has an answer to "what am I working toward and what do I type?" without paging a board.

Engagement lever: **closure + the next-action pointer.** Three short, glanceable open loops (questline step, mission, bounty) each with a reward and a countdown turn idle "I'm logged in, now what" sessions into a self-set queue. It reuses the dopamine the achievements/step-rail UI already earns (a dot fills, a card flips to COMPLETE) and points it at content that pays credits, instead of the player re-deriving their own to-do list every login.

**Add vs detract discipline**

This is a text-first, keyboard-driven MUSH. The tracker is an ADD only if it obeys these non-negotiables:

- **Never gate pace or information.** Everything shown is already reachable by typing (`chain status`, `+missions`, `+bounties`/`JOBS`). The panel is a *display* of text-reachable state, never a source of web-exclusive progress. No goal exists that you can only see or advance in the panel.
- **Optional + toggleable.** Lives in a collapsible sidebar panel exactly like `#mail-panel`/`#ach-panel` via `toggleSidePanel(id)`. Collapsed state persists. A player who never opens it loses nothing.
- **Respect density & speed.** Hard cap: questline step + at most one mission + the player's claimed/active bounties, ≤5 lines total. No board dumps (the full board stays on `board_state`/`+missions`). Push only on the existing HUD tick — no new timers server-side; the only client interval is the bounty countdown, reusing `m3_board.js fmtCountdown` (1 s), and only while the panel is open.
- **No auto-send.** A goal's action chip *stages* a command via `stageRawCommand` (mirrors `stageFromOnboard`); the player still presses Enter. The panel cannot invent a verb — it stages only the literal command the producer authored (questline `command_to_type`, the mission's `+missions` / bounty's `JOBS` anchor).
- **Web-only; telnet graceful-degrades.** Telnet users keep the existing first-class verbs (`chain status`, `+missions`, `+bounties`). No telnet string changes; the tracker is a web overlay on those, nothing more.

**Existing systems it surfaces (verified against HEAD)**

- **Questline / chain step engine.** `engine/chain_events.py:1468 build_onboarding_state()` already emits the active-step payload (`title`, `objective`, `next_hint`, `command_to_type`, step rail). `get_questline_status()` (`chain_events.py:1317`) is a thin wrapper over `get_active_step_info` pinned to the `active_questline` slot — present, but **not yet wired** into the onboarding push. Both run on the same `tutorial_chains` state machine.
- **Mission board.** `engine/missions.py:325 class Mission` (status `AVAILABLE|ACCEPTED|COMPLETE|EXPIRED|FAILED`, `MissionStatus` enum at `missions.py:118`, `accepted_by`, `reward`, `objective`). `db/database.py:2790 get_active_mission(char_id)` returns the one accepted mission. Chain-tagged missions filter through `engine/chain_missions.py:472 is_chain_mission_visible_to()`.
- **Bounty board.** `engine/bounty_board.py:99 BountyStatus` (`POSTED|CLAIMED|COLLECTED|EXPIRED|FAILED`), the singleton `get_bounty_board()` (`bounty_board.py:617`), `BountyBoard.claim()` (`bounty_board.py:540`), and `build_board_state()` (`bounty_board.py:717`) which already shapes a viewer-scoped `{claimed, board[]}` with `expires_in_secs`. Visibility filter: `engine/chain_missions.py:506 is_chain_bounty_visible_to()`. Tier pay ramp: `PAY_RANGES` (`bounty_board.py:63`).
- **HUD push spine.** `server/session.py:2146 send_hud_update()` calls per-panel async producers (`_hud_sidebar_onboarding` :1860, `_hud_sidebar_mail` :1883, `_hud_sidebar_achievements` :1916, `_hud_sidebar_places` :1938). The new producers slot in beside these on the same tick.
- **Client message spine + UI patterns.** Dispatcher `switch(msg.type)` at `static/client.html:13496`; sibling handlers `handleMailStatus`/`handleAchievementsStatus`/`handleOnboardingState` (`client.html:12717`). Renderer modules `static/spa/m3_onboard.js` (step rail, teach chips, dismiss card) and `static/spa/m3_board.js` (`TIER_TOKEN` color ramp, `fmtCountdown`) supply the exact UI vocabulary to reuse.

**Gaps / new work (must be built — none of this exists today)**

| New work | Why | Effort |
|---|---|---|
| Wire `get_questline_status()` into the questline branch of the goals push | Mid-game questlines (`active_questline` slot) don't surface anywhere in the client today | Low |
| Server producer `_hud_sidebar_goals()` | No producer assembles {questline step, active mission, claimed bounty} into one payload; must query `get_active_mission` + bounty singleton + apply both visibility filters | Low–Med |
| Client `case 'goals_status'` + `handleGoalsStatus()` | No dispatcher case / handler exists for a consolidated goals push | Low |
| `#goals-panel` HTML (head + body) | No goals sidebar div exists | Minimal |
| `m3_goals.js` renderer module | No module renders mission/bounty rows; reuses onboard rail + board countdown idioms but is new code | Med |
| (Deferred) Director-AI / admin personal-objective data model | Brief mentions "objectives" plural; no per-character third-party quest store exists. **Out of scope for launch** | High |

**Implementation sketch**

*Engine — extend, don't add.* No new system. Add one server producer `_hud_sidebar_goals(self, db, char, char_id)` in `server/session.py`, called from `send_hud_update()` immediately after `_hud_sidebar_onboarding` (same `try/except`/early-return-on-empty idiom as its siblings). It composes three existing readers — `chain_events.get_questline_status(char)`, `db.get_active_mission(char_id)`, and the bounty singleton scoped through `is_chain_bounty_visible_to` — and early-returns (sends nothing) when all three are empty, so a player with no goals gets no panel. To avoid duplicating the onboarding panel, the questline slice is suppressed whenever `build_onboarding_state` is still active (NPE first; questlines after graduation).

*Wire payload* (`goals_status`, additive — unknown keys ignored, matching the onboarding ABI discipline):

```json
{
  "type": "goals_status",
  "questline": { "chain_id": "...", "title": "...", "objective": "...",
                 "step": 2, "total_steps": 4, "next_hint": "...",
                 "command_to_type": "chain attempt" } | null,
  "mission":   { "id": "...", "title": "...", "objective": "...",
                 "reward": 750, "stage_cmd": "+missions" } | null,
  "bounty":    { "id": "...", "target_name": "...", "tier": "mid",
                 "reward": 2400, "expires_in_secs": 11030,
                 "stage_cmd": "JOBS" } | null
}
```

*Client renderer — mirror the named patterns.* Add `case 'goals_status': handleGoalsStatus(msg); return;` to the dispatcher (`client.html:13496`). `handleGoalsStatus` mirrors `handleOnboardingState`: hide `#goals-panel` if all three slots null, else delegate to a new `M3Goals.render($('goals-body'), data, stageRawCommand)`. `m3_goals.js` renders ≤3 rows: the questline row reuses the `m3_onboard.js` step-rail dot idiom; the bounty row reuses `m3_board.js` `TIER_TOKEN` for the tier color and `fmtCountdown` for a 1 s `expires_in_secs` ticker (interval armed only while the panel is visible, cleared on hide). Each row's action chip stages its `command_to_type`/`stage_cmd` via the passed `stageRawCommand` — staged, never sent — honoring the invented-verb-never rail.

*Tests.*
- **jsdom client-contract test** `tests/spa/test_m3_goals.py`, mirroring `tests/spa/test_m3_onboard.py` (loads the module under `tests/spa/spa_dom_harness.run_with_dom`): asserts (a) all-null payload renders nothing / hides the panel; (b) each present slot renders its row with the right title/reward; (c) the action chip stages exactly the authored `stage_cmd`/`command_to_type` and never auto-sends; (d) the bounty countdown formats `expires_in_secs` via the shared formatter; (e) a re-render with a dropped slot removes that row.
- **Engine/producer unit test** `tests/server/test_hud_sidebar_goals.py`: a character with no questline/mission/bounty yields no send; a character with each yields the composed payload; the questline slice is suppressed while onboarding is active; chain-bounty visibility filtering excludes a bounty the viewer can't see.

**Phasing**

- **Pre-launch slice (core experience, ship it):** the questline + mission + bounty consolidated panel exactly as sketched. This is the piece that keeps a graduated player oriented — it's onboarding-continuity, not chrome, and it surfaces the credit faucets we already built. Low/Med effort, all on verified seams.
- **Post-launch (polish, deferred):** the Director-AI / admin personal-objective data model (`gaps` High item) — needs a new per-character objective store and is genuinely out of scope for launch.

Verdict: **core-experience, near-launch.** The consolidation layer is small, rides entirely on existing producers and the existing HUD/sidebar spine, and closes a real onboarding cliff at graduation.

---

## Command palette / fuzzy autocomplete

### What + why

A keyboard-driven game with a ~270-verb surface has a discovery wall: a new player who doesn't know the verb is stuck, and a veteran who half-remembers `+bounty/collect` retypes it from scratch. The command palette is an **opt-in, fuzzy type-ahead** over the whole verb surface — press `Ctrl/Cmd+K`, start typing intent ("bounty", "sell", "med"), and get a ranked, access-filtered list of real commands with their one-line help, Enter to **stage** (not blind-fire) the chosen verb into the input line.

**Engagement lever: discoverability + friction collapse.** This is the single highest-leverage onboarding lever for a command game — it converts "I don't know what to type" (the #1 MUD-killer) into "type roughly what you want." It surfaces the *same* corpus the in-game `+help` and the web reference browser already expose, but at the speed of a fuzzy launcher instead of a paginated lookup. For veterans it's a speed win that keeps hands on the keyboard.

### Add vs detract discipline

Non-negotiables that keep this an **add** for a fast, keyboard-first client and not a mouse-driven detour:

- **Opt-in, and it never breaks raw typing.** The palette opens only on the `Ctrl/Cmd+K` chord (and an optional on-screen affordance). When closed it is **completely inert** — bare-type-and-Enter, command history (Up/Down), and the staged-command flow all behave exactly as today. No keystroke is intercepted unless the palette is open.
- **Never gate pace or information.** Everything the palette shows is already reachable via `+help` and the web reference browser. It is a faster index, never a required step; closing it (`Esc`/click-outside) returns you to a normal input line with zero state cost.
- **Stages, never blind-fires.** Selecting a result **populates the input** (the existing staged-command idiom — `resolveStagedTemplate`/`stageCommand`); the player still presses Enter, and edits args first. A verb with arguments stages a template with the cursor placed, never an auto-sent guess.
- **Access-filtered, server-authoritative.** The palette shows only commands the caller may run, replicating the access-level gate the reference API already enforces (`_caller_max_access_level`) — no admin verbs leak to players, no phantom verbs are invented client-side.
- **Web-only; telnet graceful-degrades.** Telnet keeps `+help`/`+commands` as the discovery path; the palette is a web embellishment over the same corpus, no telnet surface added or removed.

### Existing systems it surfaces (verified)

The corpus and its access-gated read API already exist — this is mostly *consumption*, no engine change for the launch slice:

- **The command corpus + help text:** the `HelpManager` help corpus (`data/help_topics.py`, ~303 entries, auto-registered from commands) and `CommandRegistry.all_commands` (`parser/commands.py`, the ~270-verb registry) — the names, aliases, and one-line summaries that feed type-ahead. `HelpEntry.aliases` carries the alternate spellings; the `+`/`@` prefix taxonomy (`GLUED_PREFIXES`, `DIRECTION_ALIASES`) and the command-syntax rework give a clean, normalized verb surface to index.
- **The access-gated reference read API (already web-facing):** `PortalAPI.handle_reference_index` and `PortalAPI.handle_reference_search` (`server/web_portal.py`) already serve a searchable command index to the web client, gated by `_caller_max_access_level` with `_summary_view`/`_full_view` shaping — the palette reuses this exact endpoint + gate rather than building a parallel command list. (`AccessLevel.PLAYER`/`ADMIN`.)
- **Client input + staging seams:** `setupInput` (`static/client.html`, the input keydown owner), `sendCmd` / `stageCommand` / `resolveStagedTemplate` (the staged-not-sent flow the qa-row already uses), `activeInputEl` (the ground/space input resolver), and `wireQuickActions` / `.qa-row` / `.qa-btn` (the existing chip-wiring pattern the palette's result rows mirror). `inSpaceMode` keeps the palette pointed at the correct active input.

### Gaps / new work (honest — none of this exists today)

| New work | Why | Effort |
|---|---|---|
| **Fuzzy scorer** | A small inline subsequence/rank scorer (fuse.js-style, but inlined — no new dependency) over the cached index. | **S** |
| **Palette dropdown UI** | The overlay component: input, ranked result rows (verb + summary + access badge), keyboard nav, `Esc`/click-outside close. Mirrors the `qa-row`/`here-actions` markup + wiring idiom. | **M** |
| **`Ctrl/Cmd+K` keybind handler** | Open/close chord, scoped so it never fires while the palette is closed and never shadows a browser/in-game binding. | **S** |
| **Client-side access filter** | Replicate the reference API's access gate so a player's palette never lists admin verbs (defense-in-depth even though the server re-checks on dispatch). | **S** |
| **Index prefetch + cache** | One batched fetch of the access-shaped command metadata at session init (or first palette open), cached so type-ahead is local + instant. | **S** |
| *(Optional, post-launch)* `GET /api/portal/reference/autocomplete` | A server-side prefix endpoint if the cached-index approach ever needs to scale or stay fresher than per-session. | **S** |

### Implementation sketch

- **Engine / server: none for the launch slice.** The reference index + search API and the access gate already exist and are already web-facing (`handle_reference_index`/`handle_reference_search`, `_caller_max_access_level`). The palette consumes them; it adds no command, no new producer (CLAUDE.md: extend-don't-add). The optional autocomplete endpoint is post-launch and would extend `PortalAPI`, not add a system.
- **Wire payload:** unchanged for the launch slice — one batched fetch of the existing access-shaped reference index at session init, cached client-side. No new socket message.
- **Client (mirror named patterns):** a `SwPalette` module — a hidden overlay opened by a `Ctrl/Cmd+K` handler registered in `setupInput`'s keydown owner (active only while open). On open it fuzzy-ranks the cached index against the query; result rows render in the `qa-btn` vocabulary (verb + dim summary + access badge); selecting a row calls the existing staged-command path (`stageCommand`/`resolveStagedTemplate`) against `activeInputEl` (respecting `inSpaceMode`) — staged, never sent. `Esc`/click-outside closes; when closed the module is inert and `setupInput` behaves exactly as today.
- **Tests:**
  - *Client contract (jsdom, `tests/spa/test_client_onclick_exports.py` / `test_gnd_ux_smart_buttons.py` pattern):* with the palette closed, bare-type-and-Enter + Up/Down history are unchanged (the load-bearing regression); `Ctrl/Cmd+K` opens it; a query ranks the seeded index; selecting a row **stages** (does not send) the verb into `activeInputEl`; `Esc` closes and restores a normal input; an admin-only verb is absent from a player-access fixture.
  - *Engine/server unit:* pin that `handle_reference_search` (or the autocomplete endpoint, if built) filters by `_caller_max_access_level` — a PLAYER caller never receives an ADMIN verb.

### Phasing

- **Pre-launch slice (core-experience):** the opt-in `Ctrl/Cmd+K` palette over the cached, access-filtered reference index with fuzzy ranking and staged selection — **no engine change**, rides the existing reference API + staging seams. It's a direct hit on the new-player discovery wall for a 270-verb game, and a veteran speed win, at low cost.
- **Post-launch (polish):** the optional `/api/portal/reference/autocomplete` endpoint, an in-palette argument-hint layer (per-verb usage from the help text), and a discovery coach-mark ("press ⌘K to find any command"). Telnet remains a non-goal (it keeps `+help`).

**Tier:** **core-experience, near-launch** — discoverability is foundational for a command game, and the launch slice is no-engine-change client work over an API the web client already calls.

---

## Living character sheet

**Origin:** UX-engagement brief — "render the sheet as a *live* panel, with values that changed since last view highlighted, and a thematic Force/dark-side visual identity." Verdict: **add** — but the entire feature is already 90% built. `+sheet` (`SheetCommand`) emits a full structured `sheet_data` payload, the web panel renders it across attributes / wound ladder / points / skills / Force tab. The "living" part is **two small, additive layers on top of an existing pipeline**: (a) a *delta highlight* (changed-since-last-view), and (b) a *Force/dark-side visual identity*. The risk — and the only way this detracts — is animating/flashing on a fast text-first client, or pushing the sheet at the player. This doc designs it with that discipline baked in.

Scope: **web client only** (`static/client.html`, with the `static/spa/m3_sheet.js` modal as a future alt-renderer). Telnet keeps the ANSI text dump (`render_game_sheet`, builtin_commands.py:2519) — no change. Engine work is *near-zero* for the MVP (the payload already carries every field); one optional server enhancement (server-computed `changed_fields`) is deferred.

---

### 1. What + why (the engagement lever)

The sheet is the player's mirror — who they are in `ND+P`. Today it's a static read: you open `+sheet`, you see numbers, you close it. The lever this pulls is **progression legibility**: a D6 character advances in small, easy-to-miss increments (a skill ticks `4D → 4D+1`, a Force point burns, credits move, a wound lands). When the sheet *highlights what changed since you last looked*, every advancement gets a beat of payoff and every loss gets registered. That's the core retention loop of any RPG — "I got better, and I can *see* it" — surfaced on data we already produce.

The second half, a **Force/dark-side visual identity**, pulls a *thematic-investment* lever: a Jedi's sheet should *feel* like the Force, a fallen character's should *feel* the dark side pulling at it. It's pure client styling on fields already in the payload (`force` block, `dsp`), so it costs theme work, not plumbing.

---

### 2. Add vs detract discipline (non-negotiable, text-first client)

This is a keyboard-driven MUSH. The sheet is a *reference surface a player pulls deliberately*, not a feed. So:

1. **Never gate pace or information.** The panel renders **immediately and fully** on every `+sheet`; the delta highlight is a *decoration layer applied after* the values are already on screen. No value waits on a diff, an animation, or a fetch. (Mirror the existing one-beat room-enter highlight sweep, client.html ~line 5667 — a *settle*, not a blocker.)
2. **Highlight is a glance, not a strobe.** Changed values get a quiet sustained marker (border/glow/badge), optionally a single fade-in beat — **never** a loop, pulse, or motion that competes with reading. Honor `prefers-reduced-motion` (the codebase already has a reduced-motion lane, tests/spa/test_a11y_reduced_motion_focus.py): reduced-motion = static marker, no fade.
3. **Optional / toggleable.** A `sheet-deltas` localStorage setting (`On`/`Off`, default `On`) and a `sheet-force-theme` toggle, mirroring the existing per-client flag pattern (`fk_clean_mode` / onboarding-tour flags in client.html). Power users who find it noisy switch it off; it never becomes mandatory chrome.
4. **Respect density + speed.** No new round-trips, no layout reflow that pushes content, no extra columns. The highlight reuses the *existing* attr/skill/point chips — it adds a class, not a row. The Force theme restyles the *existing* Force tab + DSP pips, it doesn't add a panel.
5. **Web-only; Telnet graceful-degrades.** Telnet keeps the text sheet verbatim. No delta semantics leak into the ANSI path (it has no "previous view" anyway).

If any of 1–5 breaks, it detracts. If all hold, it's free upside on data we already ship.

---

### 3. Existing systems it surfaces (verified)

This feature is mostly *wiring already-built seams together*. Verified against HEAD:

- **Command + event producer:** `SheetCommand` (`+sheet`, switches `/brief|/skills|/combat`) at `parser/builtin_commands.py:2419`; emits the `sheet_data` event at `parser/builtin_commands.py:2491` (`send_json("sheet_data", {payload, view})`), then refreshes the HUD (`send_hud_update`, line 2504). Telnet/WS-error fallback to the ANSI dump at line 2519.
- **Payload builder:** `build_sheet_payload(char_dict, skill_reg)` at `engine/sheet_renderer.py:717`. Schema documented at lines 609–637; all fields always present (client does no shape-guarding). Blocks: identity (749), **points** `cp/fp/dsp/force_sensitive/pvp_flagged/credits` (765–777), **wound** `level/label/penalty` (780–784), **attributes** as `{d,p}` pools (787–790), **skills** trained-only with `bonus/total/attr/tags` (800–812), **specializations** (820–842), **force** `control/sense/alter + powers` or `None` if not sensitive (849–872). DSP at line 768; credits at 776; pools serialize as `{d,p}` (`_pool_to_dict`, 641).
- **Force sensitivity (derived):** `char.force_sensitive` is reconstructed from the presence of `control/sense/alter` in the attributes blob (`engine/character.py:880`, fail-safe-to-Jedi note 888–898). The payload's `force` block is `None` when not sensitive — the Force theme keys off this exactly as the FORCE tab already does.
- **Client event handler + renderers** (`static/client.html`): `handleSheetData(msg)` (11331) stores `msg.payload` in the **`sheetPanelData`** global, toggles the FORCE tab on `sheetPanelData.force`, routes view, calls `renderSheetPanel()` + `openSheetPanel()`. `renderSheetPanel()` (11424) orchestrates `renderSheetAttrs(p)` (11462), `renderSheetWoundLadder(p)`, `renderSheetWeapon/Armor`, `renderSheetPoints(p)`, `renderSheetCenter()` (tab dispatcher → skills/combat/full/force), `renderSheetDetail()`. Helpers: `sheetPoolToStr` (11306) formats `{d,p}`→`'4D+1'`; constants `SHEET_ATTR_ORDER` (11303) and `SHEET_WOUND_RUNGS` (~11295).
- **Alt-renderer (no MVP change):** `static/spa/m3_sheet.js` (`M3Sheet.buildCharacterSheet`) is the modal port; if a future redesign routes the sheet through it, the same delta layer ports across. Out of scope for this drop.

---

### 4. Gaps / new work (honest build list)

Everything below is **new work** — none of it exists today:

1. **Change-tracking snapshot (client).** *LOW (~20–30 LOC JS.)* A `sheetPanelDataPrev` global at client.html ~11300. On `handleSheetData` entry, **before** overwriting `sheetPanelData`, stash the prior payload; compute changed sets (attributes, points, wound level, per-skill `bonus`/`total`, per-spec) by comparing new vs prev; pass the changed-flag into the renderers. First-ever open (no prev) = nothing highlighted. No infrastructure exists for this today.
2. **Highlight CSS + toggle.** *LOW (~30–40 LOC CSS + a few JS.)* `.sheet-val-changed` (sustained quiet border/glow + optional one-beat fade), reduced-motion variant (static marker only), and the `sheet-deltas` localStorage toggle. Up-vs-down variants optional (e.g. credit gain vs loss).
3. **Force/dark-side visual identity.** *MEDIUM (theme work, no plumbing.)* Restyle the **existing** FORCE tab (`control/sense/alter` as glowing pools, powers list) with a Force-blue accent, and the **existing** DSP pips in `renderSheetPoints` with a dark-side-red accent that *deepens with `dsp` count*. Inline-styling MVP first; a full themed-panel redesign is deferred. Gated by the `sheet-force-theme` toggle.
4. **Skill / spec delta.** *LOW (~15–20 / ~10 LOC.)* `renderSheetCenter` and the spec rows compare `bonus`/`total` against the snapshot and add the changed class. Folds into (1).
5. **Server-side `changed_fields` (optional, deferred).** *MEDIUM–HIGH.* `build_sheet_payload` could emit a `changed_fields` list by diffing against session-remembered last-emitted values. **Not needed for MVP** — the client snapshot covers the "since I last *looked*" semantic, which is the better UX anyway (changes since the player's last *view*, not last server emit).
6. **Real-time push on state change (deferred, Phase 2).** *HIGH.* "Living" in the strong sense (sheet updates the instant a wound/credit/skill mutates, no `+sheet`) requires emitting `sheet_data` from every mutation site or on an end-of-round tick. No mutation-driven sheet event exists today. Explicitly **out of scope** — see §6.

---

### 5. Implementation sketch

- **Engine:** **none for MVP.** The payload already carries every field the delta layer needs. Do **not** add a system or a parallel event (CLAUDE.md: extend-don't-add). The *only* future engine touch is the deferred `changed_fields` enhancement, which would extend `build_sheet_payload` (the existing producer) — never a new builder.
- **Wire payload:** **unchanged** for MVP — `sheet_data {payload, view}` already has it all. (Deferred: `payload.changed_fields: [...]` as a pure additive field; client treats absence as "compute deltas locally.")
- **Client (mirror the existing renderer pattern):** add `sheetPanelDataPrev`; in `handleSheetData`, snapshot prev → diff → produce a `changed` set; thread it through `renderSheetPanel()` into the **existing** `renderSheetAttrs` / `renderSheetPoints` / `renderSheetWoundLadder` / `renderSheetCenter` so each adds `.sheet-val-changed` to the chips/rows whose value moved. The Force theme is a `data-` attribute + accent classes on the already-rendered FORCE tab and DSP pips, gated on `sheetPanelData.force` (exactly the existing FORCE-tab guard, handleSheetData line 11343) and the `sheet-force-theme` toggle. All decoration applied *after* values render (rule §2.1). Honor `prefers-reduced-motion` (rule §2.2).
- **Test (jsdom client-contract, mirrors `tests/spa/`):** a new `tests/spa/test_living_sheet_deltas.py` in the static-parse / DOM-harness style of `test_sheet_content_surface.py` + `test_client_onclick_exports.py`. Assert: (a) two successive `handleSheetData` payloads where one attribute, `dsp`, `credits`, a skill `total`, and `wound.level` changed → exactly those chips/rows carry the changed class and unchanged ones do **not**; (b) the *first* open (no prev) highlights nothing; (c) the result text/values are present immediately regardless of delta state; (d) the `sheet-deltas` toggle off → no changed classes; (e) reduced-motion → static marker, no fade class; (f) Force theme classes appear only when `payload.force` is truthy. No engine unit test needed for the MVP (no engine change); if/when `changed_fields` lands, add a `build_sheet_payload` diff unit test.

---

### 6. Phasing

- **Pre-launch slice (this drop):** gaps 1, 2, 4 (client delta highlight + CSS/toggle + skill/spec deltas) and an MVP of gap 3 (inline Force-blue / dark-side-red accents on the existing FORCE tab + DSP pips). Web-only; jsdom contract test. Zero engine change. This is the whole "values changed since last view, highlighted, with a Force/dark-side identity" brief, delivered.
- **Post-launch / deferred:** gap 5 (server `changed_fields` optimization), gap 6 (real-time mutation-driven push), and a full themed-panel Force/dark-side redesign (possibly routed through `m3_sheet.js`).

**Tier:** **Polish, post-launch-shaped but cheap enough to slice pre-launch.** The sheet *works* without it; this is a satisfaction/retention multiplier, not a core mechanic. But the MVP is so low-cost (client-only, no engine, ~80–100 LOC + CSS, on fully-built seams) that the highlight slice is worth landing before launch. The strong "real-time living" version (gap 6) is genuine post-launch.

---

## Sound / atmosphere

**Origin:** Brief — subtle per-zone ambient audio (cantina hum, spaceport rumble, deep-space drone) plus UI cues (dice/hit/Force). Verdict: **conditional add.** Atmosphere is the cheapest way to make the web client *feel* like a place instead of a terminal, and the zone signal it keys off (`zone_type`) is **already on the wire** — so no engine *code* change is needed (the per-zone `environment` data is not yet populated -- see section 4). But audio in a text-first, keyboard-driven MUSH is the single most dangerous "polish" we can ship: done wrong it's a startle, a battery drain, and a thing the player reaches for the mute on within ten seconds. The value lives **entirely** in restraint + off-by-default-safe defaults. Scope: **web client only** (`static/client.html`); telnet is unaffected by policy and needs nothing.

This is **the one feature in this doc with no existing infrastructure** — no `<audio>`, no Web Audio context, no asset directory under `static/`. Honest gap, reported as such below.

---

### 1. What + why (the engagement lever)

The lever is **presence / immersion**, not feedback. A dice animation pulls *feedback* (you see the throw resolve); ambient audio pulls *place* — the low murmur-and-glassware bed under a cantina, the structural rumble of a landing field, the dead-air engine drone of deep space. It's the difference between *reading* "Chalmun's Cantina" and *being* in it. For a game whose entire fiction is delivered as text, a half-second of the right room tone does disproportionate work on the "this world is real" axis — and it's the kind of first-impression signal ("this game is cared for") that separates a web client from the 200 pure-text MUSHes it competes with.

The UI cues (dice clatter, hit thud, Force shimmer) are a **secondary, narrower** lever — feedback, overlapping the dice-animation work — and are deliberately gated harder below, because system-sound spam is exactly the failure mode that trains players to mute.

---

### 2. Add-vs-detract discipline (non-negotiable)

Audio is guilty until proven innocent. Every rule here is a kill-switch — violate one and the feature detracts:

1. **Off by default. Full stop.** Unlike the dice toggle (which can default on), audio must default **muted**. Browsers block autoplay without a gesture anyway; we lean into it. The player *opts in* via the toggle; nothing ever makes noise unprompted. localStorage key `sw_audio_enabled` defaults `'0'` — the inverse of `fk_clean_mode`'s `'1'` default.
2. **Never gate pace or information.** Audio is a *layer*, never a barrier. No sound ever blocks, delays, or precedes a text render, a HUD update, or a command echo. The keyboard flow is untouched whether audio is on, off, or still loading.
3. **Ambient is a quiet bed, not a soundtrack.** Looping, low, gapless, mixed well under speech-reading volume. No melodies, no stings on a loop, nothing that competes with the player's inner voice while they read. If you'd notice it after thirty seconds, it's too loud.
4. **Respect density + speed.** A MUSH is fast and dense. UI cues (§ if enabled) are **rate-limited and tiered** like dice drama — the killing blow and the Force power get a cue; the Nth search and combat-round-five get silence. No per-line, per-roll, per-keystroke sound. Ever.
5. **Web-only; telnet graceful-degrades to nothing.** No telnet bell, no ASCII-art "[SFX]". The feature simply doesn't exist outside the web client. (Web-first policy.)
6. **One visible control, honest state.** A single `AUDIO` button in the top strip mirroring `CLEAN`; on = "AUDIO", off = "MUTE" (or vice-versa), so the player always knows. A volume slider is a post-launch nicety, not a launch requirement.

If 1–6 hold, it's free upside. If any breaks, cut it.

---

### 3. Existing systems it surfaces (verified)

The zone signal and the toggle template both already exist — this feature is mostly *consumption*:

- **Zone type is already on the wire.** `server/session.py::_hud_zone` (`server/session.py:691-705`) resolves `hud["zone_name"]` and `hud["zone_type"]` (the latter = `zone.properties.environment`, read at `session.py:705`) and ships them in the `hud_update` push. **Caveat (verified):** the emission plumbing exists, but `environment` is not yet populated in `data/worlds/clone_wars/zones.yaml` (zone properties today carry only `security`/`threat_band`/`time_vocab`), so `zone_type` is empty for every zone until the section-4 audit fills it -- the wire is ready, the data is the gap. No server change is needed to *consume* the signal once populated.
- **The client already consumes both fields.** `handleHudUpdate` (`static/client.html:6498`) merges every push into `lastHud` (`:6499`), and the top-context strip already renders `data.zone_name` + `data.zone_type` (`static/client.html:7969`). The audio manager hooks the *same* dispatch and reads the *same* two fields — zone-change detection comes free via the `lastHud` diff already in hand.
- **The toggle pattern is a copy-paste.** The clean-mode toggle (`static/client.html:13634-13647`) is the exact template: a top-strip button flips a boolean, swaps its own label, and persists to `localStorage` (`fk_clean_mode`, `:13638`/`:13642`), with a restore-on-load block. The audio toggle is this, verbatim, with key `sw_audio_enabled` and an inverted default.
- **The button anchor exists.** `top-strip-right` (`static/client.html:4369-4373`) already holds `clean-mode-btn`, the `PORTAL` link, and `DISC`; the `AUDIO` button drops in beside `CLEAN` with the same `top-strip-btn` class.
- **Space vs. ground mode is already tracked.** `inSpaceMode` (`static/client.html:5455`) and the `data-mode` app attribute (`:6123`) let the manager pick the space-ambient tree (engine drone) vs. ground-ambient tree without any new signal.
- **Environment scalars are already stashed.** `window._sw_env` (`static/client.html:6504`, populated from `data.environment` at `:6503`) carries `time_of_day`/`weather` — available *if* we ever want night/sandstorm layering (explicitly post-launch, see §6).
- **Accessibility precedent exists.** The `prefers-reduced-motion` block (guarded by `tests/spa/test_a11y_reduced_motion_focus.py`) is the model for honoring user/OS preferences; audio honors the same opt-in posture.

---

### 4. Gaps / new work (honest — none of this exists today)

| What | Why | Effort |
|---|---|---|
| **Audio asset hosting + delivery** | No audio lives in `static/`. Need a path: small UI cues embedded (data-URI / `static/audio/`) so they ship with the client; ambient loops served from `static/audio/` or a CDN. Licensing/sourcing of the actual sound files is **separate content work** and a real dependency. | **M** (decision: embed-vs-CDN; sourcing CC0/licensed loops is the long pole) |
| **Audio manager module (new client code)** | Web Audio context init (gated on first user gesture per autoplay policy), gapless looping, **crossfade** on zone change, master mute, `localStorage` persistence, disconnect-stops-all. No playback code exists. | **M-H** (the crossfade + autoplay-gesture handling are the fiddly parts) |
| **Zone → ambient-track map** | A small table keying `zone_type` (and `inSpaceMode`) → loop file, with a default/fallback for unmapped zones. Driven by the existing taxonomy, so it extends automatically as zones grow. | **S** (~50-line JSON; the audit below feeds it) |
| **`zone_type` completeness audit** | Verify `zone.properties.environment` is actually populated across `data/worlds/clone_wars/zones.yaml` and the DB — the map needs a real key per zone or everything falls to default. Read-only; report gaps. | **S** (grep + DB read; gaps logged, not auto-filled) |
| **UI-cue triggers (dice/hit/Force)** | Secondary scope. Cues key off events the client *infers* from `hud_update`/combat messages — reuse the **dice-drama tier** rather than instrumenting `combat.py`/`skill_checks.py` (avoid the engine lane). Cue plays only at drama-tier ≥ threshold, rate-limited. | **M** (best folded into the dice-animation drop, sharing its tier signal) |
| **Autoplay / permission UX** | Modern browsers block audio pre-gesture. Manager must no-op gracefully until the first click, and the `AUDIO` button *is* that gesture. Defensive only. | **S-M** |

---

### 5. Implementation sketch

- **Engine: nothing.** This is the rare feature where "extend a funnel, don't add a system" resolves to **touch no engine at all** — `_hud_zone` already emits the key signal. The *only* possible engine-adjacent work is the read-only `zone_type` audit (a grep over `zones.yaml`, no code), and — *if* UI cues land — reusing the `drama` field the dice-animation drop adds to the roll-result payload (no new producer; same funnel output). Do **not** add a `play_sound` server message or instrument the combat/skill funnels for audio.
- **Wire payload: unchanged.** Ambient keys off the existing `hud_update` `{zone_name, zone_type}` (and client-local `inSpaceMode`). UI cues, if built, consume the existing `drama` tier on the roll result — no new fields.
- **Client: a `SwAudio` manager + a toggle, mirroring named patterns.**
  - Toggle: clone the clean-mode handler (`client.html:13634-13647`) → `sw_audio_enabled` in `localStorage`, **default `'0'`**, `AUDIO`/`MUTE` label swap, restore-on-load. Button in `top-strip-right` (`:4369-4373`) with class `top-strip-btn`.
  - Manager: lazy-init the `AudioContext` on the toggle-on click (satisfies autoplay policy). On each `handleHudUpdate` (`:6498`), read `data.zone_type` + `inSpaceMode`, look up the track map, and **crossfade** to the new loop only when it differs from the playing one (diff via `lastHud`, already computed at `:6499`). Disconnect / toggle-off / tab-hidden → fade to silence.
  - Cues (phase 2): a `playCue(kind)` invoked from the same client seam the dice renderer uses, gated on `drama >= threshold` + the rate-limiter from the dice doc.
- **Test (mirror `tests/spa/` static-parse style, like `test_a11y_reduced_motion_focus.py`):** a `test_audio_toggle_contract.py` asserting against `static/client.html`: (1) an `AUDIO`/`MUTE` button exists in `top-strip-right`; (2) `sw_audio_enabled` is read/written via `localStorage` and **defaults to off** (regex the restore block for the `'0'`/falsy default — this is the load-bearing safety check); (3) the manager reads `zone_type` and `inSpaceMode`; (4) audio init is gated behind a user gesture (no top-level `new AudioContext()` outside a handler). If a jsdom runtime harness is used (per `tests/spa/spa_dom_harness.py`), additionally assert a synthetic `hud_update` with a changed `zone_type` triggers a track-change call while a *repeat* `zone_type` does not. Plus the read-only audit's output pinned as a fixture listing zones missing `environment` (so the map's default-fallback coverage is provable). **No engine unit test** — there's no engine change to pin.

---

### 6. Phasing

- **Tier: polish, post-launch.** Unlike dice (which animates the *signature mechanic* and earns a pre-launch slice), atmosphere is pure ambiance — it sits **behind** the launch blockers (map-nav, rally rework, QA tail) and behind the dice work whose `drama` tier it wants to borrow.
- **Pre-launch slice (optional, only if the tail is clear):** ambient-only, off-by-default, ground zones + space, **no UI cues** — i.e. the toggle + manager + a handful of loops (cantina / spaceport / market / deep-space) keyed off `zone_type`. This is the whole immersion payoff at a fraction of the risk, and ships independent of the dice drop.
- **Post-launch:** UI cues (folded into / following the dice-animation drop, sharing its `drama` tier), `time_of_day`/`weather` layering via `window._sw_env`, per-zone volume slider, and a richer track map as the zone taxonomy grows.
- **Open knobs (tune at build, not blockers):** crossfade duration, master ambient volume ceiling, cue rate-limit window (reuse dice's `N`), embed-vs-CDN delivery for ambient loops, default label polarity on the button.

---

---

*See also: `dice_animation_and_ux_polish_2026-06-22.md` (the ninth UX feature, `UX.dice_and_animation_polish`). All nine are queued in `TODO.json` under `tier_2_queued` as `UX.*`. Authority: `TODO.json` + `CHANGELOG.md` remain authoritative for current state; this doc is the design-of-record for the UX-engagement track.*
