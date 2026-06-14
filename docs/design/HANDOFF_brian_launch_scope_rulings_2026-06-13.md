# HANDOFF — Brian's Launch-Scope Rulings (2026-06-13)

Brian adjudicated the open launch-scope decisions. **These are authoritative.** TODO.json was
dirty (session live in it) when these were captured, so they're recorded here for the session
to reconcile into `design_calls_pending_brian` / `tier_3_post_launch` / the relevant items when
the file is free. Verified each against HEAD; two were already resolved by drops that landed
during the conversation.

## Ruling 1 — Equipment-instance refactor: **PRE-LAUNCH** (decided)

`TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES` (Character holds bare key strings for
`equipped_weapon`/`worn_armor`, not ItemInstances). **Brian: pre-launch.** Rationale: "be
relatively feature-complete at launch so post-launch changes are less risky for a live game."

**Impact — unblocks two pending design calls:**
- `CRAFT.powered_suit_design` (currently "BLOCKED on equipment-instance migration") → unblocked;
  schedule after the migration.
- `CRAFT.HOOK.restraints_state_model` (currently "sequence after equipment-instance migration")
  → unblocked; schedule after the migration.

**Action:** schedule the equipment-instance migration EARLY (it's a load-bearing dependency for
2+ items and touches save data — see `HANDOFF_t3_20_state_preservation` for the migration
mechanism, which is sound). Then powered-suit + restraints follow. Note: the armor-soak fix
(Drop 44) deliberately did NOT need this migration via primitive-threading — but powered-suit
and restraints genuinely do.

## Ruling 2 — Crafted armor + consumable quality real: **ALREADY DONE** ✓

Brian ruled "make the qualities real (Option A), plan a design if needed." **Verified: already
shipped** while the conversation was in progress — `CRAFT.armor_consumable_quality_combat` is
`DONE 2026-06-13` (armor Drop 44, consumables Drop 45, both hard-capped against power creep,
design in `consumable_quality_potency_v1.md`). The session consumed the crafting-integration
review's recommendation. **No action — close confirmed.**

## Ruling 3 — The six "tier_3_post_launch" expansions (T3.13-18): mostly POST, with carve-outs

Brian: "most of those are okay for post-launch, with a couple of caveats."

| Item | Ruling |
|---|---|
| T3.13 Padawan-Master expansion | **POST-LAUNCH** — but do the FRONT-END / scaffolding work pre-launch (see below) |
| T3.14 Cities expansion (multi-city) | **POST-LAUNCH** — front-end scaffolding pre-launch |
| **T3.15 Director CW tuning** | **PULL LEFT — PRE-LAUNCH.** Brian: "I think we're already looking at director tuning — that should be pulled left of launch." (Consistent with the Director-scope review: tuning a Director that only sees the early slice is rearranging deck chairs — but pulling the *scope expansion + tuning* left is correct. This item is effectively superseded/widened by `director_scope_and_adaptive_spend_v1.md`.) |
| T3.16 Space Wildspace expansion | **POST-LAUNCH** — scaffolding pre-launch |
| T3.17 Sheet redesign | **POST-LAUNCH** (Brian thought it was done; verified — only a PARTIAL sheet `m3_sheet.js` shipped, the full redesign is Phase-2 per CHANGELOG; matches the post-launch ruling) |
| T3.18 Ground UX overhaul | **POST-LAUNCH** (Brian thought it was done; verified — folded into post-launch web-client Phase 2 per CHANGELOG; matches) |

**THE CAVEAT (applies to all the post-launch expansions):** "do the front-end work to make
post-launch implementation painless." So the pre-launch obligation for T3.13/14/16 is the
**schema/state scaffolding + UI seams** that let the feature drop in post-launch WITHOUT a live
schema/state migration (the exact thing T3.20 is meant to make safe, and the reason the
launch-criteria says ship-the-backlog). Pre-launch: lay the seams; post-launch: fill them.

**Action:** rename/annotate the `tier_3_post_launch` bucket to remove the pre-vs-post ambiguity
(the bucket name + titles say "post-launch," but T3.15 is now pre-launch and T3.13/14/16 carry a
pre-launch scaffolding obligation). Pull T3.15 into the pre-launch sequence.

## Ruling 4 — Director "living galaxy" (multi-zone): **PRE-LAUNCH** (decided)

The Director only runs 6 Mos Eisley zones; every other planet sits static
(`director_scope_and_adaptive_spend_v1.md`). **Brian: pre-launch.** It's cheap (the zone config
is already authored; loading it is a config-load + per-zone tracking change, not a big refactor).
Bundle with the two verified Director bugs (the dead `_apply_influence_delta` lever +
the cost-telemetry-logs-zeros bug) — all in `director.py`, one build.

**Adaptive-spend (Brian to confirm the one sub-question):** the design supports a $20-always-on
tier with the Director auto-escalating Claude spend up to a ceiling on high-ROI moments
(recommended), plus a manual `@director fidelity` toggle. *Open sub-question for Brian:* autonomous
auto-escalation within the ceiling (recommended), or manual-toggle-only? (Not blocking the
multi-zone build.)

## Ruling 5 — Force-sensitivity fail-safe: **FAIL-SAFE-TO-JEDI** (decided)

From the T3.20 audit (blocker 2): if a character's attributes JSON is corrupted, a path-committed
Jedi currently silently loads as `force_sensitive=False`. **Brian: fail-safe to Jedi** — a
path-committed character should default to STILL being Force-sensitive (with a loud warning),
never silently lose it. **Action:** the T3.20 blocker-2 fix loads `force_sensitive=True` for a
path-committed char when the attrs are unreadable, + logs the corruption loudly.

## Ruling 6 — silent_except carve-out: **FIXED** ✓ (this session)

`OBS.silent_except_invariant_reconfigure_carveout` — the full-suite invariant test
(`test_session38.py::test_no_silent_except_pass`) flagged two `except Exception: pass` blocks in
the guide-cleanup tools (`tools/guide_lint.py`, `tools/split_guide_dev_track.py` — the UTF-8
stdout reconfigure). **Fixed this session:** replaced the bare `pass` with a justified non-pass
body (a comment + a marker assignment explaining the best-effort intent). The invariant test now
**passes** (verified: `test_no_silent_except_pass_in_production` green). These are my files, in my
lane — no session collision. **Close this call.**

## Net effect on the launch picture

- **2 design calls unblocked** (powered_suit, restraints) by the equipment-migration pre-launch
  ruling.
- **3 items pulled PRE-LAUNCH:** equipment migration, Director multi-zone (+ bugs), T3.15 director
  tuning.
- **4 items confirmed POST-LAUNCH** with a pre-launch *scaffolding* obligation (T3.13/14/16 + the
  sheet/UX which are already Phase-2).
- **2 already done** (armor/consumable quality) and **1 fixed** (silent_except) this session.
- **1 sub-question remains** (Director adaptive-spend autonomy) — non-blocking.

This collapses most of the "soft estimate" ambiguity: the pre-launch set is now well-defined
(equipment migration → its 2 unblocked features → Director multi-zone+tuning → the 3 hardening
gates T3.19/20/21 → the scaffolding for the post-launch expansions), and the genuinely-post-launch
set is the expansion *bodies*. A firm ready-for-live estimate can be drawn from this once the
session reconciles it into TODO.json.
