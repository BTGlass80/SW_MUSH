# Launch-Readiness + Sequencing Review (2026-06-13)

Companion to the v52.1 arch-doc catch-up pass. The arch doc now reflects HEAD
(drops 24–33); this doc holds the readiness/sequencing analysis that doesn't belong in
the architecture-of-record. Produced by a 4-agent review (3 mapping lanes + adversarial
synthesis) cross-checked against TODO.json HEAD.

## Headline

**Feature-complete is close; launch-ready is further** — gated less by remaining code
volume than by (a) 8 unadjudicated design calls and (b) a hardening cluster (T3.19/20/21)
that hasn't started. The engine spine is solid. Rough order-of-magnitude: **weeks, not
days; not months** — but the estimate is soft until the design calls are ruled on.

## What actually remains (verified vs TODO.json HEAD)

- **tier_1_active:** 22 items, 21 DELIVERED. Only `T2.CRAFT.integration_design_pass`
  remains and it is "DESIGN COMPLETE" (build-pending, ~1–2 days). *The bucket is
  effectively done — its 21 delivered items should be archived out so remaining-work
  counts are honest.*
- **tier_2_queued:** 49 items, ~13 genuinely open. Of those, several are IN FLIGHT by the
  parallel session (the T5 master-trainer questline: `t5_trainer_storyline`,
  `t5_ship_part_items`, `t5_discoverability`) and two are the correctly-deferred PRELAUNCH
  polish items (`help_guides_rework` — Phase A already done this session;
  `web_landing_retention`). The genuinely-untouched feature set is small.
- **tier_3_post_launch:** 9 items, 0 done. Per `launch_criteria`, **6 of these (T3.13–18)
  are PRE-LAUNCH expansions** and 3 (T3.19/20/21) are PRE-LAUNCH hardening. This is the
  real remaining bulk.
- **tech_debt:** 26 entries, most low-priority / intentionally deferred. Non-blocking.

## CORRECTION to an analyst error (verified against HEAD)

One mapping lane asserted "**3 design calls definitely BLOCK LAUNCH**" (force_detector,
restraints, flag_effect_consumers). **This is false.** Reading each call's own `priority`
field in TODO.json: NONE is marked launch-blocking. `force_detector_model` = "LOW (weak era
fit → recommend DEFER)"; `flag_effect_consumers` = "MEDIUM (high flavor ROI, not
launch-blocking)"; `restraints_state_model` = "MEDIUM (sequence after equipment-instance
migration)". All 8 pending calls are LOW/MEDIUM, several explicitly recommending defer. The
real blocker is not hard design gates — it's that the blocking scope is **unadjudicated**.
Until Brian rules, the feature backlog can't be sized.

## The 8 pending design calls — and their OWN recommendations

| Call | Priority (its own field) | Recommendation in record |
|---|---|---|
| CRAFT.HOOK.force_detector_model | LOW | **DEFER** (weak CW era fit) |
| WORLDEVENT.flag_effect_consumers | MEDIUM | thin consumers, **not launch-blocking** |
| CRAFT.HOOK.restraints_state_model | MEDIUM | sequence **after** equipment-instance migration |
| CRAFT.powered_suit_design | MEDIUM | **blocked on** equipment-instance migration |
| CRAFT.mines_breaching_split | MED/LOW | split: breaching now, placed-mines defer |
| DIRECTOR.faction_model_cw_mapping | LOW-MED | internal-only mapping layer |
| ECON.commissary_sellback_model | (unset) | preliminary; ratify |
| CRAFT.harvest_skill_flavor | LOW | Survival now; per-region override defer |

## Sequencing problems (highest-leverage first)

1. **Bucket-name landmine (confirmed).** T3.13–18 are PRE-LAUNCH per `launch_criteria`,
   but they sit in a bucket named `tier_3_post_launch` AND their titles literally say
   "post-launch expansion." Three signals say "post-launch," the launch policy says
   "pre-launch." **This needs Brian's explicit ruling** — under time pressure a future
   session will read the bucket/title and defer them, which is exactly the post-launch
   schema/state surgery the whole launch strategy exists to avoid. *Cheap to fix, expensive
   to ignore.*
2. **Design-call adjudication is the real critical path.** One batch ruling sizes the
   entire feature backlog. Start from the records' own defer/de-scope recommendations.
3. **Equipment-instance migration is an unsized load-bearing dependency.**
   `TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES` gates `powered_suit_design` AND
   `restraints_state_model`. Its pre-launch scope and effort are undetermined. Rule on it
   early — if pre-launch, schedule it as a dependency; if not, formally de-scope the two
   dependent hooks.
4. **Single-threaded UI→crafting choke.** `T2.CRAFT.integration_design_pass` (and its
   downstream wiring drops) is sequenced behind `T2.UIPKG.claude_design_handoff`
   (in-progress, no completion date, no fallback). A UI slip starves the crafting lane. Put
   a date/fallback on the UI item (proceed against a frozen contract stub if it slips).
5. **State-preservation gap (NEW, from drops 28–33).** Additive persisted fields shipped on
   schema 43 with no bump (chain `kind`, questline slots, zone `threat_band`, encounter
   `min_band`/`max_band`). **Add an explicit T3.20 task** to migrate/backfill these on
   pre-existing saves, or the no-post-launch-state-surgery rationale is breached at launch.

## What's sequenced RIGHT (don't change)

- Hardening cluster LAST and sequential (T3.19 tunables/telemetry → T3.20 state-preservation
  → T3.21 optimization/security). Correct per `launch_criteria`.
- PRELAUNCH polish (help guides, landing page) tagged "do near the end." Correct.

## Recommended sequence

0. **(cheap, now)** Resolve the bucket-name/title contradiction for T3.13–18 — Brian rules
   pre- vs post-launch. Archive the 21 delivered tier_1 items.
1. **(unblocks everything)** Batch-adjudicate the 8 design calls; start from their own
   recommendations.
2. Rule on equipment-instance migration scope (gates 2 crafting hooks).
3. Put a date/fallback on the UI handoff.
4. Features in order: integration_design_pass build → T5 questline Drop B + ship-parts →
   design-adjudicated crafting hooks (only if ruled in) → T3.13–18 expansions → PRELAUNCH
   polish.
5. Hardening cluster last (add the drop-28–33 backfill task to T3.20).

## One security note

T3.21 (optimization + security) is correctly last, but that means the security review hits
the largest code surface with no slip buffer before launch. Consider a lightweight security
pre-pass earlier even though the full review stays last.

## TODO.json action items (NOT applied — TODO.json is dirty from the parallel session)

These are recommendations for Brian/the main session to apply when the tree is clean:
- Rename/split `tier_3_post_launch` (e.g. `tier_3_pre_launch_expansions` T3.13–18 +
  `tier_3_pre_launch_hardening` T3.19–21; only the post-launch telemetry-tuning LOOP stays
  "post_launch"). Fix the "post-launch expansion" wording in T3.13/T3.14 titles.
- Archive the 21 DELIVERED tier_1 items out of the active bucket.
- Add the drop-28–33 state-backfill task to T3.20.
- Log the `engine/territory.py:785` "Empire" string finding against
  `T2.CW.codebase_era_sweep` (from the guide-cleanup session).
