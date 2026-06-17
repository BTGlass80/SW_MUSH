# Claude Design — UI/UX Review Handoff Package

**Purpose:** a fresh-eyes design review of the *built* SW_MUSH web client (we are past
prototyping). This fills the pre-launch QA campaign's one explicit coverage gap — *no
automated agent could review the SPA's visual/UX layer* — and targets the two things
that actually convert a curious visitor into a retained player: **a clean first 5
minutes** and a **credible landing page**.

Screenshots live in [`docs/design/ui_screenshots/`](ui_screenshots/). Regenerate any time
with `python tools/capture_ui_screenshots.py` (drives system Edge via Playwright).

---

## 1. The product (context)
A **free, browser-playable** (also telnet) persistent-world Star Wars **MUSH/MUD** set in
the **Clone Wars era (~20 BBY)**, on the authentic **WEG Star Wars D6 Revised & Expanded**
ruleset. Solo-developed. The web client is a vanilla-JS SPA (no framework) with a
datapad/terminal aesthetic — amber-on-dark, monospace, "in-universe device" feel.
Differentiators: a **"living galaxy" Director AI**, deep D6 mechanics (combat, crafting,
factions, territory, smuggling, Jedi/Force), and the web client itself (lowers the barrier
vs telnet-only MUDs). Target player: MU*/text-game players + WEG-D6 tabletop fans.

## 2. What to review — ranked goals
1. **Onboarding / first-5-minutes UX** — the #1 MUD killer is a confusing first session.
   Look at landing → login → character creation → first ground view as a *new player who
   has never played a MUD*. Where do they get lost? Is the "what do I do now" obvious?
2. **Landing → play conversion** — does the landing page (01) make a stranger want to
   click "play"? Is the pitch clear above the fold? Is the path to playing one obvious step?
3. **Visual polish & consistency** — typography, spacing, color/contrast, alignment, the
   density of the in-game HUD (04). Does the datapad aesthetic hold together across every
   surface, or are there inconsistent panels?
4. **Information hierarchy in the ground client (04)** — the sidebar + center + context
   panel carry a LOT. Is it scannable, or overwhelming? What should be de-emphasized?
5. **Mobile responsiveness & accessibility** — contrast ratios, focus states, touch
   targets, whether the 3-column layout collapses sanely on narrow screens.

Deliverable we want back: a **ranked punch-list (blocker → polish)** with specific,
actionable fixes. The dev side executes it.

## 3. Hard constraints
- **Era-clean (Clone Wars ~20 BBY):** no Imperial/Empire/Rebel/TIE/Sequel references in
  any suggested copy or content.
- **All visual assets must be ORIGINAL.** This is an *unlicensed* Star Wars fan project on
  a deliberately **low-key / community-first** footing (to minimize Disney/Lucasfilm C&D
  risk). Do **not** suggest or use Star Wars trademark logos, fonts, or art. Original
  wordmark/iconography + the game's own screenshots only. (Public name will also change
  from the working title "SW_MUSH" to an original, non-trademarked name.)

## 4. Screenshot index
Captured at 1440×900, 2× DPI, system Edge. *Note: the **pre-login surfaces (01 landing, 02
login, 03/03b chargen) are captured LIVE against the real backend** — real data, the actual
new-player funnel. The **in-game** surfaces (04+) are populated with representative MOCK data
(a sample character "Tey Voss" in Mos Eisley) so the review is about layout/visual design,
not the specific values — e.g. shop prices show placeholder "0 cr".*

| # | File | Surface | Notes |
|---|------|---------|-------|
| 01 | `01_landing_portal.png` | **Landing / portal** (pre-login marketing+pitch surface) | first impression; the conversion hook |
| 02 | `02_login_boot.png` | **Login / boot** screen | the SPA boot + auth entry |
| 03 | `03_chargen.png` | **Character creation** — step 1, *Choose Your Path* (9 era-correct templates + Build From Scratch) | the onboarding funnel entry; **captured live** (real backend data) |
| 03b | `03b_chargen_attributes.png` | **Character creation** — step 3, *Allocate Attributes* (18D across the six D6 attributes w/ ± steppers, live remaining-dice counter) | the core chargen interaction; **captured live** |
| 04 | `04_ground_play.png` | **Integrated ground client** — the core play view (sidebar: char/condition/attributes/credits/CP/loadout · center: room · context panel: map/zone-influence/recent · command bar) | the most-used surface; one minor sub-panel (HERE/occupants) was skipped by a mock-data gap — its layout slot is visible |
| 05 | `05_holonet.png` | **Holonet** in-game news browser (modal) | the Director-AI news surface |
| 06 | `06_sheet.png` | **Character sheet** (modal) | full D6 stats |
| 07 | `07_shop.png` | **Shop / vendor** panel (droid tabs + slot-tagged items + BUY) | the commerce surface |
| 08 | `08_inventory.png` | **Inventory** panel (equipped + carried) | gear management |
| 09 | `09_map_preview.png` | **Area map** renderer (standalone preview) | the spatial/navigation surface |
| 14 | `14_ground_combat.png` | **Ground combat HUD** — the combat strip over the ground view (initiative cards w/ wound rungs + declared actions, YOUR ACTIONS / WAITING ON, and the color-coded damage feed) | the core combat experience |
| 11 | `11_space_cockpit.png` | **Space cockpit / flight console** — the full space mode (tactical radar, target lock, hull/shields/systems, crew stations, hyperspace plot, comms, and the space combat declaration strip) | the whole space + space-combat experience |
| 12 | `12_skill_check.png` | **Skill-check** showcase (unopposed + opposed rolls, dice pools, difficulty, result callouts) | the D6 dice-resolution UX |
| 13 | `13_holocron.png` | **Holocron** in-game knowledge/lore browser (modal) | the codex/learning surface |
| 15 | `15_craft.png` | **Crafting** panel (schematics + resource ledger + last-result) | the crafting system |
| 16 | `16_board.png` | **Jobs / bounty board** (tier filter chips + contract cards + reward hierarchy) | the contract/mission surface |

## 5. Known gaps / caveats
- **All in-game surfaces show representative MOCK data** (sample char "Tey Voss" in Mos
  Eisley / sample combat + ships). The review is about **layout / visual design / UX flow**,
  not the values: e.g. the shop shows "0 cr" and the bounty board shows "?" target/faction
  fields — those are mock-data field mismatches, not UI bugs. The *layouts* are faithful
  (these are the real production components + CSS).
- **Surfaces best captured from a LIVE session** (the definitive end-of-hardening pass will
  re-capture everything live so it reflects the final UI + real data): the **combat-mechanics
  inspector** (the collapsible per-hit dice/soak/wound breakdown — event-driven, no fixture),
  the **region/territory** view, the **onboarding/tutorial overlay**, and the live-populated
  **HERE/occupants** + **area-map** panels on the ground view (04). Nothing here blocks the
  review — they round out coverage.
- These 15 are a **current snapshot** for an early review. When the UI is locked (incl. the
  new public name + landing changes), `python tools/capture_ui_screenshots.py` regenerates
  the set; the final pass will be captured against a live server for full fidelity.

## 6. Where the code lives (if you want to inspect markup/CSS)
- Main client + all CSS: `static/client.html` (single file, ~13k lines).
- SPA component modules: `static/spa/m3_*.js` (holonet, sheet, shop, inventory, combat
  inspector, map navigator, palettes, asset catalogs).
- Landing/portal: `static/portal.html`. Chargen: `static/chargen.html`.
- Palette/tokens: `static/spa/m3_palettes.js`, `static/spa/m3_tokens.js`.
