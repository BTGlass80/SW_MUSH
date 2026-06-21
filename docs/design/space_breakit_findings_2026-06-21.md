# Space break-it sweep — confirmed findings (2026-06-21)

Adversarial fan-out across the space subsystem; **7 of 12** hypotheses independently reproduced. Conductor-owned fix lane (space-first launch posture).

## 1. [HIGH] +ship/uninstall emits 'An error occurred' after every successful uninstall (NameError: 'template' not defined in _uninstall_mod)
- **surface:** travel_state
- **symbol:** `parser/space_commands.py:1903 _uninstall_mod`
- **repro:** 1. Boot harness, era='clone_wars'. 2. Seed a modification into ship.systems['modifications']. 3. Board the ship (docked). 4. cmd(s, '+ship/uninstall 0'). 5. Assert 'an error occurred' not in output — FAILS. The mod IS successfully removed and item IS returned to inventory; the NameError fires only on the final slots-remaining send_line.
- **fix (verified):** Root cause is a name mismatch between the f-string (`template`) and the walrus binding (`t`) on lines 1903-1904 of parser/space_commands.py. Fix exactly as hypothesized: change `template.mod_slots` -> `t.mod_slots` (both occurrences) on line 1903.

Severity high, not blocker: the uninstall fully succeeds (mod removed from ship, component returned to inventory, DB persisted) and is NOT corrupted or rolled back by the crash — only the trailing "Slots remaining" confirmation line is lost and replaced by the scary generic error banner. So it is a user-trust/UX regression that fires on EVERY successful uninstall, not a data-integrity bug. It is invisible to the existing suite because no smoke/unit test seeds a mod and exercises the success path of _uninstall_mod (sibling sites at lines 1712, 1714, 1819 correctly use `template`, which is defined in the INSTALL method, masking the typo from casual review).

Effort to reproduce was E3 as predicted: had to seed systems['modifications'] directly via db.update_ship since crafting a real component is heavier; the slot-index path (+ship/uninstall

## 2. [HIGH] sell cargo <good> 0 triggers ZeroDivisionError (CRASH, swallowed as generic error)
- **surface:** ship_economy
- **symbol:** `parser/builtin_commands.py:5227 _handle_sell_cargo — per_ton = max(1, total_revenue // quantity)`
- **repro:** h = await _LiveHarness.boot(era='clone_wars'); ship, dock_room, _ = ...; s = await h.login_as('Test', room_id=dock_room, credits=5000); await h.cmd(s, f'board {token}'); await h.cmd(s, 'pilot'); # seed cargo via direct DB write; out = await h.cmd(s, 'sell cargo raw_ore 0'); assert 'error occurred' in out.lower()  # passes; # server log shows ZeroDivisionError
- **fix (verified):** Suggested fix (not applied; read-only task): add the same lower-bound guard the buy path has, after quantity is resolved in _handle_sell_cargo (around line 5168/5199), e.g. `if quantity is not None and quantity < 1: send "Quantity must be at least 1 ton." ; return`. Place it before line 5227. Verified via a standalone harness driver (now deleted) that boots _LiveHarness, resets engine.world_events._manager=None, and drives the live parser through h.cmd(); the gcw era has no docked ships so the repro was run under clone_wars (7 docked ships at boot).

## 3. [HIGH] land docking_fee drives credits negative via stale-cache TOCTOU (no allow_negative=False)
- **surface:** ship_economy
- **symbol:** `parser/space_commands.py:1352-1358 LandCommand.execute — actual_fee = min(char.get('credits',0), docking_fee); adjust_credits(-actual_fee, 'docking_fee') [no allow_negative=False]`
- **repro:** 1. Login as any character with 500 credits. 2. Board a ship and take pilot. 3. Launch (spends fuel, both memory and DB decrease). 4. While in space, another session or admin drains your credits to 0 (or simulate: @economy transfer). 5. Type: land. 6. Check credits — balance will be -25 (or -37 under LOCKDOWN alert). The 'Emergency landing!' message does NOT fire because char dict still shows the stale positive balance from before the drain.
- **fix (verified):** Severity: HIGH, not BLOCKER. It is a real credit-integrity violation (persisted negative balance, the exact class the recent hardening sweep targets), and the docking_fee sink is genuinely missing the allow_negative=False guard that its sibling space sinks have. But it is NOT a blocker because reproduction requires the in-space session's cached session.character["credits"] to diverge from the DB via an out-of-band drain — it is not reachable by a single player driving one session linearly (a normal launch writes the new balance back to char["credits"], keeping cache==DB, and the guard then works, as the control proves).

Realistic triggers for the stale-cache window (all real, none synthetic-only):
  - Admin drains the pilot's credits mid-flight via @economy / a direct adjust_credits sink (parser/director_commands.py:490 EconomyCommand).
  - The pilot is multi-sessioned: a `pay <other> <amt>` from a second device drains the DB (builtin_commands.py:5709-5721 p2p_transfer) while the in-space session's cache stays high.
  - Any background/cross-session sink that uses adjust_credits with

## 4. [HIGH] TELNET LEAK: space_choices and space_choices_dismiss payloads dumped as Python repr to player
- **surface:** space_combat
- **symbol:** `server/session.py:536-537 (send_json else branch), engine/space_encounters.py:354-375 (present_choices), engine/space_encounters.py:490-502 (_dismiss_choices)`
- **repro:** 1. Boot harness in telnet mode: s = await h.login_as('T', ..., protocol='telnet'); board+pilot+launch a ship. 2. Inject a pirate encounter (SpaceEncounter with choices). 3. Call enc_mgr.present_choices(enc, h.db, h.server.session_mgr). 4. Observe s.drain_text(): contains the full Python dict repr of the space_choices payload. 5. Do await h.cmd(s, 'respond pay'): output contains "{'encounter_id': 'enc-xxx'}" from dismiss.
- **fix (verified):** Root cause: server/session.py:536-537 send_json telnet fallback `else: await self.send_line(str(data))`. The three space-encounter typed messages (space_choices @ engine/space_encounters.py:370, space_choices_dismiss @ :498, space_choices_countdown @ :564) are pure web-client structured payloads with NO telnet text equivalent in the fallback, so they hit the catch-all str(data) dump. present_choices already sends the proper telnet menu via _send_telnet_choices(), and _send_deadline_warning already sends the proper telnet warning via send_line() — so the correct fix is to add these three msg_types to the telnet PASS set at session.py:532-535 (drop them silently on telnet, exactly like space_state/combat_state already are). This is a cosmetic UX leak (internal structure exposed to telnet players), not a data-integrity or security bug; severity high (visible garbage in normal gameplay on a sanctioned-but-degraded surface) rather than blocker. Per CLAUDE.md telnet is admin/purist-only with graceful degradation, which supports the silent-drop fix.

HUMAN WALKTHROUGH (telnet, real gameplay

## 5. [HIGH] buy cargo supply cap bypass on any ship where current_zone is empty or resolves to a planet=None zone
- **surface:** cross_state
- **symbol:** `parser/space_commands.py:5908 (_handle_buy_cargo `if planet:` supply gate) and parser/builtin_commands.py:5243 (_handle_sell_cargo `if planet:` demand gate); db/database.py:3441 (create_ship default systems missing current_zone)`
- **repro:** 1. Boot harness, get first docked ship. 2. Clear systems['current_zone'] directly in DB (simulates a never-launched or trade-route-landed ship). 3. login_as, board, do NOT launch. 4. `buy cargo raw_ore 1` → succeeds at flat base price with no supply check. Confirmed by harness run: 1 failed, 7 passed.
- **fix (verified):** Two corrections to the hypothesis, both verified in-harness:
1. The "trade-route-landed ship" sub-vector is REFUTED. `land` deliberately KEEPS current_zone (documented H4 fix, space_commands.py:1361-1370), and get_orbit_zone_for_room always returns a non-empty zone (falls back to default orbit). Verified: launch then land kept current_zone='coruscant_orbit'. So a landed ship is NOT in the empty-zone state.
2. The only realistic vector is the NEVER-LAUNCHED ship — but it needs no DB poking at all: every world-seeded ship AND every freshly +shipyard-bought ship is in the empty-zone state by default until its first launch. So the bug is player-reachable out of the box: buy a ship (or board a starter/seeded ship), board it, `buy cargo <good> <tons>` before ever launching.

Human walkthrough (BLOCKER-grade reachability, no admin/DB access):
  a) Board any docked ship you have not yet launched (your starter ship at first login works, or buy one via +shipyard at Kuat).
  b) Do NOT launch. From the bridge: `buy cargo raw_ore 15`. It succeeds.
  c) Repeat `buy cargo raw_ore 15` as many times 

## 6. [MEDIUM] sell cargo demand pool never saturates when docked at trade-route zone (planet=None after sublight transit to hyperspace lane + land)
- **surface:** cross_state
- **symbol:** `parser/builtin_commands.py:5243 (_handle_sell_cargo `if planet:` demand gate); engine/npc_space_traffic.py zone graph (CW trade-route zones: corellian_run, perlemian_trade_route, hydian_way, etc. all have planet=None)`
- **repro:** 1. Launch from any planet. 2. `course tatooine_deep_space` (if starting in tatooine_orbit), advance ticks until arrival. 3. `course corellian_run` from tatooine_deep_space, advance ticks until arrival (corellian_run has planet=None). 4. `land` — ship docks, current_zone='corellian_run', planet=None. 5. `sell cargo raw_ore 5` with cargo pre-loaded — demand pool not recorded, market never saturates.
- **fix (verified):** SEVERITY: the hypothesis's own "medium" is right for the SELL side, but it OVERSTATES the sell-side economic impact while UNDERSTATING that the buy side is the real exploit.

Sell-side is economically near-inert: at planet=None, get_planet_price(good, None) returns flat 100% base (None is in neither good.source nor good.demand). Demand depression only ever pulls the 140% demand-planet premium DOWN toward 100% (mult = max(PRICE_NORMAL, ...)). So selling at a null zone yields 100%, which is <= what any real demand planet pays. A rational trader never prefers the null zone to sell; "never saturates" is true but harmless. The unrecorded DEMAND_POOL sale also can't corrupt other planets' pools (keyed by planet).

The BUY side is the genuine money-printer and should be the headline: the per-planet SUPPLY_POOL cap (the exact mechanism that exists to stop ~240,000 cr/hr cargo-loop grinding, per the code comment at 5905-5906) is fully bypassed. Loop = park at corellian_run/coruscant_deep_space-adjacent lane, blind-buy unlimited raw_ore at ~100cr/t, transit to kuat/coruscant (raw_ore.demand), 

## 7. [LOW] space_fine deducts from stale cache without allow_negative=False — same class as docking_fee corruption
- **surface:** ship_economy
- **symbol:** `parser/space_commands.py:5513-5515 CustomsCommand (or space_inspection handler) — same stale-cache pattern as LandCommand docking_fee`
- **repro:** 1. Have a character trigger customs inspection (land at a port with contraband or high alert zone, or use the customs command path). 2. While customs is being resolved, drain DB credits below the calculated fine via concurrent action. 3. Fine is assessed against stale cache value — adjust_credits(-paid) without guard → negative balance.
- **fix (verified):** Real but bounded, adversarial-only, player-self-harming overdraw: a player would have to drain their own DB balance below the assessed fine during their own ship-landing customs check. The customs path itself is gated by RNG, smuggling-job state, and skill checks, and never blocks landing. This is a KNOWN, DOCUMENTED, ACCEPTED lower-tier residual from the 2026-06-21 credit-sink sweep — not an unaddressed straggler of the high-severity unguarded fixed-cost class. The hypothesis correctly identifies the code (5513-5515) and the mechanic, but mis-rates severity (claims high; should be low) and mis-states the baseline (claims docking_fee was confirmed/fixed corruption; in fact docking_fee is in the same SAFE-by-construction bucket and equally unguarded by design). Fix if desired = swap to allow_negative=False + drop the min() clamp (let the chokepoint refuse the overdraw), matching the 22 hardened sinks; but per the audit this is intentionally deferred as bounded/low-priority.
