# Web Onboarding (Webify UI-7) — Design v1

**SW_MUSH | Clone Wars · 2026-06-10**
**Status:** ACCEPTED-BY-CONSTRUCTION (grounded in HEAD symbols; genuine forks
logged, none blocking). Implementation lands in the same drop as this doc.
**Companions:** `web_client_vision_and_protocol_v1_4.md` (ABI ledger),
`cw_tutorial_chains_design_v1.md` + `Guide_16_Tutorial_Chains.md` (the chain
system this surfaces), `HANDOFF_webify_ui_implementation_2026-06-07.md` §3
(the accepted UI-7 concept sentence).

---

## 0. Mandate & stakes

Brian (2026-06-10): *"Onboarding is a major feature add. Let's make sure it
gets handled well, and thoroughly. It's one of the key features that will
encourage players sticking around."*

The competitive analysis rates the onboarding walkthrough **Very High
impact** — the highest on its board — and the retention literature it cites
(Torn's tutorial missions, Nexus's gated tutorial areas) agrees on the
mechanism: a new player who completes a guided first session converts; one
who stares at an unexplained terminal bounces. SW_MUSH's first session is
now genuinely good underneath (chains, the loop, the panels) — UI-7's job is
to make that visible in the first five minutes.

## 1. What already exists (HEAD audit — the load-bearing finding)

UI-7 is **not** a tutorial system. The tutorial system is BUILT and live:

- **Nine tutorial chains** (`data/worlds/clone_wars/tutorials/chains.yaml`):
  republic_soldier, republic_intelligence, jedi_path, jedi_path_independent,
  separatist_commando, separatist_agent, bounty_hunter, smuggler,
  shipwright_trader. 4–6 steps each (the two jedi entries are 1-step
  on-ramps into the Village), authored NPC briefings, per-step `teaches`
  command lists, objectives, completion contracts, rewards, graduation
  rooms.
- **Chargen starts the chain** — `server/api.py` (web chargen) writes
  `attributes.tutorial_chain = {chain_id, step:1, completed_steps:[],
  completion_state:'active'}` at character creation (skip path applies the
  era starter kit instead). A brand-new web player logs in already standing
  in their chain's starting room, on step 1.
- **Eleven completion hooks fire live** (`engine/chain_events.py`
  F.8.c.2.b): command_executed, talk_to_npc, combat_won, room_entered,
  mission_accepted/completed, bounty_accepted, item_acquired/used,
  prerequisite, skill_check_passed → `tutorial_chains.advance_step`.
- **Graduation works** (`engine/chain_graduation.py`):
  `execute_pending_teleport` broadcasts departure/arrival, teleports to the
  chain's drop room, runs a synthetic look. `completion_state` flips to
  `"graduated"` and persists in attrs.
- **Telnet parity exists**: `chain status` (parser/chain_commands.py) renders
  chain name / step / title / objective / completion type, and
  `chain attempt` drives skill_check steps. Both ride
  `engine.chain_events.get_active_step_info(char)` — whose docstring says
  *"Used by web HUD"*, **which nothing in the web path does yet**. That
  aspirational line is the seam this design fills.
- **UI-6 already surfaces the step objective** as the boxed line atop the
  vitals card (`hud_update.objective`, tutorial step = highest priority).
- **The loop the chains teach is now real on the web**: JOBS board (UI-5),
  inventory (UI-4a), shop (UI-4b), region (UI-2), condition chips (UI-3),
  reward juice (UI-6).

The accepted UI-7 concept (implementation handoff §3): *"Coach-mark layer
over the existing client (not a new sandbox); `onboarding_state` + the
F.8.c.2.b completion hooks."* This design is that sentence, expanded.

## 2. What UI-7 is — three layers

### Layer A — The training panel (the spine)

A right-column `.side-panel` (sibling of region/rep/ach panels, placed
**first** in the stack — it is the new player's primary surface), driven by
a new `onboarding_state` push. Visible iff the character has an active
chain; veterans and graduates see nothing.

Anatomy, top to bottom:
1. **Head**: chain name + `STEP n/M` + a `?` affordance (replays the
   first-run tour on demand) + the standard collapse toggle.
2. **Step rail**: M dots — filled = completed, ringed = current, hollow =
   ahead. The visual "I am making progress" instrument.
3. **Step title** + **NPC line** (`npc` · `npc_role`).
4. **Briefing** — the step's authored `npc_intro`, rendered as spoken text.
   This is re-display of dialogue the NPC already delivered in the stream;
   the panel keeps it in reach after it scrolls.
5. **Objective** — bold, mirrors the UI-6 line.
6. **Teaches chips** — one chip per `teaches` token. Click → **stage** the
   token into the input (token + trailing space; never auto-sent). These are
   authored, real commands straight from the corpus — the panel cannot
   invent a verb because it only renders what the yaml teaches.
   Special case: `completion_type == 'skill_check_passed'` adds an
   **ATTEMPT** chip staging the real `chain attempt`.
7. **Step-complete flash** — when the pushed `step` increases, a one-beat
   `STEP COMPLETE` band + rail-dot fill. Credits rewards already toast via
   the UI-6 `credit_event` riders — no new reward plumbing.
8. **Graduation card** — on the active→graduated transition (see §3 memo
   semantics), the panel renders a one-time `CHAIN COMPLETE — <name>` card
   with the drop-room arrival already handled by the existing teleport
   messaging; DISMISS hides the panel for good.

### Layer B — Quick-action coach pulses

Teach tokens that correspond to existing quick-action buttons pulse that
button for a few beats when the step renders: `look`→LOOK, `say`/`talk`→SAY,
`+bounties`→JOBS. Finite CSS animation (≈6 pulses, then still) — no state,
no JS cleanup, no nagging. Tokens without an anchor are chips only.
**No new anchors are invented for this** — the mapping covers what exists;
`+sheet`, `+missions`, `attack`, etc. remain chip-only.

### Layer C — First-run client tour

Four sequential coach marks over the client chrome, shown **once per
browser** (`localStorage['m3_onboard_tour_done']`, try-wrapped — the
`fk_clean_mode` convention) and **only when an active chain is present**
(veterans never see it):
1. the input bar — commands live here;
2. the quick-action row — staging shortcuts;
3. the objective line — your current goal;
4. the training panel — your chain, with tappable command chips.

Each mark = dim overlay + spotlight ring (positioned off
`getBoundingClientRect`) + caption + NEXT / SKIP TOUR. The panel-head `?`
replays it on demand. This is the only piece of UI-7 with client-side
persistence, and it is cosmetic (which hints you've seen), never game state.

## 3. The `onboarding_state` ABI (pinned in protocol ledger §1.8)

Producer: **extend, don't add** — `engine/chain_events.py` gains
`build_onboarding_state(char, era=None)` layered on the existing
`get_active_step_info` machinery (same `_get_corpus` cache; the HUD tick
never re-reads chains.yaml):

```
active chain   → { active: true, chain_id, chain_name,
                   step:int, total_steps:int, completed_steps:[int],
                   title, objective, location, npc, npc_role, npc_intro,
                   teaches:[str], completion_type }
graduated      → { active: false, graduated: true, chain_id, chain_name }
no chain ever  → None
```

`get_active_step_info` itself is extended **additively** with
`chain_total_steps`, `teaches`, `npc_role`, `npc_intro`,
`completed_steps` (existing consumers — `chain status`, `chain attempt`,
tests — read named keys and keep working).

Push: `server/session.py::_hud_sidebar_onboarding(char)` in the
sidebar-panel section of `send_hud_update` (the `_hud_sidebar_region`
pattern; WS-only by construction). **Graduation memo semantics** (the
`_last_sent_credits` precedent): the session tracks
`_last_chain_step = (chain_id, step) | None`. Active → push every tick
(panel state is cheap and idempotent). Graduated payload → pushed **once**,
only when the memo shows the chain was active this session; a reconnect
after graduation pushes nothing (no zombie celebration). Memo clears after
the graduation push.

## 4. Honesty rails (restated for this surface)

- **No invented verbs.** Every staged string is either a corpus `teaches`
  token or the real `chain attempt`. Staged, never auto-sent.
- **No web-exclusive state.** Everything the panel shows is reachable by
  text: `chain status` (step/title/objective/type), the NPC's streamed
  dialogue (briefing), the yaml-authored teaches embedded in that dialogue.
  The tour-seen flag is cosmetic browser state, not game state.
- **No producer-less fields.** Every field maps to a chains.yaml column or
  live attrs state. (`in_step_location` — "you're in the wrong room" — was
  considered and **deferred**: it needs a room-id↔slug resolve on the hud
  tick; Phase 2 candidate, logged.)
- **Telnet untouched.** The push is supplemental; `chain status` is
  unchanged except for the additive producer fields it doesn't read.
- **tutorial_v2 (core/electives) is OUT of scope.** It is the parallel
  elective system; the CW chains are the live chargen path. Surfacing
  electives is a Phase 2 candidate, logged — not silently half-built.

## 5. Phasing

**Phase 1 — this drop:** everything in §2–§3. Producer + push + panel +
chips + pulses + step flash + graduation card + tour + tests + ledger §1.8.

**Phase 2 — logged candidates (not built, not promised):**
`in_step_location` room hint · tutorial_v2 elective rail post-graduation ·
a missions web modal (the `+missions` teach token currently stages text
only) · NPC portrait/dialogue theming in the briefing block · per-chain
accent theming.

## 6. Test plan (sandbox-runnable)

- `tests/test_onboarding_state.py` — `build_onboarding_state` against a
  stubbed corpus through the `_get_corpus` seam (the UI-6 test pattern):
  active shape + field passthrough, completed_steps, graduated shape,
  no-chain None, additive `get_active_step_info` keys still present for
  legacy consumers, malformed-attrs tolerance.
- `tests/spa/test_m3_onboard.py` (jsdom) — rail counts/states; chips stage
  `token + ' '` exactly with a drop/give/invented-verb-never guard; ATTEMPT
  chip appears only for skill_check steps and stages `chain attempt`;
  step-increase render shows the flash + fills the rail; graduated payload
  renders the card and DISMISS hides; pulse class lands on mapped qa
  buttons only.
- Wireup load order += `m3_onboard.js`.
- Existing `chain status` / chain_events tests stay green (additive
  producer).

## 7. Fork log

- **DECIDED here (grounded, non-blocking):** panel placement (first side
  panel — primacy for the audience), push cadence (every hud tick while
  active — idempotent render), chip staging form (`token + ' '`), finite
  pulses (no nag), tour persistence (localStorage, established convention),
  graduation-once memo.
- **FLAGGED, not built:** Phase 2 list above (each is additive on this
  ABI). **No fork blocks Phase 1** — Brian's review happens on the working
  surface, where it's cheapest to adjust copy, placement, and pacing.
