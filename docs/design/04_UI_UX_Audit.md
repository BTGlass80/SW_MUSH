# SW_MUSH UI/UX Audit

## Verdict

The web client is one of SW_MUSH's biggest opportunities. It is not merely a terminal wrapper; it is trying to become a cockpit/datapad interface for a crunchy multiplayer RPG. That is the right direction.

The main UX risk is that the interface may be visually rich but cognitively heavy. A new player can be impressed and still not know what to do. The UI needs to become less of a command cockpit and more of an intent cockpit: goals, context, affordances, feedback, and next steps.

I recommend treating UI/UX as a standalone audit track because it crosses game design, code, accessibility, security, and retention.

## UX principles for SW_MUSH

Every screen should answer these four questions:

1. **Where am I?** Location, mode, threat, safety, active context.
2. **What can I do here?** Local commands, NPCs, vendors, exits, contracts, hazards.
3. **What am I working toward?** Quest, profession goal, faction goal, communal objective, personal milestone.
4. **What changed because of my last action?** Result, reason, reward/cost, next option.

If a panel does not help answer one of those questions, it should be hidden until relevant or moved to secondary depth.

## Strengths

### 1. The client has a strong fantasy identity.

The mode-specific visual language — datapad/cockpit/terminal feel — supports the Star Wars fantasy better than a plain web terminal. This matters. A MUSH with a thematic web shell is more approachable than raw telnet.

### 2. Staged commands are a good safety pattern.

The client appears to stage some commands rather than immediately fire every button action. That is excellent for a game where commands can spend money, fire weapons, sell items, abandon objectives, or reveal position.

The pattern should be made universal and legible:

- low-risk command: send immediately,
- medium-risk command: stage with preview,
- high-risk/destructive command: stage + confirm.

### 3. Clean mode/local preferences are a good accessibility start.

Local preference storage and clean-mode concepts are valuable. Expand this into a full accessibility track.

### 4. Structured panels are the right answer to MUSH spam.

Inventory, maps, ship state, combat, vendors, and character sheet data should not all be text spam. SW_MUSH is correctly moving toward structured panels.

## Major findings

### UX-1 — P1: The UI needs a persistent “Next Best Action” panel.

For new players and returning players, the most important feature is not a map or stats. It is “what should I do next?”

Suggested panel:

```text
NEXT ACTIONS
1. Continue training: talk to Sela Tarn at Kayson's Workshop.
2. Earn credits: low-risk courier job available nearby.
3. Join the world: communal cult threat needs scouts and medics.
```

Each action should have:

- why it is recommended,
- risk level,
- expected reward type,
- button to stage the command or route.

### UX-2 — P1: The onboarding tour is not enough if it only tours UI chrome.

A UI tour that explains “this is the map, this is the log” is useful but insufficient. Players need a gameplay tour:

- how to move,
- how to inspect a room,
- how to talk to an NPC,
- how to accept/complete a task,
- how to use a staged command,
- how to understand success/failure,
- how to recover from trouble,
- how to ask for help.

**Recommendation:** convert onboarding into guided micro-actions, not just explanatory popups.

### UX-3 — P1: Command discoverability needs a command palette.

MUSH veterans know to type commands. Web players expect searchable actions.

Add a command palette opened by `?`, `/`, or a visible button:

- search commands,
- filter by local context,
- show required target syntax,
- show examples,
- stage command with placeholders,
- mark dangerous commands.

Example:

```text
Search: armor
- wear <item> — equip armor
- repair <item> — repair damaged armor
- learn <schematic> — learn armor schematic from trainer
- craft <schematic> — craft known schematic
```

### UX-4 — P1: Refusal messages need to become UX affordances.

A lot of game systems are gated: vendor stock, vendor presence, trainer presence, faction rep, skill, contraband, threat, room state, quest stage. A refusal can either frustrate the player or teach the game.

Standard refusal format:

```text
You cannot buy that here.
Reason: this vendor does not stock restricted weapons.
Try: craft it, find a specialist vendor, or ask underworld contacts.
```

Also provide buttons where possible:

- “Show nearby vendors,”
- “Open crafting list,”
- “Ask about underworld contacts,”
- “Track this goal.”

### UX-5 — P1: The log should be filtered by intent, not only chronology.

A MUSH log can drown important messages. The web client should classify output into channels:

- local room/RP,
- direct messages/pages,
- combat,
- system/refusal,
- rewards/costs,
- tutorial/help,
- faction/world events,
- admin/debug.

Players should be able to pin or filter important categories. Critical consequences should not scroll away unnoticed.

### UX-6 — P1: Combat UI should explain, not merely display.

Combat is where crunch can become either fun or opaque.

Recommended combat card:

```text
YOUR ACTION
Blaster shot vs B1 Droid
Roll: 17 vs difficulty 14 — Hit by 3
Damage: 4D+1 vs soak 3D — Droid is Wounded
Modifiers: range -1D, armor soak +1 pip, wound penalty -1D
Next: fire again, dodge, move to cover, retreat, call for aid
```

Keep the raw text for telnet, but give web players summarized cards.

### UX-7 — P1: Accessibility needs a deliberate pass.

Risks seen from static client structure/style:

- full-page `overflow: hidden` can trap small screens or zoomed users,
- many custom controls need keyboard and focus testing,
- color-coded states need text/icon redundancy,
- dense panels need screen-reader labels,
- animations/glow effects need reduced-motion support,
- command log needs readable contrast and font scaling,
- modals need focus trap and escape behavior.

Minimum accessibility launch bar:

- keyboard-only login, movement, command entry, modal open/close,
- visible focus indicator,
- no color-only critical state,
- text scaling to 150–200%,
- reduced motion option,
- aria labels for icon buttons,
- screen-reader-friendly modal titles.

### UX-8 — P1: The web client should stop accepting privileged `ev.html` by default.

This is both UX and security. If user-generated text ever reaches an HTML render path, trust is broken. Prefer structured message types over raw HTML.

### UX-9 — P2: Modal consistency matters more than visual variety.

Inventory, vendors, crafting, character sheet, maps, boards, faction panels, and ship panels should follow the same interaction language:

- title,
- current context,
- primary action,
- secondary actions,
- disabled actions with reasons,
- cost/risk preview,
- close/back behavior,
- keyboard shortcuts.

### UX-10 — P2: Maps need purpose, not just geography.

Maps should answer:

- where am I,
- where can I go,
- what is dangerous,
- what is relevant to my current goal,
- where are known vendors/trainers/contacts,
- where is the nearest safe recovery point,
- where is current world activity.

The mission-giver POI pin issue should remain a priority because maps without actionable pins are decorative.

## Recommended UI additions

### 1. Goal stack

A persistent right-side or top panel:

```text
ACTIVE GOALS
- Starter: Finish armor orientation. Next: talk Sela Tarn.
- Faction: Republic standing 42/50. Next: complete one patrol job.
- Personal: Learn Field Medscanner schematic. Need: 350 credits.
```

### 2. Opportunity scanner

Contextual “what is available here?” button:

```text
HERE YOU CAN
- Talk: Sela Tarn, Kayson
- Buy: common tools, food, basic blasters
- Learn: armor schematics
- Jobs: 2 local contracts
- Risk: safe settlement, low threat
```

### 3. Command palette

Searchable, context-aware, with examples and stage buttons.

### 4. Explain mode

A toggle that adds one-line explanations to mechanical output:

```text
Why this matters: higher faction rep unlocks advanced trainers.
```

### 5. Playstyle dashboard

For each role, show short-term goals:

- Crafter: orders, materials, schematics, repair jobs.
- Hunter: marks, warrants, leads, risk.
- Medic: injuries, supplies, patients.
- Scout: unexplored areas, hazards, route intel.
- Pilot: cargo, passengers, ship condition, routes.

### 6. UI telemetry without privacy creep

Track anonymized local/admin metrics:

- unknown commands,
- refused commands by reason,
- buttons clicked but not sent,
- staged commands abandoned,
- onboarding step dropoff,
- time to first completed action,
- modal open/close frequency,
- scroll not at bottom during critical messages,
- combat action hesitation.

This tells you where players are confused.

## Concrete acceptance tests

### New-player UX test

A non-MUSH player should be able to:

1. log in,
2. create/select character,
3. understand current location,
4. move once,
5. talk to an NPC,
6. accept or progress a starter objective,
7. earn or spend something,
8. explain what they plan to do next.

No external coaching allowed.

### Keyboard-only test

A player should be able to:

- log in,
- open command palette,
- move,
- open/close map,
- inspect inventory,
- stage/send command,
- close modal,
- read latest important result.

### Refusal quality test

Sample 50 refusal messages. Every one should include:

- what failed,
- why,
- what to try next.

### Dangerous action test

Selling, abandoning, firing, contraband carrying, destructive admin/build actions, and large purchases should have preview/confirm behavior appropriate to risk.

## Specific Claude prompts

### Prompt: UI next-action system

> Audit the SW_MUSH web client and server outputs for all places where the game knows a player's current objective, local NPCs, vendors, trainers, jobs, threats, faction state, tutorial state, and questline state. Design a minimal “Next Best Action” panel that uses existing data only. It should show 1–3 suggested actions with reason, risk, reward type, and a button to stage the command. Do not create new content first.

### Prompt: command palette

> Design and implement a web command palette for SW_MUSH. It should index registered commands, aliases, usage strings, local context actions, and examples. It must support keyboard navigation, staging commands with placeholders, and marking risky/destructive commands. Add jsdom tests for search, keyboard selection, staging, and no accidental send.

### Prompt: refusal-message UX pass

> Audit player-facing refusal/failure messages across parser and engine code. Convert them to a standard UX format: what failed, why, what to try next. Prioritize buy/vendor/trainer/crafting/faction/quest/combat/contraband failures. Add tests for representative refusals so future changes don't regress into dead-end messages.

### Prompt: accessibility pass

> Perform an accessibility audit of `static/client.html` and SPA modules. Check keyboard-only use, focus indicators, modal focus behavior, aria labels, color-only status, text scaling, reduced motion, and small-screen behavior. Produce a prioritized fix list and implement the smallest changes that make login, movement, map, inventory, command staging, and modal close accessible.
