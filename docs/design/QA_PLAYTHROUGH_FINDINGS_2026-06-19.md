# QA Playthrough Campaign — Findings (2026-06-19)

Pre-launch comprehensive QA: a multi-agent adversarial playthrough across every
subsystem, driving the LIVE game in-process; each blocker/high finding was
independently reproduced by a second agent. **All blocker claims below were also
re-verified against HEAD by symbol grep** (no phantom claims).

- **Coverage:** 9 of 10 lanes completed (25 agents). The **onboarding_chains**
  lane died on a session/compute limit and did NOT run — re-run it (the movement
  lane partially covered tutorial-chain rooms). One parser_robustness verify
  hit an API 500 (the finding is grounded by HEAD grep regardless).
- **Verdict tally:** **6 confirmed BLOCKERS, 8 confirmed/grounded HIGHs**, plus
  ~10 medium/low. One HIGH claim was **refuted on verify** (tutorial 0-exit
  rooms = working-as-designed, see bottom).
- **Headline:** none of these block *booting* the game, but several break core
  player loops (skill training, combat with incapacitated/stunned targets,
  Force-PC web UI, the heal economy). They are launch-gating.

Full per-finding repros are in the campaign output (task wgraxi094). Fixes are
NOT applied — this is a report.

---

## BLOCKERS (confirmed real + reproduced + HEAD-verified)

### B1 — `train` and NPC trainers crash; skill progression fully broken
`Character.from_db_row` does not exist (the method is `Character.from_db_dict`).
Two call sites leak the raw `AttributeError` to the player via the global handler
(`parser/commands.py:508`).
- `parser/cp_commands.py:157` — `train <skill>` → "An error occurred… (type object 'Character' has no attribute 'from_db_row')". **All skill advancement is dead.**
- `parser/npc_commands.py:120` — `_handle_skill_trainer` → same crash when a player `talk`s to any trainer NPC.
- **Repro:** log in → `train blaster`. **Fix:** `from_db_row` → `from_db_dict` at both sites (the None-guards before each call are already present).

### B2 / B3 — combat `UnboundLocalError: 'wound'` on incapacitated & stun-KO hits
`engine/combat.py:1810` assigns `wound` only in the `damage_margin > 0` branch.
Lines `1853`/`1872` reference `wound.display_name` inside `if not target.can_act_now()`.
- **B2:** a soaked follow-up shot on an already-INCAPACITATED target (common in group combat) → crash.
- **B3:** any **stun-mode** hit with margin > 3 (≈40–60% of stun hits) → crash 100% of the time (`unconscious_until` makes `can_act_now()` always False).
- **Repro:** stun a low-soak NPC with a 5D stun weapon. **Fix:** use `wound_text` (always assigned) instead of `wound.display_name` at lines 1853 & 1872.

### B4 — web HUD always sends `force_sensitive=False` (Force PCs lose their UI)
`server/session.py:566` reads `char.get("force_sensitive")` off the **raw DB dict** —
but `force_sensitive` is **derived state** (no such column; CLAUDE.md invariant).
Every Force PC's FP block, Force-skills panel, and Force tab are hidden after any
logout (the in-memory village-commit masks it for one session only).
- **Fix:** `bool(char_obj.force_sensitive if char_obj else False)` (the `char_obj` is already fetched at line 550). Part of a **bug family** — see Themes.

### B5 — housing-lot seeder corrupts 37/40 lots (YAML id vs DB AUTOINCREMENT)
`engine/housing_lots_provider.py:178` uses `room_id = host.id` (the YAML-authored
id), but `create_room` writes AUTOINCREMENT ids. Verify found **33/40 lots point
to the wrong room and 4 are silently dropped** (FK failures swallowed at
`engine/housing.py:643`). Lots resolve to wrong planets entirely.
- **Repro (in-process):** boot CW → `SELECT * FROM housing_lots WHERE planet='geonosis'` → 0 rows. **Fix:** resolve host slug → DB id (pass `WriteResult.yaml_to_db` into the provider, or look up by slug at seed time). CW-era only.

### B6 — `healaccept` drives a patient's credits negative (stale-cache affordability)
`parser/medical_commands.py:274` checks affordability against the **session cache**,
then `:324` calls `adjust_credits(..., -rate)` with the default `allow_negative=True`.
Any concurrent credit event during the 60s heal-offer window (purchase, fine,
bounty) corrupts the balance negative; player sees "Paid 100 credits." success.
- **Fix:** read fresh DB credits for the check, and/or pass `allow_negative=False` and abort on `None`.

---

## HIGHs (confirmed / HEAD-grounded)

- **H7 — chargen text-mode skill-cap bypass.** `engine/creation.py:_cmd_skill` (~262) checks only `pips > 0`, never the 2D creation cap (`MAX_SKILL_BONUS_PIPS`). The web path (`chargen_validator.py:180`) enforces it; the **telnet/in-game wizard** does not → illegal stats persist. `_validate()` (~467) also lacks a per-skill cap.
- **H8 — combat CP double-spend goes negative.** `engine/combat.py:966` validates each action's `cp_spend` against current CP, not the running sum; resolvers at `:1407`/`:1542` subtract with no floor. Two multi-action attacks of 5 CP with 5 CP on hand → `character_points = -5` (persisted).
- **H9 — buy orders accept any resource string; credits lockable.** `engine/vendor_droids.py:1071` `list(RESOURCE_TYPES.keys())` — `RESOURCE_TYPES` is a set, so `valid_types = []` always and the guard is dead. `shop order notarealresource …` escrows real credits into an unfillable order (recoverable only via undocumented `shop cancel`). **Fix:** `list(RESOURCE_TYPES)`.
- **H10 — BountyTrack rolls flat 2D + bypasses the dice funnel.** `parser/bounty_commands.py:278` calls `get_skill_pool()` without the required `skill_registry` (TypeError swallowed → `DicePool(2,0)` floor); `:291` calls `roll_d6_pool` directly, bypassing `perform_skill_check` (wound penalties, bonuses, telemetry all skipped). Sister `BountyCollect` does it correctly.
- **H11 — mail sidebar permanently dark for everyone.** `server/session.py:1871` SQL uses `mail_messages` (→ `mail`), `mr.message_id` (→ `mr.mail_id`), `m.sender_name` (→ `sender_id`). `OperationalError` swallowed at `:2139` → `mail_status` WS event never fires; client `handleMailStatus` never called. **E1 to confirm** in DevTools WS frames.
- **H12 — `training force` rejects legitimate Force PCs.** `parser/tutorial_commands.py:156` reads `char.get("force_sensitive")` on the raw dict → always blocks the Jedi Enclave. (force_sensitive family.)
- **H13 — exception handler leaks raw `str(e)` to players.** `parser/commands.py:508-510` sends Python/SQL/JSON error text verbatim to the player channel (this is the surface that makes B1's AttributeError player-visible). Sanitize the player message; log the detail server-side.
- **H14 — (test-only) harness `give_item` crashes on dict-format inventory.** `tests/harness.py:923` `inv.append` on a dict → can mask real defects by killing test runs. Not a live-game bug.

---

## Notable MEDIUM / LOW
- **M — combat CP spend never persisted** (`parser/combat_commands.py:1182` saves `wound_level` but not `character_points`) → reconnect restores spent CP.
- **M — ghost combat round**: an orphaned `_grace_timer_handle` fires on a removed combat (`combat_commands.py:460` doesn't cancel it) → ghost narration + initiative roll.
- **M — `force sense` misses Force PCs** (`parser/force_commands.py:168`, force_sensitive family).
- **M — communal strike always floors to 2D** (`engine/communal_objective.py:223` `int("3D")` ValueError).
- **M — `_parse_dice_str` phantom import** at 4 sites (sabacc/builtin×2/space) → NPC bargain/gambling pools silently default.
- **M — `wear` lies about inventory** for items whose key isn't in `weapons.yaml` (`builtin_commands.py:3455`).
- **L — Force powers bypass `perform_skill_check`** (`engine/force_powers.py:381/397/620/800`) → buffs/telemetry not applied.
- **L — `_build_area_contacts` iterates the live sessions dict** (`session.py:1486`, should use `.all`) → contacts can blank on concurrent disconnect.
- **L — `+city home`** mutates room_id in memory before the DB commit (transient divergence on DB failure).
- **Secondary — `engine/locks.py:73`** force_sensitive raw-dict read; **`_pool_to_str` phantom import** in `heal`.

---

## Cross-cutting THEMES (fix the root, kill several findings)
1. **`force_sensitive` read off raw DB dicts** (invariant violation — it's derived). Sites: `server/session.py:566` [B4], `parser/tutorial_commands.py:156` [H12], `parser/force_commands.py:168` [M], `engine/locks.py:73` [secondary]. One sweep (grep `\.get(["']force_sensitive`) + route through `Character.from_db_dict(...).force_sensitive`) closes all of them. *(Note: the `server/api.py` reads are the web-submission path where the key is legitimately present — verify before touching.)*
2. **Stale session-cache reads instead of fresh DB** — `healaccept` credits [B6], `heal` wound_level/credits [M]. Affordability/state checks must re-read DB.
3. **Out-of-combat dice bypassing `perform_skill_check`** (funnel invariant) — BountyTrack [H10], communal strike [M], Force powers [L].
4. **Phantom method/import names silently swallowed** — `Character.from_db_row` [B1], `_parse_dice_str`, `_pool_to_str`. A grep for swallowed `AttributeError/ImportError` would surface more.

## REFUTED (do not action)
- **Tutorial chains start in 0-exit rooms** (claimed HIGH stranding) → **NOT-A-BUG.** The zero-exit policy is documented and intentional; step-1 completion is a no-move command that triggers the inter-step teleport. No invariant violated. (Still worth the onboarding lane re-run that didn't complete.)

## Recommended order
Fix the 6 blockers first (B1 is a one-line ×2; B2/B3 one-line ×2; B4 is the
force_sensitive sweep; B5 needs the slug→id resolution; B6 the fresh-read).
Then the highs, batching the force_sensitive family and the funnel-bypass family.
Re-run the QA campaign (incl. onboarding_chains) after the blocker fixes to catch
regressions + the lane we missed.
