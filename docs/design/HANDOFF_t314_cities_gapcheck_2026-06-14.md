# T3.14 Player Cities — Gap-check findings

*Main-march session, 2026-06-14 PM. Worktree C:/SW_MUSH_live. Method: 16-feature
verification workflow (engine + parser + client per area) vs
`docs/design/player_cities_design_v1_2.md` + the roadmap expansion; every non-DONE
verdict adversarially rechecked. **0 of the gaps were refuted** — all confirmed at
HEAD with file:line evidence. Workflow run wf_e4e2598b-a62.*

## Headline
The Player-Cities **core is heavily built** — `engine/player_cities.py` (~60 funcs),
`parser/city_commands.py` (`+city` switch), `engine/city_guard_runtime.py`,
`engine/security.py`, the schema, the look-tag, and the SPA city panel. 8 of 16 areas
fully DONE. The gaps are (a) a few small client/parser polish items, (b) larger
launch-spec phases gated on other systems, and (c) the roadmap expansion items.

## Verified status (16 areas)
| Area | Overall | Effort | Note |
|------|---------|--------|------|
| C1 founding | **DONE** | — | cost numbers match §2.3; debits via `adjust_org_treasury` |
| C2 expansion (claim/release/rate) | **DONE** | — | |
| C3 governance/roles/mayor | PARTIAL | small | only `+city events` missing (Director-dependent) |
| C4 founder/banishment | **DONE** | — | |
| C5 taxation | **DONE** | — | |
| C6 citizen benefits | PARTIAL | small | **client buttons** missing — SHIPPED below |
| C7 NPC guards | PARTIAL | medium | entry-trigger seam unwired + §23 density unbuilt |
| C8 decay/dissolution | PARTIAL | large | refund-formula fork + no dissolve-confirm + §8.4 takeover unbuilt |
| C9 Director integration | MISSING | medium | **parallel session's lane — DEFER** |
| C10 schema | **DONE** | — | |
| C11 command surface | PARTIAL | small | only `+city events` missing (= C3) |
| C12 look integration | **DONE** | — | |
| C13 client city panel | **DONE** | — | |
| C14 multi-city-per-org *(expansion)* | MISSING | large | one-per-org hard-gated; ~15 call sites |
| C15 paged sub-modals *(expansion)* | MISSING | small | **SHIPPED below** |
| C16 P2P discovery *(expansion)* | PARTIAL | large | `+city list` exists; §19 richer discovery unbuilt, gated on SYN.4 |

## SHIPPED this session (drop `cities-client-polish`, client-only)
- **C6** — added the missing web buttons for already-built parser commands: citizen-room ON/OFF toggle (mayor/founder-gated) + City Home teleport (citizen+). `static/client.html`.
- **C15** — `_cityPagedListSection` (pageSize 10, independent page state, Prev/Next via addEventListener) for the citizens/guests/banishments lists in the city modal.
- `tests/spa/test_cities_client_polish.py` (21) + onclick regression (4) green.

## DEFERRED — for the loop / Brian (with rationale)
- **C9 Director integration** — needs `engine/director.py` (city digest block + Phase-9 wilderness encounter roll). **Brian: strictly avoid the parallel session's director lane.** DEFER until coordinated.
- **C7 guards** — (1) wire `filter_for_city_guard_engagement()` (engine/city_guard_runtime.py:214, currently no callers) into the room-entry hostile check (parser/builtin_commands.py `_check_hostile_npcs` or engine/npc_combat_ai.py `check_room_hostiles`) — ~10-line seam, but **combat-adjacent (near the parallel session's lane)**; (2) §23 variable guard density = a later phase.
- **C8 decay/dissolution** — (a) **DESIGN FORK for Brian** (logged): voluntary-dissolution refund diverges from spec §8.3 — code refunds `DISSOLUTION_REFUND_PCT=50%` of the **HQ founding cost**, but §8.3 says **25% of the expansion-room claim costs**. Align to spec, or keep current? Balance/economy call. (b) add a confirm step to `+city dissolve` (`parser/city_commands.py` `_handle_dissolve`) — clean small, but I bundled it OUT of the client-only drop; loop or a parser drop can add it. (c) §8.4 hostile takeover / raid window = **gated on Drop 6D territory-contestation** (large, not yet built).
- **C14 multi-city-per-org** *(expansion)* — **DECIDED by Brian 2026-06-14: TIER/SIZE-GATED** (earn a 2nd city once the org/first city hits a threshold — members, treasury, or rooms). Large: `get_city_by_org()` → list + ~15 call sites + `_resolve_actor_city()` rework + a city-selector in commands/client. Table already allows multiple rows per org_id (no schema change strictly required).
- **C16 P2P discovery** *(expansion)* — `+city list` (global text enumeration) is the minimal surface and works. §19 richer mechanics (per-char `wilderness_discoveries` table, `+city share`, `+city alerts`, hidden-frontier search roll, client directory panel) are gated on the SYN.4 wilderness-city migration. Large.
- **`+city events` (C3/C11)** — Director-dependent (Phase 9). A graceful "not yet available" stub is the only non-director option; low value, skipped. Real impl waits on C9.

## Other settled calls (this session)
- **+forcebond:** Brian 2026-06-14 — KEEP the free bond-sensing via `+master`/`+padawan`; do NOT add an FP-gated `+forcebond`.
- **Parallel lanes:** Brian 2026-06-14 — STRICTLY AVOID `engine/harvest.py` (decision-4 harvest cap), `engine/combat.py` (G4), `engine/director.py` (G13 + C9). These wait for the lanes to clear.
