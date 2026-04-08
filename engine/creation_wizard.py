# -*- coding: utf-8 -*-
"""
Guided character creation wizard.

Wraps CreationEngine with a step-by-step flow that teaches the D6 rules
as it goes, using descriptions sourced from the WEG R&E rulebook (WEG40120).

Steps:
  1. Welcome & path choice (template vs. scratch)
  2a. Template selection (with R&E flavor text)   -- OR --
  2b. Species selection (with full lore & stats)
  3. Attributes (with explanations)               -- scratch only
  4. Skills (with descriptions & gameplay tips)
  5. Name & Background
  6. Force Sensitivity (if applicable)
  7. Review & Confirm

At any step: 'back' to return, 'free' to drop into free-form editor,
'undo' to revert last change, 'quit' to abort.
"""
import logging
import os
import textwrap
from enum import IntEnum, auto
from typing import Optional

import yaml

from engine.character import Character, SkillRegistry, ATTRIBUTE_NAMES
from engine.creation import CreationEngine, TEMPLATES
from engine.dice import DicePool
from engine.species import SpeciesRegistry

log = logging.getLogger(__name__)

# ANSI helpers
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
BRIGHT_WHITE = "\033[97m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_RED = "\033[91m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"

W = 78


def _bar(char="=", color=BRIGHT_CYAN):
    return f"{color}{char * W}{RESET}"


def _wrap(text, width=74, indent="  "):
    """Word-wrap text with indent."""
    lines = []
    for para in text.strip().split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        for line in textwrap.wrap(para, width=width - len(indent)):
            lines.append(f"{indent}{line}")
    return lines


def _center(text):
    stripped = text.replace(BOLD, "").replace(DIM, "").replace(RESET, "")
    stripped = stripped.replace(BRIGHT_WHITE, "").replace(BRIGHT_CYAN, "")
    stripped = stripped.replace(BRIGHT_YELLOW, "").replace(BRIGHT_GREEN, "")
    pad = max(0, W - len(stripped))
    return " " * (pad // 2) + text


class WizardStep(IntEnum):
    WELCOME = auto()
    TEMPLATE_SELECT = auto()
    SPECIES_SELECT = auto()
    SPECIES_DETAIL = auto()
    ATTRIBUTES = auto()
    SKILLS = auto()
    NAME_BACKGROUND = auto()
    FORCE_SENSITIVE = auto()
    REVIEW = auto()
    FREE_FORM = auto()
    DONE = auto()


class CreationWizard:
    """
    Step-by-step character creation wizard.

    Wraps a CreationEngine and provides guided flow with R&E lore.
    Call process_input() for each line of player input.
    """

    def __init__(self, species_reg: SpeciesRegistry, skill_reg: SkillRegistry,
                 data_dir: str = "data"):
        self.species_reg = species_reg
        self.skill_reg = skill_reg
        self.engine = CreationEngine(species_reg, skill_reg)
        self.step = WizardStep.WELCOME
        self._prev_step = None  # for 'back'
        self._step_history: list[WizardStep] = []
        self._template_path = False  # did they pick a template?
        self._attr_index = 0  # which attribute we're walking through
        self._pending_species = None  # species being confirmed
        self._background = ""
        self._force_sensitive = False

        # Load skill descriptions
        self._skill_descs = {}
        self._attr_descs = {}
        self._template_descs = {}
        desc_path = os.path.join(data_dir, "skill_descriptions.yaml")
        try:
            with open(desc_path, "r", encoding="utf-8") as f:
                desc_data = yaml.safe_load(f)
            self._attr_descs = desc_data.get("attributes", {})
            self._skill_descs = desc_data.get("skills", {})
            self._template_descs = desc_data.get("templates", {})
            log.info("Loaded skill descriptions from %s", desc_path)
        except Exception as e:
            log.warning("Could not load skill descriptions: %s", e)

    # ── Public API ──

    def get_initial_display(self) -> tuple[str, str]:
        """Return the welcome screen and prompt."""
        return self._render_welcome(), "chargen> "

    def process_input(self, text: str) -> tuple[str, str, bool]:
        """
        Process one line of input.
        Returns (display_text, prompt, is_done).
        """
        text = text.strip()

        # Universal commands
        if text.lower() == "quit":
            return "", "", False  # handled by game_server

        if text.lower() == "back" and self._step_history:
            self.step = self._step_history.pop()
            return self._render_current_step(), "chargen> ", False

        if text.lower() == "undo":
            display, _, _ = self.engine.process_input("undo")
            return display, "chargen> ", False

        if text.lower() == "free":
            self._push_step()
            self.step = WizardStep.FREE_FORM
            display, prompt = self.engine.get_initial_display()
            lines = [
                "",
                f"  {BRIGHT_CYAN}Entering free-form mode.{RESET}",
                f"  {DIM}Type 'guided' to return to the step-by-step wizard.{RESET}",
                "",
                display,
            ]
            return "\n".join(lines), prompt, False

        if text.lower() == "sheet":
            display, _, _ = self.engine.process_input("sheet")
            return display, "chargen> ", False

        # Dispatch to step handler
        handlers = {
            WizardStep.WELCOME: self._handle_welcome,
            WizardStep.TEMPLATE_SELECT: self._handle_template_select,
            WizardStep.SPECIES_SELECT: self._handle_species_select,
            WizardStep.SPECIES_DETAIL: self._handle_species_detail,
            WizardStep.ATTRIBUTES: self._handle_attributes,
            WizardStep.SKILLS: self._handle_skills,
            WizardStep.NAME_BACKGROUND: self._handle_name_background,
            WizardStep.FORCE_SENSITIVE: self._handle_force_sensitive,
            WizardStep.REVIEW: self._handle_review,
            WizardStep.FREE_FORM: self._handle_free_form,
        }

        handler = handlers.get(self.step)
        if handler:
            return handler(text)

        return "  Something went wrong. Type 'help' or 'free'.", "chargen> ", False

    def get_character(self) -> Character:
        """Build final Character from engine state, adding background."""
        char = self.engine.get_character()
        char.force_sensitive = self._force_sensitive
        # Background stored in attributes JSON by game_server on save
        return char

    def get_background(self) -> str:
        """Return the player-written background text."""
        return self._background

    def is_force_sensitive(self) -> bool:
        return self._force_sensitive

    # ── Step Renderers ──

    def _render_welcome(self) -> str:
        lines = [
            "",
            _bar("="),
            _center(f"{BOLD}{BRIGHT_WHITE}STAR WARS{RESET} {DIM}Character Creation{RESET}"),
            _bar("="),
            "",
        ]
        lines.extend(_wrap(
            "A long time ago in a galaxy far, far away...\n\n"
            "You're about to create a character for life in Mos Eisley, the most "
            "infamous spaceport on Tatooine. The Galactic Civil War rages across "
            "the galaxy. Smugglers run Imperial blockades. Bounty hunters stalk "
            "their prey through dusty cantinas. Mechanics keep battered freighters "
            "flying. And in the shadows, those attuned to the Force walk a "
            "dangerous path.\n\n"
            "Your character will have six attributes — Dexterity, Knowledge, "
            "Mechanical, Perception, Strength and Technical — and a set of "
            "skills that define what they're good at. Every dice roll in the "
            "game uses the D6 system: roll a pool of six-sided dice, with a "
            "Wild Die that can explode on a 6 or cause a fumble on a 1.\n\n"
            "How would you like to begin?"
        ))
        lines.append("")
        lines.append(f"  {BRIGHT_YELLOW}1{RESET}) {BOLD}Pick a Template{RESET} "
                     f"{DIM}— Quick start with a pre-built archetype{RESET}")
        lines.append(f"  {BRIGHT_YELLOW}2{RESET}) {BOLD}Build from Scratch{RESET} "
                     f"{DIM}— Choose species, then allocate attributes & skills{RESET}")
        lines.append(f"  {BRIGHT_YELLOW}3{RESET}) {BOLD}Free-Form{RESET} "
                     f"{DIM}— Jump straight into the editor (experienced players){RESET}")
        lines.append("")
        lines.append(f"  {DIM}Type 1, 2, or 3 (or 'template', 'scratch', 'free'){RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_current_step(self) -> str:
        """Render the current step's display."""
        renderers = {
            WizardStep.WELCOME: self._render_welcome,
            WizardStep.TEMPLATE_SELECT: self._render_template_list,
            WizardStep.SPECIES_SELECT: self._render_species_list,
            WizardStep.ATTRIBUTES: self._render_attributes,
            WizardStep.SKILLS: self._render_skills,
            WizardStep.NAME_BACKGROUND: self._render_name_background,
            WizardStep.FORCE_SENSITIVE: self._render_force_sensitive,
            WizardStep.REVIEW: self._render_review,
        }
        renderer = renderers.get(self.step)
        if renderer:
            return renderer()
        return ""

    def _render_template_list(self) -> str:
        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}Step 1: Choose a Template{RESET}"),
            _bar("-"),
            "",
        ]
        lines.extend(_wrap(
            "Templates are pre-built character archetypes. Each one sets your "
            "species, attributes and starting skills. You can customize "
            "everything after choosing — a template is a starting point, "
            "not a straitjacket."
        ))
        lines.append("")

        for key, tmpl in TEMPLATES.items():
            desc = self._template_descs.get(key, {})
            tagline = desc.get("tagline", "")
            lines.append(f"  {BRIGHT_YELLOW}{key:<18s}{RESET} "
                         f"{BOLD}{tmpl['label']}{RESET}")
            if tagline:
                lines.append(f"  {DIM}{' ' * 18}{tagline}{RESET}")
            lines.append("")

        lines.append(f"  {DIM}Type a template name to see details, or 'back' to go back.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_template_detail(self, key: str) -> str:
        tmpl = TEMPLATES.get(key)
        desc = self._template_descs.get(key, {})
        if not tmpl:
            return f"  Unknown template: '{key}'"

        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}{tmpl['label']}{RESET}"),
            _bar("-"),
            "",
        ]

        # Flavor text
        description = desc.get("description", "")
        if description:
            lines.extend(_wrap(description))
            lines.append("")

        # Gameplay note
        gameplay = desc.get("gameplay", "")
        if gameplay:
            lines.append(f"  {BRIGHT_CYAN}How it plays:{RESET}")
            lines.extend(_wrap(gameplay))
            lines.append("")

        # Stats summary
        lines.append(f"  {BOLD}Species:{RESET} {tmpl['species']}")
        lines.append(f"  {BOLD}Attributes:{RESET}")
        for attr, dice_str in tmpl["attributes"].items():
            label = attr.capitalize()
            attr_desc = self._attr_descs.get(attr, {})
            short = attr_desc.get("short", "")
            lines.append(f"    {label:15s} {BRIGHT_YELLOW}{dice_str}{RESET}"
                         f"  {DIM}{short}{RESET}")

        lines.append(f"  {BOLD}Starting Skills:{RESET}")
        for skill, dice_str in tmpl["skills"].items():
            lines.append(f"    {skill:27s} +{BRIGHT_GREEN}{dice_str}{RESET}")

        # Key skills
        key_skills = desc.get("key_skills", [])
        if key_skills:
            lines.append("")
            lines.append(f"  {BRIGHT_CYAN}Key skills for this archetype:{RESET}")
            lines.append(f"    {DIM}{', '.join(s.title() for s in key_skills)}{RESET}")

        lines.append("")
        lines.append(f"  {BRIGHT_GREEN}Type 'yes' or 'pick' to choose this template.{RESET}")
        lines.append(f"  {DIM}Type 'back' to see the list again.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_species_list(self) -> str:
        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}Step 1: Choose a Species{RESET}"),
            _bar("-"),
            "",
        ]
        lines.extend(_wrap(
            "Your species determines your attribute ranges — the minimum "
            "and maximum for each of your six attributes. Some species are "
            "stronger, some are faster, some are more perceptive. All species "
            "get the same total of 18D to distribute among attributes and "
            "7D of bonus skill dice."
        ))
        lines.append("")

        for sp in self.species_reg.list_all():
            # Build a quick stat highlight
            s_range = sp.attributes.get("strength")
            highlights = []
            if s_range:
                if s_range.max_pool.total_pips() > 14:  # above 4D+2
                    highlights.append("High STR")
                elif s_range.max_pool.total_pips() < 9:
                    highlights.append("Low STR")
            p_range = sp.attributes.get("perception")
            if p_range and p_range.max_pool.total_pips() > 14:
                highlights.append("High PER")
            m_range = sp.attributes.get("mechanical")
            if m_range and m_range.max_pool.total_pips() > 14:
                highlights.append("High MEC")

            abilities_str = ""
            if sp.special_abilities:
                ab_names = [a.name for a in sp.special_abilities[:2]]
                abilities_str = f" {BRIGHT_MAGENTA}[{', '.join(ab_names)}]{RESET}"

            highlight_str = ""
            if highlights:
                highlight_str = f" {DIM}({', '.join(highlights)}){RESET}"

            lines.append(f"  {BRIGHT_YELLOW}{sp.name:15s}{RESET}"
                         f"{highlight_str}{abilities_str}")

        lines.append("")
        lines.append(f"  {DIM}Type a species name to see full details, or 'back' to go back.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_species_detail(self, sp) -> str:
        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}{sp.name}{RESET}"),
            _bar("-"),
            "",
        ]

        # Description
        lines.extend(_wrap(sp.description))
        lines.append("")

        # Homeworld & Move
        lines.append(f"  {BOLD}Homeworld:{RESET} {sp.homeworld}")
        lines.append(f"  {BOLD}Move:{RESET} {sp.move}"
                     + (f"  {BOLD}Swim:{RESET} {sp.swim}" if sp.swim else ""))
        lines.append("")

        # Attribute ranges with explanations
        lines.append(f"  {BOLD}Attribute Ranges:{RESET} {DIM}(you have {sp.attribute_dice} to distribute){RESET}")
        for attr_name in ATTRIBUTE_NAMES:
            r = sp.attributes.get(attr_name)
            if r:
                label = attr_name.capitalize()
                attr_desc = self._attr_descs.get(attr_name, {})
                short = attr_desc.get("short", "")
                lines.append(f"    {label:15s} {BRIGHT_YELLOW}{r.min_pool} - {r.max_pool}{RESET}"
                             f"  {DIM}{short}{RESET}")
        lines.append("")

        # Special abilities
        if sp.special_abilities:
            lines.append(f"  {BOLD}Special Abilities:{RESET}")
            for ability in sp.special_abilities:
                lines.append(f"    {BRIGHT_MAGENTA}{ability.name}:{RESET}")
                lines.extend(_wrap(ability.description, width=70, indent="      "))
            lines.append("")

        # Story factors
        if sp.story_factors:
            lines.append(f"  {BOLD}Story Factors:{RESET}")
            for factor in sp.story_factors:
                lines.extend(_wrap(f"- {factor}", width=70, indent="    "))
            lines.append("")

        lines.append(f"  {BRIGHT_GREEN}Type 'yes' or 'pick' to choose this species.{RESET}")
        lines.append(f"  {DIM}Type another species name or 'back' to see the list.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_attributes(self) -> str:
        sp = self.engine.state.species
        if not sp:
            return "  Error: no species selected."

        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}Step 2: Set Attributes{RESET}"),
            _bar("-"),
            "",
        ]
        lines.extend(_wrap(
            f"You have {BRIGHT_YELLOW}{sp.attribute_dice}{RESET} to distribute among six "
            f"attributes. Each attribute has a minimum and maximum based on your "
            f"species ({sp.name}). You must spend ALL your attribute dice — "
            f"no more, no less."
        ))
        lines.append("")

        # Show all attributes with current values, ranges, and descriptions
        pips_spent = self.engine._attr_pips_spent()
        pips_total = self.engine._attr_pips_total()
        pips_left = pips_total - pips_spent

        for attr_name in ATTRIBUTE_NAMES:
            r = sp.attributes.get(attr_name)
            pool = self.engine.state.attributes.get(attr_name, DicePool(0, 0))
            attr_desc = self._attr_descs.get(attr_name, {})
            gameplay = attr_desc.get("gameplay_note", "")
            short = attr_desc.get("short", "")

            # Color: green if set above min, yellow if at min
            at_min = (r and pool.total_pips() == r.min_pool.total_pips())
            color = DIM if at_min else BRIGHT_GREEN

            lines.append(f"  {BOLD}{BRIGHT_WHITE}{attr_name.upper()}{RESET}"
                         f"  {color}{pool}{RESET}"
                         f"  {DIM}(range: {r.min_pool} - {r.max_pool}){RESET}")
            lines.append(f"    {DIM}{short}{RESET}")
            lines.append("")

        # Budget status
        if pips_left > 0:
            left_str = f"{BRIGHT_YELLOW}{_pips_to_dice(pips_left)}{RESET}"
        elif pips_left == 0:
            left_str = f"{BRIGHT_GREEN}0D (done!){RESET}"
        else:
            left_str = f"{BRIGHT_RED}{_pips_to_dice(pips_left)} OVERSPENT{RESET}"

        lines.append(f"  {BOLD}Dice remaining:{RESET} {left_str}")
        lines.append("")
        lines.append(f"  {DIM}Set an attribute:  set <attr> <dice>  (e.g. 'set dex 3D+1'){RESET}")
        lines.append(f"  {DIM}See gameplay tips:  explain <attr>   (e.g. 'explain perception'){RESET}")
        if pips_left == 0:
            lines.append(f"  {BRIGHT_GREEN}All dice spent! Type 'next' to continue to skills.{RESET}")
        lines.append(f"  {DIM}Type 'back' to change species, 'sheet' for full view.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_attribute_explain(self, attr_name: str) -> str:
        attr_desc = self._attr_descs.get(attr_name, {})
        gameplay = attr_desc.get("gameplay_note", "")
        description = attr_desc.get("description", "")

        lines = [
            "",
            f"  {BOLD}{BRIGHT_WHITE}{attr_name.upper()}{RESET}",
            "",
        ]
        if description:
            lines.extend(_wrap(description))
            lines.append("")
        if gameplay:
            lines.append(f"  {BRIGHT_CYAN}In this game:{RESET}")
            lines.extend(_wrap(gameplay))
            lines.append("")

        # List skills under this attribute with game_use
        attr_skills = self._skill_descs.get(attr_name, {})
        high_priority = []
        other = []
        for sk_key, sk_data in attr_skills.items():
            priority = sk_data.get("priority", "low")
            if priority == "high":
                high_priority.append((sk_key, sk_data))
            else:
                other.append((sk_key, sk_data))

        if high_priority:
            lines.append(f"  {BOLD}Key skills under {attr_name.capitalize()}:{RESET}")
            for sk_key, sk_data in high_priority:
                name = sk_key.replace("_", " ").title()
                game_use = sk_data.get("game_use", "")
                lines.append(f"    {BRIGHT_GREEN}{name}{RESET}")
                if game_use:
                    lines.extend(_wrap(game_use, width=66, indent="      "))
            lines.append("")

        return "\n".join(lines)

    def _render_skills(self) -> str:
        sp = self.engine.state.species
        if not sp:
            return "  Error: no species selected."

        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}Step 3: Choose Skills{RESET}"),
            _bar("-"),
            "",
        ]
        lines.extend(_wrap(
            f"You have {BRIGHT_YELLOW}{sp.skill_dice}{RESET} of bonus skill dice to add to "
            f"any skills. Skills start at their parent attribute's value — adding "
            f"dice makes you better than average. You can add 1D or 2D to "
            f"a few skills, or spread 1D across many."
        ))
        lines.append("")

        # Show recommended skills (high priority)
        lines.append(f"  {BRIGHT_CYAN}Recommended skills for new players:{RESET}")
        recommended = []
        for attr_name, skills in self._skill_descs.items():
            for sk_key, sk_data in skills.items():
                if sk_data.get("priority") == "high":
                    name = sk_key.replace("_", " ").title()
                    tip = sk_data.get("tip", "")
                    # Truncate tip
                    if len(tip) > 70:
                        tip = tip[:67] + "..."
                    recommended.append((name, attr_name.capitalize(), tip))

        for name, attr, tip in recommended:
            lines.append(f"    {BRIGHT_GREEN}{name:27s}{RESET} {DIM}({attr}){RESET}")
            if tip:
                lines.append(f"      {DIM}{tip}{RESET}")
        lines.append("")

        # Current skills
        if self.engine.state.skills:
            lines.append(f"  {BOLD}Your current skills:{RESET}")
            for sk_key, bonus in self.engine.state.skills.items():
                sd = self.skill_reg.get(sk_key)
                if sd:
                    attr_pool = self.engine.state.attributes.get(sd.attribute, DicePool(0, 0))
                    total = attr_pool + bonus
                    lines.append(f"    {sd.name:27s} +{bonus} = {BRIGHT_GREEN}{total}{RESET}")
            lines.append("")

        # Budget
        pips_spent = self.engine._skill_pips_spent()
        pips_total = self.engine._skill_pips_total()
        pips_left = pips_total - pips_spent

        if pips_left > 0:
            left_str = f"{BRIGHT_YELLOW}{_pips_to_dice(pips_left)}{RESET}"
        elif pips_left == 0:
            left_str = f"{BRIGHT_GREEN}0D (done!){RESET}"
        else:
            left_str = f"{BRIGHT_RED}{_pips_to_dice(pips_left)} OVERSPENT{RESET}"

        lines.append(f"  {BOLD}Skill dice remaining:{RESET} {left_str}")
        lines.append("")
        lines.append(f"  {DIM}Add a skill:    skill <name> <dice>  (e.g. 'skill blaster 1D'){RESET}")
        lines.append(f"  {DIM}Remove a skill: unskill <name>       (e.g. 'unskill blaster'){RESET}")
        lines.append(f"  {DIM}Browse skills:  list <attr|all>       (e.g. 'list dex'){RESET}")
        lines.append(f"  {DIM}Skill info:     info <skill>          (e.g. 'info bargain'){RESET}")
        if pips_left <= 0:
            lines.append(f"  {BRIGHT_GREEN}Type 'next' to continue.{RESET}")
        lines.append(f"  {DIM}Type 'back' to return to attributes.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_skill_info(self, skill_name: str) -> str:
        """Show detailed info about a specific skill."""
        # Find in skill_descs
        for attr_name, skills in self._skill_descs.items():
            for sk_key, sk_data in skills.items():
                # Match by normalized name
                normalized = sk_key.replace("_", " ").lower()
                if normalized == skill_name.lower() or sk_key.lower() == skill_name.lower():
                    name = sk_key.replace("_", " ").title()
                    lines = [
                        "",
                        f"  {BOLD}{BRIGHT_WHITE}{name}{RESET} {DIM}({attr_name.capitalize()}){RESET}",
                        "",
                    ]
                    desc = sk_data.get("description", "")
                    if desc:
                        lines.extend(_wrap(desc))
                        lines.append("")

                    game_use = sk_data.get("game_use", "")
                    if game_use:
                        lines.append(f"  {BRIGHT_CYAN}In this game:{RESET}")
                        lines.extend(_wrap(game_use))
                        lines.append("")

                    tip = sk_data.get("tip", "")
                    if tip:
                        lines.append(f"  {BRIGHT_GREEN}Tip:{RESET}")
                        lines.extend(_wrap(tip))
                        lines.append("")

                    tags = sk_data.get("tags", [])
                    if tags:
                        lines.append(f"  {DIM}Tags: {', '.join(tags)}{RESET}")
                        lines.append("")

                    return "\n".join(lines)

        return f"  Unknown skill: '{skill_name}'. Type 'list all' to see all skills."

    def _render_name_background(self) -> str:
        step_num = "4" if self._template_path else "4"
        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}Step {step_num}: Name & Background{RESET}"),
            _bar("-"),
            "",
        ]

        current_name = self.engine.state.name
        if current_name:
            lines.append(f"  {BOLD}Name:{RESET} {BRIGHT_WHITE}{current_name}{RESET}")
        else:
            lines.append(f"  {BOLD}Name:{RESET} {DIM}(not set){RESET}")
        lines.append("")

        lines.extend(_wrap(
            "Give your character a name. Star Wars names can be anything — "
            "from the simple (Luke, Han) to the exotic (Bib Fortuna, Ponda Baba). "
            "Wookiees have growling names (Chewbacca, Lowbacca). "
            "Rodians favor sharp sounds (Greedo, Navik)."
        ))
        lines.append("")

        if self._background:
            lines.append(f"  {BOLD}Background:{RESET}")
            lines.extend(_wrap(self._background))
        else:
            lines.extend(_wrap(
                "You can also write a short background — what brings your character "
                "to Mos Eisley? Are they running from something? Looking for work? "
                "Chasing a bounty? This is optional but helps ground your roleplay."
            ))
        lines.append("")

        lines.append(f"  {DIM}Set name:       name <name>{RESET}")
        lines.append(f"  {DIM}Set background: bg <text>{RESET}")
        if current_name:
            lines.append(f"  {BRIGHT_GREEN}Type 'next' to continue.{RESET}")
        lines.append(f"  {DIM}Type 'back' to return to skills.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_force_sensitive(self) -> str:
        lines = [
            "",
            _bar("-"),
            _center(f"{BOLD}Step 5: Force Sensitivity{RESET}"),
            _bar("-"),
            "",
        ]
        lines.extend(_wrap(
            "Only a rare few are sensitive to the Force. If you choose 'Yes', "
            "your character starts with two Force Points instead of one, and "
            "gains access to the Control, Sense and Alter Force skills."
        ))
        lines.append("")
        lines.extend(_wrap(
            "But be warned: Force-sensitive characters feel the pull of both "
            "the light and the dark. They must be careful — be moral, honest "
            "and honorable. Dark Side Points accumulate when you use the Force "
            "for selfish or evil purposes. At 6 Dark Side Points, you risk "
            "falling to the dark side."
        ))
        lines.append("")
        lines.extend(_wrap(
            "Force-sensitive characters cannot be amoral mercenaries. They must "
            "have a code. If you want to play a scoundrel who shoots first "
            "and asks questions later, choose 'No' here."
        ))
        lines.append("")

        current = f"{BRIGHT_GREEN}Yes{RESET}" if self._force_sensitive else f"{DIM}No{RESET}"
        lines.append(f"  {BOLD}Force Sensitive:{RESET} {current}")
        lines.append("")
        lines.append(f"  {BRIGHT_YELLOW}yes{RESET} — Force sensitive (2 Force Points, dark side risk)")
        lines.append(f"  {BRIGHT_YELLOW}no{RESET}  — Not Force sensitive (1 Force Point, no restrictions)")
        lines.append("")
        lines.append(f"  {DIM}Type 'next' after choosing, or 'back' to go back.{RESET}")
        lines.append("")
        return "\n".join(lines)

    def _render_review(self) -> str:
        lines = [
            "",
            _bar("="),
            _center(f"{BOLD}{BRIGHT_WHITE}FINAL REVIEW{RESET}"),
            _bar("="),
            "",
        ]

        # Get the sheet from the engine
        sheet_lines = self.engine._sheet_lines()
        lines.extend(sheet_lines)
        lines.append("")

        # Background
        if self._background:
            lines.append(f"  {BOLD}Background:{RESET}")
            lines.extend(_wrap(self._background))
            lines.append("")

        # Force sensitivity
        fs_str = f"{BRIGHT_BLUE}Yes{RESET}" if self._force_sensitive else "No"
        lines.append(f"  {BOLD}Force Sensitive:{RESET} {fs_str}")
        lines.append("")

        # Validation
        errors = self.engine._validate()
        if errors:
            lines.append(f"  {BRIGHT_RED}Issues to resolve:{RESET}")
            for e in errors:
                lines.append(f"    {BRIGHT_RED}- {e}{RESET}")
            lines.append("")
            lines.append(f"  {DIM}Fix issues before finalizing. Type 'back' to go back.{RESET}")
        else:
            lines.append(f"  {BRIGHT_GREEN}Everything looks good!{RESET}")
            lines.append(f"  {BRIGHT_GREEN}Type 'done' to finalize your character.{RESET}")
            lines.append(f"  {DIM}Type 'back' to make changes.{RESET}")

        lines.append("")
        return "\n".join(lines)

    # ── Step Handlers ──

    def _push_step(self):
        """Push current step onto history for 'back' navigation."""
        self._step_history.append(self.step)
        # Cap history at 20
        if len(self._step_history) > 20:
            self._step_history.pop(0)

    def _handle_welcome(self, text: str) -> tuple[str, str, bool]:
        t = text.lower().strip()
        if t in ("1", "template", "templates"):
            self._push_step()
            self.step = WizardStep.TEMPLATE_SELECT
            return self._render_template_list(), "chargen> ", False
        elif t in ("2", "scratch", "custom", "build"):
            self._push_step()
            self.step = WizardStep.SPECIES_SELECT
            return self._render_species_list(), "chargen> ", False
        elif t in ("3", "free", "freeform"):
            self._push_step()
            self.step = WizardStep.FREE_FORM
            display, prompt = self.engine.get_initial_display()
            lines = [
                "",
                f"  {BRIGHT_CYAN}Entering free-form mode.{RESET}",
                f"  {DIM}Type 'guided' to return to the step-by-step wizard.{RESET}",
                "",
                display,
            ]
            return "\n".join(lines), prompt, False
        else:
            return (f"  {DIM}Please choose 1 (Template), 2 (Scratch), or 3 (Free-Form).{RESET}",
                    "chargen> ", False)

    def _handle_template_select(self, text: str) -> tuple[str, str, bool]:
        t = text.lower().strip().replace(" ", "_")

        # Check if it's a template name
        if t in TEMPLATES:
            # Show detail view
            self._pending_template = t
            return self._render_template_detail(t), "chargen> ", False

        if t in ("yes", "pick", "choose", "select") and hasattr(self, '_pending_template'):
            # Apply template
            key = self._pending_template
            self.engine.process_input(f"template {key}")
            self._template_path = True
            self._push_step()
            self.step = WizardStep.SKILLS
            lines = [
                "",
                f"  {BRIGHT_GREEN}Template '{TEMPLATES[key]['label']}' applied!{RESET}",
                f"  {DIM}You can adjust any skills before continuing.{RESET}",
                "",
            ]
            lines.append(self._render_skills())
            return "\n".join(lines), "chargen> ", False

        # Partial match
        matches = [k for k in TEMPLATES if k.startswith(t)]
        if len(matches) == 1:
            self._pending_template = matches[0]
            return self._render_template_detail(matches[0]), "chargen> ", False
        elif len(matches) > 1:
            names = ", ".join(matches)
            return f"  Ambiguous: {names}", "chargen> ", False

        return (f"  Unknown template: '{text}'. Type a template name from the list.",
                "chargen> ", False)

    def _handle_species_select(self, text: str) -> tuple[str, str, bool]:
        t = text.strip()

        if t.lower() in ("yes", "pick", "choose", "select") and self._pending_species:
            # Confirm species selection
            sp = self._pending_species
            self.engine.process_input(f"species {sp.name}")
            self._pending_species = None
            self._push_step()
            self.step = WizardStep.ATTRIBUTES
            lines = [
                "",
                f"  {BRIGHT_GREEN}Species set to: {sp.name}{RESET}",
                "",
            ]
            lines.append(self._render_attributes())
            return "\n".join(lines), "chargen> ", False

        # Try to find species
        sp = self.species_reg.get(t)
        if not sp:
            matches = [s for s in self.species_reg.list_all()
                       if s.name.lower().startswith(t.lower())]
            if len(matches) == 1:
                sp = matches[0]
            elif len(matches) > 1:
                names = ", ".join(m.name for m in matches)
                return f"  Ambiguous: {names}", "chargen> ", False
            else:
                return (f"  Unknown species: '{text}'. Type a species name from the list.",
                        "chargen> ", False)

        self._pending_species = sp
        self.step = WizardStep.SPECIES_DETAIL
        return self._render_species_detail(sp), "chargen> ", False

    def _handle_species_detail(self, text: str) -> tuple[str, str, bool]:
        t = text.lower().strip()

        if t in ("yes", "pick", "choose", "select") and self._pending_species:
            sp = self._pending_species
            self.engine.process_input(f"species {sp.name}")
            self._pending_species = None
            self._push_step()
            self.step = WizardStep.ATTRIBUTES
            lines = [
                "",
                f"  {BRIGHT_GREEN}Species set to: {sp.name}{RESET}",
                "",
            ]
            lines.append(self._render_attributes())
            return "\n".join(lines), "chargen> ", False

        if t == "back":
            self.step = WizardStep.SPECIES_SELECT
            self._pending_species = None
            return self._render_species_list(), "chargen> ", False

        # Try another species name
        sp = self.species_reg.get(t)
        if not sp:
            matches = [s for s in self.species_reg.list_all()
                       if s.name.lower().startswith(t.lower())]
            if len(matches) == 1:
                sp = matches[0]
            else:
                return (f"  Type 'yes' to choose {self._pending_species.name}, "
                        f"or type another species name.",
                        "chargen> ", False)

        self._pending_species = sp
        return self._render_species_detail(sp), "chargen> ", False

    def _handle_attributes(self, text: str) -> tuple[str, str, bool]:
        t = text.strip().lower()

        if t == "next":
            # Check if attributes are fully spent
            pips_left = self.engine._attr_pips_total() - self.engine._attr_pips_spent()
            if pips_left != 0:
                return (f"  {BRIGHT_RED}You still have {_pips_to_dice(pips_left)} "
                        f"attribute dice to spend.{RESET}",
                        "chargen> ", False)
            self._push_step()
            self.step = WizardStep.SKILLS
            return self._render_skills(), "chargen> ", False

        # Handle 'explain <attr>'
        parts = text.strip().split(None, 1)
        if parts[0].lower() == "explain" and len(parts) > 1:
            attr_name = self.engine._match_attribute(parts[1].lower())
            if attr_name:
                return self._render_attribute_explain(attr_name), "chargen> ", False
            return f"  Unknown attribute: '{parts[1]}'", "chargen> ", False

        # Pass through to engine for 'set' commands
        if parts[0].lower() == "set":
            display, _, _ = self.engine.process_input(text)
            # Re-render attributes with status
            return display + "\n" + self._render_attributes(), "chargen> ", False

        # Also handle 'list' and 'sheet'
        if parts[0].lower() in ("list", "skills", "sheet"):
            display, _, _ = self.engine.process_input(text)
            return display, "chargen> ", False

        return (f"  {DIM}Use 'set <attr> <dice>' (e.g. 'set dex 3D+1'), "
                f"'explain <attr>', or 'next'.{RESET}",
                "chargen> ", False)

    def _handle_skills(self, text: str) -> tuple[str, str, bool]:
        t = text.strip().lower()
        parts = text.strip().split(None, 1)
        cmd = parts[0].lower() if parts else ""

        if t == "next":
            self._push_step()
            self.step = WizardStep.NAME_BACKGROUND
            return self._render_name_background(), "chargen> ", False

        # Handle 'info <skill>'
        if cmd == "info" and len(parts) > 1:
            return self._render_skill_info(parts[1]), "chargen> ", False

        # Pass through skill/unskill/list commands to engine
        if cmd in ("skill", "unskill", "list", "sheet"):
            display, _, _ = self.engine.process_input(text)
            return display, "chargen> ", False

        return (f"  {DIM}Use 'skill <name> <dice>', 'unskill <name>', "
                f"'list <attr>', 'info <skill>', or 'next'.{RESET}",
                "chargen> ", False)

    def _handle_name_background(self, text: str) -> tuple[str, str, bool]:
        t = text.strip()
        parts = t.split(None, 1)
        cmd = parts[0].lower() if parts else ""

        if t.lower() == "next":
            if not self.engine.state.name:
                return (f"  {BRIGHT_RED}You need to set a name first. "
                        f"Use: name <name>{RESET}",
                        "chargen> ", False)
            self._push_step()
            self.step = WizardStep.FORCE_SENSITIVE
            return self._render_force_sensitive(), "chargen> ", False

        if cmd == "name" and len(parts) > 1:
            display, _, _ = self.engine.process_input(t)
            return display, "chargen> ", False

        if cmd == "bg" and len(parts) > 1:
            self._background = parts[1].strip()
            return (f"  {BRIGHT_GREEN}Background set.{RESET}\n"
                    f"  {DIM}Type 'next' to continue, or 'bg <text>' to change it.{RESET}",
                    "chargen> ", False)

        # If they just typed a name without the command prefix
        if cmd != "name" and cmd != "bg" and not t.lower().startswith("back"):
            # Treat as name if no name set, as background if name is set
            if not self.engine.state.name:
                display, _, _ = self.engine.process_input(f"name {t}")
                return display, "chargen> ", False

        return (f"  {DIM}Use 'name <name>' or 'bg <background text>', then 'next'.{RESET}",
                "chargen> ", False)

    def _handle_force_sensitive(self, text: str) -> tuple[str, str, bool]:
        t = text.strip().lower()

        if t in ("yes", "y", "true", "force"):
            self._force_sensitive = True
            return (f"  {BRIGHT_BLUE}Force Sensitive: Yes{RESET}\n"
                    f"  {DIM}Type 'next' to continue to final review.{RESET}",
                    "chargen> ", False)

        if t in ("no", "n", "false"):
            self._force_sensitive = False
            return (f"  Force Sensitive: No\n"
                    f"  {DIM}Type 'next' to continue to final review.{RESET}",
                    "chargen> ", False)

        if t == "next":
            self._push_step()
            self.step = WizardStep.REVIEW
            return self._render_review(), "chargen> ", False

        return (f"  {DIM}Type 'yes' or 'no', then 'next' to continue.{RESET}",
                "chargen> ", False)

    def _handle_review(self, text: str) -> tuple[str, str, bool]:
        t = text.strip().lower()

        if t == "done":
            errors = self.engine._validate()
            if errors:
                lines = [f"  {BRIGHT_RED}Cannot finalize:{RESET}"]
                for e in errors:
                    lines.append(f"    {BRIGHT_RED}- {e}{RESET}")
                return "\n".join(lines), "chargen> ", False

            lines = self.engine._sheet_lines()
            lines.append("")
            lines.append(f"  {BRIGHT_GREEN}Character complete!{RESET}")
            return "\n".join(lines), "", True

        # Allow editing from review
        parts = t.split(None, 1)
        cmd = parts[0] if parts else ""

        if cmd in ("name", "set", "skill", "unskill", "species", "template"):
            display, _, _ = self.engine.process_input(text)
            # Re-render review
            return display + "\n" + self._render_review(), "chargen> ", False

        if cmd == "bg" and len(parts) > 1:
            self._background = parts[1].strip()
            return (f"  {BRIGHT_GREEN}Background updated.{RESET}\n"
                    + self._render_review(),
                    "chargen> ", False)

        return (f"  {DIM}Type 'done' to finalize, or edit with 'name', 'set', "
                f"'skill', 'bg'. Type 'back' to go back.{RESET}",
                "chargen> ", False)

    def _handle_free_form(self, text: str) -> tuple[str, str, bool]:
        t = text.strip().lower()

        if t == "guided":
            # Return to wizard at the appropriate step
            if self._step_history:
                self.step = self._step_history.pop()
            else:
                self.step = WizardStep.WELCOME
            return (f"  {BRIGHT_CYAN}Returning to guided mode.{RESET}\n"
                    + self._render_current_step(),
                    "chargen> ", False)

        # Pass everything through to the engine
        display, prompt, done = self.engine.process_input(text)
        if done:
            return display, prompt, True

        return display, prompt, False


def _pips_to_dice(pips):
    """Convert pip count to dice notation."""
    if pips < 0:
        return f"-{_pips_to_dice(-pips)}"
    d = pips // 3
    p = pips % 3
    return f"{d}D+{p}" if p > 0 else f"{d}D"
