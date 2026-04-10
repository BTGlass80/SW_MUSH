# -*- coding: utf-8 -*-
"""
data/help_topics.py — Help system for SW_MUSH

Provides:
  - HelpEntry: a single help entry (command or topic)
  - HelpManager: registry, lookup, search, auto-registration from commands
  - TOPIC_HELP: all manually-authored help topics (rules, world, economy, etc.)

The HelpManager is initialized at server boot and injected into HelpCommand.
"""
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class HelpEntry:
    key: str                            # Lookup key ("+sheet", "combat", "wounds")
    title: str                          # Display title
    category: str                       # For grouping ("Character", "Rules: D6", etc.)
    body: str                           # Full help text (plain — ANSI applied at render)
    aliases: list[str] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)
    access_level: int = 0               # 0=anyone, 3=admin


class HelpManager:
    """Registry for all help entries — commands and topics."""

    def __init__(self):
        self._entries: dict[str, HelpEntry] = {}   # key → HelpEntry
        self._alias_map: dict[str, str] = {}        # alias → key

    def register(self, entry: HelpEntry):
        k = entry.key.lower()
        self._entries[k] = entry
        for alias in entry.aliases:
            self._alias_map[alias.lower()] = k

    def get(self, name: str) -> Optional[HelpEntry]:
        name = name.lower().strip()
        if name in self._entries:
            return self._entries[name]
        if name in self._alias_map:
            return self._entries.get(self._alias_map[name])
        # Try with/without + prefix
        if not name.startswith("+"):
            alt = "+" + name
            if alt in self._entries:
                return self._entries[alt]
            if alt in self._alias_map:
                return self._entries.get(self._alias_map[alt])
        return None

    def search(self, keyword: str) -> list[HelpEntry]:
        """Search all entries by keyword in key, title, aliases, and body."""
        keyword = keyword.lower()
        results = []
        seen = set()
        for entry in self._entries.values():
            if entry.key in seen:
                continue
            if (keyword in entry.key.lower()
                    or keyword in entry.title.lower()
                    or keyword in entry.body.lower()
                    or any(keyword in a.lower() for a in entry.aliases)):
                results.append(entry)
                seen.add(entry.key)
        return results

    def categories(self) -> dict[str, list[HelpEntry]]:
        cats: dict[str, list[HelpEntry]] = {}
        for entry in self._entries.values():
            cats.setdefault(entry.category, []).append(entry)
        return cats

    def auto_register_commands(self, registry):
        """
        Create help entries from all registered BaseCommand instances.
        Called after all command modules are loaded.
        """
        for cmd in registry.all_commands:
            if not cmd.key:
                continue
            # Build body from help_text + usage + switches + aliases
            parts = []
            if cmd.help_text:
                parts.append(cmd.help_text)
            if cmd.usage:
                parts.append(f"\nUSAGE: {cmd.usage}")
            if getattr(cmd, "valid_switches", None):
                sw_lines = ", ".join("/" + s for s in cmd.valid_switches)
                parts.append(f"\nSWITCHES: {sw_lines}")
            if cmd.aliases:
                parts.append(f"\nALIASES: {', '.join(cmd.aliases)}")

            body = "\n".join(parts) if parts else "No detailed help available."

            # Determine category from access level
            if cmd.key.startswith("@"):
                cat = "Admin/Building"
            elif cmd.key.startswith("+"):
                cat = "System"
            else:
                cat = "Commands"

            entry = HelpEntry(
                key=cmd.key.lower(),
                title=cmd.key,
                category=cat,
                body=body,
                aliases=[a.lower() for a in cmd.aliases],
                access_level=cmd.access_level,
            )
            self.register(entry)

    def register_topics(self):
        """Register all manually-authored topic help entries."""
        for entry in TOPIC_HELP:
            self.register(entry)


# ═══════════════════════════════════════════════════════════════════════
# Topic help entries — manually authored
# Rules content informed by WEG40120 (R&E), WEG40069 (Mos Eisley),
# WEG40027 (Tramp Freighters), WEG40093 (Sourcebook 2nd Ed)
# ═══════════════════════════════════════════════════════════════════════

TOPIC_HELP = [

    # ── Rules: D6 System ──────────────────────────────────────────────

    HelpEntry(
        key="dice",
        title="The D6 System",
        category="Rules: D6",
        aliases=["d6", "wilddie", "wild die", "die"],
        see_also=["difficulty", "attributes", "skills"],
        body="""\
Star Wars uses the D6 system. Your abilities are measured in dice pools
like 3D+2 (roll 3 six-sided dice and add 2).

THE WILD DIE
One die in every roll is the Wild Die (shown in a different color).
  - If the Wild Die rolls a 6, it "explodes": keep the 6, roll again,
    and add the new result. This can chain — multiple 6s keep adding.
  - If the Wild Die rolls a 1 on the FIRST roll, it's a Complication:
    remove the Wild Die AND the highest other die from your total.
    The GM may also impose a narrative mishap.

READING DIE CODES
  3D     = roll 3 dice, add them up
  3D+1   = roll 3 dice, add them up, then add 1
  3D+2   = roll 3 dice, add them up, then add 2
  Every 3 pips (+1/+2/+0) equal 1 die: 3D+2 + 1 pip = 4D.""",
    ),

    HelpEntry(
        key="attributes",
        title="Attributes",
        category="Rules: D6",
        aliases=["attrs", "stats"],
        see_also=["skills", "+sheet"],
        body="""\
Every character has six attributes. Skills fall under their governing
attribute — your attribute dice are the base for all related skills.

DEXTERITY    Agility, coordination, reflexes
             Skills: blaster, dodge, melee combat, lightsaber, etc.

KNOWLEDGE    Education, streetwise, common sense
             Skills: alien species, bureaucracy, languages, etc.

MECHANICAL   Vehicle/ship operation, gunnery
             Skills: astrogation, starship piloting, repulsorlift, etc.

PERCEPTION   Awareness, charisma, empathy
             Skills: bargain, command, con, persuasion, search, etc.

STRENGTH     Physical power, stamina, toughness
             Skills: brawling, climbing/jumping, stamina, swimming, etc.

TECHNICAL    Repair, programming, demolitions
             Skills: blaster repair, computer prog., first aid, etc.

If you don't have a skill, you roll the governing attribute instead.""",
    ),

    HelpEntry(
        key="skills",
        title="Skills",
        category="Rules: D6",
        aliases=["skilllist"],
        see_also=["attributes", "advancement", "+sheet"],
        body="""\
Skills represent specialized training. Each skill falls under one of
the six attributes. If you have no ranks in a skill, you roll the
base attribute dice instead.

ADVANCING SKILLS
Use the 'train' command to spend Character Points (CP) on skills.
The cost to advance a skill by one pip equals the number of dice in
the skill's TOTAL pool (attribute + skill dice combined).

Example: Blaster at 5D costs 5 CP per pip. Three pips make one die,
so going from 5D to 6D costs 15 CP total (5 + 5 + 5).

SPECIALIZATIONS
Some skills can be specialized (e.g., blaster: blaster pistol). A
specialization costs less to advance but only applies in its narrow
area. The game handles this automatically during advancement.

Type '+sheet/skills' to see your full skill list.""",
    ),

    HelpEntry(
        key="difficulty",
        title="Difficulty Numbers",
        category="Rules: D6",
        aliases=["diff", "difficulties", "dc"],
        see_also=["dice", "combat"],
        body="""\
When you attempt an action, the GM (or the game) sets a difficulty
number. You roll your skill or attribute and try to meet or beat it.

DIFFICULTY SCALE
  Very Easy ............  1-5     Routine, almost automatic
  Easy .................  6-10    Simple, minor challenge
  Moderate ............. 11-15    Requires skill and effort
  Difficult ............ 16-20    Trained professionals struggle
  Very Difficult ....... 21-25    Expert-level challenge
  Heroic ............... 26-30    Near-impossible feats
  Heroic+ .............. 31+      Legendary, once-in-a-lifetime

OPPOSED ROLLS
When two characters act against each other (e.g., sneaking past a
guard), both roll and the higher total wins. No fixed difficulty —
you're rolling against the other person's skill.

MODIFIERS
Circumstances can add or subtract dice:
  Good conditions, preparation ........... +1D or more
  Poor conditions, distractions .......... -1D or more
  Wounded .................................. -1D per wound level""",
    ),

    # ── Rules: Combat ─────────────────────────────────────────────────

    HelpEntry(
        key="combat",
        title="Combat Basics",
        category="Rules: Combat",
        aliases=["fight", "fighting", "battle"],
        see_also=["ranged", "melee", "wounds", "dodge", "multiaction",
                  "cover", "aim"],
        body="""\
Combat follows a structured round. Each round represents roughly
5 seconds of in-game time.

THE COMBAT ROUND
  1. INITIATIVE — Everyone rolls Perception. Highest acts first.

  2. DECLARATION — In REVERSE initiative order (lowest first), each
     combatant declares what they'll do: attack, dodge, aim, flee, etc.
     Declaring later is an advantage — you see what others plan.

  3. RESOLUTION — In initiative order (highest first), actions resolve.
     The game resolves all actions and reports results.

MULTIPLE ACTIONS
You can declare more than one action per round (e.g., dodge + shoot),
but each additional action costs -1D from ALL your rolls that round.
See '+help multiaction' for details.

COMMANDS
  attack <target>     Declare an attack on a target
  dodge               Dodge a single incoming attack
  fulldodge           Dodge ALL attacks this round (uses your action)
  aim                 Aim for +1D next round (takes your action)
  flee                Attempt to leave combat
  cover               Take cover behind something
  pass                Skip your action this round""",
    ),

    HelpEntry(
        key="ranged",
        title="Ranged Combat",
        category="Rules: Combat",
        aliases=["shooting", "blaster", "rangedcombat"],
        see_also=["combat", "cover", "aim", "dodge"],
        body="""\
Ranged attacks (blasters, bowcasters, thrown weapons) roll your weapon
skill against a difficulty set by range.

RANGE DIFFICULTIES
  Point Blank (0-2m) ........  5   (Very Easy)
  Short Range ................  10  (Easy)
  Medium Range ...............  15  (Moderate)
  Long Range .................  20  (Difficult)

Each weapon has its own range bands defining the actual distances for
short/medium/long. A blaster pistol's "short" is much closer than a
blaster rifle's "short."

FIRE CONTROL
Ship and vehicle weapons add fire control dice to your attack roll.
This represents the targeting computer assisting your aim.

COVER MODIFIERS
Cover adds difficulty to attacks against the covered target:
  Quarter cover ......... +1D difficulty
  Half cover ............ +2D difficulty
  Three-quarter cover ... +3D difficulty
  Full cover ............ Cannot be targeted (but can't shoot either)

DAMAGE
If you hit, roll the weapon's damage dice. The target rolls Strength
(plus armor) to resist. The difference determines the wound level.
See '+help wounds' for the damage chart.""",
    ),

    HelpEntry(
        key="melee",
        title="Melee Combat",
        category="Rules: Combat",
        aliases=["brawl", "brawling", "meleecombat"],
        see_also=["combat", "lightsaber", "wounds"],
        body="""\
Melee combat (fists, vibroblades, lightsabers) uses OPPOSED ROLLS
instead of fixed difficulty numbers.

HOW IT WORKS
  Attacker rolls: melee combat (or brawling, or lightsaber)
  Defender rolls: melee parry (or brawling parry, or lightsaber)

If the attacker's roll beats the defender's, it's a hit. If the
defender wins or ties, the attack is blocked or dodged.

DAMAGE
  Brawling attacks: roll your Strength for damage
  Melee weapons: roll STR + weapon bonus (e.g., vibroblade is STR+2D)
  Lightsaber: 5D damage, ignores non-special armor

Melee combat is inherently dangerous — there's no range advantage,
and you're always in reach of counterattack.""",
    ),

    HelpEntry(
        key="wounds",
        title="Wounds & Healing",
        category="Rules: Combat",
        aliases=["wound", "healing", "damage", "injury", "death"],
        see_also=["combat", "armor", "heal"],
        body="""\
When damage beats your Strength roll, the difference determines your
wound level.

DAMAGE CHART (Damage Roll beats Strength Roll by)
  0-3 .................... Stunned
  4-8 .................... Wounded
  9-12 ................... Incapacitated
  13-15 .................. Mortally Wounded
  16+ .................... Killed

WOUND EFFECTS
  Stunned       -1D to all rolls for the rest of this round and next.
                Multiple stuns can knock you unconscious.
  Wounded       -1D to all rolls until healed.
                A second Wounded result → Wounded Twice (-2D).
  Incapacitated You collapse. Cannot act until healed.
  Mortally Wounded  Dying. Will die without medical attention.
                    Someone must make a Moderate first aid roll.
  Killed        Dead. Type 'respawn' to return to life.

HEALING
  Natural healing is slow — hours to days depending on severity.
  The 'heal' command lets a character with first aid or Medicine
  treat wounds. The healer rolls against the wound's difficulty.
  
  Type '+help heal' for the healing command details.""",
    ),

    HelpEntry(
        key="dodge",
        title="Dodging",
        category="Rules: Combat",
        aliases=["dodging", "fulldodge", "reaction"],
        see_also=["combat", "multiaction"],
        body="""\
Dodging lets you avoid incoming attacks by rolling your Dodge skill.

REACTION DODGE
  Type 'dodge' — uses your action to dodge ONE incoming attack.
  Your Dodge roll replaces the normal difficulty the attacker must beat.
  If you also want to attack, this counts as multiple actions (-1D).

FULL DODGE
  Type 'fulldodge' — dedicate your ENTIRE round to dodging.
  Your full Dodge pool applies against ALL incoming attacks.
  You cannot attack, aim, or do anything else that round.
  Best used when outnumbered or badly wounded.

PARRY (Melee)
  Works like dodge but for melee combat. Use 'parry' or 'fullparry'.
  Rolls melee parry, brawling parry, or lightsaber (as appropriate).""",
    ),

    HelpEntry(
        key="cover",
        title="Cover",
        category="Rules: Combat",
        aliases=["hiding"],
        see_also=["combat", "ranged"],
        body="""\
Taking cover makes you harder to hit with ranged attacks.

USAGE: cover [quarter|half|3/4|full]

COVER LEVELS
  Quarter ......... +1D to attacker's difficulty
  Half ............ +2D to attacker's difficulty
  Three-quarter ... +3D to attacker's difficulty
  Full ............ Cannot be targeted (but you can't shoot either)

Taking cover costs an action. Each room has a maximum cover level
(cover_max) based on its environment — an open desert has less
available cover than a junkyard.

You keep your cover until you move or the cover is destroyed.""",
    ),

    HelpEntry(
        key="multiaction",
        title="Multiple Actions",
        category="Rules: Combat",
        aliases=["multi-action", "multipleactions", "penalty"],
        see_also=["combat", "dodge"],
        body="""\
You can attempt multiple actions in a single round, but each
additional action costs -1D from ALL your rolls that round.

PENALTY TABLE
  1 action ......... no penalty
  2 actions ........ -1D to all rolls
  3 actions ........ -2D to all rolls
  4 actions ........ -3D to all rolls
  ...and so on.

COMMON COMBINATIONS
  Dodge + Attack = 2 actions = -1D to both your dodge and attack
  Attack + Attack = 2 actions = -1D to both attacks
  Dodge + Attack + Attack = 3 actions = -2D to everything

The penalty is applied BEFORE you roll, so it can significantly
reduce your effectiveness. Choose carefully — sometimes one
well-aimed shot is better than three sloppy ones.""",
    ),

    HelpEntry(
        key="armor",
        title="Armor",
        category="Rules: Combat",
        aliases=[],
        see_also=["wounds", "combat", "scale"],
        body="""\
Armor adds dice to your Strength when resisting damage. If you have
3D Strength and wear armor providing +1D, you roll 4D to resist.

Armor may not cover your entire body — some hits may bypass it
depending on hit location.

ARMOR DAMAGE
When you take damage through armor, the armor itself is damaged:
  You are Wounded .......... Armor takes -1 pip
  Incapacitated ............ Armor is heavily damaged
  Mortally Wounded ......... Armor is useless (needs full repair)
  Killed ................... Armor is destroyed

Armor can be repaired with the appropriate repair skill.""",
    ),

    HelpEntry(
        key="scale",
        title="Scale Modifiers",
        category="Rules: Combat",
        aliases=["scales", "vehiclescale"],
        see_also=["spacecombat", "combat"],
        body="""\
Different sizes of targets use different combat scales. The scales,
from smallest to largest:

  Character ........ People, creatures, droids
  Speeder .......... Landspeeders, swoops (modifier: 2D)
  Walker ........... AT-ST, AT-AT (modifier: 4D)
  Starfighter ...... X-Wing, TIE Fighter (modifier: 6D)
  Capital .......... Star Destroyers, frigates (modifier: 12D)
  Death Star ....... The big one (modifier: 24D)

CROSS-SCALE COMBAT
When shooting at a different scale, apply the difference:
  Smaller vs. Larger: the smaller attacker adds the modifier to
    their attack roll (easier to hit a big target), but the larger
    target adds it to damage resistance (tougher hull).
  Larger vs. Smaller: the larger attacker rolls normally, but the
    smaller target adds the modifier to dodge (harder to hit a tiny
    target). The larger weapon adds the modifier to damage.""",
    ),

    # ── Rules: Force ──────────────────────────────────────────────────

    HelpEntry(
        key="force",
        title="The Force",
        category="Rules: Force",
        aliases=["theforce", "jedi"],
        see_also=["forcepoints", "darkside", "lightsaber", "+powers"],
        body="""\
The Force is an energy field that binds the galaxy together. Some
characters are Force-sensitive and can learn to manipulate it.

FORCE SKILLS
Force abilities are organized into three disciplines:
  Control — Mastery over your own body and mind
  Sense   — Awareness of the world and other living things
  Alter   — Ability to change the physical world

Each Force power requires one or more of these skills. Type '+powers'
to see your available Force powers.

USING FORCE POWERS
Type 'force <power> [target]' to use a Force power. Powers that
require multiple Force skills roll each one — all must succeed.

THE DARK SIDE
Using the Force for aggression, domination, or selfish ends risks
gaining Dark Side Points. Accumulate too many and your character
falls to the Dark Side. See '+help darkside'.""",
    ),

    HelpEntry(
        key="forcepoints",
        title="Force Points",
        category="Rules: Force",
        aliases=["fp", "forcepoint"],
        see_also=["force", "darkside", "cp"],
        body="""\
Force Points represent moments of extraordinary heroism or villainy.

SPENDING A FORCE POINT
Type 'forcepoint' during combat to spend 1 FP. All your dice are
DOUBLED for the remainder of that round. This is incredibly powerful
but you have very few Force Points.

EARNING FORCE POINTS
  - Spend an FP at a dramatically appropriate, heroic moment and
    you get it back (plus potentially a bonus FP) at adventure's end.
  - Spend it at an inappropriate time and it's gone.

LOSING FORCE POINTS
  - Spending an FP for selfish or evil purposes costs the FP AND
    earns you a Dark Side Point.

Most characters start with 1-2 Force Points. They're precious —
save them for the moments that matter most.""",
    ),

    HelpEntry(
        key="darkside",
        title="The Dark Side",
        category="Rules: Force",
        aliases=["dsp", "darksidepoints"],
        see_also=["force", "forcepoints"],
        body="""\
The Dark Side is seductive and powerful, but it corrupts utterly.

GAINING DARK SIDE POINTS (DSP)
  - Using Force powers to harm, dominate, or for selfish ends
  - Committing evil acts (murder, torture, betrayal)
  - Spending Force Points for evil purposes

FALLING TO THE DARK SIDE
  If your Dark Side Points equal or exceed your total Force Points
  + Character Points combined, you fall. Your character becomes an
  NPC villain controlled by the game.

ATONEMENT
  A character can attempt to atone for Dark Side Points through
  selfless acts and meditation. This is difficult and slow — the
  Dark Side does not release its hold easily.

TEMPTATION
  The Dark Side offers quick, easy power. Dark Side Force powers
  are often more destructive than their Light Side equivalents,
  but every use brings you closer to the edge.""",
    ),

    HelpEntry(
        key="lightsaber",
        title="Lightsaber Combat",
        category="Rules: Force",
        aliases=["saber"],
        see_also=["melee", "force", "combat"],
        body="""\
The lightsaber is the weapon of a Jedi — elegant, deadly, and
requiring extensive training to wield effectively.

COMBAT STATS
  Skill: lightsaber (Dexterity)
  Damage: 5D (ignores most non-special armor)
  Defense: lightsaber skill is used for parrying

DEFLECTING BLASTERS
A trained lightsaber wielder can attempt to deflect blaster bolts.
This uses the lightsaber skill as a reaction (like dodge, but for
melee parry against ranged attacks). It's extremely difficult but
iconic — this is what Jedi do.

LIGHTSABER vs. LIGHTSABER
Both combatants roll lightsaber skill in opposed rolls. The loser
takes the winner's 5D damage minus their Strength.""",
    ),

    # ── Rules: Character Points & Advancement ─────────────────────────

    HelpEntry(
        key="cp",
        title="Character Points",
        category="Rules: Advancement",
        aliases=["characterpoints", "spending cp"],
        see_also=["advancement", "forcepoints", "+cpstatus"],
        body="""\
Character Points (CP) serve two purposes: spending in play for
temporary boosts, and spending between scenes to permanently
improve skills.

SPENDING CP IN PLAY
During any roll, you can spend CP to add extra dice:
  1 CP = +1D to a single roll
These are rolled AFTER seeing your initial result, so you can
decide to spend only when you really need the boost. CP dice do
NOT count as Wild Dice.

ADVANCING SKILLS
Between adventures, spend CP to permanently improve skills.
Use the 'train' command. Cost per pip = number of dice in total pool.
See '+help advancement' for the full progression system.""",
    ),

    HelpEntry(
        key="advancement",
        title="Advancement & Progression",
        category="Rules: Advancement",
        aliases=["progression", "training", "leveling"],
        see_also=["cp", "+cpstatus", "train"],
        body="""\
Characters earn Character Points (CP) through play and spend them
to permanently improve skills.

EARNING CP
  Passive trickle: 5 ticks/day just for being connected
  Scene bonuses: Completing RP scenes with other players
  Kudos: Players can award each other kudos (3/week, 35 ticks each)
  AI evaluator: Small bonus trickle for quality RP (when available)

  300 ticks = 1 CP. Weekly cap: 300 ticks.
  Expected pace: ~1 CP per 10-12 days for an active player.

SPENDING CP TO TRAIN
  Type 'train <skill name>' to advance a skill by one pip.
  Cost = number of dice in the skill's total pool.
  Example: Blaster at 5D → costs 5 CP per pip.
  Three pips (+1, +2, +0) advance the die: 5D → 5D+1 → 5D+2 → 6D.

TYPICAL ADVANCEMENT TIME
  3D → 4D: ~30 CP (3+3+3 + 4+4+4 + ...) over several months
  3D → 5D: ~7 months of active play""",
    ),

    # ── Rules: Space ──────────────────────────────────────────────────

    HelpEntry(
        key="space",
        title="Space Travel",
        category="Rules: Space",
        aliases=["spaceflight", "travel"],
        see_also=["spacecombat", "crew", "hyperdrive", "+ship"],
        body="""\
Space travel in SW_MUSH uses a zone-based model. Ships move between
named zones (e.g., "Tatooine Orbit", "Deep Space", "Mos Eisley Approach")
rather than tracking exact coordinates.

BASIC OPERATIONS
  board <ship>     Board a docked ship
  launch           Take off (pilot only)
  land             Land at a docking bay (pilot only)
  hyperspace <dest> Jump to hyperspace (pilot only, requires hyperdrive)
  disembark        Leave a docked ship

CREW STATIONS
Ships have up to 7 crew stations. Each grants different abilities.
Type '+help crew' for details on each station.

SHIP STATUS
  +ship             Your current ship's status and crew
  +ship/info <n>    Detailed stats on a ship type
  +ship/list        Browse all available ship types
  +ship/mine        Ships you own""",
    ),

    HelpEntry(
        key="spacecombat",
        title="Space Combat",
        category="Rules: Space",
        aliases=["shipcombat", "dogfight"],
        see_also=["space", "crew", "shields", "sensors", "scale"],
        body="""\
Space combat works similarly to personal combat but at starfighter
or capital scale. Crew stations determine who can do what.

KEY DIFFERENCES FROM PERSONAL COMBAT
  - Scale modifiers apply (6D between starfighter and capital scale)
  - Fire arcs matter — weapons can only fire in certain directions
  - Range is abstracted into zones (close/medium/long)
  - Multiple crew members contribute simultaneously

COMBAT ACTIONS
  fire <target>             Fire your weapon (gunner station)
  fire <target> with <wpn>  Fire a specific weapon by name
  fire <target> 2           Fire weapon #2 by index
  close <target>            Close range to a target (pilot)
  evade                     Perform evasive maneuvers (pilot)
  fleeship                  Attempt to break away (pilot)
  shields <f> <r>           Redistribute shields (pilot/shields op)
  shields front             All shields forward
  scan <target>             Scan a ship for details (sensors)
  lockon <target>           Begin targeting lock (+1D/round, max +3D)
  resist                    Break free of a tractor beam (pilot)

WEAPON TYPES
  Laser/Turbolaser  Standard damage — roll vs hull+shields
  Ion Cannon        Bypasses shields — ionizes controls (-1D per hit)
  Tractor Beam      Captures target — resist or get reeled in

EVASIVE MANEUVERS
  jink              Quick lateral shift (+5 difficulty, Easy)
  barrelroll        Roll to evade (+8 difficulty, Moderate)
  loop              Reverse direction, break tails (Difficult)
  slip              Sideslip to flank (+10 difficulty, V.Difficult)

CAPITAL SHIPS
Capital ships have multiple weapon stations. Use 'gunner <N>' to man
a specific weapon. '+ship' shows all stations and their crew.""",
    ),

    HelpEntry(
        key="crew",
        title="Crew Stations",
        category="Rules: Space",
        aliases=["stations", "crewstations"],
        see_also=["space", "spacecombat"],
        body="""\
Ships have up to 7 crew stations. Take a station with its command.

  pilot         Flies the ship. Can launch, land, close, evade, flee,
                resist tractor beams, and perform evasive maneuvers.
  copilot       Assists the pilot. Provides bonus dice to pilot actions.
  gunner [N]    Fires weapons. Specify a station number for capital
                ships with multiple weapon groups (see +ship for list).
  engineer      Manages power and repairs. Can run +ship/repair.
  navigator     Plots hyperspace courses. Grants bonus to astrogation.
  sensors       Operates sensors. Can scan ships, enhanced detail.
  commander     Coordinates crew. Grants +1D to all crew this round.

  vacate        Leave your current station.
  assist        Assist another crew member's roll.
  coordinate    Commander ability: grant +1D to all crew this round.

SHIELD MANAGEMENT
On starfighters, the pilot manages shields. On capital ships, a
dedicated shields operator can be assigned. Use 'shields front',
'shields rear', 'shields even', or 'shields <F> <R> <L> <R>' for
4-arc distribution. Difficulty scales with arcs covered.

NPC CREW
You can hire NPC crew members with the 'hire' command. They auto-act
each tick based on their assigned station. Type '+roster' to view.""",
    ),

    HelpEntry(
        key="hyperdrive",
        title="Hyperspace Travel",
        category="Rules: Space",
        aliases=["hyperspace", "astrogation", "jump"],
        see_also=["space", "crew"],
        body="""\
Hyperspace allows faster-than-light travel between star systems.

REQUIREMENTS
  - Ship must have a functioning hyperdrive
  - Must be piloted (pilot station occupied)
  - Astrogation check required

USAGE: hyperspace <destination>  |  hyperspace list

ASTROGATION CHECK
The navigator (or pilot if no navigator) rolls Astrogation:
  Fumble .......... Misjump! Random zone + hazard table + full fuel
  Fail ............ Jump aborted, no fuel consumed
  Success ......... Normal jump to destination
  Critical ........ Jump succeeds, fuel cost halved

A navigator at the sensors station grants +1D to the astrogation roll.

HYPERDRIVE MULTIPLIERS
  x1 = standard (Millennium Falcon)
  x2 = common freighter
  x3+ = slow, older ships
  Lower multiplier = faster travel.""",
    ),

    HelpEntry(
        key="sensors",
        title="Sensors",
        category="Rules: Space",
        aliases=["scanning", "scan"],
        see_also=["spacecombat", "crew"],
        body="""\
Sensors detect other ships and reveal their details.

USAGE: scan [target]

Without a target, scan sweeps the area and lists all detected ships.
With a target, performs a focused scan for detailed information.

SCAN RESULTS (based on Sensors skill roll)
  Fumble .......... Sensors offline briefly
  Fail ............ Name and range only
  Success ......... Standard readout (weapons, shields, hull)
  Critical ........ Deep scan + cargo flag

The sensors station operator gets +2D bonus to scan rolls.

SENSOR COUNTERMEASURES
Ships can reduce their sensor signature through stealth. Jamming
floods the area with static, degrading all sensor readings. Decoys
broadcast false signatures to confuse scanners.""",
    ),

    # ── World Topics ──────────────────────────────────────────────────

    HelpEntry(
        key="moseisley",
        title="Mos Eisley",
        category="World",
        aliases=["mos eisley", "spaceport", "city"],
        see_also=["cantina", "tatooine", "empire"],
        body="""\
"You will never find a more wretched hive of scum and villainy."

Mos Eisley is Tatooine's largest spaceport — a dusty, dangerous city
of smugglers, bounty hunters, moisture farmers, and Imperial patrols.
It sprawls across the desert floor, its domed buildings and landing
bays baking under the twin suns.

DISTRICTS
The city is divided into several areas, each with its own character.
The Cantina District is the social hub. The Market District handles
commerce. The Docking Bays ring the city's edge. The Outskirts fade
into open desert where Tusken Raiders roam.

LIFE IN MOS EISLEY
Credits talk. The Empire maintains a garrison but can't control
everything — the underworld thrives in the shadows. Deals are struck
in cantina booths, cargo changes hands in darkened bays, and those
who ask too many questions tend to disappear.""",
    ),

    HelpEntry(
        key="cantina",
        title="Chalmun's Cantina",
        category="World",
        aliases=["bar", "chalmuns"],
        see_also=["moseisley", "perform"],
        body="""\
Chalmun's Cantina is the most famous watering hole in the Outer Rim.
A domed building in the heart of Mos Eisley, it serves as the social
nexus of the spaceport — the place where pilots find work, smugglers
find cargo, and bounty hunters find marks.

RULES OF THE CANTINA
  - No droids allowed inside (they wait outside)
  - Blasters are technically prohibited (loosely enforced)
  - Wuher the bartender runs a tight bar
  - The band plays jizz-wailer music most nights

The cantina is a good place to find NPCs to talk to, hear rumors,
and pick up jobs. It's also a good place to get shot if you're
not careful.""",
    ),

    HelpEntry(
        key="tatooine",
        title="Tatooine",
        category="World",
        aliases=["planet"],
        see_also=["moseisley", "empire"],
        body="""\
Tatooine is a harsh desert world orbiting twin suns in the Outer Rim.
Far from the galactic core, it's a backwater planet known for moisture
farming, podracing, and a thriving underworld.

ENVIRONMENT
The desert is lethal to the unprepared. Sandstorms can ground all
surface traffic. The twin suns — Tatoo I and Tatoo II — make daytime
travel exhausting.

INHABITANTS
  Moisture farmers scratch a living from the arid soil.
  Jawas are diminutive scavengers who trade in salvaged droids.
  Tusken Raiders (Sand People) are nomadic warriors hostile to
    outsiders. They roam the Jundland Wastes and beyond.
  Hutts control much of the planet's underworld from their palaces.

IMPERIAL PRESENCE
The Empire maintains a garrison in Mos Eisley, but Tatooine is far
from a priority. Stormtrooper patrols are routine but not thorough.
The real power lies with the Hutts and the criminal syndicates.""",
    ),

    # ── Economy Topics ────────────────────────────────────────────────

    HelpEntry(
        key="trading",
        title="Trading & Commerce",
        category="Economy",
        aliases=["trade", "buying", "selling", "commerce"],
        see_also=["smuggling", "+credits", "economy"],
        body="""\
Making money in Mos Eisley comes in several forms.

BUYING & SELLING WEAPONS
  '+weapons' lists available weapons and prices.
  'buy <weapon>' purchases and equips a weapon.
  'sell' sells your equipped weapon at 25-50% of its value.
  The Bargain skill affects your selling price.

MISSIONS
  '+missions' shows the mission board with available jobs.
  'accept <id>' takes a mission. 'complete' finishes it.
  Mission types include delivery, escort, and investigation.

CREDITS
  '+credits' shows your current balance.
  Credits are earned from missions, selling, smuggling, bounties,
  and entertaining. They're spent on weapons, repairs, ship fuel,
  crew wages, and supplies.""",
    ),

    HelpEntry(
        key="smuggling",
        title="Smuggling",
        category="Economy",
        aliases=["smuggle", "contraband"],
        see_also=["trading", "+smugjobs"],
        body="""\
Smuggling is high-risk, high-reward work. You transport illegal or
restricted cargo between locations while avoiding Imperial patrols.

HOW IT WORKS
  '+smugjobs' shows available smuggling contracts.
  'smugaccept' takes a job. You receive contraband cargo.
  Fly to the destination and 'smugdeliver' to collect payment.

RISKS
  Imperial patrols may intercept you on launch. A Perception check
  determines if they scan your ship. If caught with contraband:
  fines, confiscation, or combat.

  'smugdump' jettisons your cargo if things get too hot. You lose
  the cargo and fail the job, but avoid criminal charges.

REWARDS
  Smuggling pays 2-5x more than legitimate delivery missions.
  The best runs require navigating dangerous routes and fast ships.""",
    ),

    HelpEntry(
        key="bounty",
        title="Bounty Hunting",
        category="Economy",
        aliases=["bountyhunting", "hunting"],
        see_also=["+bounties", "+mybounty"],
        body="""\
Bounty hunting is the pursuit and capture (or elimination) of targets
with prices on their heads.

HOW IT WORKS
  '+bounties' shows the bounty board with active contracts.
  'bountyclaim <id>' accepts a bounty. You become the hunter.
  'bountytrack' uses your Search/Investigation skill to locate
    the target. Track them to their location.
  'bountycollect' turns in a completed bounty for payment.

TRACKING
  Tracking rolls use Search or Investigation skill. Better rolls
  give more precise location information. Targets may move, so
  you may need to track multiple times.

THREAT LEVELS
  Bounties have threat ratings indicating target difficulty.
  Higher threat = better pay, but tougher fight.""",
    ),

    # ── Character Topics ──────────────────────────────────────────────

    HelpEntry(
        key="species",
        title="Playable Species",
        category="Character",
        aliases=["races", "aliens"],
        see_also=["attributes", "+sheet"],
        body="""\
Nine species are available during character creation. Each has
different attribute ranges and special abilities.

  Human          The baseline. Balanced attributes, no special
                 abilities but no weaknesses either.
  Wookiee        Powerful. High Strength, low Dexterity ceiling.
                 Berserker rage ability.
  Twi'lek        Charismatic. Bonus to Perception-based social skills.
  Rodian         Natural hunters. Perception and Dexterity bonuses.
  Mon Calamari   Aquatic. Can breathe underwater. Good Technical.
  Trandoshan     Reptilian hunters. Regeneration, natural claws.
  Duros          Natural pilots. Bonus to Mechanical, especially
                 astrogation and starship piloting.
  Bothan         Information brokers. Perception bonuses, stealth.
  Zabrak         Resilient. Stamina bonuses, resist pain.

Each species has minimum and maximum attribute values that differ
from the human baseline. Type '+sheet' to see your current stats.""",
    ),

    # ── MUSH / How-to-Play Topics ─────────────────────────────────────

    HelpEntry(
        key="rp",
        title="Roleplaying Guide",
        category="MUSH Basics",
        aliases=["roleplay", "roleplaying", "posing", "emoting"],
        see_also=["commands", "newbie"],
        body="""\
This is a roleplaying game. You write what your character says, does,
and feels, and interact with other players' characters.

BASIC COMMANDS
  say <message>    Speak in-character. Alias: 'message
  emote <action>   Describe an action. Alias: :action
  ;                Semipose (name-glued). ;'s blaster → Tundra's blaster
  whisper <who>=<msg>  Private message to someone in the room

GOOD POSING
  - Write in third person, present tense:
    :draws his blaster and scans the room warily.
  - Include reactions and body language, not just actions.
  - Give other players something to respond to.
  - Respect the collaborative story — don't auto-hit or god-mod.

IC vs. OOC
  Everything you say and emote is In-Character (IC).
  Use '+ooc <message>' or 'ooc <message>' for Out-Of-Character chat.
  OOC is for coordinating with other players, asking questions, etc.""",
    ),

    HelpEntry(
        key="newbie",
        title="New Player Guide",
        category="MUSH Basics",
        aliases=["newplayer", "getting started", "tutorial", "start"],
        see_also=["rp", "commands", "attributes", "combat"],
        body="""\
Welcome to Star Wars D6 MUSH! Here's how to get started.

FIRST STEPS
  1. Create your character during login (choose species, allocate
     attributes, pick skills).
  2. Once in-game, type 'look' to see your surroundings.
  3. Use compass directions to move: north, south, east, west (or
     n, s, e, w for short).
  4. Type '+sheet' to see your character stats.
  5. Type '+inv' to see what you're carrying.

GETTING AROUND
  Mos Eisley is the starting area. Explore the cantina, market,
  and docking bays. Talk to NPCs with 'talk <npc name>'.

MAKING MONEY
  Check '+missions' for available jobs. Accept one and complete it
  for credits. Use credits to buy better equipment.

COMBAT
  You'll encounter hostile NPCs in some areas. Combat starts
  automatically. Type 'attack <target>' to fight, 'dodge' to
  defend, or 'flee' to run away.

GETTING HELP
  Type '+help <topic>' for detailed help on any subject.
  Type '+help/search <keyword>' to search all help files.
  Use '+ooc' to ask other players for help.""",
    ),

    HelpEntry(
        key="commands",
        title="Command Quick Reference",
        category="MUSH Basics",
        aliases=["quickref", "reference", "cmdref"],
        see_also=["+help", "newbie"],
        body="""\
Commands use three prefix conventions:

  (bare)   IC actions: say, emote, look, attack, dodge, move, flee
  +        System/OOC: +sheet, +roll, +who, +help, +credits, +missions
  @        Admin/builder: @dig, @npc, @spawn, @grant, @director

SHORTCUTS
  '         say (e.g., 'Hello there.)
  "         say (e.g., "Hello there.)
  :         emote (e.g., :draws a blaster.)
  ;         semipose (e.g., ;'s blaster hums. → Tundra's blaster hums.)
  n/s/e/w   movement directions

SWITCHES
  Some commands accept /switches for sub-modes:
  +sheet/brief     condensed character sheet
  +help/search     search all help topics
  +combat/rolls    show combat roll details

Type '+help <command>' for detailed help on any command.
Type '+help <topic>' for rules topics (combat, dice, force, etc.).""",
    ),

    HelpEntry(
        key="channels",
        title="Communication Channels",
        category="MUSH Basics",
        aliases=["comms", "communication"],
        see_also=["+channels", "+freqs", "rp"],
        body="""\
Beyond local say/emote, several communication channels are available.

CHANNEL COMMANDS
  ooc <message>       Global OOC chat (out of character)
  comlink <message>   IC comlink channel (like a radio)
  fcomm <message>     Faction-only IC channel
  commfreq <freq> <msg>  Broadcast on a custom frequency

MANAGING CHANNELS
  +channels           List all available channels
  tune <channel>      Join a channel
  untune <channel>    Leave a channel
  +freqs              List your active frequencies

CUSTOM FREQUENCIES
  You can set up private frequencies for crew or group communication.
  Anyone tuned to the same frequency can hear transmissions.""",
    ),

    HelpEntry(
        key="building",
        title="Building Guide",
        category="Admin",
        aliases=["builder", "worldbuilding"],
        see_also=["@dig", "@tunnel", "@set", "@lock"],
        access_level=2,
        body="""\
Builders create and modify the game world: rooms, exits, objects.

CREATING ROOMS
  @dig <name>          Create a new room
  @tunnel <dir>=<name> Create a room with a two-way exit
  @open <dir>=<room#>  Create an exit to an existing room

MODIFYING ROOMS
  @rdesc <text>        Set room description
  @rname <name>        Rename current room
  @set <prop>=<val>    Set room properties (cover_max, etc.)
  @zone <name>         Assign room to a zone

EXITS & LOCKS
  @link <dir>=<room#>  Link an exit to a room
  @unlink <dir>        Remove an exit link
  @lock <dir>=<expr>   Lock an exit (e.g., has:keycard & !wounded)

INFORMATION
  @examine             Show detailed room/object info
  @rooms               List all rooms
  @find <name>         Search for rooms by name
  @entrances           Show what exits lead to this room""",
    ),
]
