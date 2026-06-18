# Claude Design Review — Parsec (working title SW_MUSH) web client — 2026-06-18

**Reviewer:** Claude (Opus), in-session visual review of the 17 handoff screenshots (`docs/design/ui_screenshots/`).
**Scope:** static desktop captures @1440×900. **Mobile/responsive + a11y were NOT assessable** from these (need narrow-width captures — see C2).
**Legend:** `[auto]` = the dev loops/main session can execute autonomously · `[brian]` = needs Brian (asset/decision) · `[capture]` = a capture-methodology caveat, not a product bug.

---

## BLOCKERS (before launch)

- **B1 — Public rebrand SW_MUSH → Parsec `[auto, gated on B1-domain]`.** The landing hero reads "STAR WARS D6 MUSH" (01); a trademark in the public title is the cheapest enforcement target (marketing-plan IP guardrail). Name decided = **Parsec**. Swap across `static/portal.html` title/meta/og/twitter + hero, GNN/holonet branding, footer, and the `[GAME NAME]` placeholders in `MARKETING_PLAN_2026-06-17.md`. *Hold the live flip until Brian confirms the `parsec.*` domain + a quick TM check (so we don't bake it in before it's secured).*

## HIGH — first-5-minutes + landing→play conversion (the launch-critical UX)

- **H1 — Landing "dead-game" empty state (01) `[auto]`.** Shows **"0 ONLINE"**, several `0` stats, and **"No recent events."** A stranger reads that as abandoned → bounce. Fix: pre-launch show "Launching soon" / suppress zero-value stats; at launch seed-or-hide the online count and curate the GNN feed so the page never looks empty.
- **H2 — No hero visual on the landing (01) `[brian]`.** It's pure text — the single thing that refutes "text game = boring" is a 5–10s gameplay GIF (room description → one combat round → the area map). The marketing plan calls this the highest-leverage asset for a text game. Brian records it; we frame it above the fold.
- **H3 — Ground client (04) overwhelms a brand-new player `[auto]`.** Three dense columns, flat hierarchy, every panel competing — and a confusing first session is the #1 MUD-killer. Fix: progressive disclosure for new characters (collapse faction-standing / achievements / mail / places until relevant), a "first steps" nudge in the center pane, and visually de-emphasize secondary panels. (The clickable command bar + direction chips are already a good newcomer affordance — keep + lean into them.)
- **H4 — Single primary CTA on the landing (01) `[auto]`.** `PLAY NOW` and `CREATE CHARACTER` are co-equal; the plan says don't split attention. Make PLAY NOW dominant; CREATE CHARACTER smaller/secondary.

## MEDIUM — polish + accessibility

- **M1 — Low contrast throughout `[auto]`.** Dim amber/grey secondary text (subtitles, labels, footers) on near-black sits below comfortable contrast and hurts scannability on every surface. Lift secondary-text luminance one tier; keep the datapad atmosphere. (Verify against WCAG AA once narrow/contrast captures exist.)
- **M2 — Mock-data artifacts that read as "broken" `[capture]`.** "0 cr" prices (07 shop) and "? · ?" target/faction (16 board) are mock-fixture field mismatches, not UI bugs — but they make commerce/contracts look unfinished. Verify the real backend data renders, and re-capture with realistic values.
- **M3 — Cryptic labels `[auto]`.** Craft materials render `x q62 / q80 / q55` with no label (15) — unclear they're quality values; board cards show `? · ?` (mock). Add field labels (e.g., "quality 62").

## LOW / polish

- **L1 `[auto]`** — Dense top nav (9+ items) on the landing; trim/group for first-time visitors.
- **L2 `[auto]`** — Holonet featured-story image is a placeholder (05); cockpit (11) is very dense but it's a power-user surface, so the density is acceptable there.

## CAPTURE / METHODOLOGY caveats (not product bugs)

- **C1 — Container-mode artifact `[capture]`.** Shop / inventory / craft / board (07/08/15/16) render crammed top-left with a large empty black field — that's the standalone container capture, not the real **centered, bounded modal**. Re-capture them framed for a fair layout review. (The framed modals — 05/06/11/13 — show the intended presentation.)
- **C2 — Mobile + a11y unassessed `[capture]`.** Focus states, touch targets, and the 3-column → narrow collapse can't be judged from 1440px desktop shots. Capture at ~390px width to review responsiveness before launch.

## STRENGTHS (keep / lean into)

- The **datapad/terminal aesthetic is cohesive and distinctive** across every surface — a real brand asset.
- **Holonet (05), character sheet (06), skill-check (12), holocron (13), and the galaxy navigator (10)** are genuinely polished and information-rich — among the best surfaces.
- The **clickable command bar + direction chips (04)** are a strong onboarding affordance for MUD newcomers.
- **Era-cleanness holds** in every capture (Republic / CIS / Hutt; no Imperial/Rebel/TIE).

---

### Suggested execution order (for the loops / main session)
1. H1 (landing empty-state) + H4 (CTA hierarchy) + M1 (contrast) — all `[auto]`, high-value, low-risk, ship now.
2. H3 (ground-view progressive disclosure) — `[auto]`, bigger; the highest-leverage onboarding fix.
3. B1 rebrand — `[auto]` but **hold the live flip** until Brian confirms domain/TM.
4. M3 + L1 + L2 — `[auto]` polish.
5. H2 (hero GIF) — `[brian]` asset; C1/C2 re-captures feed the final end-of-hardening pass.
