# Design — `+sheet` GUI Redesign (Roadmap, post UI fixes)

**Status:** Roadmap.  Not in current UI fix sweep.
**Sourced from:** Apr 27 session — Brian observed that the current `+sheet`
is a Telnet-era holdover that doesn't take advantage of the GUI, and that
chargen has rich tooltip content (`data/skill_descriptions.yaml`) which is
lost once the character is built.

---

## The problem in one paragraph

`+sheet` today refreshes the left sidebar HUD (attributes, vitals, credits,
CP, equipment) and shows nothing else.  The full character — skills,
specializations, force powers, advantages, disadvantages, chargen rationale,
trained-skill counts, the player's own notes — is invisible in the GUI.
Chargen builds a vivid picture of *who* this character is using
`data/skill_descriptions.yaml` (1,122 lines of WEG40120-sourced descriptions,
game-use notes, gameplay rationale, and icons), but once the character is
created, none of that surfaces in normal play.  `+sheet/skills` and
`+sheet/combat` exist but only emit text dumps — not what the GUI deserves.

A character sheet is the deepest single piece of UI a player interacts with
between sessions.  It should be a destination, not a sidebar afterthought.

---

## Goals

The redesigned `+sheet` should feel like *opening your character file* — a
modal or full-content panel that's a pleasure to read and explore, not a
text dump and not a sidebar refresh.  Specifically:

1. **Show everything the character actually has** — attributes, all trained
   skills (grouped by attribute), specializations, Force skills + powers,
   advantages, disadvantages, equipment, credits, CP, wound state, FP, DSP,
   biographical fields (species, gender, homeworld, age, height, hair, eyes),
   and the player-supplied background.
2. **Resurface chargen tooltips** — clicking or hovering a skill shows the
   description + game_use from `data/skill_descriptions.yaml`.  Same for
   attributes.  Same for Force powers.  No more "what does Survival actually
   do" amnesia after chargen.
3. **Group sensibly** — attributes left, skills grouped by attribute pool
   underneath, force powers in their own pane, biographical/RP at the
   bottom or in a tab.  Whatever the layout, *no infinite scroll* of raw
   skill rows.
4. **Be fast to read** — at a glance, the player should see total skill
   count, weapon proficiencies, signature specializations, current vitals.
   Detail is one click away, not always-visible.
5. **Stop the silent-feedback problem** — typing `+sheet` should produce
   immediate visible response in the GUI, not just a sidebar refresh.

---

## Existing assets to reuse

**Don't rebuild what's already there:**

- **`data/skill_descriptions.yaml`** — 1,122 lines.  Has per-skill
  `description`, `game_use`, `gameplay_note`, `icon`, plus per-attribute
  versions of all of the above.  Has the wood-panel-textbook content that
  chargen uses.  Surface this as tooltips.
- **`engine/sheet_renderer.py`** — `render_game_sheet`, `render_brief_sheet`,
  `render_skills_sheet`, `render_combat_sheet`.  Already does the data
  collection + grouping logic.  The redesign reuses the data assembly,
  swaps the `render_*` text emission for a structured payload sent over
  WebSocket as a `sheet_data` event.
- **`server/session.py::send_hud_update`** — the well-tested HUD pipeline.
  The new `sheet_data` event is a sibling of the existing HUD event,
  not a replacement.
- **Chargen wizard's tooltip styling** — the descriptions render somewhere
  in the existing chargen UI.  The same component should render them in
  `+sheet`, so the look-and-feel matches.

**Files likely to be touched:**

- `parser/builtin_commands.py::SheetCommand` — emit `sheet_data` event
  instead of (or in addition to) the current behavior
- `engine/sheet_renderer.py` — add `build_sheet_payload(char_dict, skill_reg)`
  alongside the existing `render_*` text functions
- `static/client.html` — add a sheet modal with tabs (Stats / Skills / Force
  / Background), wire `case 'sheet_data'` in the WebSocket dispatcher
- `static/portal.html` — possibly mirror in the portal "My Characters" tab

---

## Open questions for design

1. **Modal or panel?**  A full-screen modal (like the sector map modal) is
   immersive but heavy.  A right-side slide-out panel is lighter but might
   feel cramped on the data this should surface.  Recommend mockups before
   committing.
2. **`/skills` and `/combat` switches** — keep them as text-dump fallbacks
   for Telnet, or fold them into tabs of the modal?  Easier to keep them
   as fallbacks; the GUI doesn't need switch-driven views when it has tabs.
3. **Edit-in-place?**  Background, notes, and aliases could be editable
   from the sheet (with a save button) rather than requiring `+bg` /
   `+notes` commands.  Nice-to-have, not required for v1.
4. **Tooltip vs. drawer?**  A small tooltip on hover is quick.  A drawer
   that opens a panel with the full description, game-use, and gameplay
   rationale gives a richer learning surface.  Probably want both:
   tooltip for the short, drawer for the long.

---

## Latent bugs to fix in the same drop

While investigating: `+sheet/skills` may be silent in the GUI even though
`render_skills_sheet` produces text.  The current code path:

1. `send_hud_update` runs and succeeds (sidebar refreshes silently).
2. The early-confirmation `send_line` is skipped because `"skills"` is in
   `ctx.switches`.
3. The `for line in lines` loop dumps the rendered text via `send_line`.

If step 3 truly produces no visible output in the GUI, the most likely
causes (untested in this design — verify before fixing):

- The pose-log classifier may be filtering the rendered text under the
  same logic that prevented the original "sheet bleed."  If so, route
  the output through a different channel (e.g., a `sheet_text` event
  type the client renders into a dedicated area).
- Switch parsing may not be normalizing `/skills` consistently — check
  whether `ctx.switches` stores `"skills"` (lowercased, no slash) or
  something else.
- The character may have no trained skills, in which case
  `render_skills_sheet` emits a single dim "No trained skills." line that
  is easy to miss in the comms feed.

Fold these into the `+sheet` redesign rather than spot-fixing the text-dump
path; the redesign obsoletes the issue.

---

## Sequencing

This work is **NOT in the current UI fix sweep** (UI #1 reference, #2 space
state + sheet feedback, #3 space mode, #4 patrol frequency, #2a label
scaling, #2b ground-UX overhaul).  It comes after the UI sweep finishes and
the current UI fix #2's confirmation line is no longer needed because the
real GUI sheet exists.

Estimated effort: **2–3 sessions.**  Session 1 = data assembly + WS event
+ basic modal.  Session 2 = tooltips + chargen content surfacing.
Session 3 = polish + the latent `/skills` bug.

---

*End of design.*
