# Help + Guides Rework — Plan & Conventions (v1)

Spec for `PRELAUNCH.help_guides_rework` (TODO.json tier_2_queued). Captures Brian's
2026-06-13 decisions so the end-of-cycle rework is execution, not re-litigation. Primary
dev runs in a parallel session in engine/parser/data-code; this whole effort lives in
`data/guides/`, `data/help/`, and `docs/dev/` — a disjoint surface, so it is parallel-safe.

## What the audit found (the starting state — better than feared)

- **Storage is flat markdown**, not DB or code-embedded. Guides: 24 files in
  `data/guides/` (`Guide_01..26`, gaps at 13/15), loaded by
  `server/web_portal.py::_load_guides()`. Help: 71 markdown files in `data/help/{topics,commands}/`
  (loaded by `engine/help_loader.py` into `data/help_topics.py::HelpManager`) + 48
  hardcoded `TOPIC_HELP` entries + ~140 auto-registered command-help entries. Editing
  content = editing `.md` files. No migration.
- **Format is ALREADY uniform.** All 24 guides share identical frontmatter
  (`category`/`order`/`summary`/`tags`) and an identical title-header + numbered-section
  layout. The "get them into the same format" ask is largely already satisfied — minimal
  reformatting work.
- **Hyperlinks are ALREADY consistent.** Every cross-reference uses
  `[label](#/guide/slug)`, rendered by the web portal. Work here is *auditing for dead
  links* (stale slugs after months of change), not standardizing syntax.
- **Dual-track structure:** 8 of the 24 guides split each section into `### Player Rules`
  and `### 🔧 Developer Internals` (61 dev headings total, marker 100% consistent). This
  is the real "developer notes in player content" issue — it is structural and by design,
  not a few stray lines.
- **Admin seam exists for help, NOT for guides.** `HelpEntry.access_level` (0/2/3) gates
  help topics (`building.md`, `@city.md` are level 2) and in-game `+help` hides
  Building/Admin categories from non-admins. Guides have **no `access_level` field** —
  all 24 are visible to everyone. No administration guide exists.

## Brian's decisions (2026-06-13)

1. **Dev track → SPLIT OUT, not deleted.** Extract every `### 🔧 Developer Internals`
   section from the 8 guides into a parallel `docs/dev/` set (preserved for Brian/Claude),
   leaving the player guides clean. Content-preserving relocation.
2. **Admin guide: YES. Admin wall on existing guides: NO.** The 24 existing guides are all
   genuinely player-relevant — leave them ungated (`access_level: 0`). Author ONE new
   administration guide for Brian, gated to admins.
3. **Scope now = SAFE WINS ONLY.** Do the changes that future feature work cannot
   invalidate; defer per-system accuracy rewrites to the end (once the feature suite is
   frozen), per the item's existing PRE-RELEASE status.

## Resolving the decision interaction

"Split the dev track" (a change to all 8 dual-track guides) vs. "just the safe wins" reads
like a conflict. It is not: the split is a **mechanical, content-preserving relocation** of
existing text — it cannot be invalidated by a future economy/combat change, because it
moves text rather than re-deriving it from systems. So the split COUNTS as a safe win and
is in-scope now. What stays deferred is the **accuracy rewrite** (does Guide_06 still
describe the *real* current economy?) — that waits for system freeze.

## Work plan

### Phase A — DONE (2026-06-13)

Executed: dev-track split (1,092 lines out of 8 guides → `docs/dev/internals_*.md`),
`### Player Rules` labels + `File Reference`/`Implementation Status` sections removed, the
generic two-track boilerplate preamble stripped from Guide_01/02 (the 18 rewritten "How to
Read" intros KEPT — confirmed against the existing `TestGoldStandardRewrites` spec). The 3
city-guards placeholder leaks (Guide_12) and 2 era findings (Guide_11 `look`-example →
Republic; Guide_21 fcomm prefixes → drop Empire) stripped. Guide_04's "Empire will
eventually" line KEPT as sanctioned CW-vantage flavor (marked `lint-era-ok`). Authored
`Guide_27_Administration.md` (access_level 3) against the live registry (30 verified admin
commands; explicitly notes the non-existent verbs). Wired guide `access_level` gating into
`server/web_portal.py` (`_load_guides` + both handlers) so the admin guide is hidden from
players — new test class `TestGuideAccessGating` (5 tests) + count/category pins updated.
`guide_lint`: 0 actionable. 43 guide tests + 39 portal tests green. Tools:
`tools/split_guide_dev_track.py`, `tools/guide_lint.py`.

Engine-side finding logged for the era sweep (NOT fixed here — engine surface, parallel
session): `engine/territory.py:785` emits the literal `"The Empire's presence is felt
here"` for the `empire` faction key — a real GCW string in a live producer.

### Phase A — original plan (safe wins; all delivered above)

1. **Strip the 3 confirmed dev-note leaks** from player-facing prose (exact lines):
   - `Guide_06_Economy.md:34` — "...documented but not yet implemented." → reword to
     describe only what players experience today, no roadmap leak.
   - `Guide_12_Player_Cities.md:148` — "(a planned later feature — placeholder for now)."
   - `Guide_12_Player_Cities.md:289` — "placeholder for a future feature... Not live yet."
   For 148/289: either cut the `+city guards` entry entirely, or keep a one-line
   player-true statement ("City guards are not available."). Brian's call at edit time;
   default = cut the forward-looking phrasing, keep a terse present-tense truth.
2. **Dev-track split** (the 8 guides with `### 🔧 Developer Internals`): for each, move the
   dev subsections into `docs/dev/internals_<NN>_<slug>.md` (new files), delete them from
   the player guide, and remove the now-orphaned "How to Read This Guide / two tracks"
   preamble. Comment-preserving string edits; the guide loader tolerates the shorter files
   (frontmatter unchanged). Net result: player guides become single-track and clean.
3. **Dead-link audit**: resolve every `[label](#/guide/slug)` slug against the actual guide
   set; fix or drop links whose target no longer exists. (Tooling: the guide-lint below.)
4. **Author the administration guide** — `Guide_27_Administration.md` (new, additive),
   `access_level: 3` in frontmatter. Covers the staff/builder surface: `@dig`/`@tunnel`/
   world-edit commands, `is_admin` powers, the Director AI admin controls, spawn/grant
   commands, moderation. Verify EVERY command named against the live registry
   (no phantom commands — grep parser/ at author time). This is the one net-new content
   piece; it's additive so it cannot break a player guide.

### Phase B — deferred to system freeze (end of cycle)

5. **Per-system accuracy pass**: walk each guide against its shipped subsystem and correct
   anything stale (dice codes, command names, economy numbers, faction model). This is the
   bulk of the original item and MUST wait until features stop moving.
6. **Cross-link enrichment**: add `[label](#/guide/slug)` references where new systems
   lack them.

## Conventions (the unified format, for Phase B authors / the accuracy pass)

- **Frontmatter:** keep the existing schema verbatim (`category`, `order`, `summary`,
  `tags`). For the admin guide add `access_level: 3`. Do NOT add `access_level` to the 24
  player guides (decision 2).
- **Single track:** after Phase A, player guides have NO `### 🔧 Developer Internals` and
  NO "two tracks" preamble. Dev content lives only in `docs/dev/`.
- **Hyperlinks:** `[label](#/guide/slug)`, slug = kebab-case of the title. Nothing else.
- **No dev-note vocabulary in player prose:** no "not yet implemented", "placeholder",
  "WIP", "TODO/FIXME", "Not live yet", file paths, function names, or design-doc
  citations. The guide-lint enforces this.
- **Era cleanness** still applies to guide prose (CW, no Imperial/Empire/Rebel/TIE except
  the sanctioned director-axis / era-mapping contexts).

## Tooling: `tools/guide_lint.py` (built now)

Read-only checker over `data/guides/` + `data/help/`. Flags, per file: (a) dev-note
vocabulary in player-facing prose, (b) `### 🔧 Developer Internals` headings still present
in a player guide (post-Phase-A regression guard), (c) dead `#/guide/<slug>` links whose
slug has no matching guide, (d) era-cleanness violations in prose. Advisory only — never
edits, never blocks. Run before/after the rework to measure and to prevent backslide.
