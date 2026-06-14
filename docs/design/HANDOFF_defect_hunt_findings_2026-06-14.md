# HANDOFF — Overnight defect-hunt findings (cross-session coordination) — 2026-06-14

> Produced by the parallel content/defect-hunt session (worktree `c:\SW_MUSH`,
> branch `drop/t3-20-safe-load`). A 10-cell adversarial defect-hunt workflow
> (Explore finders → adversarial verifiers) confirmed **30 real defects** across
> parallel-safe SW_MUSH surfaces. This doc records the ones THIS session did NOT
> fix — because the fix lands in another session's avoid-set, or it's a genuine
> design fork — so they aren't lost. Every item below was adversarially
> re-verified at HEAD by the workflow; spot-check before acting.

## Fixed by this session (for context — NOT deferred)
- **Encounter spawn count range** (`creature_library`) — drop `encounter-count-range` (pushed `5f9a679`).
- **Off-era GCW profession chains** (`tutorial_v2` REBEL_CELL/IMPERIAL_SERVICE + 5 barks) — drop `tutorial-v2-era-remediation` (`0faab3a`). This subsumes the defect-hunt's two `era_static` BLOCKER findings.
- **Breaching false-success on delete failure** (`breaching.py`) — drop `breaching-delete-failsafe` (`e36085f`).
- **Encounter skill-check funnel bypass** (`engine/encounter_*.py`) — drop `encounter-skillcheck-funnel` (in progress this session; see below — being FIXED, not deferred).

---

## A. PARSER-domain (Session B / parser owner must fix)

### A1. Achievement hooks defined but never called — 8 achievements unwinnable  *(HIGH)*
`engine/achievements.py` defines these hooks, but no code ever calls them, so the achievements depending on their events can NEVER fire. The hooks live in (parallel-safe) `achievements.py`, but the FIX is to *emit* them at their subsystem seam, which is in `parser/` (avoid-set for this session). Pattern to copy: `parser/mission_commands.py` already calls `on_mission_complete` correctly.

| Hook | Achievements blocked | Emit seam (where to call it) |
|------|----------------------|------------------------------|
| `on_item_crafted` (L520) | apprentice/journeyman/master_crafter, mad_scientist | `parser/crafting_commands.py` craft-success path (~L349-374) |
| `on_experiment_success` (L530) | mad_scientist | crafting/experimentation success |
| `on_trade_goods_sold` (L505) | merchant_prince | trade/commerce sell command |
| `on_scene_completed` (L540) | storyteller | `parser/scene_commands.py` scene completion |
| `on_ship_launch` (L451) | first_flight (→ ace_pilot prereq) | `parser/space_commands.py` launch |
| `on_anomaly_salvaged` (L466) | salvage_king | `parser/space_commands.py` salvage |
| `on_org_rank_reached` (L545) | faction_loyalist | org rank-promotion seam (maybe `engine/organizations.py` — could be engine-side/parallel-safe) |
| `on_dark_side_atoned` (L601) | redeemed | `parser/force_commands.py` atonement |

Each is one `try/except`-wrapped `await on_X(...)` call at the seam (graceful-drop pattern). `on_org_rank_reached` may be fixable engine-side if rank promotion lives in `engine/organizations.py` — worth checking.

### A2. `intercept` achievement: wrong arg order + undefined achievement  *(HIGH)*
`parser/espionage_commands.py:715` calls `check_achievement(char, "intercept", ctx.db)` — but the signature is `check_achievement(db, char_id, event, ...)`. Args are mis-ordered (dict where db expected, etc.), so it silently no-ops (`_BY_EVENT.get(ctx.db, [])` → `[]`). AND there is no `intercept` achievement/event in `data/achievements.yaml`. Fix: correct the call to `check_achievement(ctx.db, char["id"], "<event>", session=ctx.session)` and add the achievement, OR remove the call. (The data half is parallel-safe; the call fix is parser.)

### A3. Sabacc rake ledger bugs  *(HIGH — economy/funnel)* — `parser/sabacc_commands.py`
- **A3a (L297, 324):** non-den cantina win logs only `net_win` (bet − rake); the house rake is never logged as a sink → phantom faucet. Spec (`dens.py:21-26`) wants "credit FULL gross win then DEBIT the rake."
- **A3b (L290):** den rake logged as `adjust_credits(0, rake_to_org, 'sabacc_rake')` with a **positive** delta → registers as a faucet, not a sink. Should be a negative-delta sink.
- **A3c (L284-295):** den rake routing (`get_room_den`/`adjust_org_treasury`) wrapped in a broad try/except that swallows failures and still credits the player → silent org-income loss.

---

## B. MISSIONS-domain (Session A — `missions` avoid-set)

### B1. `destination_slug` written but never read → fragile fuzzy completion  *(MEDIUM)*
`engine/chain_missions.py:201` writes `destination_slug` to `mission_data`, but nothing reads it. `_materialize_mission` reads `destination_room_id` directly from the entry (L187) which isn't in the data, leaving it `None`, so mission-completion validation (`parser/mission_commands.py:504-514`) falls back to fragile fuzzy string matching. Fix: resolve `destination_slug` → `destination_room_id` at materialize time. (Touches mission engine + parser → Session A.)

---

## C. Low-value engine cleanups — parallel-safe but deliberately NOT done (ROI)
These are harmless dead writes / unused reads. Confirmed real but low value; left for a future tidy pass (or delete on sight). Listed so they're not "rediscovered" as new:
- `engine/contest.py:1210-1211, 1237-1239, 1367` — phantom writes of `anchor_target_hp`/`anchor_tier`/`anchor_for_region`/`anchor_contest_id`/`anchor_org`/`anchor_reinforcement_for` to NPC sheet/ai_config; only read by tests. (class A, low)
- `engine/hazards.py:429` — `char['credits']` in-memory mutation that's dead (the real write is `adjust_credits` on L432). (class A, low)
- `engine/espionage.py:275` — a `faction` field queried but never used in `generate_investigation_findings`. (class B, low)
- `engine/achievements.py:257-280` — `notify_room_achievement` is never called anywhere (dead function; contains a silent `send_line` swallow at 275-278). Remove, or wire if intended. (class A, medium)

---

## D. Design fork RESOLVED into a fix this session (no longer pending)
The defect-hunt re-flagged the encounter `_skill_check` raw-3D fallback as a funnel bypass. On inspection it was worse than a rare fallback: `perform_skill_check` is **synchronous** and takes `char` (dict) positionally with no `char_id`/`db` params, but `engine/encounter_{anomaly,hunter,patrol,pirate,texture}.py::_skill_check` call it as `await perform_skill_check(char_id=..., db=...)` — which **always raises**, so every space-encounter skill check silently used **raw 3D, ignoring the character's skill** (and reported roll 0 via wrong result-field names). The WEG difficulty values (15 = Moderate) are standard for *real* checks, so this was purely an accidental bug, not balance tuning. Fixed this session (drop `encounter-skillcheck-funnel`): load the char via `db.get_character`, call `perform_skill_check(char, skill, difficulty)` correctly, map `.success`/`.critical_success`/`.roll`, and make the exception fallback LOUD. Note for playtest: space-encounter checks now reflect skill (skilled pilots pass Moderate checks they used to coin-flip).

---

## Method note
The recurring root cause across the era + reachability findings is the **partial-coverage test blind spot**: surgical curated-list tests (e.g. `test_laneb_era_cleanness.py`) and per-subset contracts miss whole files/objects. Candidate systemic follow-up: a broad allow-listed AST era scan over `engine/*.py` player-facing string constants. Logged in `TODO.json` design call `ERA.tutorial_v2_gcw_profession_chains` → `related`.
