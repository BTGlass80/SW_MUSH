# -*- coding: utf-8 -*-
"""
Free-form character creation engine.

Players see a persistent status line and can edit any field in any order.
Commands: name, species, set, skill, unskill, template, undo, sheet, done, help.
"""
import copy
import logging
from dataclasses import dataclass, field
from typing import Optional

from engine.dice import DicePool
from engine.character import Character, SkillRegistry, ATTRIBUTE_NAMES
from engine.species import Species, SpeciesRegistry
from engine.sheet_renderer import render_creation_sheet, render_status_line

log = logging.getLogger(__name__)


@dataclass
class _Snapshot:
    """Undo checkpoint."""
    label: str
    name: str
    species_name: str
    attributes: dict
    skills: dict


@dataclass
class CreationState:
    name: str = ""
    species: Optional[Species] = None
    attributes: dict[str, DicePool] = field(default_factory=dict)
    skills: dict[str, DicePool] = field(default_factory=dict)
    undo_stack: list = field(default_factory=list)


# ── Templates ──

TEMPLATES = {
    "smuggler": {
        "label": "Smuggler",
        "species": "Human",
        "attributes": {"dexterity": "3D+1", "knowledge": "2D+1", "mechanical": "4D",
                        "perception": "3D+1", "strength": "2D+2", "technical": "2D+1"},
        "skills": {"blaster": "1D+1", "dodge": "1D", "space transports": "1D+2",
                    "starship gunnery": "1D", "streetwise": "1D", "bargain": "1D"},
    },
    "bounty_hunter": {
        "label": "Bounty Hunter",
        "species": "Human",
        "attributes": {"dexterity": "3D+2", "knowledge": "2D+1", "mechanical": "2D+2",
                        "perception": "3D+1", "strength": "3D+1", "technical": "2D+2"},
        "skills": {"blaster": "2D", "dodge": "1D", "brawling": "1D",
                    "search": "1D", "sneak": "1D", "security": "1D"},
    },
    "rebel_pilot": {
        "label": "Rebel Pilot",
        "species": "Human",
        "attributes": {"dexterity": "3D", "knowledge": "2D+2", "mechanical": "4D+1",
                        "perception": "2D+2", "strength": "2D+2", "technical": "2D+2"},
        "skills": {"blaster": "1D", "starfighter piloting": "2D",
                    "starship gunnery": "1D", "astrogation": "1D", "sensors": "1D",
                    "starfighter repair": "1D"},
    },
    "scoundrel": {
        "label": "Scoundrel",
        "species": "Human",
        "attributes": {"dexterity": "3D", "knowledge": "3D", "mechanical": "2D+2",
                        "perception": "4D", "strength": "2D+2", "technical": "2D+2"},
        "skills": {"blaster": "1D", "dodge": "1D", "con": "1D+2",
                    "persuasion": "1D", "gambling": "1D", "sneak": "1D+1"},
    },
    "technician": {
        "label": "Technician",
        "species": "Human",
        "attributes": {"dexterity": "2D+1", "knowledge": "3D", "mechanical": "2D+2",
                        "perception": "2D+2", "strength": "2D+2", "technical": "4D+2"},
        "skills": {"computer programming/repair": "1D+2", "droid repair": "1D",
                    "first aid": "1D", "security": "1D", "blaster repair": "1D",
                    "space transport repair": "1D+1"},
    },
    "jedi_apprentice": {
        "label": "Jedi Apprentice",
        "species": "Human",
        "attributes": {"dexterity": "3D+1", "knowledge": "3D", "mechanical": "2D+1",
                        "perception": "3D+2", "strength": "3D", "technical": "2D+2"},
        "skills": {"lightsaber": "1D+2", "dodge": "1D", "scholar": "1D",
                    "willpower": "1D", "sneak": "1D", "climbing/jumping": "1D+1"},
    },
    "soldier": {
        "label": "Soldier",
        "species": "Human",
        "attributes": {"dexterity": "3D+2", "knowledge": "2D+2", "mechanical": "2D+2",
                        "perception": "2D+2", "strength": "3D+2", "technical": "2D+2"},
        "skills": {"blaster": "1D+2", "dodge": "1D", "brawling": "1D",
                    "grenade": "1D", "tactics": "1D", "stamina": "1D+1"},
    },
}


class CreationEngine:
    """Free-form character creation. Call process_input() for each line."""

    def __init__(self, species_reg: SpeciesRegistry, skill_reg: SkillRegistry):
        self.species_reg = species_reg
        self.skill_reg = skill_reg
        self.state = CreationState()
        # Default to Human
        self.state.species = species_reg.get("human")
        if self.state.species:
            self._set_minimums()

    def get_initial_display(self) -> tuple[str, str]:
        """Opening screen with help + sheet."""
        lines = self._help_lines()
        lines.append("")
        lines.extend(self._sheet_lines())
        lines.append(self._status())
        return "\n".join(lines), "create> "

    def process_input(self, text: str) -> tuple[str, str, bool]:
        """Process a command. Returns (display, prompt, is_done)."""
        text = text.strip()
        if not text:
            return self._status(), "create> ", False

        parts = text.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "name": self._cmd_name,
            "species": self._cmd_species,
            "set": self._cmd_set,
            "skill": self._cmd_skill,
            "unskill": self._cmd_unskill,
            "template": self._cmd_template,
            "undo": self._cmd_undo,
            "sheet": self._cmd_sheet,
            "review": self._cmd_sheet,
            "done": self._cmd_done,
            "help": self._cmd_help,
            "skills": self._cmd_list_skills,
            "list": self._cmd_list_skills,
            "info": self._cmd_info,
        }

        handler = handlers.get(cmd)
        if handler:
            return handler(args)

        return f"  Unknown command: '{cmd}'. Type 'help' for commands.", "create> ", False

    def get_character(self) -> Character:
        """Build final Character from state."""
        char = Character()
        char.name = self.state.name
        char.species_name = self.state.species.name if self.state.species else "Human"
        char.move = self.state.species.move if self.state.species else 10
        for attr, pool in self.state.attributes.items():
            char.set_attribute(attr, pool)
        for sk, bonus in self.state.skills.items():
            char.skills[sk] = bonus
        return char

    # ── Commands ──

    def _cmd_name(self, args):
        if not args:
            return f"  Current name: {self.state.name or '(not set)'}. Usage: name <name>", "create> ", False
        if len(args) < 2 or len(args) > 30:
            return "  Name must be 2-30 characters.", "create> ", False
        self._push_undo(f"name -> {args}")
        self.state.name = args
        return f"  Name set to: {args}\n{self._status()}", "create> ", False

    def _cmd_species(self, args):
        if not args:
            return self._species_list(), "create> ", False

        sp = self.species_reg.get(args)
        if not sp:
            # Try partial match
            matches = [s for s in self.species_reg.list_all()
                       if s.name.lower().startswith(args.lower())]
            if len(matches) == 1:
                sp = matches[0]
            else:
                return f"  Unknown species: '{args}'. Type 'species' to list.", "create> ", False

        self._push_undo(f"species -> {sp.name}")
        self.state.species = sp
        self.state.skills.clear()  # Reset skills since attribute bases change
        self._set_minimums()
        lines = [f"  Species set to: {sp.name}. Attributes reset to minimums, skills cleared."]
        if sp.special_abilities:
            for ab in sp.special_abilities:
                lines.append(f"    * {ab.name}")
        lines.append(self._status())
        return "\n".join(lines), "create> ", False

    def _cmd_set(self, args):
        parts = args.split()
        if len(parts) < 2:
            return "  Usage: set <attribute> <dice>  (e.g. 'set dex 4D+1')", "create> ", False

        attr_input = parts[0].lower()
        dice_str = parts[1]

        # Match attribute by prefix
        attr_name = self._match_attribute(attr_input)
        if not attr_name:
            return f"  Unknown attribute: '{attr_input}'", "create> ", False

        try:
            pool = DicePool.parse(dice_str)
        except (ValueError, IndexError):
            return f"  Invalid dice: '{dice_str}'", "create> ", False

        # Validate range
        sp = self.state.species
        if sp:
            r = sp.attributes.get(attr_name)
            if r:
                if pool.total_pips() < r.min_pool.total_pips():
                    return f"  {attr_name.capitalize()} min for {sp.name}: {r.min_pool}", "create> ", False
                if pool.total_pips() > r.max_pool.total_pips():
                    return f"  {attr_name.capitalize()} max for {sp.name}: {r.max_pool}", "create> ", False

        self._push_undo(f"set {attr_name} {pool}")
        self.state.attributes[attr_name] = pool
        return f"  {attr_name.capitalize()}: {pool}\n{self._status()}", "create> ", False

    def _cmd_skill(self, args):
        # Parse: everything except last token is skill name, last token is dice
        parts = args.rsplit(None, 1)
        if len(parts) < 2:
            return "  Usage: skill <name> <dice>  (e.g. 'skill blaster 2D+1')", "create> ", False

        skill_name = parts[0].strip()
        dice_str = parts[1].strip()

        sd = self.skill_reg.get(skill_name)
        if not sd:
            # Try partial match
            all_skills = self.skill_reg.all_skills()
            matches = [s for s in all_skills if s.name.lower().startswith(skill_name.lower())]
            if len(matches) == 1:
                sd = matches[0]
            elif len(matches) > 1:
                names = ", ".join(m.name for m in matches[:5])
                return f"  Ambiguous: {names}", "create> ", False
            else:
                return f"  Unknown skill: '{skill_name}'. Type 'list <attr>' to browse.", "create> ", False

        try:
            bonus = DicePool.parse(dice_str)
        except (ValueError, IndexError):
            return f"  Invalid dice: '{dice_str}'", "create> ", False

        if bonus.total_pips() <= 0:
            return "  Bonus must be at least +1 pip.", "create> ", False

        self._push_undo(f"skill {sd.name} {bonus}")
        self.state.skills[sd.key] = bonus

        attr_pool = self.state.attributes.get(sd.attribute, DicePool(0, 0))
        total = attr_pool + bonus
        return f"  {sd.name}: +{bonus} = {total}\n{self._status()}", "create> ", False

    def _cmd_unskill(self, args):
        if not args:
            return "  Usage: unskill <name>  (e.g. 'unskill blaster')", "create> ", False

        sd = self.skill_reg.get(args)
        if not sd:
            matches = [s for s in self.skill_reg.all_skills()
                       if s.name.lower().startswith(args.lower())]
            if len(matches) == 1:
                sd = matches[0]
            else:
                return f"  Unknown skill: '{args}'", "create> ", False

        if sd.key not in self.state.skills:
            return f"  You have no dice in {sd.name}.", "create> ", False

        self._push_undo(f"unskill {sd.name}")
        del self.state.skills[sd.key]
        return f"  Removed {sd.name}.\n{self._status()}", "create> ", False

    def _cmd_template(self, args):
        if not args:
            lines = ["", "  Available templates:"]
            for key, tmpl in TEMPLATES.items():
                lines.append(f"    {key:20s} {tmpl['label']}")
            lines.append("")
            lines.append("  Usage: template <name>  (e.g. 'template smuggler')")
            lines.append("  Templates set species, attributes, and skills. You can edit after.")
            lines.append("")
            return "\n".join(lines), "create> ", False

        key = args.lower().replace(" ", "_")
        tmpl = TEMPLATES.get(key)
        if not tmpl:
            return f"  Unknown template: '{args}'. Type 'template' to list.", "create> ", False

        self._push_undo(f"template {tmpl['label']}")

        # Apply species
        sp = self.species_reg.get(tmpl["species"])
        if sp:
            self.state.species = sp

        # Apply attributes
        self.state.attributes.clear()
        for attr, dice_str in tmpl["attributes"].items():
            self.state.attributes[attr] = DicePool.parse(dice_str)

        # Apply skills
        self.state.skills.clear()
        for skill, dice_str in tmpl["skills"].items():
            self.state.skills[skill.lower()] = DicePool.parse(dice_str)

        lines = [f"  Template '{tmpl['label']}' applied. You can edit anything."]
        lines.append(self._status())
        return "\n".join(lines), "create> ", False

    def _cmd_undo(self, args):
        if not self.state.undo_stack:
            return "  Nothing to undo.", "create> ", False

        snap = self.state.undo_stack.pop()
        self.state.name = snap.name
        sp = self.species_reg.get(snap.species_name)
        self.state.species = sp
        self.state.attributes = snap.attributes
        self.state.skills = snap.skills
        return f"  Undid: {snap.label}\n{self._status()}", "create> ", False

    def _cmd_sheet(self, args):
        lines = self._sheet_lines()
        lines.append(self._status())
        return "\n".join(lines), "create> ", False

    def _cmd_help(self, args):
        return "\n".join(self._help_lines()), "create> ", False

    def _cmd_list_skills(self, args):
        if not args:
            return "  Usage: list <attribute>  (e.g. 'list dex' or 'list all')", "create> ", False

        if args.lower() == "all":
            attrs = list(ATTRIBUTE_NAMES)
        else:
            attr = self._match_attribute(args.lower())
            if not attr:
                return f"  Unknown attribute: '{args}'", "create> ", False
            attrs = [attr]

        lines = [""]
        for attr in attrs:
            pool = self.state.attributes.get(attr, DicePool(0, 0))
            lines.append(f"  {attr.upper()} ({pool}):")
            for sd in self.skill_reg.skills_for_attribute(attr):
                current = self.state.skills.get(sd.key)
                if current:
                    total = pool + current
                    lines.append(f"    {sd.name:27s} +{current} = {total}")
                else:
                    specs = f"  {', '.join(sd.specializations)}" if sd.specializations else ""
                    lines.append(f"    {sd.name:27s} (untrained){specs}")
        lines.append("")
        return "\n".join(lines), "create> ", False

    def _cmd_info(self, args):
        if not args:
            return "  Usage: info <species>  (e.g. 'info wookiee')", "create> ", False
        sp = self.species_reg.get(args)
        if not sp:
            matches = [s for s in self.species_reg.list_all()
                       if s.name.lower().startswith(args.lower())]
            if len(matches) == 1:
                sp = matches[0]
            else:
                return f"  Unknown species: '{args}'", "create> ", False
        return sp.format_display(), "create> ", False

    def _cmd_done(self, args):
        errors = self._validate()
        if errors:
            lines = ["  Cannot finalize:"]
            for e in errors:
                lines.append(f"    - {e}")
            return "\n".join(lines), "create> ", False

        lines = self._sheet_lines()
        lines.append("")
        lines.append("  Character complete!")
        return "\n".join(lines), "", True

    # ── Helpers ──

    def _push_undo(self, label):
        self.state.undo_stack.append(_Snapshot(
            label=label,
            name=self.state.name,
            species_name=self.state.species.name if self.state.species else "Human",
            attributes=copy.deepcopy(self.state.attributes),
            skills=copy.deepcopy(self.state.skills),
        ))
        # Cap stack at 20
        if len(self.state.undo_stack) > 20:
            self.state.undo_stack.pop(0)

    def _set_minimums(self):
        """Set all attributes to species minimums."""
        self.state.attributes.clear()
        if self.state.species:
            for attr in ATTRIBUTE_NAMES:
                r = self.state.species.attributes.get(attr)
                if r:
                    self.state.attributes[attr] = DicePool(r.min_pool.dice, r.min_pool.pips)

    def _match_attribute(self, text):
        """Match an attribute name by prefix (dex -> dexterity)."""
        text = text.lower()
        for attr in ATTRIBUTE_NAMES:
            if attr.startswith(text):
                return attr
        # Also match force attrs
        for fa in ("control", "sense", "alter"):
            if fa.startswith(text):
                return fa
        return None

    def _attr_pips_spent(self):
        return sum(p.total_pips() for p in self.state.attributes.values())

    def _attr_pips_total(self):
        if self.state.species:
            return self.state.species.attribute_dice.total_pips()
        return 54  # 18D

    def _skill_pips_spent(self):
        return sum(p.total_pips() for p in self.state.skills.values())

    def _skill_pips_total(self):
        if self.state.species:
            return self.state.species.skill_dice.total_pips()
        return 21  # 7D

    def _status(self):
        return render_status_line(
            self._attr_pips_total() - self._attr_pips_spent(),
            self._skill_pips_total() - self._skill_pips_spent(),
        )

    def _sheet_lines(self):
        return render_creation_sheet(
            self.state.name, self.state.species,
            self.state.attributes, self.state.skills, self.skill_reg,
            self._attr_pips_total(), self._attr_pips_spent(),
            self._skill_pips_total(), self._skill_pips_spent(),
        )

    def _validate(self):
        errors = []
        if not self.state.name or len(self.state.name) < 2:
            errors.append("Name not set (use: name <name>)")
        if not self.state.species:
            errors.append("Species not set (use: species <name>)")

        attr_left = self._attr_pips_total() - self._attr_pips_spent()
        if attr_left != 0:
            errors.append(f"Attribute points not fully spent ({attr_left} pips remaining)")

        # Skill overspend check
        skill_left = self._skill_pips_total() - self._skill_pips_spent()
        if skill_left < 0:
            errors.append(f"Skill points overspent by {-skill_left} pips")

        # Attribute range check
        if self.state.species:
            for attr in ATTRIBUTE_NAMES:
                pool = self.state.attributes.get(attr, DicePool(0, 0))
                r = self.state.species.attributes.get(attr)
                if r:
                    if pool.total_pips() < r.min_pool.total_pips():
                        errors.append(f"{attr.capitalize()} below minimum ({pool} < {r.min_pool})")
                    if pool.total_pips() > r.max_pool.total_pips():
                        errors.append(f"{attr.capitalize()} above maximum ({pool} > {r.max_pool})")

        return errors

    def _species_list(self):
        lines = ["", "  Available species:"]
        for sp in self.species_reg.list_all():
            s_range = sp.attributes.get("strength")
            s_str = f"STR {s_range.min_pool}-{s_range.max_pool}" if s_range else ""
            lines.append(f"    {sp.name:20s} {s_str}")
        lines.append("")
        lines.append("  Usage: species <name>  |  info <name> for details")
        lines.append("")
        return "\n".join(lines)

    def _help_lines(self):
        return [
            "",
            "  +--- CHARACTER CREATION ---------------------------------+",
            "  |                                                        |",
            "  |  name <name>          Set character name               |",
            "  |  species [name]       List or set species              |",
            "  |  info <species>       View species details             |",
            "  |  template [name]      List or apply a template         |",
            "  |  set <attr> <dice>    Set attribute (e.g. set dex 4D)  |",
            "  |  skill <name> <dice>  Add skill dice                   |",
            "  |  unskill <name>       Remove skill dice                |",
            "  |  list <attr|all>      Browse skills by attribute       |",
            "  |  undo                 Undo last change                 |",
            "  |  sheet / review       Show full character sheet        |",
            "  |  done                 Finalize character               |",
            "  |  help                 Show this help                   |",
            "  |  quit                 Abort creation                   |",
            "  |                                                        |",
            "  +--------------------------------------------------------+",
            "",
        ]
