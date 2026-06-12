# SW MUSH — Help System Rename + Content Pass Design

**S54 design doc · April 18, 2026**

## Goal

Move all "game" commands to canonical `+verb/switch [args]` form, with bare-word forms preserved as aliases. Author rich per-command help markdown for every game command, citing WEG sourcebooks where mechanics are lifted. Match the information density of the existing 47 `data/help/topics/*.md` files.

## Convention (locked)

```
+<verb>/<switch> [args]

Examples:
  +combat/attack greedo
  +combat/aim 2
  +mission/accept m-4f3a
  +ship/launch
  +crew/order pilot evade
```

- **Switch** = the operation modifier following `/`, MUSH-tradition.
- **Args** = whatever follows after a space.
- The **bare form remains as an alias.** `attack greedo` keeps working — only the canonical key moves.
- **`+help <bare>` redirects** to the canonical entry. Players asking `+help attack` see the `+combat` page (or `+combat/attack` sub-page if we add per-switch help).

## Architecture decision (locked)

**Umbrella command per verb namespace.** Replace per-verb classes with one umbrella class registered as the `+verb` key, dispatching internally on `ctx.switches[0]` (canonical) or `ctx.command` (alias). This is the **only** model that works given:

- aliases are unique across the registry — can't have two classes claim `+combat`
- the parser strips switches before lookup, so `+combat/attack` → looks up `+combat`
- the existing `CombatStatusCommand` (`+combat`) already uses the switch-dispatch pattern with `valid_switches = ["rolls", "status"]`

**Within each umbrella class:**
- One `execute()` that dispatches to private `_<verb>()` handlers
- Each `_<verb>()` is the body of an old per-verb command's `execute()` lifted in
- Module-level helpers (`_active_combats`, `_get_or_create_combat`, `_npc_behaviors`, etc.) stay where they are — external imports continue to work
- `valid_switches` lists every operation, e.g. `["attack", "dodge", "parry", "aim", ...]`
- Aliases include both the bare verbs (`attack`, `dodge`, `parry`, ...) AND short combinations (`att`, `kill`, `shoot`, `hit` for attack)

## Module-by-module rename map

### combat_commands.py — `+combat/*` (PROOF OF PATTERN, this drop)

18 commands consolidate to one umbrella class:

| Switch | Old class | Old key | Aliases preserved |
|---|---|---|---|
| /attack | AttackCommand | attack | att, kill, shoot, hit |
| /dodge | DodgeCommand | dodge | (none) |
| /fulldodge | FullDodgeCommand | fulldodge | full dodge, fdodge |
| /parry | ParryCommand | parry | (none) |
| /fullparry | FullParryCommand | fullparry | full parry, fparry |
| /aim | AimCommand | aim | (none) |
| /flee | FleeCommand | flee | run, retreat |
| /pass | PassCommand | pass | (none) |
| /resolve | ResolveCommand | resolve | (admin) |
| /disengage | DisengageCommand | disengage | (none) |
| /range | RangeCommand | range | distance |
| /cover | CoverCommand | cover | hide |
| /forcepoint | ForcePointCommand | forcepoint | fp, +fp |
| /pose | CombatPoseCommand | cpose | combatpose |
| /rolls | CombatRollsCommand | crolls | combat rolls |
| /challenge | ChallengeCommand | challenge | duel |
| /accept | AcceptCommand | accept | (PvP-only) |
| /decline | DeclineCommand | decline | refuse |
| (default, no switch) | CombatStatusCommand | +combat | combat, cs, +cs |

`accept` collision: this is the combat PvP-challenge accept. Mission-accept (`+mission/accept`) and smug-accept (`+smuggle/accept`) live in their own umbrellas. The bare `accept <name>` still reaches the combat one via alias precedence.

`order` collision: not in combat. Lives in crew_commands and space_commands.

### Other modules — to be done in subsequent drops

After combat_commands.py validates the pattern:

- **mission_commands.py** → `+mission/{accept,complete,abandon}`
- **smuggling_commands.py** → `+smuggle/{accept,deliver,dump}`
- **bounty_commands.py** → `+bounty/{claim,collect,track}`
- **narrative_commands.py** → `+quest/{accept,complete,abandon}` (or merge with mission?)
- **crafting_commands.py** → `+craft/{start,survey,experiment,teach,resources,buyresources,schematics}`
- **crew_commands.py** → `+crew/{hire,dismiss,assign,unassign,order}`
- **space_commands.py** → split by station: `+pilot/*`, `+gunner/*`, `+sensors/*`, `+bridge/*`, `+ship/*`
- **shop_commands.py** → `+shop/{browse,market}` (keep `shop` as separate scoped command)
- **places_commands.py** → `+place/{join,depart,places}` (keep `tt`, `mutter`, `ttooc` as bare RP shortcuts)
- **espionage_commands.py** → `+spy/{assess,eavesdrop,intercept,investigate}`
- **medical_commands.py** → `+medical/{heal,accept}`
- **housing_commands.py** → `+home/{set,info}`
- **faction_commands.py** → `+faction/*` (already mostly there)
- **entertainer_commands.py** → `+perform`
- **sabacc_commands.py** → `+sabacc/*`

### Stays bare (RP, navigation, social — no umbrella)

`say`, `whisper`, `emote`/`pose`, `ooc`, `think`, `page`, `mutter`, `tt`, `ttooc`, `look`, `move`, `who`, `quit`

## Help authoring conventions

### Per-command markdown — file location and naming

`data/help/commands/+combat.md` for the umbrella entry. Slash-encoded for sub-switches if we want per-switch detail pages: `data/help/commands/+combat__attack.md` for `+combat/attack`.

For S54 (combat proof-of-pattern): **one umbrella file `+combat.md`** covering all 18 switches in a single document with subsection per switch. If players ask for per-switch detail later, we split.

### Frontmatter (matches existing topic file convention)

```yaml
---
key: +combat
title: Combat Command — Attack, Defend, Maneuver
category: Commands · Combat
summary: All ground combat verbs are switches under +combat. attack, dodge, parry, aim, cover, etc.
aliases: [combat, cs, +cs, attack, att, kill, shoot, hit, dodge, fulldodge, parry, fullparry, aim, flee, run, retreat, pass, disengage, range, distance, cover, hide, forcepoint, fp, +fp, cpose, crolls, challenge, duel, accept, decline, refuse]
see_also: [combat, dodge, melee, ranged, wounds, cover, multiaction, dice, scale, forcepoints]
tags: [combat, core, command]
access_level: 0
examples:
  - cmd: +combat/attack greedo
    description: Make a ranged or melee attack on Greedo. Skill is auto-detected from your equipped weapon.
  - cmd: +combat/attack greedo cp 2
    description: Spend 2 Character Points on the attack roll.
  - cmd: +combat/dodge
    description: Reactive dodge for the round (use against ranged attacks).
  - cmd: +combat/fullparry
    description: Spend the entire round parrying — adds difficulty to ALL incoming melee.
  - cmd: +combat/aim 2
    description: Spend 2 rounds aiming for +2D on the next attack (cap +3D).
  - cmd: +combat/cover half
    description: Take half cover (+1D defense, +5 to ranged difficulty against you).
  - cmd: +combat/range greedo medium
    description: Move yourself to medium range from Greedo.
  - cmd: +combat/forcepoint
    description: Spend a Force Point — doubles your skill dice this round.
---
```

### Body sections (per existing topic file density)

- **Quick reference table** — switch, what it does, skill used, action cost
- **Per-switch detail** — one H2 per switch, body explains mechanics with sourcebook citation
- **Multi-action penalty** — cross-reference to `+help multiaction` and the rule
- **Difficulty scaling** — table for what attack difficulty is at what range
- **Combat round flow** — declaration phase → resolution phase → posing window
- **See also** — links to the conceptual topic files (combat, wounds, cover, etc.)

### Sourcebook citation convention

Format: `(R&E p.97)` or `(R&E p.97; GG6 p.78)` after the rule. Only cite where the mechanic is directly lifted, not for every paragraph. WEG D6 R&E is `R&E`, Galaxy Guide N is `GGn`, Imperial Sourcebook is `ISB`, Tramp Freighters specifically is `TF`, GM Screen is `GMS`.

For combat specifically:
- Difficulty tables — R&E p.95-99
- Multi-action penalty — R&E p.83
- Cover modifiers — R&E p.99
- Force Point spending — R&E p.135
- Wounds & damage — R&E p.107-109
- Scale — R&E p.96

## Test coverage

`tests/test_session54_combat_umbrella.py` — covers:

1. `+combat/attack greedo` reaches the same handler as `attack greedo` (aliases work)
2. `+combat/dodge` works
3. `+combat/banana` returns "Unknown switch: /banana. Valid: /attack, /dodge, ..."
4. `+combat` (no switch) shows status (existing CombatStatusCommand behavior preserved)
5. Each old test in `test_combat.py` still passes (regression)
6. `+help +combat` shows the umbrella help with all switches listed
7. `+help attack` resolves to the same entry as `+help +combat` (alias help redirect)

## Defer until later (not in this drop)

- The other 26 modules. Combat is proof-of-pattern; if the umbrella + per-command markdown approach feels right, I repeat for one or two modules per drop until done.
- Per-switch detail pages (`+combat__attack.md` etc.). Single umbrella file is fine until players ask for finer-grain.
- The "default behavior when no switch supplied" decision per umbrella. For combat it's clearly "show status." For mission it's clearly "show board." Each umbrella picks its own default.
- Removing the bare-form aliases later. Not in scope. The whole point of preserving them is that they NEVER need to be removed — both forms work forever.

## Implementation plan for this drop

1. Refactor `parser/combat_commands.py`:
   - Lift each per-verb class's `execute()` body into a private method on a new `CombatCommand` umbrella class
   - Set `key="+combat"`, full alias list, full `valid_switches` list
   - `execute()` dispatches: if `ctx.switches`, look at first switch; else look at `ctx.command` to map alias → switch; else default to status
   - Old classes (AttackCommand, DodgeCommand, etc.) get deleted
   - Module-level helpers stay
   - `register_combat_commands(registry)` registers just the umbrella

2. Write `data/help/commands/+combat.md` per the spec above

3. Write `tests/test_session54_combat_umbrella.py`

4. Run regression: `tests/test_combat.py`, `tests/test_combat_mechanics.py`, `tests/test_session38.py`, `tests/test_multiplayer.py` (PvP challenge), full economy/faction/portal buckets

5. Package zip + handoff

## Notes for the record

- The umbrella migration is **one-way** — once combat is consolidated, going back to per-verb classes would be a real refactor. That's fine, the umbrella is the right destination, but worth flagging.
- The 1500-line combat_commands.py becomes a roughly 1700-line file (small growth — `_<verb>` private methods are slightly larger than the equivalent `execute()` because of `self`/dispatch overhead, but the alias and registry consolidation saves some).
- This is the kind of change where doing the help content in the same drop as the rename matters: rename without help is half a feature. Help without rename is mid-stream documentation. Both together is the whole point.
