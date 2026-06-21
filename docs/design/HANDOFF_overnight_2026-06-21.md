# HANDOFF — overnight drive 2026-06-20 → 2026-06-21

Self-contained pickup. Branch `drop/sidebar-contract-handoff-capture` == `origin/main` == **`8e39ccb`**.
Everything below is merged + pushed. The two durable loops (`SWMUSH-DurableLoop` Sonnet content,
`SWMUSH-OpusLoop` Opus quality) are **Ready/firing**; coordination lives in
`C:/Users/btgla/.claude/projects/c--SW-MUSH/OPUS_CLAIM.md`.

## What shipped this session (newest first)
| commit | drop | what |
|---|---|---|
| `8e39ccb` | qa-mail-body-cap | QA MED: cap in-game mail body at 8000 (was a 262 KB storage-DoS). |
| `932cfe8` | qa-combat-disconnect-persist | **QA HIGH:** FP/CP/wound were refunded on a mid-round disconnect (DB save was gated on the session) — now persists always. |
| `eb6dd30` | **solo-pve-mob-grind** | **FEATURE (Brian's "B"):** defeating an ordinary roaming hostile pays a small daily-capped credit trickle (15/kill, 400/day cap, 3 floor) + prestige (kill-count + earned hunter titles), **ZERO CP**. Self-sinking via combat costs. `+hunting` view. |
| `(in B)` | qa-kuat-kamino-landing | **QA HIGH:** ships landing from Kuat/Kamino were dumped on Tatooine. |
| `16986da` | qa-credit-integrity | **QA HIGH+MED:** shop-upgrade + learn-tuition could go negative (stale-cache) — now `allow_negative=False`. |
| earlier | npe-npc-desc-not-posed / npe-contextual-hints / npe-command-to-type | **NPE targeted pass COMPLETE** (huge-text fix, first-hit guide nudges, "TYPE THIS" spotlight). Smoke-verified 220. |
| earlier | maps-interior-fork-log | Interiors painted + montaged; wiring logged as a design fork. |
| earlier | datetime-utcnow-hardening | Removed deprecated `utcnow()` (box is Py 3.14). |

Also a **QA break-it campaign** (5 adversarial agents) ran: **NPE surfaces came back CLEAN**; it found the
3 HIGHs + 2 MEDs + 1 LOW above — all 3 HIGHs are now fixed, 1 MED done, the rest delegated to the loops.

## ★ Two findings that need Brian
1. **`COMBAT.dead_gated_hooks_inert`** (logged in `design_calls_pending_brian`) — **the DEAD-gated reward hooks
   inside `_apply_combat_wear` are structurally inert**: `resolve_round()` runs `_cleanup()` which removes dead
   combatants BEFORE `_apply_combat_wear` iterates. So the pre-existing **bounty auto-collect, anomaly-on-kill,
   and WoW.3a Jedi-weight-on-kill** hooks likely never fired. (Bounties still pay via the manual `+bounty/collect`.)
   The new mob-grind reward works around it via `_award_mob_grind_rewards()` on a **pre-resolution snapshot** at
   the `resolve_round` call sites — that's the proven fix pattern to migrate the other three onto. **It's all in
   `parser/combat_commands.py` (NOT the avoid-lane engine/combat.py)**, so it's a clean attended fix — but it
   touches 3 shipped reward systems, so I left it for a fresh careful pass. Decide: migrate all three, or confirm
   the manual paths make the auto-hooks redundant + delete them.
2. **`MAP.interior_slug_collision_wiring`** (logged) — the 6 unwired interiors are painted + montaged
   (`static/tools/batches/_review/<key>_choices.png`) but wiring is blocked on a slug collision (their room slugs
   already live in city maps). My lean: deterministic interior-beats-city registry precedence. Your call.

## Loops (delegated, working in parallel)
`OPUS_CLAIM.md` has the live partition. Delegated this session: the **+scene LOW** fix (`+scene -1` mis-message),
the **+scene/+plot summary cap** MED, and **grind CONTENT** (the Sonnet loop can now author roaming HOSTILE mobs
into sparse zones — they become huntable targets for the mob-grind reward). The loops also shipped Guide_26,
the CW ambient-event resolver, and help entries for the new browse commands during the session.

## Launch tail (unchanged)
NPE = **DONE**. Remaining: **hosting/go-live** (UNSTARTED, Brian-gated: Cloudflare Tunnel + NSSM per
`docs/ops/GO_LIVE_RUNBOOK.md`) **+ marketing**. Features are complete. The solo-PvE grind v1 numbers are a
`T2.ECON.review` knob (economist pass) — they're conservative on purpose.

## Operating notes
- Loop-merge dance per drop: disable both loops → `git fetch` → merge origin/main (union CHANGELOG, splice TODO
  `last_updated_note`, keep BOTH entries) → `git branch -f main HEAD` → push → re-enable. Used ~11× tonight; clean.
- Gate single-process targeted (`-o addopts= --timeout=120`); the full xdist gate hangs on this box.
- `tools/mapgen/term_boundaries.json` is a working-tree artifact — never stage it.
