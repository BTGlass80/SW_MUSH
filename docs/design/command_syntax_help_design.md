# Command Syntax & Help System Overhaul — Design Document
## SW_MUSH · April 9, 2026

Two passes that share a common goal: make the game feel like a real MUSH to
veteran players while being learnable by newcomers. Pass 1 changes how
commands are parsed, named, and aliased. Pass 2 replaces the help system
with a structured, searchable, WEG-sourcebook-informed reference.

---

## Context: Current State

185+ commands across 23 parser modules. The `BaseCommand` class already
supports `key`, `aliases`, `help_text`, `usage`. The `CommandRegistry` does
prefix matching and alias lookup. The `@` prefix is established for
admin/builder commands.

### Known bugs

1. **Single-char prefix aliases are broken.** `'hello` becomes command
   `'hello` (no match) instead of command `'` + args `hello`. Same for
   `:waves`. The parser splits on whitespace before checking aliases,
   so no single-character prefix alias actually works unless you type a
   space after it (`' hello`).

2. **No switch syntax.** Commands that need sub-modes use separate command
   classes (`combat` vs `combat rolls`) or parse raw args themselves.

3. **No `+` prefix convention.** System commands sit alongside IC verbs
   with no visual distinction. MUSH veterans expect `+sheet`, `+who`, etc.

4. **Thin aliases.** Many commands have zero aliases. Standard MUSH
   shortcuts are missing.

5. **No semipose.** The `;` prefix (name-glued emote) doesn't exist.

---

# PASS 1: Command Syntax & Parser Overhaul

## 1. Prefix Convention

Three prefix tiers, matching standard MUSH tradition:

| Prefix | Meaning | Examples |
|--------|---------|----------|
| *(bare)* | IC actions — things your character does | `say`, `emote`, `look`, `attack`, `dodge`, `flee` |
| `+` | OOC/system — things the player does | `+sheet`, `+roll`, `+who`, `+help`, `+inv`, `+credits` |
| `@` | Admin/builder — world manipulation | `@dig`, `@npc`, `@spawn`, `@grant`, `@director` |

Single-character shortcuts:

| Char | Expands to | Example |
|------|-----------|---------|
| `'` | `say` | `'Hello there.` → You say, "Hello there." |
| `"` | `say` | `"Hello there.` → same as above |
| `:` | `emote` | `:draws his blaster.` → Tundra draws his blaster. |
| `;` | `semipose` | `;'s blaster hums.` → Tundra's blaster hums. |

**Backward compatibility rule:** The bare-word version ALWAYS remains as an
alias. `sheet` and `+sheet` both work. `who` and `+who` both work. Players
never break muscle memory. The `+` form is the canonical name taught in
help, but the old name keeps working forever.

## 2. Parser Changes (commands.py)

### 2.1 Prefix Extraction

Insert a prefix extraction step in `parse_and_dispatch()` BEFORE the
whitespace split. The prefix characters `'`, `"`, `:`, `;` are special
because they can be glued to their arguments with no space.

```python
# ── Prefix extraction ─────────────────────────────────────────
# Single-char prefixes that can be glued to args: '  "  :  ;
GLUED_PREFIXES = {"'", '"', ":", ";"}

first_char = raw_input[0]
if first_char in GLUED_PREFIXES:
    cmd_name = first_char
    args_str = raw_input[1:].strip()
else:
    parts = raw_input.split(None, 1)
    cmd_name = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""
```

The `+` and `@` prefixes do NOT need special extraction — they're part of
the command name and already work with normal whitespace splitting. `+sheet`
splits naturally into command `+sheet` + args `""`.

### 2.2 Switch Parsing

After extracting the command name, parse `/switch` suffixes:

```python
# ── Switch extraction ─────────────────────────────────────────
switches = []
if "/" in cmd_name:
    parts = cmd_name.split("/")
    cmd_name = parts[0]
    switches = [s.lower() for s in parts[1:] if s]
```

So `+help/search combat` → `cmd_name = "+help"`, `switches = ["search"]`,
`args = "combat"`. And `+sheet/brief` → `cmd_name = "+sheet"`,
`switches = ["brief"]`.

### 2.3 CommandContext Changes

Add `switches` to the dataclass:

```python
@dataclass
class CommandContext:
    session: Session
    raw_input: str
    command: str
    args: str
    args_list: list[str]
    switches: list[str] = field(default_factory=list)  # NEW
    db: object = None
    session_mgr: object = None
```

### 2.4 BaseCommand Changes

Add optional switch declaration:

```python
class BaseCommand:
    key: str = ""
    aliases: list[str] = []
    access_level: int = AccessLevel.PLAYER
    help_text: str = ""
    usage: str = ""
    valid_switches: list[str] = []  # NEW — if non-empty, reject unknown switches
```

In `_execute()`, before calling `cmd.execute(ctx)`:

```python
if cmd.valid_switches and ctx.switches:
    bad = [s for s in ctx.switches if s not in cmd.valid_switches]
    if bad:
        await ctx.session.send_line(
            f"  Unknown switch: /{bad[0]}. "
            f"Valid: {', '.join('/' + s for s in cmd.valid_switches)}"
        )
        return
```

### 2.5 Semipose Command

New command class in `builtin_commands.py`:

```python
class SemiposeCommand(BaseCommand):
    key = ";"
    aliases = ["semipose"]
    help_text = "Emote with name glued to text (no space)."
    usage = ";'s lightsaber hums. → Tundra's lightsaber hums."

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Semipose what?")
            return
        char = ctx.session.character
        name = ansi.player_name(char["name"])
        text = f"{name}{ctx.args}"  # No space between name and args
        room_id = char["room_id"]
        for s in ctx.session_mgr.sessions_in_room(room_id):
            await s.send_line(text)
```

### 2.6 Updated parse_and_dispatch()

Full replacement method (shows the complete flow):

```python
async def parse_and_dispatch(self, session: Session, raw_input: str):
    raw_input = raw_input.strip()
    if not raw_input:
        await session.send_prompt()
        return

    if not self._check_rate_limit(session):
        await session.send_line("  Slow down! Too many commands.")
        return

    # ── Prefix extraction ──
    GLUED_PREFIXES = {"'", '"', ":", ";"}
    first_char = raw_input[0]

    if first_char in GLUED_PREFIXES:
        cmd_name = first_char
        args_str = raw_input[1:].strip()
    else:
        # Expand direction aliases before splitting
        first_word = raw_input.split()[0].lower()
        if first_word in DIRECTION_ALIASES:
            raw_input = (DIRECTION_ALIASES[first_word]
                         + raw_input[len(first_word):])

        parts = raw_input.split(None, 1)
        cmd_name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

    # ── Switch extraction ──
    switches = []
    if "/" in cmd_name and cmd_name not in GLUED_PREFIXES:
        switch_parts = cmd_name.split("/")
        cmd_name = switch_parts[0]
        switches = [s.lower() for s in switch_parts[1:] if s]

    # ── Build context ──
    ctx = CommandContext(
        session=session,
        raw_input=raw_input,
        command=cmd_name,
        args=args_str,
        args_list=args_str.split() if args_str else [],
        switches=switches,
        db=self.db,
        session_mgr=self.session_mgr,
    )

    # ── Look up command ──
    cmd = self.registry.get(cmd_name)

    if cmd is None:
        # Direction movement fallback
        if cmd_name in (
            "north", "south", "east", "west", "up", "down",
            "northeast", "northwest", "southeast", "southwest",
            "enter", "leave",
        ):
            move_cmd = self.registry.get("move")
            if move_cmd:
                ctx.args = cmd_name
                ctx.args_list = [cmd_name]
                await self._execute(move_cmd, ctx)
                return

        # NL combat intercept
        if session.character:
            from parser.combat_commands import try_nl_combat_action
            handled = await try_nl_combat_action(ctx, raw_input)
            if handled:
                return

        await session.send_line(f"Huh? Unknown command: '{cmd_name}'")
        await session.send_prompt()
        return

    await self._execute(cmd, ctx)
```

### 2.7 `"` alias for say

Add `'"'` to SayCommand aliases:

```python
class SayCommand(BaseCommand):
    key = "say"
    aliases = ["'", '"']
```

Both `'hello` and `"hello` now work identically.

---

## 3. Complete Command Rename & Alias Table

Canonical name is the `key`. All other names are aliases. The **first alias
listed** is the bare-word backward-compat form where the canonical key
changes to a `+` prefix.

### 3.1 Core / Builtin (`builtin_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `look` | `l` | — |
| `move` | — | — |
| `say` | `'`, `"` | — |
| `whisper` | `wh`, `page`, `tell` | — |
| `emote` | `:`, `pose`, `em` | — |
| `;` | `semipose` | — |
| `+who` | `who`, `online`, `+online` | — |
| `+inv` | `inventory`, `inv`, `i`, `+inventory` | — |
| `+sheet` | `sheet`, `score`, `stats`, `+score`, `+stats`, `sc` | `brief`, `skills`, `combat` |
| `+help` | `help`, `?`, `commands`, `+commands` | `search` |
| `respawn` | `revive` | — |
| `quit` | `@quit`, `logout`, `QUIT` | — |
| `+ooc` | `ooc`, `@ooc` | — |
| `@desc` | `@describe` | — |
| `equip` | `wield`, `draw` | — |
| `unequip` | `holster`, `sheathe` | — |
| `+repair` | `repair` | — |
| `sell` | — | — |
| `+weapons` | `weapons`, `weaponlist`, `armory`, `+armory` | — |

### 3.2 D6 Dice (`d6_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `+roll` | `roll` | — |
| `+check` | `check` | — |
| `+opposed` | `opposed`, `vs` | — |

### 3.3 Combat (`combat_commands.py`)

Combat commands stay bare-word — they're IC actions.

| Canonical Key | Aliases | Switches |
|---|---|---|
| `attack` | `att`, `kill`, `shoot`, `hit` | — |
| `dodge` | — | — |
| `fulldodge` | `fdodge` | — |
| `parry` | — | — |
| `fullparry` | `fparry` | — |
| `aim` | — | — |
| `flee` | `run`, `retreat` | — |
| `pass` | — | — |
| `+combat` | `combat`, `cs`, `+cs` | `rolls`, `status` |
| `resolve` | — | — |
| `disengage` | — | — |
| `range` | `distance` | — |
| `cover` | `hide` | — |
| `forcepoint` | `fp` | — |
| `cpose` | `combatpose` | — |

Note: `+combat/rolls` replaces the current `combat rolls` two-word command
by using the switch system. The old `crolls` alias also routes here.

### 3.4 Space (`space_commands.py`)

Space commands are a mix. Ship operations are IC (bare), info/status are
system (`+`).

| Canonical Key | Aliases | Switches |
|---|---|---|
| `+ships` | `ships`, `shiplist` | — |
| `+shipinfo` | `shipinfo`, `si` | — |
| `board` | — | — |
| `disembark` | `deboard`, `leave_ship` | — |
| `pilot` | — | — |
| `gunner` | `gunnery` | — |
| `copilot` | — | — |
| `engineer` | `eng` | — |
| `navigator` | `nav` | — |
| `commander` | `command`, `captain` | — |
| `sensors` | `sensor` | — |
| `vacate` | `unstation` | — |
| `assist` | — | — |
| `coordinate` | `coord` | — |
| `+shiprepair` | `shiprepair`, `srepair` | — |
| `+myships` | `myships`, `ownedships` | — |
| `launch` | `takeoff` | — |
| `land` | `dock` | — |
| `+shipstatus` | `shipstatus`, `ss`, `+ss` | — |
| `scan` | — | — |
| `fire` | — | — |
| `lockon` | `lock`, `targetlock` | — |
| `close` | `approach` | — |
| `fleeship` | `breakaway` | — |
| `tail` | `getbehind` | — |
| `outmaneuver` | `shake` | — |
| `evade` | `evasive` | — |
| `jink` | — | — |
| `barrelroll` | `broll` | — |
| `loop` | `immelmann` | — |
| `slip` | `sideslip` | — |
| `shields` | — | — |
| `hyperspace` | `jump`, `hyper` | — |
| `buy` | `purchase` | — |
| `damcon` | `damagecontrol` | — |
| `pay` | — | — |
| `hail` | — | — |
| `comms` | `comm`, `radio` | — |
| `+credits` | `credits`, `balance`, `wallet`, `+wallet` | — |
| `@spawn` | — | — |
| `@setbounty` | `@bounty` | — |

### 3.5 Force (`force_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `force` | `useforce` | — |
| `+powers` | `powers`, `forcepowers`, `listpowers` | — |
| `+forcestatus` | `forcestatus`, `fstatus`, `forcesheet`, `+fstatus` | — |

### 3.6 CP / Advancement (`cp_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `+cpstatus` | `cpstatus`, `cpinfo`, `advancement`, `+cp`, `+advancement` | — |
| `train` | — | — |
| `+kudos` | `kudos`, `givekudos`, `+givekudos` | — |
| `+scenebonus` | `scenebonus`, `endscene`, `closescene`, `+endscene` | — |

### 3.7 Missions (`mission_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `+missions` | `missions`, `mb`, `jobs`, `+jobs`, `+mb` | — |
| `accept` | `takejob` | — |
| `+mission` | `mission`, `myjob`, `activemission`, `+myjob` | — |
| `complete` | `finishjob`, `turnin` | — |
| `abandon` | `dropmission`, `quitjob` | — |

### 3.8 Smuggling (`smuggling_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `+smugjobs` | `smugjobs`, `smugboard`, `smugcontacts`, `underworld`, `+underworld` | — |
| `smugaccept` | `takesmug`, `takerun` | — |
| `+smugjob` | `smugjob`, `myrun`, `activerun`, `cargo`, `+cargo` | — |
| `smugdeliver` | `deliver`, `dropoff` | — |
| `smugdump` | `dumpcargo`, `jettison` | — |

### 3.9 Bounty Hunting (`bounty_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `+bounties` | `bounties`, `bboard`, `bountyboard`, `+bboard` | — |
| `bountyclaim` | `claimbounty`, `acceptbounty` | — |
| `+mybounty` | `mybounty`, `activebounty`, `myhunt`, `+myhunt` | — |
| `bountytrack` | `tracktarget`, `hunttrack` | — |
| `bountycollect` | `collectbounty`, `claimreward` | — |

### 3.10 Crew (`crew_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `hire` | `recruiting`, `hireboard` | — |
| `+roster` | `roster`, `crew`, `mycrew`, `+crew`, `+mycrew` | — |
| `assign` | — | — |
| `unassign` | — | — |
| `dismiss` | `firecrew` | — |
| `order` | `ord` | — |

### 3.11 Channels (`channel_commands.py`)

| Canonical Key | Aliases | Switches |
|---|---|---|
| `ooc` | `newbie`, `oocsay` | — |
| `comlink` | `cl`, `clink` | — |
| `fcomm` | `fc` | — |
| `+faction` | `faction`, `affiliation` | — |
| `tune` | `tunein` | — |
| `untune` | `tuneout` | — |
| `+freqs` | `freqs`, `frequencies`, `myfreqs` | — |
| `commfreq` | `cf`, `freq` | — |
| `+channels` | `channels`, `chan`, `channellist` | — |

### 3.12 Other Systems

| Module | Canonical Key | Aliases | Switches |
|---|---|---|---|
| `sabacc` | `sabacc` | `gamble`, `cards` | `join`, `bet`, `fold`, `call`, `raise`, `leave` |
| `entertainer` | `perform` | `entertain`, `play` | — |
| `medical` | `heal` | — | — |
| `medical` | `healaccept` | `haccept` | — |
| `medical` | `+healrate` | `healrate`, `hrate` | — |
| `npc` | `talk` | — | — |
| `npc` | `ask` | — | — |
| `npc` | `@npc` | — | `gen`, `list`, `set`, `delete`, `equip`, `place`, `move`, `rename` |
| `npc` | `@ai` | — | — |
| `director` | `@director` | — | `status`, `enable`, `disable`, `trigger`, `budget`, `influence`, `log`, `reset` |
| `news` | `+news` | `news`, `worldnews`, `galacticnews` | — |
| `party` | `+party` | `party`, `p` | `invite`, `join`, `leave`, `list`, `kick`, `disband` |
| `crafting` | `survey` | — | — |
| `crafting` | `+resources` | `resources`, `res` | — |
| `crafting` | `buyresource` | — | — |
| `crafting` | `+schematics` | `schematics`, `schem` | — |
| `crafting` | `craft` | — | — |

### 3.13 Building (`building_commands.py`, `building_tier2.py`)

All building commands keep their existing `@` prefix. No changes needed
except adding a few convenience aliases:

| Canonical Key | Added Aliases |
|---|---|
| `@dig` | — |
| `@tunnel` | `@tun` |
| `@open` | — |
| `@rdesc` | `@roomdesc` |
| `@rname` | `@roomname` |
| `@destroy` | `@nuke` |
| `@teleport` | `@tel` |
| `@link` | — |
| `@unlink` | — |
| `@examine` | `@exam`, `@ex` |
| `@rooms` | — |
| `@set` | — |
| `@lock` | — |
| `@entrances` | — |
| `@find` | — |
| `@zone` | — |
| `@create` | — |
| `@success` | `@succ` |
| `@fail` | — |
| `@emit` | — |
| `@grant` | — |

---

## 4. Switch Migration for Existing Multi-Word Commands

Some current commands are split into separate classes but would be cleaner
as switches on a parent command. The switch system makes this possible
without breaking the old forms.

### 4.1 `+combat/rolls`

Currently `combat rolls` (key `"combat rolls"`) and alias `crolls`. Under
the switch system, `+combat/rolls` is the canonical form, but `crolls`
stays as a direct alias.

Implementation: In `CombatStatusCommand.execute()`, check
`ctx.switches`:

```python
async def execute(self, ctx: CommandContext):
    if "rolls" in ctx.switches:
        return await self._show_rolls(ctx)
    if "status" in ctx.switches:
        return await self._show_status(ctx)
    # Default: show status
    return await self._show_status(ctx)
```

The old `CombatRollsCommand` class becomes a thin redirect:

```python
class CombatRollsCommand(BaseCommand):
    key = "crolls"
    aliases = []

    async def execute(self, ctx):
        ctx.switches = ["rolls"]
        cmd = CombatStatusCommand()
        await cmd.execute(ctx)
```

### 4.2 `@npc` with sub-commands

`@npc` already parses its first argument as a sub-command (`gen`, `list`,
`set`, etc.). These can optionally migrate to switch syntax: `@npc/gen`
alongside `@npc gen`. No urgency — the existing arg-based dispatch works
fine.

### 4.3 `@director` with sub-commands

Same pattern as `@npc`. `@director/status` works alongside
`@director status`. No code change needed if we leave the existing
arg-parse in place and just add switch support.

---

## 5. Implementation Plan — Pass 1

### Drop 1: Parser Infrastructure

**Files modified:**
- `parser/commands.py` — prefix extraction, switch parsing,
  `CommandContext.switches`, `BaseCommand.valid_switches`, switch
  validation in `_execute()`

**Files created:**
- None

**Estimated size:** ~60 lines changed in `commands.py`

### Drop 2: Command Rename & Alias Sweep

**Files modified:** All 23 parser modules — update `key` and `aliases`
on every command class.

**Files created:**
- `parser/builtin_commands.py` gains `SemiposeCommand`

This is a large but mechanical patch. Every command class gets its `key`
and `aliases` updated per the table in Section 3. No logic changes.

### Drop 3: Switch Wiring

**Files modified:**
- `parser/combat_commands.py` — `+combat/rolls` switch
- `parser/builtin_commands.py` — `+sheet/brief`, `+sheet/skills`, `+sheet/combat`

Lower priority. The switch infrastructure is there from Drop 1; individual
commands can adopt switches at any pace.

---

# PASS 2: Help System Overhaul

## 6. Architecture

### 6.1 HelpEntry

```python
@dataclass
class HelpEntry:
    key: str               # Lookup key (e.g., "combat", "+sheet", "wounds")
    title: str             # Display title
    category: str          # Category for grouping
    aliases: list[str]     # Alternate lookup keys
    body: str              # Full help text (ANSI-formatted)
    see_also: list[str]    # Related help keys
    access_level: int = 0  # 0=anyone, 3=admin (filter display)
```

### 6.2 HelpManager

```python
class HelpManager:
    def __init__(self):
        self._entries: dict[str, HelpEntry] = {}
        self._alias_map: dict[str, str] = {}

    def register(self, entry: HelpEntry): ...
    def get(self, key: str) -> Optional[HelpEntry]: ...
    def search(self, keyword: str) -> list[HelpEntry]: ...
    def categories(self) -> dict[str, list[HelpEntry]]: ...
    def auto_register_commands(self, registry: CommandRegistry): ...
```

`auto_register_commands()` iterates the command registry and creates a
`HelpEntry` for every command that has `help_text` and `usage` set. This
ensures command help is always in sync with the code.

### 6.3 Help Sources

Two tiers:

1. **Command help** — auto-generated from `BaseCommand` fields. The
   `HelpManager` reads `key`, `aliases`, `help_text`, `usage`,
   `valid_switches`, and `access_level` to build entries like:

   ```
   +sheet                                        [Character]
   View your character sheet.
   Usage: +sheet
   Switches: /brief — condensed view
             /skills — skill list only
             /combat — combat-relevant stats only
   Aliases: sheet, score, stats, sc
   See also: +inv, +cpstatus, train
   ```

2. **Topic help** — manually authored entries in `data/help_topics.py`.
   These cover game rules, WEG D6 mechanics, the game world, and
   conceptual guides. Not tied to any single command.

### 6.4 The New +help Command

```
+help                    — Category overview
+help <command>          — Command-specific help
+help <topic>            — Topic help (combat, dice, wounds, etc.)
+help/search <keyword>   — Search all entries by keyword
```

### 6.5 Display Format

All help output uses ANSI formatting for telnet readability and wraps to
78 columns.

```
==============================================================================
  +SHEET                                                         [Character]
==============================================================================

  View your character sheet showing attributes, skills, wounds, and
  equipment.

  USAGE:  +sheet [/switch]

  SWITCHES:
    /brief    — Condensed one-line-per-attribute view
    /skills   — Skill list only, grouped by attribute
    /combat   — Combat-relevant stats: wounds, armor, weapon, soak

  ALIASES: sheet, score, stats, sc

  SEE ALSO: +inv, +cpstatus, train
==============================================================================
```

Topic help uses a similar frame but with free-form body text:

```
==============================================================================
  COMBAT                                                       [Rules: D6]
==============================================================================

  Combat in Star Wars D6 follows a structured round sequence:

  1. INITIATIVE — All combatants roll Perception. Highest goes first.

  2. DECLARATION — In reverse initiative order (lowest first), each
     combatant declares their actions. You can declare multiple actions,
     but each additional action beyond the first costs -1D from ALL
     your rolls that round.

  3. RESOLUTION — In initiative order (highest first), actions resolve.
     Attacks roll weapon skill vs. difficulty (ranged) or opposed roll
     (melee). Damage vs. Strength determines wound level.

  The round then repeats from step 1.

  DIFFICULTY BY RANGE (Ranged Combat):
    Point Blank ............... 5
    Short Range .............. 10
    Medium Range ............. 15
    Long Range ............... 20

  WOUND LEVELS (Damage Roll beats Strength Roll by):
    0-3 ..................... Stunned
    4-8 ..................... Wounded
    9-12 .................... Incapacitated
    13-15 ................... Mortally Wounded
    16+ ..................... Killed

  SEE ALSO: +help wounds, +help dice, +help cover, +help dodge,
            +help multiaction
==============================================================================
```

---

## 7. Topic Help Entries

### 7.1 Rules Topics (sourced from WEG40120 R&E)

These cover the core D6 mechanics as implemented in the game:

| Topic Key | Title | Content Summary |
|---|---|---|
| `dice` | The D6 System | Dice pools, the Wild Die (exploding 6, mishap on 1), pips, reading die codes |
| `attributes` | Attributes | The 6 attributes (Dexterity, Knowledge, Mechanical, Perception, Strength, Technical), what they govern |
| `skills` | Skills | How skills relate to attributes, defaulting to attribute, specializations |
| `difficulty` | Difficulty Numbers | The difficulty scale (Very Easy 5 through Heroic 30+), opposed rolls |
| `combat` | Combat Basics | Round structure: initiative → declaration → resolution. Multi-action penalty |
| `ranged` | Ranged Combat | Range bands and difficulties, fire control, cover modifiers |
| `melee` | Melee Combat | Opposed rolls (attack vs. parry), brawling, melee weapons |
| `wounds` | Wounds & Healing | The 5 wound levels, cumulative effects, natural healing, medical treatment |
| `dodge` | Dodging | Reaction dodge vs. full dodge, when to declare, how it works |
| `cover` | Cover | Quarter/half/three-quarter/full cover, bonus dice, room cover_max |
| `multiaction` | Multiple Actions | -1D per additional action, how to declare, combining with dodge |
| `armor` | Armor | How armor adds to Strength for damage resistance, armor damage |
| `scale` | Scale | Character/speeder/walker/starfighter/capital/Death Star scale modifiers |
| `cp` | Character Points | Spending CP in play (+1D per CP), advancing skills between adventures |
| `forcepoints` | Force Points | Double all dice for one round, earning/losing FP, Dark Side temptation |
| `darkside` | The Dark Side | Dark Side Points, temptation, atonement, the path to corruption |
| `force` | The Force | Overview of Force skills (Control/Sense/Alter), available powers |
| `lightsaber` | Lightsaber Combat | Lightsaber skill, damage (5D), deflecting blaster bolts |

### 7.2 Space Topics (sourced from WEG40120 + WEG40093 Sourcebook)

| Topic Key | Title | Content Summary |
|---|---|---|
| `space` | Space Travel | Overview of space zones, hyperspace, sublight travel |
| `spacecombat` | Space Combat | How ship combat works: crew stations, fire arcs, range zones |
| `crew` | Crew Stations | The 7 stations (pilot, copilot, gunner, engineer, navigator, commander, sensors) and what each does |
| `hyperdrive` | Hyperspace | Hyperdrive multipliers, astrogation, misjump consequences |
| `sensors` | Sensors | Sensor modes, scan command, sensor countermeasures |
| `shields` | Shields | How shield dice work, redistributing between arcs |
| `capital` | Capital Ships | Capital-scale rules, how they differ from starfighter-scale |

### 7.3 World Topics (sourced from WEG40069 Galaxy Guide 7: Mos Eisley)

| Topic Key | Title | Content Summary |
|---|---|---|
| `moseisley` | Mos Eisley | Overview of the spaceport city: layout, districts, atmosphere |
| `cantina` | The Cantina | Chalmun's Cantina, the famous watering hole, no droids |
| `tatooine` | Tatooine | The desert planet: twin suns, Jawas, Tusken Raiders, moisture farming |
| `empire` | The Empire | Imperial presence on Tatooine, garrison, patrols |

### 7.4 Economy Topics (sourced from WEG40027 Galaxy Guide 6 + game systems)

| Topic Key | Title | Content Summary |
|---|---|---|
| `trading` | Trading | How speculative trading works, bargain skill, profit/loss |
| `smuggling` | Smuggling | Smuggling jobs, contraband, Imperial patrols, risk/reward |
| `missions` | Mission System | How the mission board works, mission types, completion |
| `bounty` | Bounty Hunting | Bounty board, tracking, collecting, target threat levels |
| `crafting` | Crafting | Survey → gather → craft pipeline, schematics, experiments |
| `economy` | The Economy | Credits, buying/selling, wages, how money flows in the game |

### 7.5 Character Topics

| Topic Key | Title | Content Summary |
|---|---|---|
| `species` | Playable Species | All 9 species with attribute bonuses and special abilities |
| `advancement` | Advancement | CP progression system, tick sources, training between sessions |
| `equipment` | Equipment | Weapon condition, repair, selling, the armory |

### 7.6 MUSH Topics (meta/how-to-play)

| Topic Key | Title | Content Summary |
|---|---|---|
| `rp` | Roleplaying | Posing, emoting, IC vs. OOC, scene etiquette |
| `newbie` | New Player Guide | Getting started, creating a character, first steps in Mos Eisley |
| `commands` | Command Reference | Quick reference of all command prefixes and categories |
| `building` | Building Guide | For builders: how rooms, exits, zones, locks work |
| `channels` | Communication | OOC, comlink, faction channels, frequencies |

---

## 8. Implementation Plan — Pass 2

### Drop A: Help Infrastructure

**Files created:**
- `data/help_topics.py` — `HelpEntry` dataclass, `HelpManager` class,
  `load_command_help()` and `load_topic_help()` functions

**Files modified:**
- `parser/builtin_commands.py` — rewritten `HelpCommand` class using
  `HelpManager`, supporting `+help`, `+help <topic>`, `+help/search`

**Files modified:**
- `server/game_server.py` — wire `HelpManager` initialization at boot,
  call `auto_register_commands()` after all command modules load

### Drop B: Rules Topic Content

**Files modified:**
- `data/help_topics.py` — add all rules topic entries from Section 7.1
  and 7.2 (dice, combat, wounds, Force, space, etc.)

This is the big content authoring pass. Each topic gets 15–40 lines of
carefully written help text that teaches the mechanic as implemented in the
game (not just quoting the rulebook). Text is wrapped to 78 columns and
uses ANSI-safe formatting.

### Drop C: World & Economy Topic Content

**Files modified:**
- `data/help_topics.py` — add world topics (7.3), economy topics (7.4),
  character topics (7.5), MUSH topics (7.6)

### Drop D: Enhanced Command Help

**Files modified:**
- Every parser module — flesh out `help_text` and `usage` strings on
  all 185+ command classes to provide enough detail for the auto-generated
  command help entries to be genuinely useful.

This is another mechanical sweep, similar to Pass 1 Drop 2.

---

## 9. Sourcebook Assessment

### Books to pull from (priority order):

1. **WEG40120 — R&E Core Rulebook** (real PDF, 273 pages)
   The primary source for all rules topics. Clean text extraction via
   `pdftotext`. Chapters 4 (The Rules), 5 (Combat), 6 (Movement), 7
   (Space Travel), 9 (The Force), 17 (Weapons & Equipment), 20
   (Starships) are the most relevant.

2. **WEG40069 — Galaxy Guide 7: Mos Eisley** (zip-of-JPEGs)
   Directly relevant world lore. Location descriptions, NPC backgrounds,
   city layout. Feeds the world topic help entries.

3. **WEG40027 — Galaxy Guide 6: Tramp Freighters** (zip-of-JPEGs)
   Speculative trading mechanics, cargo operations. Feeds economy and
   trading help topics.

4. **WEG40093 — Star Wars Sourcebook 2nd Ed.** (zip-of-JPEGs)
   Spacecraft systems, sensors, military hardware. Supplements the
   space combat help topics.

### Books to skip (for now):

- **WEG40092 — Imperial Sourcebook** — GM-facing military org charts and
  intelligence procedures. Interesting flavor but not player-facing help.
- **WEG40048 — Gamemaster Kit** — GM screen, spy networks, campaign
  scenarios. Not relevant to player help.
- **WEG40124 — Galaxy Guide 1: A New Hope** — ANH-era character stats
  and location descriptions. Useful for NPC YAML extraction (a separate
  project) but not for the help system.

---

## 10. Delivery Sequence

| Order | Drop | Pass | Scope | Effort |
|-------|------|------|-------|--------|
| 1 | Pass 1, Drop 1 | Parser infrastructure | `commands.py` changes | Small |
| 2 | Pass 1, Drop 2 | Command rename/alias sweep | All 23 parser modules | Medium (mechanical) |
| 3 | Pass 2, Drop A | Help infrastructure | `HelpManager`, new `HelpCommand` | Medium |
| 4 | Pass 2, Drop B | Rules topic content | D6 mechanics help entries | Medium (content) |
| 5 | Pass 2, Drop C | World & economy content | Mos Eisley, trading, etc. | Medium (content) |
| 6 | Pass 1, Drop 3 | Switch wiring | `+combat/rolls`, `+sheet/brief` | Small |
| 7 | Pass 2, Drop D | Enhanced command help | `help_text`/`usage` on all commands | Medium (mechanical) |

Drops 1 and 2 are the critical path — they fix the parser bugs and
establish the `+` convention. Everything else layers on top.

---

*End of design document.*
*Opus session, April 9, 2026.*
