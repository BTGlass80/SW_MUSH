# HANDOFF — Autonomous roadmap session setup
## Session 2026-06-12 (9th) · for the NEXT chat (Opus 4.8 1M, unattended)

**Audience:** the next Claude Code session, which Brian will start as a fresh
Opus 4.8 (1M) chat and then walk away from. Your job is to make autonomous
progress on the roadmap using the subagent pipeline, committing per drop,
**without stopping for permission prompts** and **without guessing on design
forks.** Brian is git-naive — keep git simple and never do anything
outward-facing (push) or destructive.

---

## 0. ONE-TIME manual step Brian must do before the unattended chat (READ FIRST)

Unattended auto-run is configured in `.claude/settings.local.json`
(`defaultMode: "bypassPermissions"`, gitignored, this machine only). But the
VS Code extension will **not** honor it until you flip a toggle once:

> **VS Code → Claude Code extension settings → enable "Allow dangerously skip
> permissions"** (the dangerous-skip toggle). Then either it's already the
> default via settings.local.json, or pick **"Bypass permissions"** in the
> mode dropdown at the bottom of the chat box when you start the session.

You cannot enter bypass mode from a session that started without it — so set
this BEFORE starting the autonomous chat. Verify: the first Bash/python call
should run with no approval prompt. If you're still being prompted, the
toggle isn't on.

The destructive-command **deny list stays enforced even in bypass mode**
(deny is evaluated before bypass). Hard-blocked: `git push`, `git reset
--hard`, `git checkout`, `git clean`, `git merge`, `git rebase`, `rm -rf`,
`run_all_tests.bat`, and the PowerShell equivalents (`.claude/settings.json`).
So the autonomous session physically cannot push, merge to main, discard
your files, or run the full suite by accident.

---

## 1. Git state — where things are, what Brian does

- **Branch:** `roadmap` (renamed this session from `chore/claude-code-migration`
  — the migration is "closed"). Local only; never pushed. `origin` =
  `github.com/BTGlass80/SW_MUSH.git`; `main`/`origin/main` are the published
  line.
- **This session's work is committed** on `roadmap` (one commit closing the
  migration + the v52 doc + agent infra + the commissary drop).
- **The full suite has NOT been run** on the Gundark lane (drops 1–11), the
  commissary drop (drop 12), or anything since. Per discipline, **nothing is
  merged to main until Brian runs `run_all_tests.bat` green.**

**Autonomous session git discipline (MANDATORY):**
- Commit **per drop** on `roadmap`, each commit including its `CHANGELOG.md` +
  `TODO.json` updates (so Brian can bisect if the suite fails). Use
  `git add -A && git commit -m "..."` (commit is allow-listed).
- **Never** merge to main, **never** push, **never** rebase/reset/clean — all
  deny-listed. You can't run the full suite either (deny-listed; it times out
  in-session anyway). Keep **targeted** tests green per drop instead.
- End commit messages with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

**Brian's steps when he returns (git-naive cheat-sheet — run in the VS Code
terminal from `c:\SW_MUSH`):**
```sh
run_all_tests.bat                 # the full ~7,700-test gate (Windows)
# If GREEN, publish the work:
git switch main
git merge roadmap                 # fast-forwards main to include everything
git push                          # sends it to GitHub
git switch roadmap                # go back to the working branch
```
If the suite is RED, don't merge — tell the next session which tests failed;
it triages. (Several Gundark watch-item flips are EXPECTED and are bug-pins,
see §5.)

---

## 2. What shipped this session (context)

1. **Architecture-of-record → v52.** `docs/design/sw_d6_mush_architecture_v52.md`
   supersedes the stale v51. It reconciles the v51 invariant-numbering
   collision (restores §4.30 creature-attack, §4.31 creature-spoils, §4.32
   ledger-chokepoint, renumbers communal-objective to §4.33), folds in the
   June economy/creature/Force waves, and documents the **Gundark crafting
   lane drops 1–11** with four new invariants §4.34–§4.37 (skill-key
   canonicalization, craftable faucet-with-sink, vendor buy-gate, tuition
   sink). `CLAUDE.md` authority order + `TODO.json architecture_of_record`
   now point to v52. **Do NOT point-update the arch doc per drop** — that's
   the lossy round-trip that broke v51; CHANGELOG/TODO carry per-drop state.
2. **Agent infrastructure.** New subagents `drop-implementer` (Sonnet) and
   `content-author` (Sonnet); existing `design-reviewer` (Opus),
   `invariant-auditor` (Sonnet), `test-runner` (Sonnet). The delegation
   policy is in `CLAUDE.md` → "Agent roster & delegation".
3. **Permission config** for unattended runs (§0).
4. **CLAUDE.md "Sourcebook PDFs" section** — `docs/sourcebooks/` (gitignored)
   holds WEG40120; it's the ultimate mechanics authority; grep the sidecar to
   find, verify against the PDF page.
5. **Drop 12 — WEBIFY.commissary_vendor_mode** (buy-side): the rank-gated
   commissary now renders in the web shop panel via `shop_state mode:'vendor'`
   + `renderVendor` in `m3_shop.js`; BUY stages the existing `+commissary buy
   <key>`. Sellback deferred → `ECON.commissary_sellback_model` design call.
   Ran clean through implementer → invariant-auditor (CLEAN) → test-runner
   (28/28 commissary; the 3 new spa render tests SKIP locally — jsdom/SSL env
   gap, not a regression; need a jsdom/Windows run to truly verify).

---

## 3. The agent pipeline (how to work — the user explicitly wants this used)

The main session (you, Opus) keeps the **judgment endpoints** and delegates
the mechanical middle to Sonnet. Default per-drop flow:

1. **Scope** with `Explore` (read-only fan-out) when the surface spans many
   files — get the map without burning your context.
2. **Design surface?** If the work touches economy/balance/a new system, run
   `design-reviewer` (Opus, read-only) first. If it's a genuine fork (see §4),
   **STOP and log it — do not guess.**
3. **Implement** settled, mechanical work via `drop-implementer` (Sonnet).
   Give it a fully self-contained spec (it starts with fresh context): exact
   files, functions to reuse, the message/data shapes, invariants, tests to
   add, and the hygiene updates. Worldbuilding/data content → `content-author`
   (Sonnet), one agent per disjoint zone/file for parallelism.
4. **Verify** every diff with `invariant-auditor` + `test-runner` (Sonnet,
   parallel) BEFORE committing.
5. **Commit** the drop (code + CHANGELOG + TODO) on `roadmap`.

Create new agents when a repeatable role emerges (the 5 are a starting set).
Candidates not yet built: a `doc-writer`/guide author for the pre-release
help/guides rework; a `web-smoke` driver if a jsdom harness gets installed.

---

## 4. Design forks — LOG, never guess (the autonomous guardrail)

These need a Brian decision before any code. If the roadmap leads here, run
`design-reviewer`, write the options into `TODO.json
design_calls_pending_brian` with a recommendation, and **move on to the next
implementable item.** Do NOT implement them.

- `ECON.commissary_sellback_model` (logged this session) — can faction-issued
  commissary gear be sold back, at what price, bind-on-pickup?
- `OBS.quality_and_boosts_not_combat_read` — how crafted quality + experiment
  boosts should reach combat math (today combat reads stats by registry key).
- **Powered-suit** design pass; **mines/breaching** design pass.
- `CRAFT.HOOK.restraints` (restraint state, PvP-consent norms, escape checks)
  and `CRAFT.HOOK.force_detector` (force-use detection surface) — both
  "design first" long poles.
- World-event **6 FLAG effects** (`T2.E3`, arch §8.19).
- `TD.DIRECTOR_FACTION_MODEL_GCW` (Director internal faction re-key).
- **Eavesdrop `target_char`** model (carried since v45).
- `CRAFT.market_segmentation_impl` has a per-vendor-family **grandfather-vs-
  withdraw** sub-decision — the audit is mechanical but each withdrawal is a
  call; log withdrawals rather than ripping live stock.

---

## 5. The autonomous work QUEUE (do these, in roughly this order)

**Implementable now (no fork) — start here:**

1. **Buy-verb tail (small, validates the pipeline end-to-end).** (a) Wire the
   commissary `tracking_fob`'s "+1D to Search" onto the Drop-F carried-tool
   `skill_bonus` seam (it now shows in the commissary panel but has no
   consumer) — check the issued-item landing shape first, per the vendor
   handoff. (b) Rename the `ship_weapon_purchase` ledger tag for ground buys
   (`T3.19`), minding ledger-continuity. Both are in arch §1.5 /
   `OBS.buy_verb_followups`.
2. **`T2.DEF.t5_drop_hooks`** — wire the 4 remaining T5 material drop hooks.
   Scope against the design doc first (some land naturally inside SYN.7.b /
   SYN.8). Engine+content, small each.
3. **`T2.DEF.handler_npcs`** — intel-handler NPC seeding; "complete for
   static-HQ factions," the dynamic-`hq_room_id` ones remain (arch §10.6
   dependency: HQ rooms are created by `engine/housing.py`, not pre-seeded).
   Content + light seeding.
4. **Coruscant Underworld full 40×40×3 region build** (arch §8.13, the main
   pre-launch content task) — **parallelize** with `content-author` agents,
   one per disjoint sub-grid/landmark cluster, consistent with the existing
   Coruscant Underworld landmarks YAML, on the wilderness substrate. This is
   the big worldbuilding item Brian flagged as parallel-friendly.

**Design-review-then-log (produce queued decisions for Brian):** run
`design-reviewer` over the §4 items and write recommendations into
`design_calls_pending_brian` so Brian has a batch of decisions waiting.

**Pre-release (DEFER to end of roadmap — Brian's explicit call):**
- `PRELAUNCH.help_guides_rework` — re-author in-game help + Codex guides
  (Guide_01..26) for accuracy against the shipped suite. Do near the end so
  it captures the final state.
- `PRELAUNCH.web_landing_retention` — relook the public login/landing page
  (NOT the gameplay client): login, guides/help surfacing, character
  list/creation, world pitch; tighten as a retention hook. End of roadmap.
- Browser smoke-tests of the substrate map + the commissary `renderVendor`
  panel — **Brian/Windows only** (sandbox can't render). Leave for him.

---

## 6. Standing invariants (the non-negotiables — full set in CLAUDE.md + arch §4)

No phantom claims (grep HEAD at symbol level before claiming exists/missing).
Extend don't add. No phantom producers/consumers. Faucets ship with sinks.
Funnel functions (`adjust_credits` / `perform_skill_check` /
`adjust_territory_influence`). `force_sensitive` is derived, never a
`save_character` kwarg. WEG R&E D6 only — WEG40120 is the authority (grep
sidecar, verify against PDF). Era cleanness B3. Map-YAML edits purely additive
via comment-preserving string replacement. Skill lookups via
`canonical_skill_key()`. Schema-neutral when possible (live `SCHEMA_VERSION`
in `db/database.py` = 43). Test isolation: reset `engine.world_events._manager`
to `None` between event tests.

## 7. Known residuals / watch items

- **Gundark lane (drops 1–11) Windows watch items** — 7 deliberate behavior
  changes that will flip suite tests that were pinning bugs (trained pools
  jump · armor Dex penalties live · grenades consume · mitigation gear
  depletes · tuition charges · buy gates on stock · buy gates on vendor
  presence). When Brian runs the suite, flips in those areas are expected;
  fix any test still asserting the OLD (buggy) numbers — don't restore the
  bug. (arch §1.4-M.)
- **spa JS render tests skip locally** (jsdom/SSL). The commissary
  `renderVendor` + the substrate overlay need a jsdom-capable or Windows run.
- The commissary panel surfaces `tracking_fob` whose Search bonus has no
  consumer yet → queue item 5.1(a).

---

## 8. Misc Brian asks captured

- VS Code extensions: answered in-chat (jsdom/Node for spa tests is the main
  ROI; otherwise the env is sufficient). If a jsdom harness gets installed,
  the spa render tests stop skipping and a `web-smoke` agent becomes viable.
- Parallelism: worldbuilding (item 5.4) is the parallel-friendly lane —
  fan out `content-author` agents on disjoint files. Design work stays
  single-threaded (one reviewer, sequential decisions).
