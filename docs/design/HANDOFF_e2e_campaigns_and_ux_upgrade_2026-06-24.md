# HANDOFF — E2E QA campaigns + UX upgrade roadmap (2026-06-24)

Pick-up doc for a fresh chat. Branch: **`drop/sidebar-contract-handoff-capture`**.
Authority order unchanged (TODO.json + CHANGELOG.md first).

---

## TL;DR — where we are

This session built a **real-browser E2E QA capability** and used it to find the
bugs that were the binding launch uncertainty, then started fixing them and
queued the UX upgrade.

- **On main already** (ff'd this session): the 4 forks (ENV/SPACE/EVENT/CP),
  housing multi-home, the E2E gate + break-it harness, the `load_default` space
  fix, and the 2 break-it defects. Main was at `19758ba` after the load_default
  ff; the parallel telemetry session has pushed past it since (re-merge needed).
- **On the branch, pushed, NOT yet ff-main'd** (`9c09c55`): **11 of 13**
  normal-playthrough experience-defect fixes (see below). 71 new tests green;
  full suite NOT yet run on this batch.

## The two E2E campaigns (the new capability)

Both are real Chromium driving the live SPA, with a per-finding **adversarial
triage** stage that root-causes real-vs-artifact before reporting.

1. **Break-it** (adversarial input): `Workflow` over 10 SPA surfaces. Result: 8/10
   robust, **2 confirmed defects (both fixed + on main, 39c2bc7)** — the dead INV
   HUD button (`data-cmd=inventory`, a deleted alias -> retargeted to `+inv`) and a
   char-select silent stuck-state.
2. **Normal-playthrough** (play it, judge it with vision): `Workflow` over 6 player
   journeys. Result: **13 confirmed experience defects** — the class Brian hits by
   hand (broken progression, era violations, unreachable content). 11 fixed
   (`9c09c55`); 2 remain (below).

**Infra (in the tree):** `tests/e2e/breakit_harness.py` (BreakItSession — boots
server+Chromium, auto-captures pageerror/console.error/5xx/requestfailed),
`tests/e2e/breakit_scenarios_smoke.py` (template). Agent-generated scenario
scripts `tests/e2e/breakit_<surface>.py` + `tests/e2e/play_<journey>.py` are
UNCOMMITTED campaign artifacts (curate the useful ones into committed regression
tests). Run a scenario: `NODE_OPTIONS=--use-system-ca python tests/e2e/<file>.py`.

## REMAINING work — do these first, in order

### 1. BLOCKER: economy linkage (NOT done — mid-investigation)
A CW player who graduates the Tatooine tutorial lands in a **vendorless 3-room
pocket** — the whole economy loop is walled off. Root cause: `build_mos_eisley.py`
**line ~199** gates the seed-room->city exit-linking on `era == "gcw"`, so for CW
the `else` branch SKIPS it and the pocket stays disconnected.
- **Fix direction:** run the linking for CW too. The CW Mos Eisley map EXISTS
  (`data/worlds/clone_wars/maps/mos_eisley.yaml`).
- **VERIFY BEFORE EDITING:** the GCW block uses `room_ids[7]` (spaceport),
  `room_ids[8]` (market), `room_ids[12]` (cantina_entrance). Confirm those
  yaml-ids exist in the CW build (grep the CW mos_eisley.yaml for the room ids +
  names), and **guard each lookup with `room_ids.get(...)`** + skip/warn if absent
  so it can't KeyError-crash the build. Also bump the `seed_exits = 6 if era ==
  "gcw" else 0` print at ~line 480.
- **Verify the fix:** rebuild the CW world + re-run the playthrough `economy`
  journey (or check that the graduation room reaches a vendor in the connected
  graph). This is a world-build change — sensitive; get the room ids right.

### 2. LOW: guide-protect (DEFERRED — not mine to touch)
Friendly tutorial guide Kessa Dray is attackable (murder her for First Blood).
Fix is in `server/session.py` `_classify_npc_role` (protect quest-givers/guides).
**`server/session.py` is the parallel session's active surface** — coordinate or
let them take it; do NOT edit it from this branch.

### 3. Gate + land
After the economy blocker: run the **threaded full suite** (xdist default HANGS on
this box; use `python -m pytest tests/ -n auto --dist loadscope -p no:cacheprovider
--continue-on-collection-errors --maxfail=300 --timeout=120 --timeout-method=thread
-o addopts= -q`). Known baseline-reds to expect (NOT regressions): 3 chain-
walkthrough smokes, `test_cities_phase4b` cargo-tax (watch-item #7), the mapgen
`term_boundaries` seed (parallel session's dirty working-tree; committed HEAD is
empty), and untracked `_verify_bacta.py`/`_probe_bacta*.py`. Then **re-merge
origin/main** (CHANGELOG/TODO union; watch for a real housing.py/code conflict),
and **ff main** via `git branch -f main HEAD && git push origin main` (checkout is
denied on this box).

## THEN — the UX upgrade (Brian's decided sequence: UI upgrade BEFORE a fun pass)

Brian confirmed: do the UI upgrade before any fun-assessment, because in a web
client the UI *is* a huge fraction of perceived fun, and the upgrade's thesis is
"surface the invisible depth that already runs" = the biggest engagement lever.
Two design docs are the spec (both already grounded against HEAD):
`docs/design/ux_engagement_roadmap_2026-06-23.md` + `dice_animation_and_ux_polish_2026-06-22.md`.

Consolidated build order (each ~1 drop, rides an existing producer seam, ships
jsdom contract tests + a gate):
1. **Clickable affordances** (CLAIM/SELL/FLEE + click-a-name) — includes the
   `get_combat` dead-hook fix it needs (`engine.combat` has no `get_combat`; the
   `_hud_room_contents` import silently swallows ImportError so `in_combat` is
   always False — add a real room->combat accessor over `_active_combats`).
2. **Combat HUD** (cover + wound track + coaching + the dice §5 hit-flash).
3. **Dice animation** (`drama` classifier at the skill-check funnel + real-dice
   renderer; pre-launch slice = Force powers + sabacc + combat finishing blow).
4. **Situation board** (SIT tab). 5. **Scene/presence UI**. 6. **Goals tracker**.
7. **Command palette** (Ctrl/Cmd+K). 8. **Polish batch** (living sheet delta-
   highlight, credit/XP tick-up, map pan, off-by-default sound).

## THEN — the fun-assessment campaign (ARMED, not launched)
`tools/_fun_wf.js` is a ready Workflow: 4 player archetypes + onboarding/systems/
world audits, vision-judged, with a synthesis agent producing a candid "is it fun
yet + prioritized recommendations" verdict. Launch it AFTER the UI upgrade lands
(so it judges the real shipping experience), via
`Workflow({scriptPath: "c:\\SW_MUSH\\tools\\_fun_wf.js"})`. Brian wants all four
dimensions weighted.

## Gotchas / standing constraints
- **Shared tree:** explicit pathspecs in `git add` (never `-A`); avoid
  `server/session.py` (parallel session's surface); ff-main races on origin/main
  (re-merge; conflicts are usually CHANGELOG/TODO union only).
- **`static/client.html`** is CRLF + has literal escape chars — if Edit fails,
  use a Python string-replace script (`open(newline='')`).
- **Onboarding fix** (this session) is pinned by structural tests; the authoritative
  behavioral check is re-running the playthrough `onboarding` journey on a fresh
  standalone-chargen player (do it once the economy blocker lands so graduation
  also works).
- **Command-syntax rework** deliberately deleted natural aliases (`inventory`,
  `who`) in favor of `+inv`/`+who` — fix dead BUTTONS by retargeting to the
  canonical form, or add a redirect STUB (not a full alias re-add). See the INV
  and `WhoStubCommand` precedents.
