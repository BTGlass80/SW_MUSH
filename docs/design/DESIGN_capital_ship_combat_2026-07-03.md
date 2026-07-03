# DESIGN — Real Ship-vs-Ship Capital Combat as a Chain-Completable Feature

Status: BUILDABLE (composition + one small new seam). HEAD-verified against every loader, matcher, seam, and
balance-guard cited below (2026-07-03).

Author: Opus design-synthesis. Brian directive: "design + build real ship battles."

**One-line thesis:** The space-combat *fight machinery* (spawn → promote → tick-fire → kill) is already
capital-capable and needs **zero** engine change. The only missing piece is a **space-combat → chain event
bridge**: a per-ship chain tag + a ~6-line hook at the one kill chokepoint + a new completion type that mirrors
`on_combat_won`. This doc specifies that bridge, the WEG-D6 capital target, the winnability shape, the first
slice, and the genuine forks for Brian.

---

## 0. Why this exists (the gap the 36th arc could not close)

The just-shipped 36th arc, *The Phantom Tonnage* (`DESIGN_36th_arc_big_ship_spec_2026-07-03.md`), realizes
"big-ship combat" as **person-scale ground combat aboard a capital liner** — deliberately, because
(§2/§10 fork #1) there is **NO capital-ship-as-combatant seam**:

- `ALLOWED_COMPLETION_TYPES` (`engine/tutorial_chains.py:59`, HEAD-verified) has 11 types — `combat_won` is
  **ground-only** — and **no** `ship_destroyed` / `space_combat_won`.
- Space combat (`engine/starships.py`, `parser/space_commands.py`, `engine/npc_space_combat_ai.py`) emits
  **no chain event anywhere** — grep-confirmed: the only chain reference in `parser/space_commands.py` is a
  planet-arrival trigger at line 1454, unrelated to kills. `handle_traffic_ship_destroyed` /
  `_handle_combat_end` fire nothing chain-relevant.

So a chain step **cannot** complete on "destroy capital ship X." The 36th-arc spec logged the true
ship-vs-ship path as exactly *"a new `ALLOWED_COMPLETION_TYPES` value + a space-combat → chain bridge"* and
punted it as a non-blocking future fork. **This doc is that fork, designed and specced.**

---

## 1. What "real ship-vs-ship capital combat" IS, in concrete terms

A **questline step** whose completion is: *fly to (or intercept) a capital-class hostile, fight it
ship-to-ship with `fire` / maneuver / lock-on, and win — where "win" = the capital target is destroyed
(hull threshold crossed).* The player fights **from a capital-scale ship** (scale parity is required for a
winnable capital duel — see §6); the target is **one beatable light-capital escort**, not a Venator, not an
ISD, and not a fleet. The step advances the instant the target's hull crosses its destruction threshold, and
graduation teleports/rewards fire exactly as every existing chain step does.

Crucially this is **not** the 36th arc's aboard-a-ship ground fight. This is a genuine **space-combat
resolution** (a ship dies on the SpaceGrid) driving a chain step — the axis the roster has never had.

---

## 2. The live space-combat machinery is already capital-capable (EXISTS — do NOT rebuild)

All symbols HEAD-verified. The fight loop is fully reusable for capital ships:

| Stage | Reused symbol (EXISTS) | Capital-ready? |
|---|---|---|
| Spawn one hostile in a specific zone | `NpcSpaceTrafficManager.spawn_for_encounter(db, session_mgr, zone_id, archetype)` (`npc_space_traffic.py:1056`) — no wander route, holds station, returns `(TrafficShip, template_dict)` | YES — accepts any template |
| Promote to live combatant | `NpcSpaceCombatManager.promote_to_combat(...)` (`npc_space_combat_ai.py:161`) — reads `tmpl.hull`→`total_pips()`=`hull_max_pips`, `tmpl.speed`, `tmpl.scale_value`; `SpaceGrid.add_ship(...)` | YES — reads scale generically; `scale_value`=6 for capital |
| The capital fights back | `NpcSpaceCombatManager.tick` (`:253`) → `_select_action` → `_do_fire` → `resolve_space_attack` | YES — scale-agnostic |
| Player fire + kill detect | `FireCommand.execute` (`space_commands.py:2380`) → `_apply_hull_damage` (`:2784`): writes `hull_damage`, `destroyed_threshold = hull_dice*6`, crosses → tear down + reward + wreck | YES — capital hull → higher threshold, same code |
| Range/position/lock-on | `SpaceGrid` (`starships.py:168`) — keyed only on ship_id + speed | YES — fully scale-agnostic |
| Damage resolution | `resolve_space_attack` (`starships.py:728`) — R&E Ch.10; `scale_diff = target_scale − attacker_scale` applies ±dice to **both** to-hit and damage | YES — capital-vs-capital → `scale_diff 0` → clean |

**Proof it already runs:** `course anomaly <id>` → `CourseCommand._engage_combat(kind="patrol")`
(`space_commands.py:3695`) already `spawn_for_encounter`s + `promote_to_combat`s a **capital** ship today —
the PATROL template resolves via `_pick_patrol_template` to `consular_cruiser` (`scale: capital`, hull `3D+1`).
A capital hostile that returns fire is live on `main`. The *only* thing that never happens is the **kill
crediting a chain step.**

---

## 3. THE BRIDGE — the exact new seam (this is the whole feature)

### 3.1 What fires today when a ship dies (EXISTS)

`FireCommand._apply_hull_damage` (`space_commands.py:2784-2864`), on threshold cross:
1. `destroy_combatant(..., already_rewarded=True)` — combat-AI teardown (`:2820`).
2. `handle_traffic_ship_destroyed(target_ship["id"], ctx.session.character, ctx.db, ctx.session_mgr)`
   (`:2832`) — **PIRATE-only** credit bounty, then `_despawn` → `delete_traffic_ship`.
3. `add_wreck_anomaly(...)` salvage (`:2843`).
4. `on_ship_destroyed(ctx.db, ctx.session.character["id"], ...)` — achievement, a **global** counter, not
   chain-aware (`:2858`). **← this is the exact hook shape the new chain hook parallels.**

`handle_traffic_ship_destroyed` (`npc_space_traffic.py:1829`) is the **single convergence point**: both kill
paths funnel through it exactly once — the fire path (from `space_commands.py:2832`) and the NPC-tick
self-kill path (from `_handle_combat_end:577`, only when `already_rewarded=False`). It already carries
`player_char` (used as `player_char["id"]`/`["credits"]` at `:1841`), `db`, and `session_mgr` — **everything a
chain dispatcher needs.** It despawns at `:1843`, so any hook must run **before** despawn and must read the
tag off the in-memory `TrafficShip` (the DB row is about to be deleted).

### 3.2 The one genuinely-new data wrinkle

Ground combat identifies its chain foil via `ai_config_json.chain_enemy_template` on a persistent NPC row
(`combat_commands.py::_collect_defeated_chain_templates:994`). **Space targets have no equivalent field.**
Confirmed at HEAD: `TrafficShip` (`npc_space_traffic.py:684-716`) has routing/timing/hail/pirate/hunter/
display fields — **no `chain_*` anything**; `SpaceNpcCombatant` (`npc_space_combat_ai.py:103`) has no chain
field; `promote_to_combat` has no chain param. So the foil tag is **NEW plumbing with no current analog** — it
is the real design surface, and it is small.

### 3.3 The bridge — three NEW pieces (the entire engine delta)

**(A) NEW field on `TrafficShip`** (`npc_space_traffic.py:684`), the space analog of ground
`ai_config.chain_enemy_template`:
```python
chain_enemy_ship_template: str = ""   # non-empty => destroying this ship credits a space_combat_won step
```
+ one line each in `to_json` (`:753`) / `from_json` so it survives a persist/reload mid-fight.

**(B) NEW seed** where the tagged capital target is spawned — a dedicated deterministic spawn for the
questline battle (§5), NOT the random ambient/anomaly spawn. Sets `ts.chain_enemy_ship_template = "<tag>"`,
`ts.transponder_type = "combat"`, and a distinct `ts.display_name` so `fire <name>` targets it (mirrors the
existing `_engage_combat` pirate-callsign pattern at `space_commands.py:3734`).

**(C) NEW ~6-line guarded hook** inside `handle_traffic_ship_destroyed` (`:1829`), **before** `_despawn`
(`:1843`), paralleling the neighboring `on_ship_destroyed` achievement hook's try/except shape:
```python
if ts.chain_enemy_ship_template:
    try:
        from engine.chain_events import on_space_combat_won
        await on_space_combat_won(db, player_char, ts.chain_enemy_ship_template, 1)
    except Exception:
        log.warning("[traffic] space_combat_won chain hook failed", exc_info=True)
```
Because this sits at the single chokepoint, **one insertion covers both kill paths.** `player_char` here is
already the `ctx.session.character` dict — the exact shape `on_space_combat_won` expects.

> **Builder note (tick-path attribution):** the fire-kill path is the *credited* path — it always has a real
> PC winner (`ctx.session.character`). The NPC-tick self-kill path (`_handle_combat_end:577`) passes whatever
> `player_char` it holds; guard the hook so it only fires for a real PC dict (the `if ts.chain_enemy_ship_template`
> gate + the surrounding try/except make a non-PC caller a safe no-op). In practice `apply_damage_to_npc` is
> dead code (the SPACE.b1 comment at `space_commands.py:2809`), so the fire path is the live path.

### 3.4 How the dispatcher reuses `on_combat_won`-style accumulation (NEW, mirrors EXISTS)

In `engine/chain_events.py`, mirror the ground `combat_won` pair (`_match_combat_won:292` +
`on_combat_won:458`):

- `_match_space_combat_won(completion, ship_template, count) -> bool` — mirror of `_match_combat_won:292`:
  `completion.enemy_ship_template == ship_template` (exact) **AND** `count >= completion.enemy_count`
  (default 1).
- `async def on_space_combat_won(db, char, ship_template, count=1) -> bool` — mirror of `on_combat_won:458`.
  **First slice (enemy_count:1):** call `_try_advance_all_slots(db, char, event_type="space_combat_won",
  matcher=lambda c: _match_space_combat_won(c, ship_template, count))` directly — the multi-kill tally is
  **not needed** for a single target, so no `record_combat_kills` call. **Optional parity extension:** if a
  future "destroy 2 of 3 escorts" step is wanted, add the same per-slot `record_combat_kills` accumulation
  `on_combat_won` uses (safe — the tally is keyed by template string; a ship template never collides with a
  ground template, and a player is only on one combat step per slot at a time).

**Everything downstream is 100% reused, unchanged:** `_try_advance_all_slots:930` → `_try_advance:966`
(the `event_type` gate at `:1066` + the matcher gate at `:1069`) → `advance_step` (`tutorial_chains.py:692`)
→ `chain_rewards` / `chain_graduation` teleport / merge-persist. A `kind: questline` arc rides the same
`active_questline` slot with zero further engine code.

### 3.5 Graduation follow-up (reuse)

The ground path runs `execute_pending_teleport` on the survivor's session after `on_combat_won` returns True
(`combat_commands.py:486-507`). The space seam already lives in an async command context (`FireCommand`), and
the chain graduation teleport is applied inside `_try_advance` via `chain_graduation`, so no separate
teleport-drive is needed at the fire seam — but the builder should confirm the graduating player's session
receives the standard graduation broadcast (the questline slot's normal path handles it).

---

## 4. The new completion type — `space_combat_won`

**Name:** `space_combat_won` (chosen over `ship_destroyed` — it reads as a *win condition*, parallels
`combat_won`, and leaves room for a future disable/board variant without renaming).

**Where it registers (must be kept in sync or CI breaks):**
1. `engine/tutorial_chains.py:59` — add `"space_combat_won"` to `ALLOWED_COMPLETION_TYPES`. This is the ONLY
   runtime gate (`tutorial_chains.py:456-463` rejects any step whose `completion.type` is unknown at
   corpus-load). No dataclass change — `TutorialStep.completion` (`:106`) is a raw dict, so the new inner
   shape (`enemy_ship_template`, optional `enemy_count`) needs no schema edit.
2. `tools/verify_tutorial_chains.py:40` — the schema linter's own copy of the set (commit gate).
3. `tools/verify_jedi_village.py:49` — second linter copy (village-specific; a duplicate of the set — keep in
   sync so the linter doesn't reject an unknown type).
4. `tests/test_f8_tutorial_chains_yaml.py:306-312` imports the real frozenset and auto-covers once registered;
   `:732` pins the exported symbol names — add `space_combat_won` there if it enumerates members.
5. Flip the intended-gap doc-strings: `tests/test_generalized_questline_phantom_tonnage.py:17` and the NPC
   file header (`npcs_drop_generalized_questline_phantom_tonnage.yaml:16,27`) currently *assert the gap*
   ("`ALLOWED_COMPLETION_TYPES` has no ship_destroyed / space_combat_won") as prose markers — update them to
   note the gap is now closed.

**Completion predicate:** a step with
```yaml
completion:
  type: space_combat_won
  enemy_ship_template: "<tag>"     # matched exactly against the destroyed ship's chain_enemy_ship_template
  enemy_count: 1                    # optional, default 1
```
advances when the player destroys a hostile whose `TrafficShip.chain_enemy_ship_template == enemy_ship_template`
and the running destroyed-count `>= enemy_count`.

**How it is detected:** §3.3 hook at `handle_traffic_ship_destroyed` → `on_space_combat_won` →
`_match_space_combat_won` → `_try_advance_all_slots`. Single chokepoint, both kill paths, before despawn.

---

## 5. How a questline step triggers + resolves the battle

**Trigger (start the battle) — reuse the `course anomaly` promote pattern, deterministically.** Add a dedicated
spawn for the chain battle rather than relying on a random anomaly roll. Two clean shapes (see fork #8):

- *Recommended:* a **preceding `command_executed` step** on an intercept/course verb (e.g. the player is told
  to `course <target>` / `intercept <callsign>`) whose handler calls a new `_engage_combat(kind="chain_target")`
  branch (or a small `spawn_chain_capital(zone_id, template, tag, display_name)` helper). That branch:
  `spawn_for_encounter(zone, PATROL-or-a-new-archetype)` with a **capital** template → set
  `ts.chain_enemy_ship_template = tag`, `ts.transponder_type = "combat"`, `ts.display_name = "<name>"` →
  `promote_to_combat(..., template_key=<capital template>, profile=..., starting_range=SHORT)` →
  `ts.in_live_combat = True`. This mirrors `_engage_combat` (`space_commands.py:3715-3751`) exactly.
- *Alternative:* a `room_entered` step on the target zone auto-spawns the hostile on arrival.

**Resolve (win the battle) — reuse the live kill seam.** Player fires (`fire <name>`) → `resolve_space_attack`
→ `_apply_hull_damage` crosses `hull_dice*6` → `destroy_combatant` + `handle_traffic_ship_destroyed` → **§3.3
hook** → `on_space_combat_won` → `_match_space_combat_won` → step advances → graduation teleport/reward. The
capital returns fire the whole time via the NPC combat tick, so it is a real duel, not a turkey-shoot.

**Reward — reuse chain machinery, add NO traffic reward branch.** `handle_traffic_ship_destroyed` pays only
PIRATE bounty; a chain capital-target would award 0 there. That is **correct and intended** — the payout comes
from the **chain step `reward` + `graduation`** (`chain_rewards.py`: `adjust_credits` / `adjust_rep` /
achievements), exactly like every ground `combat_won` arc pays via the step, not a mob loot table. Zero new
reward code. (A new `WARSHIP` archetype reward table would only matter for *ambient* non-chain capital kills —
out of scope; see fork #7.)

---

## 6. WEG-D6 capital target + winnability (the balance core)

**Stats are already WEG-D6.** `ShipTemplate` (`starships.py:452`): `hull`/`shields`/`maneuverability` are D6
strings, `weapons` are `ShipWeapon` with `damage`/`fire_control` dice + `skill`. `resolve_space_attack` is a
faithful R&E Ch.10 implementation. Scale is **binary**: `SCALE_STARFIGHTER=0`, `SCALE_CAPITAL=6`
(`starships.py:42-43`); `scale_diff` applies ±6D to both to-hit and damage.

### 6.1 The root balance fact (why solo starfighter-vs-capital is unwinnable)

`resolve_space_attack:839-841`: starfighter hitting capital → **damage `max(1, dice − 6)`**. A capital is
*trivial to hit* (`+6D` to-hit) but the shot is *absorbed*: e.g. ARC-170 proton torpedo `9D` → `max(1, 9−6)`
= **3D** (~10.5 avg) versus a light capital's hull+shields soak (`~4D+3`, ~16.5 avg). To *destroy* a
`3D+1`-hull capital you must accumulate `hull_dice*6 = 18` pips of `hull_damage` through margin-crossing hits
that a 3D shot rarely lands. **Confirmed: a lone starfighter cannot meaningfully damage a capital.** This is
the exact reason *The Phantom Tonnage* went person-scale.

### 6.2 Winnability approach — scale parity + a single beatable light-capital target

Two levers make a capital duel winnable and bounded, **conservatively**:

1. **The player fights FROM a capital-scale ship** → `scale_diff = 0` → normal R&E capital-vs-capital math
   (turbolasers 4D–5D vs soak, no ±6D swing). See fork #2 for *how* the player gets that ship.
2. **The target is ONE new light-capital escort**, statted *low* so a player capital's turbolasers reliably
   beat soak and cross the destruction threshold in a **bounded** number of rounds — not a Venator (hull
   `4D` → 24-pip threshold, a marathon) and not an ISD (`7D` → 42 pips, unwinnable-feeling).

**Proposed new WEG-D6 template — a light corvette/escort "the *first beatable capital*":**
```
scale: capital
hull:            2D+2      # threshold = hull_dice*6 = 12 pips  (bounded: a handful of solid turbolaser hits)
shields:         1D        # low soak -> player turbolasers beat it reliably
maneuverability: 1D
speed:           4
weapons:
  - a single light turbolaser (damage ~3D, fire_control 2D, capital_ship_gunnery)   # it fights back, but lightly
```
Math check (player in a capital firing a 4D turbolaser, `scale_diff 0`): damage `4D`(~14) vs target soak
`hull 2D+2 + shields 1D = 3D+2`(~12.5) → beats soak most rounds; each clear hit stacks 1/2/4 `hull_damage`;
~12-pip threshold falls in a small, satisfying number of rounds. Its own `3D` return fire vs a player capital's
`hull+shields` soak is survivable (real jeopardy, not a death sentence). This is a **real duel that the player
wins** — the "single beatable capital target" the brief calls for. **Provenance:** re-stat from a canonical
WEG light-capital escort against `WEG40120` at build time; the numbers above are a conservative sketch to
verify, not final. Cross-check the destruction-threshold pacing against `_apply_hull_damage`'s `hull_dice*6`.

**Era-clean:** the target is a **generic civilian/syndicate/pirate light warship or a customs cutter gone
rogue** — NO Imperial/Empire/Rebel/TIE strings, NO canonical Clone Wars figures, NO Republic-Navy warship
framing; keep the arc `independent`/faction-neutral like its 35+ peers.

**`force_sensitive` derived:** any NPC crew/captain authored for the arc gets `force_sensitive` reconstructed
from `control`/`sense`/`alter` keys — never passed as a `save_character` kwarg. (A ship template has no
`force_sensitive`; this only applies to any human NPC the arc adds, e.g. a stand-down captain.)

---

## 7. Reuse map (compose, do not rebuild)

| Concern | REUSED (EXISTS) | seam |
|---|---|---|
| Spawn one capital hostile in a zone | `spawn_for_encounter` (`npc_space_traffic.py:1056`) | called from the new chain-battle spawn branch |
| Build the combatant from a capital template | `promote_to_combat` (`npc_space_combat_ai.py:161`) | reads hull/speed/scale generically |
| Capital returns fire / maneuvers | `NpcSpaceCombatManager.tick` / `_select_action` / `_do_fire` (`:253+`) | unchanged |
| Player fire + capital-scale damage + kill detect | `FireCommand` / `resolve_space_attack` / `_apply_hull_damage` (`space_commands.py:2380/2784`, `starships.py:728`) | unchanged |
| **Single kill chokepoint** | `handle_traffic_ship_destroyed` (`npc_space_traffic.py:1829`) | **← the ~6-line NEW hook** |
| Range/position/lock-on | `SpaceGrid` (`starships.py:168`) — scale-agnostic | unchanged |
| Chain advance/accumulate | `_try_advance_all_slots` / `_try_advance` / `advance_step` | reused verbatim by `on_space_combat_won` |
| The mirror pattern | `on_combat_won` / `_match_combat_won` (`chain_events.py:458/292`) | **mirrored** into `on_space_combat_won` / `_match_space_combat_won` |
| Rewards / graduation | `chain_rewards.py` / `chain_graduation` (teleport) | per-step `reward` + `graduation` |
| Questline container | `tutorial_chains.py` (`kind: questline`, `active_questline` slot) | new chain in `chains.yaml` |

| GENUINELY NEW | file |
|---|---|
| `space_combat_won` in `ALLOWED_COMPLETION_TYPES` + 2 linter copies + test-doc flips | `tutorial_chains.py:59`, `tools/verify_tutorial_chains.py:40`, `tools/verify_jedi_village.py:49`, tests |
| `_match_space_combat_won` + `on_space_combat_won` | `engine/chain_events.py` |
| `TrafficShip.chain_enemy_ship_template` field + `to_json`/`from_json` lines | `engine/npc_space_traffic.py:684` |
| ~6-line kill hook | `engine/npc_space_traffic.py:1829` (before `:1843`) |
| Dedicated chain-battle capital spawn (`_engage_combat` branch or `spawn_chain_capital` helper) | `parser/space_commands.py:3695` area |
| New light-capital WEG-D6 escort template | `data/worlds/clone_wars/starships.yaml` |
| The arc itself (chain steps + trigger step + any NPC + achievement) | `chains.yaml`, npcs drop, `achievements.yaml` |

**Explicitly NOT reused (and why):** `engine/wilderness_anomalies.py` multi-phase "wave" combat — parallel and
unbridged (hardcodes `is_anomaly_target`, never passes a chain tag, never calls `on_*`); bridging it would be
*more* new engine code than this seam. `world_events`/`staged_event` cult machinery — a global menace counter,
not a per-target kill. Neither is needed.

---

## 8. First slice (smallest shippable proof)

The vertical slice that proves the bridge is **one questline step that fights + destroys one capital target**:

1. Register `space_combat_won` (frozenset + 2 linter copies + test doc-flips) — §4.
2. Add `TrafficShip.chain_enemy_ship_template` + `to_json`/`from_json` — §3.3(A).
3. Add `_match_space_combat_won` + `on_space_combat_won` (single-hit, no tally) — §3.4.
4. Add the ~6-line hook in `handle_traffic_ship_destroyed` — §3.3(C).
5. Add ONE dedicated capital-battle spawn that tags one light-capital hostile (§6 template) with a step tag,
   in a zone, promoted to combat — §5 / §3.3(B).
6. Add a **two-step** questline (or a two-step addition to an existing space arc):
   - step A `type: command_executed` (the intercept/course verb that fires the spawn),
   - step B `type: space_combat_won` / `enemy_ship_template: <tag>` that completes on the kill → graduation
     (credits via chain reward).
7. Provision the player a capital-scale ship for the battle — for the slice, the **simplest** provisioning
   (fork #2): the battle assumes the player is in / is given command of a capital hull (scale parity). If no
   solo-capital exists yet, the slice can hand a temporary capital-scale command for the encounter.

Proving criterion: destroy the tagged light-capital in space → the `space_combat_won` step advances and the
questline graduates. That single observed advance is the whole feature de-risked; the arc's prose, NPCs, and
polish layer on after.

**Per-drop test file (hygiene-required):** `tests/test_space_combat_won_bridge.py` — assert the type is
registered, `on_space_combat_won` advances a `space_combat_won` step on a tag match and no-ops on a mismatch,
and the chain loads with the new completion shape. Mirror `tests/test_generalized_questline_papered_refit.py`
for the arc-structure slice.

**Validation gate:** targeted `pytest` for `chain_events` / `tutorial_chains` / the new test + the four
questline balance guards (`test_chain_corpus_reachability_invariant`, `test_questline_reward_tier_consistency`,
`test_questline_skill_difficulty_winnability`, `test_questline_foil_winnability_band`);
`python tools/verify_tutorial_chains.py`; AST-validate touched `.py`, YAML-validate touched data; full
`run_all_tests.bat` is the merge gate.

> **Guard caveat to design around:** `test_questline_foil_winnability_band` reads a `combat_won` foil's
> **ground-NPC sheet** (dex/blaster/dodge). A `space_combat_won` foil is a **ship stat block**
> (hull/shields/scale), balanced by the space math, not the ground band. Because we use a **distinct**
> completion type (not reused `combat_won`), the guard's foil-collection keys off `combat_won` and simply
> **does not see** the ship foil — no crash, no false red. If Brian ever wants a space-foil winnability guard,
> add a *separate* assertion keyed on `enemy_ship_template` → the ship template's hull/shields vs a player
> capital (a new, small guard — do not overload the ground band). This is precisely why the distinct type
> (fork #1) is the clean choice.

---

## 9. GENUINE FORKS for Brian (each a concrete either/or + tradeoff)

1. **Completion-type strategy — NEW `space_combat_won` type *(recommended)* vs REUSE `combat_won` with a ship
   tag.** New type: touches `ALLOWED_COMPLETION_TYPES` + 2 linter copies + test docs, but keeps the
   foil-winnability guard clean (it keys off `combat_won` and never tries to read a ship as a person sheet) and
   reads honestly in the corpus. Reuse-`combat_won`: fewer lines, zero frozenset change — but the guard tries
   to load a ship as a ground-NPC sheet (blind/misleading) and the corpus can't tell a person kill from a ship
   kill. *Tradeoff: clarity + guard-correctness vs a slightly smaller diff.* Recommend the NEW type.

2. **Who is the player's ship? — a provisioned SOLO-FLYABLE capital *(recommended for the first slice)* vs the
   player's OWN ship (starfighter → unwinnable, §6.1) vs a CREWED multi-gunner capital.** Scale parity is
   mandatory for a winnable duel. Solo-flyable capital ships now (arc grants/assumes a capital command for the
   encounter). Crewed multi-gunner is the richer "real capital bridge" fantasy but needs crew/gunner-seat
   mechanics — **does a multi-crew gunnery seat model exist today? If not, that is its own build.** *Tradeoff:
   ships now vs the crewed-capital fantasy.* Recommend solo-flyable for the slice; crewed as a later arc.

3. **The single target — a NEW LIGHT-CAPITAL escort statted beatable *(recommended)* vs an existing
   Venator/named capital.** Light escort (§6.2, hull ~`2D+2`/shields `1D`) → destroyed in a bounded, satisfying
   number of rounds. Venator (hull `4D` → 24-pip threshold) is a marathon slug; ISD (`7D` → 42) feels
   unwinnable. *Tradeoff: winnability + pacing vs spectacle/name-recognition.* Recommend the new light-capital.

4. **Win condition — DESTROY *(recommended)* vs DISABLE/BOARD.** Destroy rides the existing NPC-ship kill seam
   (`handle_traffic_ship_destroyed`) → ships now. Disable-and-board fits capture/boarding themes and the
   Phantom-Tonnage aesthetic, **but NPC ships have no "disabled" state today** — only *player* ships are
   disabled-not-destroyed (`_do_fire`/`_handle_combat_end` asymmetry); an NPC disable + board is a NEW seam
   (ion-to-cripple threshold + a board-a-crippled-capital verb). *Tradeoff: reuse-now vs a richer capture verb.*
   Recommend destroy for the first slice; disable/board as a future extension of the same bridge.

5. **Battle arena — REUSE the live anomaly/traffic space *(recommended)* vs a NEW instanced set-piece arena.**
   Reuse: the existing SpaceGrid/zone, `promote_to_combat` as-is, ambient traffic may be present. New arena:
   controlled, no ambient interference, cinematic staging — but new instancing/zone-lifecycle code. *Tradeoff:
   reuse-now vs authored control.* Recommend reuse the live space.

6. **Fleet size — `enemy_count: 1` *(recommended)* vs a small escort screen (2–3).** One capital matches the
   "single beatable target" and needs no kill-tally. A screen delivers the fleet feel but needs the
   `record_combat_kills` accumulation path (parity with `on_combat_won`) **and** raises the multi-target
   soft-lock risk the fun-drive kept hitting; no open-world questline ships `enemy_count > 1` today. *Tradeoff:
   conservative-and-safe vs the fleet fantasy.* Recommend 1; a 2–3 screen is a deliberate, playtested item to
   raise separately.

7. **Reward path — CHAIN STEP reward only *(recommended, zero new code)* vs a NEW `WARSHIP` archetype reward
   branch in `handle_traffic_ship_destroyed`.** Chain-reward-only: the questline pays via `chain_rewards` like
   every ground `combat_won` arc; the traffic manager stays PIRATE-only. WARSHIP branch: needed **only** for
   *ambient* (non-chain) capital kills to pay out — out of scope for a chain feature. *Tradeoff: minimal +
   consistent vs ambient-capital-kill economy (a separate initiative).* Recommend chain-reward-only.

8. **Battle trigger shape — a preceding `command_executed` course/intercept step *(recommended, mirrors
   `course anomaly`)* vs a `room_entered` zone-entry auto-spawn.** Command step: explicit player commit, mirrors
   the live `_engage_combat` promote. Zone-entry: more ambient/cinematic (you jump in and they're on you) but
   spawns on transit rather than on a deliberate act. *Tradeoff: explicit commit vs ambient arrival.* Recommend
   the command step for the first slice.

---

## 10. Buildability verdict

**BUILDABLE = true.** The fight machinery is already capital-capable and runs on `main` today (a capital
PATROL is spawned + promoted + fought via `course anomaly`). The entire feature reduces to a **small,
well-bounded bridge**: one new completion type (registered in 3 places + 2 test-doc flips), one new
`TrafficShip` tag field, a ~6-line hook at the single kill chokepoint, a mirror of the `on_combat_won`
dispatcher, one deterministic capital-battle spawn, and one new WEG-D6 light-capital template — plus the arc
data. No new top-level system, no rebuild of space combat, no new engine subsystem. Everything downstream of the
hook is reused verbatim. The winnability is solved conservatively (scale parity + a single beatable light
capital, not a fleet). The genuine decisions (completion-type strategy, player-ship provisioning, target class,
destroy-vs-disable, arena, fleet size, reward path, trigger shape) are logged as forks §9 for Brian, with a
recommended default for each so the first slice can proceed on the conservative path.
